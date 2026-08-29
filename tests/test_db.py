from apple_refurb_watch.db import Database
from apple_refurb_watch.web.settings_public import public_settings


def test_create_watch_normalizes_dim_filters(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    watch = db.create_watch({"name": "内存", "dim_filters": {"tsMemorySize": "24gb"}})
    assert watch["dim_filters"]["tsMemorySize"] == ["24gb"]
    loaded = db.get_watch(watch["id"])
    assert loaded["dim_filters"]["tsMemorySize"] == ["24gb"]


def test_public_settings_redacts_secrets() -> None:
    data = public_settings(
        {
            "interval_seconds": 300,
            "bind_host": "0.0.0.0",
            "bind_port": 8766,
            "lan_enabled": True,
            "listings": ["mac"],
            "detail_delay_seconds": 1.4,
            "close_window_keeps_daemon": True,
            "listen_enabled": True,
            "access_token": "super-secret-token",
            "notify": {"telegram": {"enabled": True, "bot_token": "123:ABC", "chat_id": "99"}},
        }
    )
    assert data["access_token"] == ""
    assert data["access_token_set"] is True
    assert data["notify"]["telegram"]["bot_token"] == ""
    assert data["notify"]["telegram"]["bot_token_set"] is True
    assert data["notify"]["telegram"]["chat_id"] == "99"
