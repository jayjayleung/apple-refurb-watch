from apple_refurb_watch.db import DEFAULT_NOTIFY, DEFAULT_SETTINGS
from apple_refurb_watch.settings import notify_channel_ready, notify_channel_status
from apple_refurb_watch.web.settings_public import form_settings


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


def test_notify_channel_status_labels() -> None:
    assert notify_channel_status({}, "bark") == "未配置"
    assert notify_channel_status({"url_set": True}, "bark") == "已保存，未启用"
    assert notify_channel_status({"enabled": True, "url": "https://api.day.app/x"}, "bark") == "已启用"
    assert notify_channel_status({"enabled": True}, "bark") == "已启用，缺密钥"
    assert notify_channel_ready({"bot_token_set": True, "chat_id": "1"}, "telegram") is True
    assert notify_channel_ready({"bot_token_set": True}, "telegram") is False
