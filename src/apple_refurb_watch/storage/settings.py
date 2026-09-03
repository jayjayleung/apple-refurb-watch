from __future__ import annotations

import json
from typing import Any

from apple_refurb_watch.storage.schema import DEFAULT_NOTIFY, DEFAULT_SETTINGS
from apple_refurb_watch.storage.sqlite import SQLiteStore


def _decode(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value if value is not None else default


class SettingsRepository:
    """Read and update values stored in the SQLite meta table."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store
        self.version = 0

    def get(self, key: str, default: Any = None) -> Any:
        with self.store.lock:
            row = self.store.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        return _decode(row["value"], default)

    def set(self, key: str, value: Any) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
        self.version += 1

    def all(self) -> dict[str, Any]:
        merged = dict(DEFAULT_SETTINGS)
        with self.store.lock:
            rows = self.store.conn.execute("SELECT key, value FROM meta").fetchall()
        for row in rows:
            merged[row["key"]] = _decode(row["value"])
        stored = merged.get("notify") or {}
        notify = {name: dict(conf) for name, conf in DEFAULT_NOTIFY.items()}
        for name, conf in DEFAULT_NOTIFY.items():
            notify[name] = {**conf, **(stored.get(name) or {})}
        merged["notify"] = notify
        return merged

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.all()
        pending = dict(patch)
        with self.store.transaction() as conn:
            if isinstance(pending.get("notify"), dict):
                merged_notify = {name: dict(conf) for name, conf in current["notify"].items()}
                for name, conf in pending["notify"].items():
                    merged_notify[name] = {**merged_notify.get(name, {}), **(conf or {})}
                current["notify"] = merged_notify
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("notify", json.dumps(merged_notify, ensure_ascii=False)),
                )
                pending.pop("notify", None)
            for key, value in pending.items():
                current[key] = value
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value, ensure_ascii=False)),
                )
        self.version += 1
        return self.all()

    def scan_status(self) -> dict[str, Any]:
        keys = (
            "last_scan_at",
            "last_success_at",
            "last_error",
            "last_product_count",
            "baseline_done",
            "scanning",
        )
        placeholders = ",".join("?" for _ in keys)
        with self.store.lock:
            rows = self.store.conn.execute(
                f"SELECT key, value FROM meta WHERE key IN ({placeholders})",
                keys,
            ).fetchall()
        found = {row["key"]: _decode(row["value"]) for row in rows}
        return {
            "last_scan_at": found.get("last_scan_at"),
            "last_success_at": found.get("last_success_at"),
            "last_error": found.get("last_error"),
            "last_product_count": found.get("last_product_count") or 0,
            "baseline_done": bool(found.get("baseline_done")),
            "scanning": bool(found.get("scanning")),
        }
