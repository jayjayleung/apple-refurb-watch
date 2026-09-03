from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from apple_refurb_watch.storage.schema import HISTORY_KEEP_DAYS, MAX_EVENT_LIMIT, utcnow
from apple_refurb_watch.storage.sqlite import SQLiteStore


def _json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return default


def _product_dict(product: Any) -> dict[str, Any]:
    if is_dataclass(product):
        return asdict(product)
    if isinstance(product, dict):
        return dict(product)
    raise TypeError(f"unsupported product type: {type(product)!r}")


class ScanRunRepository:
    """Persistence for scan lifecycle records and immutable observations."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def start(self, requested_listings: Iterable[str], *, metadata: dict | None = None) -> int:
        started = utcnow()
        requested = [str(item) for item in requested_listings]
        with self.store.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO scan_runs(started_at, status, requested_listings, metadata)
                VALUES(?, 'running', ?, ?)
                """,
                (started, json.dumps(requested, ensure_ascii=False), json.dumps(metadata or {}, ensure_ascii=False)),
            )
            return int(cur.lastrowid or 0)

    def finish(
        self,
        run_id: int,
        *,
        status: str,
        successful_listings: Iterable[str] = (),
        product_count: int = 0,
        matched_count: int = 0,
        errors: Iterable[str] = (),
        finished_at: str | None = None,
    ) -> None:
        error_list = [str(item) for item in errors if str(item)]
        with self.store.transaction() as conn:
            conn.execute(
                """
                UPDATE scan_runs
                SET finished_at=?, status=?, successful_listings=?, product_count=?,
                    matched_count=?, error_count=?, error_summary=?
                WHERE id=?
                """,
                (
                    finished_at or utcnow(),
                    str(status),
                    json.dumps([str(item) for item in successful_listings], ensure_ascii=False),
                    int(product_count),
                    int(matched_count),
                    len(error_list),
                    "; ".join(error_list) or None,
                    int(run_id),
                ),
            )
            if str(status) == "succeeded":
                self._prune(conn, (datetime.now(timezone.utc) - timedelta(days=HISTORY_KEEP_DAYS)).isoformat())

    def get(self, run_id: int) -> dict | None:
        with self.store.lock:
            row = self.store.conn.execute("SELECT * FROM scan_runs WHERE id=?", (int(run_id),)).fetchone()
        return self._row(row) if row else None

    def list(self, limit: int = 50) -> list[dict]:
        with self.store.lock:
            rows = self.store.conn.execute(
                "SELECT * FROM scan_runs ORDER BY id DESC LIMIT ?",
                (min(MAX_EVENT_LIMIT, max(1, int(limit))),),
            ).fetchall()
        return [self._row(row) for row in rows]

    def mark_abandoned(self, *, older_than: str) -> int:
        """Mark runs left in ``running`` after a process crash as failed."""

        with self.store.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE scan_runs
                SET status='failed', finished_at=?, error_count=1,
                    error_summary='进程中断，扫描未完成'
                WHERE status='running' AND started_at < ?
                """,
                (utcnow(), str(older_than)),
            )
            return int(cur.rowcount or 0)

    def prune(self, *, older_than: str | None = None, keep_days: int | None = None) -> int:
        cutoff = older_than or (
            datetime.now(timezone.utc) - timedelta(days=keep_days if keep_days is not None else HISTORY_KEEP_DAYS)
        ).isoformat()
        with self.store.transaction() as conn:
            return self._prune(conn, cutoff)

    @staticmethod
    def _prune(conn, cutoff: str) -> int:
        cur = conn.execute(
            "DELETE FROM scan_runs WHERE started_at < ? AND status != 'running'",
            (str(cutoff),),
        )
        return int(cur.rowcount or 0)

    def count_observations(self) -> int:
        with self.store.lock:
            row = self.store.conn.execute("SELECT COUNT(*) FROM observations").fetchone()
        return int(row[0] if row else 0)

    def count_runs(self) -> int:
        with self.store.lock:
            row = self.store.conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()
        return int(row[0] if row else 0)

    def add_observations(
        self,
        run_id: int,
        products: Iterable[Any],
        *,
        observed_at: str | None = None,
        in_stock: bool = True,
    ) -> int:
        timestamp = observed_at or utcnow()
        items = [_product_dict(product) for product in products]
        count = 0
        with self.store.transaction() as conn:
            latest = {
                str(row["sku"]): row["fingerprint"]
                for row in conn.execute(
                    """
                    SELECT sku, fingerprint FROM observations
                    WHERE id IN (SELECT MAX(id) FROM observations GROUP BY sku)
                    """
                )
            }
            for item in items:
                payload = item.get("extra") or {}
                payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                fingerprint = hashlib.sha256(
                    json.dumps(
                        {
                            "sku": item.get("sku"),
                            "listing_key": item.get("listing_key"),
                            "price": item.get("price"),
                            "in_stock": bool(in_stock),
                            "payload": payload,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ).encode("utf-8")
                ).hexdigest()
                sku = str(item.get("sku") or "")
                if sku and latest.get(sku) == fingerprint:
                    continue
                conn.execute(
                    """
                    INSERT INTO observations(
                        scan_run_id, sku, listing_key, title, url, price, in_stock,
                        observed_at, payload, fingerprint
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(scan_run_id, sku) DO UPDATE SET
                        listing_key=excluded.listing_key, title=excluded.title,
                        url=excluded.url, price=excluded.price,
                        in_stock=excluded.in_stock, observed_at=excluded.observed_at,
                        payload=excluded.payload, fingerprint=excluded.fingerprint
                    """,
                    (
                        int(run_id),
                        sku,
                        item.get("listing_key"),
                        item.get("title"),
                        item.get("url"),
                        item.get("price"),
                        int(bool(in_stock)),
                        timestamp,
                        payload_text,
                        fingerprint,
                    ),
                )
                latest[sku] = fingerprint
                count += 1
        return count

    def list_observations(self, run_id: int, *, limit: int = 1000) -> list[dict]:
        with self.store.lock:
            rows = self.store.conn.execute(
                "SELECT * FROM observations WHERE scan_run_id=? ORDER BY id LIMIT ?",
                (int(run_id), max(1, int(limit))),
            ).fetchall()
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["in_stock"] = bool(item.get("in_stock"))
            item["payload"] = _json(item.get("payload"), {})
            result.append(item)
        return result

    @staticmethod
    def _row(row: Any) -> dict:
        item = dict(row)
        item["requested_listings"] = _json(item.get("requested_listings"), [])
        item["successful_listings"] = _json(item.get("successful_listings"), [])
        item["metadata"] = _json(item.get("metadata"), {})
        return item


ScansRepository = ScanRunRepository

__all__ = ["ScanRunRepository", "ScansRepository"]
