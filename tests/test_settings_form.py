from apple_refurb_watch.db import DEFAULT_NOTIFY, DEFAULT_SETTINGS
from apple_refurb_watch.settings import notify_channel_ready, notify_channel_status, public_settings
from apple_refurb_watch.web.settings_public import form_settings, overlay_notify_from_form


def _current(**overrides) -> dict:
    data = dict(DEFAULT_SETTINGS)
    data["notify"] = {name: dict(conf) for name, conf in DEFAULT_NOTIFY.items()}
    data.update(overrides)
    return data


def test_form_settings_omits_listen_and_listings() -> None:
    current = _current(listen_enabled=True, listings=["mac", "ipad"])
    patch = form_settings(
        {
            "interval_seconds": "180",
            "bind_port": "8765",
            "save_access": "1",
            "save_notify": "1",
        },
        current,
    )
    assert patch["interval_seconds"] == 180
    assert "listen_enabled" not in patch
    assert "listings" not in patch
    assert "close_window_keeps_daemon" not in patch
    assert patch["lan_enabled"] is False


def test_form_settings_clear_secret() -> None:
    current = _current()
    current["notify"]["bark"] = {"enabled": True, "url": "https://api.day.app/key"}
    patch = form_settings(
        {
            "save_notify": "1",
            "notify_bark_enabled": "on",
            "notify_bark_url_clear": "1",
        },
        current,
    )
    assert patch["notify"]["bark"]["url"] == ""
    assert patch["notify"]["bark"]["enabled"] is True


def test_form_settings_blank_secret_keeps_value() -> None:
    current = _current()
    current["notify"]["bark"] = {"enabled": True, "url": "https://api.day.app/key"}
    patch = form_settings(
        {
            "save_notify": "1",
            "notify_bark_enabled": "on",
            "notify_bark_url": "",
        },
        current,
    )
    assert patch["notify"]["bark"]["url"] == "https://api.day.app/key"


def test_overlay_notify_from_form_uses_typed_secret_without_saving_semantics() -> None:
    current = _current()
    current["notify"]["bark"] = {"enabled": False, "url": "https://api.day.app/saved"}
    merged = overlay_notify_from_form(
        {
            "save_notify": "1",
            "notify_bark_url": "https://api.day.app/draft",
        },
        current,
    )
    assert merged["notify"]["bark"]["url"] == "https://api.day.app/draft"
    assert current["notify"]["bark"]["url"] == "https://api.day.app/saved"
    blank = overlay_notify_from_form(
        {"save_notify": "1", "notify_bark_url": ""},
        current,
    )
    assert blank["notify"]["bark"]["url"] == "https://api.day.app/saved"
    unchanged = overlay_notify_from_form({"channel": "bark"}, current)
    assert unchanged["notify"]["bark"]["url"] == "https://api.day.app/saved"


def test_notify_channel_status_labels() -> None:
    assert notify_channel_status({}, "bark") == "未配置"
    assert notify_channel_status({"url_set": True}, "bark") == "已保存，未启用"
    assert notify_channel_status({"enabled": True, "url": "https://api.day.app/x"}, "bark") == "已启用"
    assert notify_channel_status({"enabled": True}, "bark") == "已启用，缺密钥"
    assert notify_channel_ready({"bot_token_set": True, "chat_id": "1"}, "telegram") is True
    assert notify_channel_ready({"bot_token_set": True}, "telegram") is False


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
    assert data["close_window_keeps_daemon"] is True
    assert data["notify"]["telegram"]["bot_token"] == ""
    assert data["notify"]["telegram"]["bot_token_set"] is True
    assert data["notify"]["telegram"]["chat_id"] == "99"
    assert data["allowed_hosts"] == []


def test_normalize_allowed_hosts_strips_scheme_port_and_ips() -> None:
    from apple_refurb_watch.settings import normalize_allowed_hosts

    assert normalize_allowed_hosts(
        ["https://Watch.Example.com:8443/path", "127.0.0.1", "watch.example.com", "nas.local, nas.local"]
    ) == ["watch.example.com", "nas.local"]
    patch = form_settings(
        {
            "save_access": "1",
            "allowed_hosts": "https://watch.example.com, 10.0.0.1, mypc.local",
        },
        _current(),
    )
    assert patch["allowed_hosts"] == ["watch.example.com", "mypc.local"]
