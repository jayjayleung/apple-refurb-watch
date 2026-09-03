from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from apple_refurb_watch.storage.schema import EVENT_KEEP, MAX_EVENT_LIMIT, utcnow
from apple_refurb_watch.storage.sqlite import SQLiteStore


MAX_DELIVERY_ATTEMPTS = 8
DEFAULT_LEASE_SECONDS = 60
MAX_BACKOFF_SECONDS = 3600
_TERMINAL_CANONICAL = {"sent", "dead", "cancelled"}


def _canonical_delivery_status(value: Any) -> str:
    """Normalize legacy and canonical status names to one state vocabulary."""

    status = str(value or "pending").strip().lower()
    if status == "ok":
        return "sent"
    if status not in {"pending", "processing", "sent", "dead", "cancelled"}:
        return "pending"
    return status


def _after_seconds(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0.0, seconds))).isoformat()


class EventRepository:
    """Persistence for scan events and notification delivery state."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def add(self, **kwargs: Any) -> int:
        fingerprint = str(kwargs.get("fingerprint") or "").strip() or None
        with self.store.transaction() as conn:
            if fingerprint:
                existing = conn.execute("SELECT id FROM events WHERE fingerprint=?", (fingerprint,)).fetchone()
                if existing:
                    return int(existing["id"])
            values = (
                kwargs.get("type"),
                kwargs.get("sku"),
                kwargs.get("watch_id"),
                kwargs.get("title"),
                kwargs.get("price"),
                kwargs.get("url"),
                kwargs.get("message"),
                kwargs.get("created_at") or utcnow(),
                fingerprint,
            )
            if fingerprint:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO events(
                        type, sku, watch_id, title, price, url, message, created_at, fingerprint
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    values,
                )
                row = conn.execute("SELECT id FROM events WHERE fingerprint=?", (fingerprint,)).fetchone()
                if row:
                    event_id = int(row["id"])
                else:
                    raise RuntimeError("无法写入事件指纹")
            else:
                cur = conn.execute(
                    """
                    INSERT INTO events(
                        type, sku, watch_id, title, price, url, message, created_at, fingerprint
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    values,
                )
                event_id = int(cur.lastrowid or 0)
            conn.execute(
                "DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY id DESC LIMIT -1 OFFSET ?)",
                (EVENT_KEEP,),
            )
            conn.execute("DELETE FROM notification_deliveries WHERE event_id NOT IN (SELECT id FROM events)")
            conn.execute("DELETE FROM notification_outbox WHERE event_id NOT IN (SELECT id FROM events)")
            return event_id

    def get(self, event_id: int) -> dict | None:
        with self.store.lock:
            row = self.store.conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return dict(row) if row else None

    def list(
        self,
        limit: int = 100,
        *,
        after_id: int | None = None,
        type: str | None = None,
    ) -> list[dict]:
        sql = "SELECT * FROM events WHERE 1=1"
        args: list[Any] = []
        if after_id is not None:
            sql += " AND id > ?"
            args.append(int(after_id))
        if type:
            sql += " AND type = ?"
            args.append(str(type))
        sql += " ORDER BY id ASC LIMIT ?" if after_id is not None else " ORDER BY id DESC LIMIT ?"
        args.append(min(MAX_EVENT_LIMIT, max(0, int(limit))))
        with self.store.lock:
            rows = self.store.conn.execute(sql, args).fetchall()
        return [dict(row) for row in rows]

    def clear(self) -> int:
        with self.store.transaction() as conn:
            conn.execute("DELETE FROM notification_deliveries")
            conn.execute("DELETE FROM notification_outbox")
            cur = conn.execute("DELETE FROM events")
            return int(cur.rowcount or 0)

    def enqueue_delivery(self, event_id: int, channel: str) -> None:
        created = utcnow()
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO notification_outbox(event_id, channel, status, attempts, created_at)
                VALUES(?,?, 'pending', 0, ?)
                ON CONFLICT(event_id, channel) DO NOTHING
                """,
                (event_id, channel, created),
            )

    def has_due_deliveries(self) -> bool:
        now = utcnow()
        with self.store.lock:
            row = self.store.conn.execute(
                """
                SELECT 1 FROM notification_outbox
                WHERE status NOT IN ('ok', 'sent', 'dead', 'cancelled')
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                  AND (status != 'processing' OR leased_until IS NULL OR leased_until <= ?)
                LIMIT 1
                """,
                (now, now),
            ).fetchone()
        return row is not None

    def list_pending_deliveries(self) -> list[dict]:
        now = utcnow()
        with self.store.lock:
            rows = self.store.conn.execute(
                """
                SELECT * FROM notification_outbox
                WHERE status NOT IN ('ok', 'sent', 'processing', 'dead', 'cancelled')
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY id
                """,
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_pending_deliveries(
        self,
        *,
        limit: int = 20,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        lease_token: str | None = None,
    ) -> list[dict]:
        """Atomically lease pending deliveries for one worker instance."""

        token = str(lease_token or secrets.token_hex(16))
        now = utcnow()
        leased_until = _after_seconds(lease_seconds)
        claimed: list[dict] = []
        with self.store.transaction(immediate=True) as conn:
            rows = conn.execute(
                """
                SELECT * FROM notification_outbox
                WHERE status NOT IN ('ok', 'sent', 'dead', 'cancelled')
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                  AND (status != 'processing' OR leased_until IS NULL OR leased_until <= ?)
                ORDER BY id
                LIMIT ?
                """,
                (now, now, max(1, int(limit))),
            ).fetchall()
            for row in rows:
                attempts = int(row["attempts"] or 0) + 1
                if attempts > MAX_DELIVERY_ATTEMPTS:
                    conn.execute(
                        """
                        UPDATE notification_outbox
                        SET status='dead', last_error=?, next_retry_at=NULL,
                            lease_token=NULL, leased_until=NULL, sent_at=NULL
                        WHERE id=?
                        """,
                        ("超过最大重试次数", row["id"]),
                    )
                    continue
                conn.execute(
                    """
                    UPDATE notification_outbox
                    SET status='processing', attempts=?, lease_token=?, leased_until=?,
                        last_attempt_at=?
                    WHERE id=?
                    """,
                    (attempts, token, leased_until, now, row["id"]),
                )
                item = dict(row)
                item.update({"attempts": attempts, "lease_token": token, "leased_until": leased_until})
                claimed.append(item)
        return claimed

    def complete_delivery(
        self,
        event_id: int,
        channel: str,
        *,
        lease_token: str,
        ok: bool,
        last_error: str | None = None,
        retry_after: float | None = None,
    ) -> bool:
        """Complete a leased delivery, ignoring stale worker acknowledgements."""

        now = utcnow()
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT attempts FROM notification_outbox "
                "WHERE event_id=? AND channel=? AND lease_token=?",
                (event_id, channel, lease_token),
            ).fetchone()
            if row is None:
                return False
            attempts = int(row["attempts"] or 0)
            if ok:
                status = "sent"
                retry_at = None
                error = None
            elif attempts >= MAX_DELIVERY_ATTEMPTS:
                status = "dead"
                retry_at = None
                error = last_error or "超过最大重试次数"
            else:
                status = "pending"
                delay = retry_after if retry_after is not None else min(
                    MAX_BACKOFF_SECONDS, 2 ** max(0, attempts - 1)
                )
                retry_at = _after_seconds(delay)
                error = last_error
            conn.execute(
                """
                UPDATE notification_outbox
                SET status=?, last_error=?, next_retry_at=?, lease_token=NULL, leased_until=NULL,
                    sent_at=?
                WHERE event_id=? AND channel=? AND lease_token=?
                """,
                (status, error, retry_at, now if ok else None, event_id, channel, lease_token),
            )
            return True

    def release_delivery(
        self,
        event_id: int,
        channel: str,
        *,
        lease_token: str,
        retry_after: float = 5.0,
    ) -> bool:
        """Release a lease without counting an attempt (for disabled channels)."""

        retry_at = _after_seconds(retry_after)
        with self.store.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE notification_outbox
                SET status='pending', next_retry_at=?, lease_token=NULL, leased_until=NULL
                WHERE event_id=? AND channel=? AND lease_token=?
                """,
                (retry_at, event_id, channel, lease_token),
            )
            return bool(cur.rowcount)

    def cancel_delivery(self, event_id: int, channel: str, *, reason: str = "通道未启用") -> bool:
        """Stop retrying a delivery that is no longer configured."""

        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT status FROM notification_outbox WHERE event_id=? AND channel=?",
                (event_id, channel),
            ).fetchone()
            if row is None:
                return False
            status = _canonical_delivery_status(row["status"])
            if status == "processing" or status in _TERMINAL_CANONICAL:
                return False
            cur = conn.execute(
                """
                UPDATE notification_outbox
                SET status='cancelled', last_error=?, lease_token=NULL, leased_until=NULL,
                    next_retry_at=NULL
                WHERE event_id=? AND channel=? AND status NOT IN ('processing', 'ok', 'sent', 'dead', 'cancelled')
                """,
                (reason, event_id, channel),
            )
            return bool(cur.rowcount)

    def release_expired_leases(self) -> int:
        """Make work abandoned by a crashed worker immediately retryable."""

        now = utcnow()
        with self.store.transaction(immediate=True) as conn:
            cur = conn.execute(
                """
                UPDATE notification_outbox
                SET status='pending', lease_token=NULL, leased_until=NULL,
                    next_retry_at=COALESCE(next_retry_at, ?)
                WHERE status='processing' AND leased_until IS NOT NULL AND leased_until <= ?
                """,
                (now, now),
            )
            return int(cur.rowcount or 0)

    def mark_delivery(
        self,
        event_id: int,
        channel: str,
        *,
        ok: bool,
        last_error: str | None = None,
        lease_token: str | None = None,
    ) -> bool:
        """Record a legacy, non-resource delivery result.

        New workers should use :meth:`complete_delivery` with a lease token.
        The compatibility method remains available for older integrations,
        but an un-tokened call is refused once another worker has leased the
        row so a stale callback cannot overwrite active work.
        """

        status = "sent" if ok else "pending"
        now = utcnow()
        where = "event_id=? AND channel=?"
        args: list[Any] = [event_id, channel]
        if lease_token:
            where += " AND lease_token=?"
            args.append(str(lease_token))
        else:
            where += " AND status NOT IN ('ok', 'sent', 'dead', 'cancelled')"
            where += " AND (status != 'processing' OR lease_token IS NULL)"
        with self.store.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE notification_outbox
                SET status=?, attempts=attempts+1, last_error=?, next_retry_at=?,
                    last_attempt_at=?, sent_at=?, lease_token=NULL, leased_until=NULL
                WHERE """ + where,
                (status, last_error, None if ok else now, now, now if ok else None, *args),
            )
            return bool(cur.rowcount)


def event_fingerprint(
    event_type: str,
    *,
    sku: str | None = None,
    watch_id: int | None = None,
    old_price: Any = None,
    new_price: Any = None,
    state: str | None = None,
) -> str:
    """Build a stable idempotency key for a domain event."""

    payload = {
        "type": str(event_type),
        "sku": sku,
        "watch_id": watch_id,
        "old_price": old_price,
        "new_price": new_price,
        "state": state,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


EventsRepository = EventRepository

__all__ = ["EventRepository", "EventsRepository", "event_fingerprint"]
