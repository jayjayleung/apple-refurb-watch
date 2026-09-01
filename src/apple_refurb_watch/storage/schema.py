from __future__ import annotations

from datetime import datetime, timezone

from apple_refurb_watch.categories import DEFAULT_LISTINGS

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
    created_at TEXT NOT NULL,
    fingerprint TEXT
);
CREATE TABLE IF NOT EXISTS spec_cache (
    sku TEXT PRIMARY KEY,
    ram_gb INTEGER,
    storage_gb INTEGER,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notification_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    last_error TEXT,
    lease_token TEXT,
    leased_until TEXT,
    last_attempt_at TEXT,
    sent_at TEXT,
    UNIQUE(event_id, channel)
);
CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    requested_listings TEXT NOT NULL DEFAULT '[]',
    successful_listings TEXT NOT NULL DEFAULT '[]',
    product_count INTEGER NOT NULL DEFAULT 0,
    matched_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    listing_key TEXT,
    title TEXT,
    url TEXT,
    price REAL,
    in_stock INTEGER NOT NULL DEFAULT 1,
    observed_at TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    fingerprint TEXT,
    UNIQUE(scan_run_id, sku),
    FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS notification_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    last_error TEXT,
    lease_token TEXT,
    leased_until TEXT,
    last_attempt_at TEXT,
    sent_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(event_id, channel)
);
CREATE INDEX IF NOT EXISTS idx_products_listing_stock
    ON products(listing_key, in_stock);
CREATE INDEX IF NOT EXISTS idx_events_created_at
    ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_deliveries_status_retry
    ON notification_deliveries(status, next_retry_at);
CREATE INDEX IF NOT EXISTS idx_outbox_status_retry
    ON notification_outbox(status, next_retry_at);
CREATE INDEX IF NOT EXISTS idx_scan_runs_started
    ON scan_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_observations_sku_time
    ON observations(sku, observed_at);
"""

SCHEMA_VERSION = 3
EVENT_KEEP = 500
MAX_EVENT_LIMIT = 500
MAX_PRODUCT_PAGE = 1000

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


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
