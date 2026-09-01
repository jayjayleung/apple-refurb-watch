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
                INSERT INTO notification_deliveries(event_id, channel, status, attempts, created_at)
                VALUES(?,?, 'pending', 0, ?)
                ON CONFLICT(event_id, channel) DO NOTHING
                """,
                (event_id, channel, created),
            )
            conn.execute(
                """
                INSERT INTO notification_outbox(event_id, channel, status, attempts, created_at)
                VALUES(?,?, 'pending', 0, ?)
                ON CONFLICT(event_id, channel) DO NOTHING
                """,
                (event_id, channel, created),
            )

    def list_pending_deliveries(self) -> list[dict]:
        with self.store.transaction() as conn:
            # Keep read-side status in agreement with the canonical outbox when
            # an older integration has touched the compatibility table.
            self._sync_outbox_from_legacy(conn)
            rows = self.store.conn.execute(
                """
                SELECT * FROM notification_deliveries
                WHERE status NOT IN ('ok', 'sent', 'processing', 'dead', 'cancelled')
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY id
                """,
                (utcnow(),),
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
            # A caller may have updated the legacy compatibility table directly;
            # mirror its state before claiming from the canonical outbox.
            self._sync_outbox_from_legacy(conn)
            rows = conn.execute(
                """
                SELECT * FROM notification_deliveries
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
                        UPDATE notification_deliveries
                        SET status='dead', last_error=?, next_retry_at=NULL,
                            lease_token=NULL, leased_until=NULL, sent_at=NULL
                        WHERE id=?
                        """,
                        ("超过最大重试次数", row["id"]),
                    )
                    conn.execute(
                        """
                        UPDATE notification_outbox
                        SET status='dead', last_error=?, next_retry_at=NULL,
                            lease_token=NULL, leased_until=NULL, sent_at=NULL
                        WHERE event_id=? AND channel=?
                        """,
                        ("超过最大重试次数", row["event_id"], row["channel"]),
                    )
                    continue
                conn.execute(
                    """
                    UPDATE notification_deliveries
                    SET status='processing', attempts=?, lease_token=?, leased_until=?,
                        last_attempt_at=?
                    WHERE id=?
                    """,
                    (attempts, token, leased_until, now, row["id"]),
                )
                conn.execute(
                    """
                    UPDATE notification_outbox
                    SET status='processing', attempts=?, lease_token=?, leased_until=?,
                        last_attempt_at=?
                    WHERE event_id=? AND channel=?
                    """,
                    (attempts, token, leased_until, now, row["event_id"], row["channel"]),
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
            self._sync_outbox_from_legacy(conn)
            row = conn.execute(
                "SELECT attempts FROM notification_deliveries "
                "WHERE event_id=? AND channel=? AND lease_token=?",
                (event_id, channel, lease_token),
            ).fetchone()
            if row is None:
                return False
            attempts = int(row["attempts"] or 0)
            if ok:
                status = "ok"
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
                UPDATE notification_deliveries
                SET status=?, last_error=?, next_retry_at=?, lease_token=NULL, leased_until=NULL,
                    sent_at=?
                WHERE event_id=? AND channel=? AND lease_token=?
                """,
                (status, error, retry_at, now if ok else None, event_id, channel, lease_token),
            )
            conn.execute(
                """
                UPDATE notification_outbox
                SET status=?, last_error=?, next_retry_at=?, lease_token=NULL, leased_until=NULL,
                    sent_at=?
                WHERE event_id=? AND channel=? AND lease_token=?
                """,
                (
                    "sent" if ok else status,
                    error,
                    retry_at,
                    now if ok else None,
                    event_id,
                    channel,
                    lease_token,
                ),
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
            self._sync_outbox_from_legacy(conn)
            cur = conn.execute(
                """
                UPDATE notification_deliveries
                SET status='pending', next_retry_at=?, lease_token=NULL, leased_until=NULL
                WHERE event_id=? AND channel=? AND lease_token=?
                """,
                (retry_at, event_id, channel, lease_token),
            )
            conn.execute(
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
            self._sync_outbox_from_legacy(conn)
            row = conn.execute(
                "SELECT status FROM notification_deliveries WHERE event_id=? AND channel=?",
                (event_id, channel),
            ).fetchone()
            if row is None:
                return False
            # Never cancel an active lease behind the worker's back.  The
            # worker may already be sending, and clearing only one table here
            # would make a later compatibility sync resurrect or duplicate it.
            status = _canonical_delivery_status(row["status"])
            if status == "processing":
                return False
            if status in _TERMINAL_CANONICAL:
                return False
            cur = conn.execute(
                """
                UPDATE notification_deliveries
                SET status='cancelled', last_error=?, lease_token=NULL, leased_until=NULL,
                    next_retry_at=NULL
                WHERE event_id=? AND channel=? AND status NOT IN ('processing', 'ok', 'sent', 'dead', 'cancelled')
                """,
                (reason, event_id, channel),
            )
            outbox_cur = conn.execute(
                """
                UPDATE notification_outbox
                SET status='cancelled', last_error=?, lease_token=NULL, leased_until=NULL,
                    next_retry_at=NULL
                WHERE event_id=? AND channel=? AND status NOT IN ('processing', 'ok', 'sent', 'dead', 'cancelled')
                """,
                (reason, event_id, channel),
            )
            if cur.rowcount != outbox_cur.rowcount:
                raise RuntimeError("通知投递状态同步失败")
            return bool(cur.rowcount)

    def release_expired_leases(self) -> int:
        """Make work abandoned by a crashed worker immediately retryable."""

        now = utcnow()
        with self.store.transaction(immediate=True) as conn:
            # Keep the compatibility and canonical tables aligned even when a
            # legacy caller updated only one of them (a common recovery case).
            self._sync_outbox_from_legacy(conn)
            pairs = {
                (int(row["event_id"]), str(row["channel"]))
                for row in conn.execute(
                    """
                    SELECT event_id, channel FROM notification_deliveries
                    WHERE status='processing' AND leased_until IS NOT NULL AND leased_until <= ?
                    """,
                    (now,),
                ).fetchall()
            }
            pairs.update(
                (int(row["event_id"]), str(row["channel"]))
                for row in conn.execute(
                    """
                    SELECT event_id, channel FROM notification_outbox
                    WHERE status='processing' AND leased_until IS NOT NULL AND leased_until <= ?
                    """,
                    (now,),
                ).fetchall()
            )
            for event_id, channel in pairs:
                conn.execute(
                    """
                    UPDATE notification_deliveries
                    SET status='pending', lease_token=NULL, leased_until=NULL,
                        next_retry_at=COALESCE(next_retry_at, ?)
                    WHERE event_id=? AND channel=?
                    """,
                    (now, event_id, channel),
                )
                conn.execute(
                    """
                    UPDATE notification_outbox
                    SET status='pending', lease_token=NULL, leased_until=NULL,
                        next_retry_at=COALESCE(next_retry_at, ?)
                    WHERE event_id=? AND channel=?
                    """,
                    (now, event_id, channel),
                )
            return len(pairs)

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

        status = "ok" if ok else "pending"
        now = utcnow()
        where = "event_id=? AND channel=?"
        args: list[Any] = [event_id, channel]
        if lease_token:
            where += " AND lease_token=?"
            args.append(str(lease_token))
        else:
            # A pre-lease caller may acknowledge a pending row, but it must not
            # resurrect a terminal delivery or overwrite another worker's lease.
            where += " AND status NOT IN ('ok', 'sent', 'dead', 'cancelled')"
            where += " AND (status != 'processing' OR lease_token IS NULL)"
        with self.store.transaction() as conn:
            self._sync_outbox_from_legacy(conn)
            cur = conn.execute(
                """
                UPDATE notification_deliveries
                SET status=?, attempts=attempts+1, last_error=?, next_retry_at=?,
                    last_attempt_at=?, sent_at=?, lease_token=NULL, leased_until=NULL
                WHERE """ + where,
                (status, last_error, None if ok else now, now, now if ok else None, *args),
            )
            if not cur.rowcount:
                return False
            # The compatibility table historically used ``ok`` while the
            # canonical resource outbox uses ``sent``.
            conn.execute(
                """
                UPDATE notification_outbox
                SET status=?, attempts=attempts+1, last_error=?, next_retry_at=?,
                    last_attempt_at=?, sent_at=?
                WHERE """ + where,
                (
                    "sent" if ok else status,
                    last_error,
                    None if ok else now,
                    now,
                    now if ok else None,
                    *args,
                ),
            )
            return True

    @staticmethod
    def _sync_outbox_from_legacy(conn) -> None:
        rows = conn.execute(
            "SELECT event_id, channel, status, attempts, next_retry_at, last_error, "
            "lease_token, leased_until, last_attempt_at, sent_at, created_at "
            "FROM notification_deliveries"
        ).fetchall()
        for row in rows:
            legacy = dict(row)
            canonical_row = conn.execute(
                "SELECT event_id, channel, status, attempts, next_retry_at, last_error, "
                "lease_token, leased_until, last_attempt_at, sent_at, created_at "
                "FROM notification_outbox WHERE event_id=? AND channel=?",
                (legacy["event_id"], legacy["channel"]),
            ).fetchone()
            if canonical_row is None:
                canonical = legacy
                canonical["status"] = _canonical_delivery_status(canonical.get("status"))
            else:
                canonical = EventRepository._merge_delivery_rows(dict(canonical_row), legacy)

            values = (
                canonical["event_id"],
                canonical["channel"],
                canonical["status"],
                int(canonical.get("attempts") or 0),
                canonical.get("next_retry_at"),
                canonical.get("last_error"),
                canonical.get("lease_token"),
                canonical.get("leased_until"),
                canonical.get("last_attempt_at"),
                canonical.get("sent_at"),
                canonical.get("created_at") or utcnow(),
            )
            conn.execute(
                """
                INSERT INTO notification_outbox(
                    event_id, channel, status, attempts, next_retry_at, last_error,
                    lease_token, leased_until, last_attempt_at, sent_at, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(event_id, channel) DO UPDATE SET
                    status=excluded.status, attempts=excluded.attempts,
                    next_retry_at=excluded.next_retry_at, last_error=excluded.last_error,
                    lease_token=excluded.lease_token, leased_until=excluded.leased_until,
                    last_attempt_at=excluded.last_attempt_at, sent_at=excluded.sent_at,
                    created_at=COALESCE(notification_outbox.created_at, excluded.created_at)
                """,
                values,
            )
            # Mirror the merged state back to the old table as well.  This makes
            # a terminal canonical result visible to legacy readers and prevents
            # a later compatibility sync from downgrading it.
            legacy_status = "ok" if canonical["status"] == "sent" else canonical["status"]
            conn.execute(
                """
                UPDATE notification_deliveries
                SET status=?, attempts=?, next_retry_at=?, last_error=?,
                    lease_token=?, leased_until=?, last_attempt_at=?, sent_at=?,
                    created_at=COALESCE(created_at, ?)
                WHERE event_id=? AND channel=?
                """,
                (
                    legacy_status,
                    int(canonical.get("attempts") or 0),
                    canonical.get("next_retry_at"),
                    canonical.get("last_error"),
                    canonical.get("lease_token"),
                    canonical.get("leased_until"),
                    canonical.get("last_attempt_at"),
                    canonical.get("sent_at"),
                    canonical.get("created_at") or utcnow(),
                    canonical["event_id"],
                    canonical["channel"],
                ),
            )

    @staticmethod
    def _merge_delivery_rows(canonical: dict, legacy: dict) -> dict:
        """Merge old/new delivery rows without allowing stale state rollback."""

        canonical_status = _canonical_delivery_status(canonical.get("status"))
        legacy_status = _canonical_delivery_status(legacy.get("status"))

        # A successful send is irreversible for an event/channel pair.  Dead or
        # cancelled rows are also terminal; a pending compatibility row must not
        # resurrect them after a restart.
        if canonical_status == "sent" or legacy_status == "sent":
            status = "sent"
        elif canonical_status in _TERMINAL_CANONICAL:
            status = canonical_status
        elif legacy_status in _TERMINAL_CANONICAL:
            status = legacy_status
        elif canonical_status == "processing" or legacy_status == "processing":
            status = "processing"
        else:
            status = "pending"

        # Prefer the row that carries an active lease when both sides disagree;
        # otherwise retain the canonical row's token and timestamps.
        lease_source = canonical
        if canonical_status != "processing" and legacy_status == "processing":
            lease_source = legacy
        elif canonical_status == "processing" and legacy_status == "processing":
            lease_source = EventRepository._choose_processing_source(canonical, legacy)
        attempts = max(int(canonical.get("attempts") or 0), int(legacy.get("attempts") or 0))
        next_retry = None
        if status == "pending":
            retry_values = [value for value in (canonical.get("next_retry_at"), legacy.get("next_retry_at")) if value]
            if canonical_status == legacy_status == "pending" and legacy.get("next_retry_at") is not None:
                # Claiming still reads the compatibility table for old clients;
                # honor an explicit legacy retry schedule when both sides are
                # otherwise the same state.
                next_retry = legacy.get("next_retry_at")
            else:
                next_retry = min(retry_values) if retry_values else None
        if status in _TERMINAL_CANONICAL:
            next_retry = None
        last_attempt_values = [value for value in (canonical.get("last_attempt_at"), legacy.get("last_attempt_at")) if value]
        sent_values = [value for value in (canonical.get("sent_at"), legacy.get("sent_at")) if value]
        created_values = [value for value in (canonical.get("created_at"), legacy.get("created_at")) if value]
        error = canonical.get("last_error") or legacy.get("last_error")
        if status == "sent":
            error = None
        return {
            "event_id": canonical.get("event_id", legacy.get("event_id")),
            "channel": canonical.get("channel", legacy.get("channel")),
            "status": status,
            "attempts": attempts,
            "next_retry_at": next_retry,
            "last_error": error,
            "lease_token": lease_source.get("lease_token") if status == "processing" else None,
            "leased_until": (
                min(
                    value
                    for value in (canonical.get("leased_until"), legacy.get("leased_until"))
                    if value
                )
                if status == "processing"
                and canonical_status == legacy_status == "processing"
                and canonical.get("lease_token") == legacy.get("lease_token")
                and canonical.get("leased_until")
                and legacy.get("leased_until")
                else lease_source.get("leased_until") if status == "processing" else None
            ),
            "last_attempt_at": max(last_attempt_values) if last_attempt_values else None,
            "sent_at": max(sent_values) if status == "sent" and sent_values else None,
            "created_at": min(created_values) if created_values else utcnow(),
        }

    @staticmethod
    def _choose_processing_source(canonical: dict, legacy: dict) -> dict:
        """Choose the freshest lease when compatibility rows diverge.

        Normal claims update both tables in one transaction, so divergence is
        limited to older processes or an interrupted/manual write.  A higher
        attempt count and a newer attempt timestamp identify the newer lease;
        when those are tied, prefer the canonical row.  If only one side has a
        token, retain that token so a live worker is not made unacknowledgeable.
        """

        canonical_token = str(canonical.get("lease_token") or "")
        legacy_token = str(legacy.get("lease_token") or "")
        if bool(canonical_token) != bool(legacy_token):
            return canonical if canonical_token else legacy

        def freshness(row: dict) -> tuple[int, str]:
            return (
                int(row.get("attempts") or 0),
                str(row.get("last_attempt_at") or ""),
            )

        if freshness(legacy) > freshness(canonical):
            return legacy
        return canonical


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
