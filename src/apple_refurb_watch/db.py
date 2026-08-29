from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from apple_refurb_watch.categories import DEFAULT_LISTINGS
from apple_refurb_watch.paths import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    mode TEXT NOT NULL DEFAULT 'condition',
    sku TEXT,
    listing_key TEXT,
    all_of TEXT NOT NULL DEFAULT '[]',
    none_of TEXT NOT NULL DEFAULT '[]',
    colors TEXT NOT NULL DEFAULT '[]',
    min_ram_gb INTEGER,
    min_storage_gb INTEGER,
    min_price REAL,
    max_price REAL,
    dim_filters TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    price REAL,
    listing_key TEXT,
    ram_gb INTEGER,
    storage_gb INTEGER,
    color_key TEXT,
    color_label TEXT,
    model_key TEXT,
    year TEXT,
    screensize TEXT,
    image_url TEXT,
    in_stock INTEGER NOT NULL DEFAULT 1,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    extra TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS watch_sku (
    watch_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    in_stock INTEGER NOT NULL DEFAULT 0,
    notified INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (watch_id, sku)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    sku TEXT,
    watch_id INTEGER,
    title TEXT,
    price REAL,
    url TEXT,
    message TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spec_cache (
    sku TEXT PRIMARY KEY,
    ram_gb INTEGER,
    storage_gb INTEGER,
    fetched_at TEXT NOT NULL
);
"""

DEFAULT_NOTIFY = {
    "bark": {"enabled": False, "url": ""},
    "serverchan": {"enabled": False, "sendkey": ""},
    "pushplus": {"enabled": False, "token": ""},
    "feishu": {"enabled": False, "webhook": "", "secret": ""},
    "dingtalk": {"enabled": False, "webhook": "", "secret": ""},
    "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
    "email": {
        "enabled": False,
        "smtp_host": "",
        "smtp_port": 465,
        "username": "",
        "password": "",
        "to": "",
        "use_tls": True,
    },
}

DEFAULT_SETTINGS = {
    "interval_seconds": 300,
    "bind_host": "127.0.0.1",
    "bind_port": 8765,
    "lan_enabled": False,
    "access_token": "",
    "listings": DEFAULT_LISTINGS,
    "detail_delay_seconds": 1.4,
    "notify": DEFAULT_NOTIFY,
    "close_window_keeps_daemon": True,
    "listen_enabled": True,
    "baseline_done": False,
}

EVENT_KEEP = 500


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        with self._lock:
            self.conn.executescript(SCHEMA)
            cols = [row[1] for row in self.conn.execute("PRAGMA table_info(watches)").fetchall()]
            if "dim_filters" not in cols:
                self.conn.execute("ALTER TABLE watches ADD COLUMN dim_filters TEXT NOT NULL DEFAULT '{}'")
            self.conn.commit()
            for key, value in DEFAULT_SETTINGS.items():
                existing = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
                if existing is None:
                    self.set_setting(key, value)

    def close(self) -> None:
        self.conn.close()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
            self.conn.commit()

    def settings(self) -> dict[str, Any]:
        merged = dict(DEFAULT_SETTINGS)
        with self._lock:
            rows = self.conn.execute("SELECT key, value FROM meta").fetchall()
        for row in rows:
            try:
                merged[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                merged[row["key"]] = row["value"]
        notify = dict(DEFAULT_NOTIFY)
        stored = merged.get("notify") or {}
        for name, conf in DEFAULT_NOTIFY.items():
            notify[name] = {**conf, **(stored.get(name) or {})}
        merged["notify"] = notify
        return merged

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.settings()
        if "notify" in patch and isinstance(patch["notify"], dict):
            merged_notify = current["notify"]
            for name, conf in patch["notify"].items():
                merged_notify[name] = {**merged_notify.get(name, {}), **conf}
            current["notify"] = merged_notify
            patch = {k: v for k, v in patch.items() if k != "notify"}
            self.set_setting("notify", merged_notify)
        for key, value in patch.items():
            current[key] = value
            self.set_setting(key, value)
        return self.settings()

    def list_watches(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM watches ORDER BY id DESC").fetchall()
        return [self._watch_row(row) for row in rows]

    def count_watches(self, *, enabled: bool | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM watches"
        if enabled is True:
            sql += " WHERE enabled=1"
        elif enabled is False:
            sql += " WHERE enabled=0"
        with self._lock:
            return int(self.conn.execute(sql).fetchone()["n"])

    def get_watch(self, watch_id: int) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM watches WHERE id=?", (watch_id,)).fetchone()
        return self._watch_row(row) if row else None

    def create_watch(self, data: dict) -> dict:
        now = utcnow()
        payload = self._watch_payload(data)
        with self._lock:
            cur = self.conn.execute(
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
            self.conn.commit()
            return self.get_watch(int(cur.lastrowid))  # type: ignore[arg-type]

    def update_watch(self, watch_id: int, data: dict) -> dict | None:
        current = self.get_watch(watch_id)
        if not current:
            return None
        current.update({k: v for k, v in data.items() if v is not None or k in data})
        payload = self._watch_payload(current)
        with self._lock:
            self.conn.execute(
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
            self.conn.commit()
        return self.get_watch(watch_id)

    def delete_watch(self, watch_id: int) -> bool:
        with self._lock:
            cur = self.conn.execute("DELETE FROM watches WHERE id=?", (watch_id,))
            self.conn.execute("DELETE FROM watch_sku WHERE watch_id=?", (watch_id,))
            self.conn.commit()
            return cur.rowcount > 0

    def enabled_watches(self) -> list[dict]:
        return [w for w in self.list_watches() if w["enabled"]]

    def upsert_products(self, products: Iterable[dict]) -> None:
        now = utcnow()
        with self._lock:
            for item in products:
                extra = item.get("extra") or {}
                extra_text = json.dumps(extra, ensure_ascii=False) if isinstance(extra, dict) else str(extra)
                self.conn.execute(
                    """
                    INSERT INTO products(sku, title, url, price, listing_key, ram_gb, storage_gb, color_key,
                        color_label, model_key, year, screensize, image_url, in_stock, first_seen_at, last_seen_at, extra)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)
                    ON CONFLICT(sku) DO UPDATE SET
                        title=excluded.title,
                        url=excluded.url,
                        price=excluded.price,
                        listing_key=excluded.listing_key,
                        ram_gb=COALESCE(excluded.ram_gb, products.ram_gb),
                        storage_gb=COALESCE(excluded.storage_gb, products.storage_gb),
                        color_key=excluded.color_key,
                        color_label=excluded.color_label,
                        model_key=excluded.model_key,
                        year=excluded.year,
                        screensize=excluded.screensize,
                        image_url=excluded.image_url,
                        in_stock=1,
                        last_seen_at=excluded.last_seen_at,
                        extra=excluded.extra
                    """,
                    (
                        item["sku"],
                        item["title"],
                        item["url"],
                        item.get("price"),
                        item.get("listing_key"),
                        item.get("ram_gb"),
                        item.get("storage_gb"),
                        item.get("color_key"),
                        item.get("color_label"),
                        item.get("model_key"),
                        item.get("year"),
                        item.get("screensize"),
                        item.get("image_url"),
                        now,
                        now,
                        extra_text,
                    ),
                )
            self.conn.commit()

    def mark_listing_stock(self, listing_keys: list[str], seen_skus: set[str]) -> None:
        with self._lock:
            if not listing_keys:
                return
            keys_ph = ",".join("?" for _ in listing_keys)
            if seen_skus:
                sku_ph = ",".join("?" for _ in seen_skus)
                self.conn.execute(
                    f"UPDATE products SET in_stock=0 WHERE listing_key IN ({keys_ph}) AND sku NOT IN ({sku_ph})",
                    (*listing_keys, *seen_skus),
                )
            else:
                self.conn.execute(
                    f"UPDATE products SET in_stock=0 WHERE listing_key IN ({keys_ph})",
                    tuple(listing_keys),
                )
            self.conn.commit()

    def list_products(self, in_stock: bool | None = True) -> list[dict]:
        sql = "SELECT * FROM products"
        args: list[Any] = []
        if in_stock is True:
            sql += " WHERE in_stock=1"
        elif in_stock is False:
            sql += " WHERE in_stock=0"
        sql += " ORDER BY price IS NULL, price ASC, title"
        with self._lock:
            rows = self.conn.execute(sql, args).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            extra = item.get("extra")
            if isinstance(extra, str):
                try:
                    item["extra"] = json.loads(extra)
                except json.JSONDecodeError:
                    item["extra"] = {}
        return items

    def get_spec(self, sku: str) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM spec_cache WHERE sku=?", (sku,)).fetchone()
        return dict(row) if row else None

    def set_spec(self, sku: str, ram_gb: int | None, storage_gb: int | None) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO spec_cache(sku, ram_gb, storage_gb, fetched_at) VALUES(?,?,?,?)
                ON CONFLICT(sku) DO UPDATE SET ram_gb=excluded.ram_gb, storage_gb=excluded.storage_gb, fetched_at=excluded.fetched_at
                """,
                (sku, ram_gb, storage_gb, utcnow()),
            )
            if ram_gb is not None or storage_gb is not None:
                self.conn.execute(
                    "UPDATE products SET ram_gb=COALESCE(?, ram_gb), storage_gb=COALESCE(?, storage_gb) WHERE sku=?",
                    (ram_gb, storage_gb, sku),
                )
            self.conn.commit()

    def watch_sku_state(self, watch_id: int, sku: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM watch_sku WHERE watch_id=? AND sku=?",
                (watch_id, sku),
            ).fetchone()
        return dict(row) if row else None

    def set_watch_sku(self, watch_id: int, sku: str, in_stock: bool, notified: bool) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO watch_sku(watch_id, sku, in_stock, notified, updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(watch_id, sku) DO UPDATE SET in_stock=excluded.in_stock, notified=excluded.notified, updated_at=excluded.updated_at
                """,
                (watch_id, sku, int(in_stock), int(notified), utcnow()),
            )
            self.conn.commit()

    def mark_watch_skus_out(self, watch_id: int, present: set[str]) -> None:
        with self._lock:
            rows = self.conn.execute(
                "SELECT sku FROM watch_sku WHERE watch_id=? AND in_stock=1",
                (watch_id,),
            ).fetchall()
        for row in rows:
            if row["sku"] not in present:
                self.set_watch_sku(watch_id, row["sku"], in_stock=False, notified=False)

    def add_event(self, **kwargs: Any) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO events(type, sku, watch_id, title, price, url, message, created_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    kwargs.get("type"),
                    kwargs.get("sku"),
                    kwargs.get("watch_id"),
                    kwargs.get("title"),
                    kwargs.get("price"),
                    kwargs.get("url"),
                    kwargs.get("message"),
                    utcnow(),
                ),
            )
            self.conn.execute(
                "DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY id DESC LIMIT -1 OFFSET ?)",
                (EVENT_KEEP,),
            )
            self.conn.commit()

    def list_events(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def count_products(self, *, in_stock: bool | None = True) -> int:
        sql = "SELECT COUNT(*) AS n FROM products"
        if in_stock is True:
            sql += " WHERE in_stock=1"
        elif in_stock is False:
            sql += " WHERE in_stock=0"
        with self._lock:
            return int(self.conn.execute(sql).fetchone()["n"])

    def scan_status(self) -> dict[str, Any]:
        return {
            "last_scan_at": self.get_setting("last_scan_at"),
            "last_success_at": self.get_setting("last_success_at"),
            "last_error": self.get_setting("last_error"),
            "last_product_count": self.get_setting("last_product_count") or 0,
            "baseline_done": bool(self.get_setting("baseline_done")),
            "scanning": bool(self.get_setting("scanning")),
        }

    @staticmethod
    def _watch_row(row: sqlite3.Row) -> dict:
        data = dict(row)
        for field in ("all_of", "none_of", "colors"):
            try:
                data[field] = json.loads(data[field] or "[]")
            except json.JSONDecodeError:
                data[field] = []
        try:
            data["dim_filters"] = json.loads(data.get("dim_filters") or "{}")
        except json.JSONDecodeError:
            data["dim_filters"] = {}
        if not isinstance(data["dim_filters"], dict):
            data["dim_filters"] = {}
        data["enabled"] = bool(data["enabled"])
        return data

    @staticmethod
    def _watch_payload(data: dict) -> dict:
        def as_list(value: Any) -> list[str]:
            if value is None:
                return []
            if isinstance(value, str):
                parts = [p.strip() for p in value.replace("\n", ",").split(",")]
                return [p for p in parts if p]
            return [str(v).strip() for v in value if str(v).strip()]

        return {
            "name": (data.get("name") or "未命名规则").strip(),
            "enabled": bool(data.get("enabled", True)),
            "mode": data.get("mode") or "condition",
            "sku": (data.get("sku") or "").strip().upper() or None,
            "listing_key": data.get("listing_key") or None,
            "all_of": as_list(data.get("all_of")),
            "none_of": as_list(data.get("none_of")),
            "colors": as_list(data.get("colors")),
            "min_ram_gb": _as_int(data.get("min_ram_gb")),
            "min_storage_gb": _as_int(data.get("min_storage_gb")),
            "min_price": _as_float(data.get("min_price")),
            "max_price": _as_float(data.get("max_price")),
            "dim_filters": _as_dim_filters(data.get("dim_filters")),
        }


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
