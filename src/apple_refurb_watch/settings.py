from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlparse

from apple_refurb_watch.categories import compact_listings, listing_url

_SECRET_NOTIFY_KEYS = ("password", "bot_token", "sendkey", "token", "secret", "webhook", "url")


def public_url(settings: dict) -> str:
    host = settings.get("bind_host") or "127.0.0.1"
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = settings.get("bind_port") or 8765
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


def safe_listings(keys: list[str]) -> list[str]:
    out: list[str] = []
    for key in keys:
        try:
            listing_url(str(key))
        except KeyError:
            continue
        out.append(str(key))
    return compact_listings(out) or ["mac"]


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
    if data.get("lan_enabled") and not (data.get("access_token") or current.get("access_token")):
        data["access_token"] = secrets.token_urlsafe(16)
    if data.get("lan_enabled"):
        data.setdefault("bind_host", "0.0.0.0")
    if data.get("lan_enabled") is False:
        data.setdefault("bind_host", "127.0.0.1")
    return data
