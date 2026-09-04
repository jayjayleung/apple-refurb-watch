from __future__ import annotations

import ipaddress
import os
import secrets
from typing import Any
from urllib.parse import urlparse

from apple_refurb_watch.categories import compact_listings, listing_url, shop_family_key
from apple_refurb_watch.storage.schema import DEFAULT_BIND_PORT, DEFAULT_LISTING_KEY

ENV_ALLOWED_HOSTS = "APPLE_REFURB_WATCH_ALLOWED_HOSTS"


class SettingsValueError(ValueError):
    """Invalid numeric settings that should surface as HTTP 400, not 500."""

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


def _host_from_value(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    if "://" in text:
        host = (urlparse(text).hostname or "").strip().lower()
        return host.rstrip(".")
    if text.startswith("["):
        end = text.find("]")
        return text[1:end] if end > 1 else text
    if text.count(":") == 1:
        return text.split(":", 1)[0].rstrip(".")
    return text.strip("/").rstrip(".")


def _split_host_text(text: str) -> list[str]:
    return [part.strip() for part in str(text or "").replace(";", ",").replace("\n", ",").split(",") if part.strip()]


def normalize_allowed_hosts(values: Any) -> list[str]:
    items: list[str] = []
    if values is None or values is False:
        items = []
    elif isinstance(values, str):
        items = _split_host_text(values)
    elif isinstance(values, (list, tuple, set)):
        for item in values:
            if item is None:
                continue
            if isinstance(item, str):
                items.extend(_split_host_text(item))
            else:
                items.extend(_split_host_text(str(item)))
    else:
        items = _split_host_text(str(values))
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        host = _host_from_value(item)
        if not host:
            continue
        try:
            ipaddress.ip_address(host)
            continue
        except ValueError:
            pass
        if host in seen:
            continue
        seen.add(host)
        out.append(host)
    return out


def env_allowed_hosts() -> list[str]:
    return normalize_allowed_hosts(os.environ.get(ENV_ALLOWED_HOSTS) or "")


def resolved_allowed_hosts(settings: dict | None = None) -> list[str]:
    stored = (settings or {}).get("allowed_hosts") or []
    merged: list[Any] = []
    if isinstance(stored, str):
        merged.append(stored)
    elif isinstance(stored, (list, tuple, set)):
        merged.extend(stored)
    merged.extend(env_allowed_hosts())
    return normalize_allowed_hosts(merged)


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
            "allowed_hosts",
        )
    }
    data["allowed_hosts"] = normalize_allowed_hosts(data.get("allowed_hosts") or [])
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


def _parse_int(raw: Any, *, name: str) -> int:
    if isinstance(raw, bool) or raw is None or raw == "":
        raise SettingsValueError(f"{name}必须是整数")
    try:
        if isinstance(raw, float) and not raw.is_integer():
            raise SettingsValueError(f"{name}必须是整数")
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise SettingsValueError(f"{name}必须是整数") from exc


def parse_interval_seconds(raw: Any) -> int:
    value = _parse_int(raw, name="扫描间隔")
    if value < 60:
        raise SettingsValueError("扫描间隔不能小于 60 秒")
    return value


def parse_tcp_port(raw: Any, *, name: str = "端口") -> int:
    value = _parse_int(raw, name=name)
    if value < 1 or value > 65535:
        raise SettingsValueError(f"{name}必须在 1–65535 之间")
    return value


def parse_detail_delay_seconds(raw: Any) -> float:
    if isinstance(raw, bool) or raw is None or raw == "":
        raise SettingsValueError("详情延迟必须是数字")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise SettingsValueError("详情延迟必须是数字") from exc
    if value != value or value in {float("inf"), float("-inf")} or value < 0:
        raise SettingsValueError("详情延迟必须是非负数")
    return value


def normalize_settings_patch(patch: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    data = dict(patch)
    if "interval_seconds" in data and data["interval_seconds"] is not None:
        data["interval_seconds"] = parse_interval_seconds(data["interval_seconds"])
    if "bind_port" in data and data["bind_port"] is not None:
        data["bind_port"] = parse_tcp_port(data["bind_port"], name="服务端口")
    if "detail_delay_seconds" in data and data["detail_delay_seconds"] is not None:
        data["detail_delay_seconds"] = parse_detail_delay_seconds(data["detail_delay_seconds"])
    notify = data.get("notify")
    if isinstance(notify, dict):
        for conf in notify.values():
            if isinstance(conf, dict) and "smtp_port" in conf and conf["smtp_port"] not in (None, ""):
                conf["smtp_port"] = parse_tcp_port(conf["smtp_port"], name="SMTP 端口")
    if "access_token" in data:
        token = str(data.get("access_token") or "").strip()
        if token:
            data["access_token"] = token
        else:
            data.pop("access_token", None)
    if "listings" in data and data["listings"] is not None:
        data["listings"] = safe_listings(list(data["listings"]))
    if "allowed_hosts" in data:
        data["allowed_hosts"] = normalize_allowed_hosts(data["allowed_hosts"])
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
