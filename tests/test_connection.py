import os

import pytest

from apple_refurb_watch.connection import (
    check_client_compat,
    clear_connection,
    compat_notice,
    has_capability,
    load_connection,
    save_computer_notify,
    save_connection,
    token_path,
    validate_server_url,
)
from apple_refurb_watch.desktop import hide_to_tray_enabled


def test_validate_private_http_ok() -> None:
    assert validate_server_url("http://192.168.1.8:8765") == "http://192.168.1.8:8765"
    assert validate_server_url("http://localhost:8765") == "http://localhost:8765"
    assert validate_server_url("https://example.com") == "https://example.com"


def test_validate_public_http_rejected() -> None:
    with pytest.raises(ValueError, match="https"):
        validate_server_url("http://example.com")
    assert validate_server_url("http://example.com", allow_insecure=True) == "http://example.com"


def test_validate_rejects_token_in_url() -> None:
    with pytest.raises(ValueError, match="口令"):
        validate_server_url("http://user:secret@192.168.1.8:8765")


def test_save_and_clear_connection(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("APPLE_REFURB_WATCH_URL", raising=False)
    monkeypatch.delenv("APPLE_REFURB_WATCH_TOKEN", raising=False)
    conn = save_connection("http://10.0.0.2:8765", "s3cret")
    assert conn.mode == "remote"
    assert conn.url == "http://10.0.0.2:8765"
    loaded = load_connection()
    assert loaded.token == "s3cret"
    assert "s3cret" not in loaded.url
    path = token_path()
    assert path.read_text(encoding="utf-8") == "s3cret"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    clear_connection()
    assert load_connection().mode == "local"


def test_env_url_wins(monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("APPLE_REFURB_WATCH_TOKEN", "from-env")
    conn = load_connection()
    assert conn.url == "http://127.0.0.1:9999"
    assert conn.token == "from-env"


def test_compat_newer_server() -> None:
    assert check_client_compat({"ok": True}) is None
    assert check_client_compat({"ok": True, "api_revision": 2}) is None
    err = check_client_compat({"ok": True, "api_revision": 99})
    assert err and "升级客户端" in err


def test_compat_missing_core_upgrades_server() -> None:
    err = check_client_compat({"ok": True, "api_revision": 2, "capabilities": ["listings"]})
    assert err and "升级服务器" in err
    assert "watches" in err


def test_compat_notice_hides_optional_on_old_server() -> None:
    notice = compat_notice({"ok": True})
    assert notice and "较旧" in notice
    assert "电脑通知" in notice
    assert has_capability({"ok": True}, "listings")
    assert not has_capability({"ok": True}, "events.after_id")
    current = {
        "ok": True,
        "api_revision": 2,
        "capabilities": [
            "listings",
            "watches",
            "events",
            "events.after_id",
            "notify.deliveries",
            "filter-catalog",
            "listen",
        ],
    }
    assert check_client_compat(current) is None
    assert compat_notice(current) is None
    assert has_capability(current, "events.after_id")


def test_save_computer_notify(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("APPLE_REFURB_WATCH_URL", raising=False)
    monkeypatch.delenv("APPLE_REFURB_WATCH_TOKEN", raising=False)
    save_computer_notify(False)
    assert load_connection().computer_notify is False
    save_connection("http://10.0.0.2:8765", "x")
    save_computer_notify(True)
    loaded = load_connection()
    assert loaded.computer_notify is True
    assert loaded.url == "http://10.0.0.2:8765"


def test_hide_to_tray_setting() -> None:
    assert hide_to_tray_enabled(None) is True
    assert hide_to_tray_enabled({"close_window_keeps_daemon": True}) is True
    assert hide_to_tray_enabled({"close_window_keeps_daemon": False}) is False


def test_load_connection_rejects_invalid_env_url(monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_URL", "http://example.com")
    monkeypatch.delenv("APPLE_REFURB_WATCH_TOKEN", raising=False)
    conn = load_connection()
    assert conn.mode == "local"
    assert conn.url is None


def test_load_connection_rejects_invalid_stored_url(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("APPLE_REFURB_WATCH_URL", raising=False)
    monkeypatch.delenv("APPLE_REFURB_WATCH_TOKEN", raising=False)
    from apple_refurb_watch.connection import connection_path

    connection_path().parent.mkdir(parents=True, exist_ok=True)
    connection_path().write_text(
        '{"mode": "remote", "url": "ftp://example.com", "allow_insecure": false}',
        encoding="utf-8",
    )
    conn = load_connection()
    assert conn.mode == "local"
    assert conn.url is None


def test_load_connection_rejects_embedded_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("APPLE_REFURB_WATCH_URL", raising=False)
    monkeypatch.delenv("APPLE_REFURB_WATCH_TOKEN", raising=False)
    from apple_refurb_watch.connection import connection_path

    connection_path().parent.mkdir(parents=True, exist_ok=True)
    connection_path().write_text(
        '{"mode": "remote", "url": "http://user:secret@10.0.0.2:8765"}',
        encoding="utf-8",
    )
    conn = load_connection()
    assert conn.mode == "local"
    assert conn.url is None
