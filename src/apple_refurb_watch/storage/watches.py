from __future__ import annotations

import json
import sqlite3
from typing import Any

from apple_refurb_watch.query import ProductQuery
from apple_refurb_watch.storage.schema import utcnow
from apple_refurb_watch.storage.sqlite import SQLiteStore


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace("\n", ",").split(",")]
        return [part for part in parts if part]
    return [str(item).strip() for item in value if str(item).strip()]


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _as_dim_filters(value: Any) -> dict:
    from apple_refurb_watch.filters import normalize_dim_filters

    return normalize_dim_filters(value)


class WatchRepository:
    """Persistence for watch rules and their per-SKU state."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def list(self) -> list[dict]:
        with self.store.lock:
            rows = self.store.conn.execute("SELECT * FROM watches ORDER BY id DESC").fetchall()
        return [self._row(row) for row in rows]

    def count(self, *, enabled: bool | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM watches"
        if enabled is True:
            sql += " WHERE enabled=1"
        elif enabled is False:
            sql += " WHERE enabled=0"
        with self.store.lock:
            return int(self.store.conn.execute(sql).fetchone()["n"])

    def get(self, watch_id: int) -> dict | None:
        with self.store.lock:
            row = self.store.conn.execute("SELECT * FROM watches WHERE id=?", (watch_id,)).fetchone()
        return self._row(row) if row else None

    def create(self, data: dict) -> dict:
        now = utcnow()
        payload = self._payload(data)
        with self.store.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO watches(name, enabled, mode, sku, listing_key, all_of, none_of, colors,
                    min_ram_gb, min_storage_gb, min_price, max_price, dim_filters, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    payload["name"],
                    int(payload["enabled"]),
                    payload["mode"],
                    payload["sku"],
                    payload["listing_key"],
                    json.dumps(payload["all_of"], ensure_ascii=False),
                    json.dumps(payload["none_of"], ensure_ascii=False),
                    json.dumps(payload["colors"], ensure_ascii=False),
                    payload["min_ram_gb"],
                    payload["min_storage_gb"],
                    payload["min_price"],
                    payload["max_price"],
                    json.dumps(payload["dim_filters"], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            watch_id = int(cur.lastrowid or 0)
        return self.get(watch_id)  # type: ignore[return-value]

    def update(self, watch_id: int, data: dict) -> dict | None:
        current = self.get(watch_id)
        if not current:
            return None
        current.update({key: value for key, value in data.items() if value is not None or key in data})
        payload = self._payload(current)
        with self.store.transaction() as conn:
            conn.execute(
                """
                UPDATE watches SET name=?, enabled=?, mode=?, sku=?, listing_key=?, all_of=?, none_of=?,
                    colors=?, min_ram_gb=?, min_storage_gb=?, min_price=?, max_price=?, dim_filters=?, updated_at=?
                WHERE id=?
                """,
                (
                    payload["name"],
                    int(payload["enabled"]),
                    payload["mode"],
                    payload["sku"],
                    payload["listing_key"],
                    json.dumps(payload["all_of"], ensure_ascii=False),
                    json.dumps(payload["none_of"], ensure_ascii=False),
                    json.dumps(payload["colors"], ensure_ascii=False),
                    payload["min_ram_gb"],
                    payload["min_storage_gb"],
                    payload["min_price"],
                    payload["max_price"],
                    json.dumps(payload["dim_filters"], ensure_ascii=False),
                    utcnow(),
                    watch_id,
                ),
            )
        return self.get(watch_id)

    def delete(self, watch_id: int) -> bool:
        with self.store.transaction() as conn:
            cur = conn.execute("DELETE FROM watches WHERE id=?", (watch_id,))
            conn.execute("DELETE FROM watch_sku WHERE watch_id=?", (watch_id,))
        return cur.rowcount > 0

    def enabled(self) -> list[dict]:
        return [watch for watch in self.list() if watch["enabled"]]

    def sku_state(self, watch_id: int, sku: str) -> dict | None:
        with self.store.lock:
            row = self.store.conn.execute(
                "SELECT * FROM watch_sku WHERE watch_id=? AND sku=?",
                (watch_id, sku),
            ).fetchone()
        return dict(row) if row else None

    def set_sku(self, watch_id: int, sku: str, in_stock: bool, notified: bool) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO watch_sku(watch_id, sku, in_stock, notified, updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(watch_id, sku) DO UPDATE SET
                    in_stock=excluded.in_stock, notified=excluded.notified, updated_at=excluded.updated_at
                """,
                (watch_id, sku, int(in_stock), int(notified), utcnow()),
            )

    def mark_skus_out(self, watch_id: int, present: set[str]) -> None:
        with self.store.lock:
            rows = self.store.conn.execute(
                "SELECT sku FROM watch_sku WHERE watch_id=? AND in_stock=1",
                (watch_id,),
            ).fetchall()
        with self.store.transaction() as conn:
            for row in rows:
                if row["sku"] not in present:
                    conn.execute(
                        """
                        UPDATE watch_sku
                        SET in_stock=0, notified=0, updated_at=?
                        WHERE watch_id=? AND sku=?
                        """,
                        (utcnow(), watch_id, row["sku"]),
                    )

    @staticmethod
    def _row(row: sqlite3.Row) -> dict:
        data = dict(row)
        for field in ("all_of", "none_of", "colors"):
            try:
                data[field] = json.loads(data[field] or "[]")
            except (TypeError, json.JSONDecodeError):
                data[field] = []
        try:
            data["dim_filters"] = json.loads(data.get("dim_filters") or "{}")
        except (TypeError, json.JSONDecodeError):
            data["dim_filters"] = {}
        if not isinstance(data["dim_filters"], dict):
            data["dim_filters"] = {}
        data["enabled"] = bool(data["enabled"])
        data["query"] = ProductQuery.from_watch(data).to_dict()
        return data

    @staticmethod
    def _payload(data: dict) -> dict:
        nested = data.get("query")
        if isinstance(nested, dict) and nested:
            folded = ProductQuery.from_mapping(nested).to_watch_fields()
            merged = dict(folded)
            merged.update({key: value for key, value in data.items() if key != "query" and value is not None})
            data = merged
        return {
            "name": str(data.get("name") or "未命名规则").strip(),
            "enabled": bool(data.get("enabled", True)),
            "mode": data.get("mode") or "condition",
            "sku": str(data.get("sku") or "").strip().upper() or None,
            "listing_key": data.get("listing_key") or None,
            "all_of": _as_list(data.get("all_of")),
            "none_of": _as_list(data.get("none_of")),
            "colors": _as_list(data.get("colors")),
            "min_ram_gb": _as_int(data.get("min_ram_gb")),
            "min_storage_gb": _as_int(data.get("min_storage_gb")),
            "min_price": _as_float(data.get("min_price")),
            "max_price": _as_float(data.get("max_price")),
            "dim_filters": _as_dim_filters(data.get("dim_filters")),
        }
