from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apple_refurb_watch.db import Database, EVENT_KEEP
from apple_refurb_watch.deliveries import OutboxWorker
from apple_refurb_watch.storage.events import EventRepository, EventsRepository, event_fingerprint
from apple_refurb_watch.storage.products import ProductRepository, ProductsRepository


def test_repositories_preserve_crud_and_bound_queries(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    assert isinstance(db.products_repo, ProductRepository)
    assert ProductsRepository is ProductRepository
    assert EventsRepository is EventRepository

    watch = db.create_watch({"name": "测试规则", "all_of": ["MacBook"]})
    assert db.get_watch(watch["id"])["name"] == "测试规则"
    assert db.update_watch(watch["id"], {"enabled": False})["enabled"] is False
    assert db.count_watches(enabled=False) == 1

    db.upsert_products(
        [
            {
                "sku": f"SKU{i}CH/A",
                "title": f"翻新 Mac {i}",
                "url": f"https://www.apple.com.cn/shop/product/SKU{i}CH/A",
                "price": i,
                "listing_key": "mac",
                "extra": {"index": i},
            }
            for i in range(4)
        ]
    )
    assert len(db.list_products(limit=2, offset=1)) == 2
    assert db.list_products(limit=9999, offset=0)
    db.set_spec("SKU0CH/A", 16, 512)
    assert db.get_spec("SKU0CH/A")["ram_gb"] == 16
    assert db.get_spec("SKU0CH/A")["storage_gb"] == 512

    for i in range(EVENT_KEEP + 3):
        db.add_event(type="scan_ok", message=str(i))
    assert len(db.list_events(EVENT_KEEP + 100)) == EVENT_KEEP
    db.close()


def test_delivery_retry_respects_next_retry_at(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", message="new")
    db.enqueue_delivery(event_id, "bark")
    db.mark_delivery(event_id, "bark", ok=False, last_error="timeout")
    assert db.list_pending_deliveries()

    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    db.conn.execute(
        "UPDATE notification_deliveries SET next_retry_at=? WHERE event_id=? AND channel=?",
        (future, event_id, "bark"),
    )
    db.conn.commit()
    assert db.list_pending_deliveries() == []
    db.close()


def test_event_fingerprint_is_idempotent(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    fingerprint = event_fingerprint("appeared", sku="SKU/A", watch_id=1, state="initial")
    first = db.add_event(type="appeared", sku="SKU/A", watch_id=1, fingerprint=fingerprint)
    second = db.add_event(type="appeared", sku="SKU/A", watch_id=1, fingerprint=fingerprint)
    assert first == second
    assert len(db.list_events()) == 1
    db.close()


def test_outbox_worker_leases_and_completes_delivery(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", title="新货", message="body")
    db.enqueue_delivery(event_id, "hook")
    calls: list[str] = []

    def hook(settings, title, body, url):
        calls.append(title)
        return []

    worker = OutboxWorker(db, hook=hook, worker_id="worker-a", lease_seconds=30)
    assert worker.run_once() == 1
    assert calls == ["新货"]
    assert db.list_pending_deliveries() == []
    outbox = db.conn.execute(
        "SELECT status, attempts, sent_at FROM notification_outbox WHERE event_id=?",
        (event_id,),
    ).fetchone()
    assert outbox["status"] == "sent"
    assert outbox["attempts"] == 1
    assert outbox["sent_at"]
    db.close()


def test_outbox_expired_lease_can_be_reclaimed(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", title="新货")
    db.enqueue_delivery(event_id, "hook")
    first = db.claim_pending_deliveries(lease_token="worker-a", lease_seconds=60)
    assert len(first) == 1
    db.conn.execute(
        "UPDATE notification_deliveries SET leased_until=? WHERE event_id=? AND channel=?",
        ("2000-01-01T00:00:00+00:00", event_id, "hook"),
    )
    db.conn.commit()
    assert db.release_expired_leases() == 1
    second = db.claim_pending_deliveries(lease_token="worker-b", lease_seconds=60)
    assert len(second) == 1
    assert second[0]["lease_token"] == "worker-b"
    assert db.complete_delivery(
        event_id,
        "hook",
        lease_token="worker-a",
        ok=True,
    ) is False
    assert db.complete_delivery(
        event_id,
        "hook",
        lease_token="worker-b",
        ok=True,
    ) is True
    db.close()


def test_outbox_failure_uses_exponential_backoff(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", title="新货")
    db.enqueue_delivery(event_id, "hook")
    attempts: list[int] = []

    def send(channel, conf, settings, title, body, url):
        attempts.append(1)
        return "provider timeout"

    worker = OutboxWorker(
        db,
        hook=lambda *args: [],
        worker_id="worker-backoff",
        send_fn=send,
        lease_seconds=30,
    )
    # The hook mode intentionally retries immediately for legacy test callers;
    # use a real-channel worker here to exercise provider backoff.
    worker.hook = None
    db.update_settings({"notify": {"bark": {"enabled": True, "url": "https://api.day.app/key"}}})
    db.conn.execute("UPDATE notification_deliveries SET channel='bark' WHERE event_id=?", (event_id,))
    db.conn.execute("UPDATE notification_outbox SET channel='bark' WHERE event_id=?", (event_id,))
    db.conn.commit()
    assert worker.run_once() == 0
    row = db.conn.execute(
        "SELECT attempts, status, next_retry_at FROM notification_outbox WHERE event_id=?",
        (event_id,),
    ).fetchone()
    assert row["attempts"] == 1
    assert row["status"] == "pending"
    assert row["next_retry_at"]
    assert worker.run_once() == 0
    assert len(attempts) == 1
    db.close()


def test_legacy_ack_cannot_overwrite_a_live_lease(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", title="新货")
    db.enqueue_delivery(event_id, "hook")
    claimed = db.claim_pending_deliveries(lease_token="worker-a", lease_seconds=60)
    assert claimed
    assert db.mark_delivery(event_id, "hook", ok=True) is False
    row = db.conn.execute(
        "SELECT status, lease_token FROM notification_deliveries WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    assert row["status"] == "processing"
    assert row["lease_token"] == "worker-a"
    assert db.complete_delivery(event_id, "hook", lease_token="worker-a", ok=True) is True
    db.close()


def test_legacy_ack_cannot_resurrect_a_completed_delivery(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", title="新货")
    db.enqueue_delivery(event_id, "hook")
    db.claim_pending_deliveries(lease_token="worker-a", lease_seconds=60)
    assert db.complete_delivery(event_id, "hook", lease_token="worker-a", ok=True) is True

    # A delayed pre-lease callback must not turn a successful send back into a
    # retryable row (which would produce a duplicate notification).
    assert db.mark_delivery(event_id, "hook", ok=False, last_error="late") is False
    legacy = db.conn.execute(
        "SELECT status, attempts FROM notification_deliveries WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    canonical = db.conn.execute(
        "SELECT status, attempts FROM notification_outbox WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    assert legacy["status"] == "ok" and canonical["status"] == "sent"
    assert legacy["attempts"] == canonical["attempts"] == 1
    db.close()


def test_canonical_terminal_state_is_not_downgraded_by_stale_legacy_row(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", title="新货")
    db.enqueue_delivery(event_id, "hook")
    db.conn.execute(
        "UPDATE notification_outbox SET status='sent', attempts=2, sent_at=? WHERE event_id=? AND channel='hook'",
        ("2026-01-01T00:00:00+00:00", event_id),
    )
    db.conn.commit()

    # Reading/claiming through the old compatibility path must preserve the
    # canonical terminal result and mirror it back as ``ok``.
    assert db.list_pending_deliveries() == []
    legacy = db.conn.execute(
        "SELECT status, attempts FROM notification_deliveries WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    canonical = db.conn.execute(
        "SELECT status, attempts FROM notification_outbox WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    assert legacy["status"] == "ok" and canonical["status"] == "sent"
    assert legacy["attempts"] == canonical["attempts"] == 2
    db.close()


def test_expired_lease_recovery_updates_both_delivery_tables(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", title="新货")
    db.enqueue_delivery(event_id, "hook")
    db.claim_pending_deliveries(lease_token="worker-a", lease_seconds=60)
    # Simulate a partial legacy write from an older process.
    db.conn.execute(
        "UPDATE notification_outbox SET leased_until=? WHERE event_id=? AND channel='hook'",
        ("2000-01-01T00:00:00+00:00", event_id),
    )
    db.conn.commit()
    assert db.release_expired_leases() == 1
    legacy = db.conn.execute(
        "SELECT status, lease_token, leased_until FROM notification_deliveries WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    canonical = db.conn.execute(
        "SELECT status, lease_token, leased_until FROM notification_outbox WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    assert legacy["status"] == canonical["status"] == "pending"
    assert legacy["lease_token"] is None and canonical["lease_token"] is None
    db.close()


def test_cancel_does_not_clear_a_processing_lease(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", title="新货")
    db.enqueue_delivery(event_id, "hook")
    db.claim_pending_deliveries(lease_token="worker-a", lease_seconds=60)

    assert db.cancel_delivery(event_id, "hook", reason="已关闭通道") is False
    legacy = db.conn.execute(
        "SELECT status, lease_token FROM notification_deliveries WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    canonical = db.conn.execute(
        "SELECT status, lease_token FROM notification_outbox WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    assert legacy["status"] == canonical["status"] == "processing"
    assert legacy["lease_token"] == canonical["lease_token"] == "worker-a"
    db.close()


def test_explicit_sent_status_is_not_claimed(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", title="新货")
    db.enqueue_delivery(event_id, "hook")
    db.conn.execute(
        "UPDATE notification_deliveries SET status='sent', attempts=3 WHERE event_id=? AND channel='hook'",
        (event_id,),
    )
    db.conn.execute(
        "UPDATE notification_outbox SET status='sent', attempts=3 WHERE event_id=? AND channel='hook'",
        (event_id,),
    )
    db.conn.commit()

    assert db.claim_pending_deliveries(lease_token="worker-a") == []
    assert db.list_pending_deliveries() == []
    db.close()


@pytest.mark.parametrize("terminal", ["sent", "dead", "cancelled"])
def test_cancel_does_not_downgrade_terminal_delivery(tmp_path, terminal: str) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", title="新货")
    db.enqueue_delivery(event_id, "hook")
    legacy_status = "ok" if terminal == "sent" else terminal
    db.conn.execute(
        "UPDATE notification_deliveries SET status=?, last_error='old', next_retry_at='2026-01-01T00:00:00+00:00' WHERE event_id=? AND channel='hook'",
        (legacy_status, event_id),
    )
    db.conn.execute(
        "UPDATE notification_outbox SET status=?, last_error='old', next_retry_at='2026-01-01T00:00:00+00:00' WHERE event_id=? AND channel='hook'",
        (terminal, event_id),
    )
    db.conn.commit()

    assert db.cancel_delivery(event_id, "hook", reason="关闭通道") is False
    legacy = db.conn.execute(
        "SELECT status, last_error, next_retry_at FROM notification_deliveries WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    canonical = db.conn.execute(
        "SELECT status, last_error, next_retry_at FROM notification_outbox WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    assert legacy["status"] == legacy_status
    assert canonical["status"] == terminal
    if terminal in {"sent", "dead", "cancelled"}:
        assert legacy["next_retry_at"] is None
        assert canonical["next_retry_at"] is None
    db.close()


def test_sync_prefers_newer_processing_lease_when_tokens_diverge(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    event_id = db.add_event(type="appeared", title="新货")
    db.enqueue_delivery(event_id, "hook")
    db.conn.execute(
        """
        UPDATE notification_outbox
        SET status='processing', attempts=1, lease_token='old-token',
            leased_until='2026-01-01T00:01:00+00:00',
            last_attempt_at='2026-01-01T00:00:00+00:00'
        WHERE event_id=? AND channel='hook'
        """,
        (event_id,),
    )
    db.conn.execute(
        """
        UPDATE notification_deliveries
        SET status='processing', attempts=2, lease_token='new-token',
            leased_until='2026-01-01T00:02:00+00:00',
            last_attempt_at='2026-01-01T00:00:30+00:00'
        WHERE event_id=? AND channel='hook'
        """,
        (event_id,),
    )
    db.conn.commit()

    assert db.list_pending_deliveries() == []
    legacy = db.conn.execute(
        "SELECT attempts, lease_token, leased_until FROM notification_deliveries WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    canonical = db.conn.execute(
        "SELECT attempts, lease_token, leased_until FROM notification_outbox WHERE event_id=? AND channel='hook'",
        (event_id,),
    ).fetchone()
    assert legacy["attempts"] == canonical["attempts"] == 2
    assert legacy["lease_token"] == canonical["lease_token"] == "new-token"
    assert legacy["leased_until"] == canonical["leased_until"] == "2026-01-01T00:02:00+00:00"
    db.close()
