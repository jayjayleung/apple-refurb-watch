from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlparse

from apple_refurb_watch.categories import listing_url

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
    return out or ["mac"]


def safe_next(raw: str | None, fallback: str = "/") -> str:
    text = str(raw or "").strip()
    if not text:
        return fallback
    if "://" in text:
        parsed = urlparse(text)
        text = parsed.path + (("?" + parsed.query) if parsed.query else "")
    if not text.startswith("/") or text.startswith("//"):
        return fallback
    return text


def form_settings(form: dict, current: dict) -> dict:
    listings = form.get("listings")
    if isinstance(listings, str):
        listing_keys = [listings]
    elif listings:
        listing_keys = list(listings)
    else:
        listing_keys = current.get("listings") or ["mac"]
    listing_keys = safe_listings(listing_keys)
    lan = form.get("lan_enabled") in {"1", "on", "true", "yes"}
    patch: dict[str, Any] = {
        "interval_seconds": int(form.get("interval_seconds") or current.get("interval_seconds") or 300),
        "lan_enabled": lan,
        "listings": listing_keys,
        "bind_host": "0.0.0.0" if lan else "127.0.0.1",
        "bind_port": int(form.get("bind_port") or current.get("bind_port") or 8765),
        "close_window_keeps_daemon": form.get("close_window_keeps_daemon") in {"1", "on", "true", "yes"},
        "listen_enabled": form.get("listen_enabled") in {"1", "on", "true", "yes"},
    }
    token = str(form.get("access_token") or "").strip()
    if token:
        patch["access_token"] = token
    elif lan and not current.get("access_token"):
        patch["access_token"] = secrets.token_urlsafe(16)
    notify = current.get("notify") or {}
    for name, conf in notify.items():
        enabled = form.get(f"notify_{name}_enabled") in {"1", "on", "true"}
        updated = {**conf, "enabled": enabled}
        for field in ("url", "sendkey", "token", "webhook", "secret", "bot_token", "chat_id", "smtp_host", "username", "password", "to"):
            key = f"notify_{name}_{field}"
            if key in form and str(form[key]).strip():
                updated[field] = str(form[key]).strip()
        if f"notify_{name}_smtp_port" in form and form[f"notify_{name}_smtp_port"]:
            updated["smtp_port"] = int(form[f"notify_{name}_smtp_port"])
        notify[name] = updated
    patch["notify"] = notify
    return patch
