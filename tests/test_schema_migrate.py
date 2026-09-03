import json
import sqlite3

import pytest

from apple_refurb_watch.db import SCHEMA_VERSION, Database

V016_SCHEMA = """
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


def test_upgrades_v016_keeps_data_and_writes_backup(tmp_path) -> None:
    path = tmp_path / "app.db"
    conn = sqlite3.connect(path)
    conn.executescript(V016_SCHEMA)
    conn.execute("INSERT INTO meta(key, value) VALUES(?, ?)", ("interval_seconds", "300"))
    conn.execute(
        """
        INSERT INTO watches(name, enabled, mode, sku, listing_key, all_of, none_of, colors,
            min_ram_gb, min_storage_gb, min_price, max_price, dim_filters, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        ("旧规则", 1, "condition", None, "mac", '["MacBook Pro"]', "[]", "[]", 24, None, None, 18000, "{}", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    conn.execute(
        """
        INSERT INTO products(sku, title, url, price, listing_key, in_stock, first_seen_at, last_seen_at)
        VALUES(?,?,?,?,?,1,?,?)
        """,
        ("FGDN4CH/A", "翻新 MacBook Pro", "https://www.apple.com.cn/shop/product/FGDN4CH/A", 15000, "mac", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    db = Database(path)
    assert db.get_setting("schema_version") == SCHEMA_VERSION
    watches = db.list_watches()
    assert watches[0]["name"] == "旧规则"
    assert watches[0]["min_ram_gb"] == 24
    assert watches[0]["query"]["min_ram_gb"] == 24
    products = db.list_products(in_stock=True)
    assert products[0]["sku"] == "FGDN4CH/A"
    tables = {row[0] for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "notification_deliveries" in tables
    backup = path.with_name("app.db.bak-v1")
    assert backup.exists()
    old = sqlite3.connect(backup)
    try:
        names = [row[0] for row in old.execute("SELECT name FROM watches")]
        assert names == ["旧规则"]
        delivery_tables = [
            row[0]
            for row in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notification_deliveries'")
        ]
        assert delivery_tables == []
    finally:
        old.close()
    db.close()

    again = Database(path)
    assert again.get_setting("schema_version") == SCHEMA_VERSION
    again.close()


def test_migrate_failure_restores_backup(tmp_path, monkeypatch) -> None:
    path = tmp_path / "app.db"
    conn = sqlite3.connect(path)
    conn.executescript(V016_SCHEMA)
    conn.execute("INSERT INTO meta(key, value) VALUES(?, ?)", ("interval_seconds", "300"))
    conn.execute(
        """
        INSERT INTO watches(name, enabled, mode, sku, listing_key, all_of, none_of, colors,
            min_ram_gb, min_storage_gb, min_price, max_price, dim_filters, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        ("旧规则", 1, "condition", None, "mac", '["MacBook Pro"]', "[]", "[]", 24, None, None, 18000, "{}", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    def boom(self):  # noqa: ARG001
        raise sqlite3.DatabaseError("simulated migrate failure")

    monkeypatch.setattr(Database, "_apply_schema", boom)

    with pytest.raises(RuntimeError, match="备份"):
        Database(path)

    backup = path.with_name("app.db.bak-v1")
    assert backup.exists()
    live = sqlite3.connect(path)
    try:
        names = [row[0] for row in live.execute("SELECT name FROM watches")]
        assert names == ["旧规则"]
        tables = [
            row[0]
            for row in live.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='notification_deliveries'"
            )
        ]
        assert tables == []
    finally:
        live.close()


def test_create_watch_normalizes_dim_filters(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    watch = db.create_watch({"name": "内存", "dim_filters": {"tsMemorySize": "24gb"}})
    assert watch["dim_filters"]["tsMemorySize"] == ["24gb"]
    loaded = db.get_watch(watch["id"])
    assert loaded["dim_filters"]["tsMemorySize"] == ["24gb"]
    db.close()


def test_upgrades_v2_deliveries_into_outbox(tmp_path) -> None:
    path = tmp_path / "app.db"
    conn = sqlite3.connect(path)
    conn.executescript(V016_SCHEMA)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS notification_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_retry_at TEXT,
            last_error TEXT,
            UNIQUE(event_id, channel)
        );
        """
    )
    conn.execute("INSERT INTO meta(key, value) VALUES(?, ?)", ("schema_version", json.dumps(2)))
    conn.execute(
        "INSERT INTO events(type, message, created_at) VALUES(?,?,?)",
        ("appeared", "上新", "2026-01-01T00:00:00+00:00"),
    )
    event_id = conn.execute("SELECT id FROM events").fetchone()[0]
    conn.execute(
        "INSERT INTO notification_deliveries(event_id, channel, status, attempts) VALUES(?,?,?,?)",
        (event_id, "bark", "ok", 3),
    )
    conn.commit()
    conn.close()

    db = Database(path)
    row = db.conn.execute(
        "SELECT status, attempts FROM notification_outbox WHERE event_id=? AND channel='bark'",
        (event_id,),
    ).fetchone()
    assert row is not None
    assert row["status"] == "sent"
    assert row["attempts"] == 3
    assert db.list_pending_deliveries() == []
    db.close()
