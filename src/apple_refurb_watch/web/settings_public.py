from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from apple_refurb_watch.settings import normalize_settings_patch, public_settings, public_url, safe_listings

__all__ = ["form_settings", "public_settings", "public_url", "safe_listings", "safe_next"]


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
    patch = normalize_settings_patch(patch, current)
    notify = current.get("notify") or {}
    for name, conf in notify.items():
        enabled = form.get(f"notify_{name}_enabled") in {"1", "on", "true"}
        updated = {**conf, "enabled": enabled}
        for field in (
            "url",
            "sendkey",
            "token",
            "webhook",
            "secret",
            "bot_token",
            "chat_id",
            "smtp_host",
            "username",
            "password",
            "to",
        ):
            key = f"notify_{name}_{field}"
            if key in form and str(form[key]).strip():
                updated[field] = str(form[key]).strip()
        if f"notify_{name}_smtp_port" in form and form[f"notify_{name}_smtp_port"]:
            updated["smtp_port"] = int(form[f"notify_{name}_smtp_port"])
        notify[name] = updated
    patch["notify"] = notify
    return patch
