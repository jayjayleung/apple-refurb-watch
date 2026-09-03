from __future__ import annotations

import ipaddress
import secrets
from typing import Any

from apple_refurb_watch.categories import compact_listings, listing_url, shop_family_key
from apple_refurb_watch.storage.schema import DEFAULT_BIND_PORT, DEFAULT_LISTING_KEY

_SECRET_NOTIFY_KEYS = ("password", "bot_token", "sendkey", "token", "secret", "webhook", "url")

NOTIFY_CHANNEL_UI: tuple[dict[str, Any], ...] = (
    {
        "name": "bark",
        "label": "Bark",
        "secrets": (("url", "URL"),),
        "optional_secrets": (),
        "fields": (),
    },
    {
        "name": "serverchan",
        "label": "Server酱",
        "secrets": (("sendkey", "SendKey"),),
        "optional_secrets": (),
        "fields": (),
    },
    {
        "name": "pushplus",
        "label": "PushPlus",
        "secrets": (("token", "Token"),),
        "optional_secrets": (),
        "fields": (),
    },
    {
        "name": "feishu",
        "label": "飞书",
        "secrets": (("webhook", "Webhook"),),
        "optional_secrets": (("secret", "Secret"),),
        "fields": (),
    },
    {
        "name": "dingtalk",
        "label": "钉钉",
        "secrets": (("webhook", "Webhook"),),
        "optional_secrets": (("secret", "Secret"),),
        "fields": (),
    },
    {
        "name": "telegram",
        "label": "Telegram",
        "secrets": (("bot_token", "Bot token"),),
        "optional_secrets": (),
        "fields": (("chat_id", "Chat ID", "text"),),
    },
    {
        "name": "email",
        "label": "邮件",
        "secrets": (("password", "密码"),),
        "optional_secrets": (),
        "fields": (
            ("smtp_host", "SMTP", "text"),
            ("smtp_port", "端口", "number"),
            ("username", "用户名", "text"),
            ("to", "收件人", "text"),
        ),
    },
)

_CHANNEL_UI_BY_NAME = {item["name"]: item for item in NOTIFY_CHANNEL_UI}
_LOOPBACK_HOSTS = {"localhost", "localhost.localdomain"}
_WILDCARD_HOSTS = {"0.0.0.0", "::", "[::]", ""}


def is_loopback_bind(host: str | None) -> bool:
    """Return whether a bind address is restricted to this machine."""

    value = str(host or "127.0.0.1").strip().lower().rstrip(".")
    if value in _LOOPBACK_HOSTS:
        return True
    if value in _WILDCARD_HOSTS:
        return False
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if "%" in value:
        value = value.split("%", 1)[0]
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        # Unresolved host names may resolve to a LAN address at bind time.
        return False


def listener_requires_auth(settings: dict) -> bool:
    return not is_loopback_bind(settings.get("bind_host"))


def public_url(settings: dict) -> str:
    host = settings.get("bind_host") or "127.0.0.1"
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = settings.get("bind_port") or DEFAULT_BIND_PORT
    return f"http://{host}:{port}"


def public_settings(settings: dict) -> dict:
    data = {
        key: settings.get(key)
        for key in (
            "interval_seconds",
            "bind_host",
            "bind_port",
            "lan_enabled",
            "listings",
            "detail_delay_seconds",
            "close_window_keeps_daemon",
            "listen_enabled",
        )
    }
    notify = {}
    for name, conf in (settings.get("notify") or {}).items():
        safe = dict(conf)
        for secret_key in _SECRET_NOTIFY_KEYS:
            if safe.get(secret_key):
                safe[secret_key + "_set"] = True
                safe[secret_key] = ""
        notify[name] = safe
    data["notify"] = notify
    data["access_token"] = ""
    data["access_token_set"] = bool(settings.get("access_token"))
    return data


def _secret_present(conf: dict[str, Any], key: str) -> bool:
    return bool(conf.get(key) or conf.get(f"{key}_set"))


def notify_channel_spec(name: str) -> dict[str, Any] | None:
    return _CHANNEL_UI_BY_NAME.get(name)


def notify_channel_ready(conf: dict[str, Any] | None, name: str) -> bool:
    spec = notify_channel_spec(name)
    if spec is None:
        return False
    data = conf or {}
    for key, _label in spec["secrets"]:
        if not _secret_present(data, key):
            return False
    for field in spec["fields"]:
        key = field[0]
        if key == "smtp_port":
            continue
        if not str(data.get(key) or "").strip():
            return False
    return True


def notify_channel_status(conf: dict[str, Any] | None, name: str) -> str:
    data = conf or {}
    ready = notify_channel_ready(data, name)
    enabled = bool(data.get("enabled"))
    if enabled and ready:
        return "已启用"
    if enabled and not ready:
        return "已启用，缺密钥"
    if ready:
        return "已保存，未启用"
    return "未配置"


def listing_family_checked(key: str, listings: list | None) -> bool:
    selected = [str(item) for item in (listings or [])]
    if key in selected or shop_family_key(key) in selected:
        return True
    return key == DEFAULT_LISTING_KEY and ("macbook-pro" in selected or "macbook-air" in selected)


def safe_listings(keys: list[str]) -> list[str]:
    out: list[str] = []
    for key in keys:
        try:
            listing_url(str(key))
        except KeyError:
            continue
        out.append(str(key))
    return compact_listings(out) or [DEFAULT_LISTING_KEY]


def normalize_settings_patch(patch: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    data = dict(patch)
    if "access_token" in data:
        token = str(data.get("access_token") or "").strip()
        if token:
            data["access_token"] = token
        else:
            data.pop("access_token", None)
    if "listings" in data and data["listings"] is not None:
        data["listings"] = safe_listings(list(data["listings"]))
    if data.get("lan_enabled"):
        data.setdefault("bind_host", "0.0.0.0")
    if data.get("lan_enabled") is False:
        data.setdefault("bind_host", "127.0.0.1")
    effective_host = data.get("bind_host", current.get("bind_host"))
    if listener_requires_auth({"bind_host": effective_host}) and not (
        data.get("access_token") or current.get("access_token")
    ):
        data["access_token"] = secrets.token_urlsafe(16)
    return data
