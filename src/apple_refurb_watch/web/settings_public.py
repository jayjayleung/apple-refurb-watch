from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from apple_refurb_watch.settings import (
    NOTIFY_CHANNEL_UI,
    normalize_settings_patch,
    public_settings,
    public_url,
    safe_listings,
)

__all__ = [
    "form_settings",
    "overlay_notify_from_form",
    "public_settings",
    "public_url",
    "safe_listings",
    "safe_next",
]

_TRUTHY = {"1", "on", "true", "yes"}
_NOTIFY_VALUE_FIELDS = (
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
)


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


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in _TRUTHY


def _has(form: dict, key: str) -> bool:
    return key in form and form.get(key) not in (None, "")


def form_settings(form: dict, current: dict) -> dict:
    patch: dict[str, Any] = {}
    clear_access = False
    if _has(form, "interval_seconds"):
        patch["interval_seconds"] = int(form.get("interval_seconds") or current.get("interval_seconds") or 300)
    if _has(form, "bind_port"):
        patch["bind_port"] = int(form.get("bind_port") or current.get("bind_port") or 8765)
    if _has(form, "save_listings"):
        listings = form.get("listings")
        if isinstance(listings, str):
            listing_keys = [listings]
        elif listings:
            listing_keys = list(listings)
        else:
            listing_keys = []
        patch["listings"] = safe_listings(listing_keys)
    if _has(form, "save_access"):
        lan = _truthy(form.get("lan_enabled"))
        patch["lan_enabled"] = lan
        patch["bind_host"] = "0.0.0.0" if lan else "127.0.0.1"
        token = str(form.get("access_token") or "").strip()
        if token:
            patch["access_token"] = token
        else:
            clear_access = _truthy(form.get("access_token_clear"))
            if clear_access:
                # Clearing the only credential must also turn off the remote
                # listener.  The actual socket remains protected by the
                # process-bound host until a restart applies this setting.
                patch["lan_enabled"] = False
                patch["bind_host"] = "127.0.0.1"
                patch["access_token"] = ""
    if _has(form, "listen_enabled"):
        patch["listen_enabled"] = _truthy(form.get("listen_enabled"))
    if _has(form, "close_window_keeps_daemon"):
        patch["close_window_keeps_daemon"] = _truthy(form.get("close_window_keeps_daemon"))
    patch = normalize_settings_patch(patch, current)
    if clear_access:
        patch["access_token"] = ""
    if _has(form, "save_notify"):
        notify = dict(current.get("notify") or {})
        names = {item["name"] for item in NOTIFY_CHANNEL_UI} | set(notify)
        for name in names:
            conf = dict(notify.get(name) or {})
            updated = {**conf, "enabled": _truthy(form.get(f"notify_{name}_enabled"))}
            for field in _NOTIFY_VALUE_FIELDS:
                clear_key = f"notify_{name}_{field}_clear"
                key = f"notify_{name}_{field}"
                if _truthy(form.get(clear_key)):
                    updated[field] = ""
                elif _has(form, key) and str(form[key]).strip():
                    updated[field] = str(form[key]).strip()
            port_key = f"notify_{name}_smtp_port"
            if _has(form, port_key):
                updated["smtp_port"] = int(form[port_key])
            notify[name] = updated
        patch["notify"] = notify
    return patch


def overlay_notify_from_form(form: dict, current: dict) -> dict:
    """Merge typed notify fields onto current settings without persisting.

    Blank secrets keep the saved values, matching save-settings behavior.
    """
    if not any(key == "save_notify" or str(key).startswith("notify_") for key in form):
        return current
    payload = dict(form)
    payload["save_notify"] = "1"
    notify = form_settings(payload, current).get("notify")
    if not notify:
        return current
    merged = dict(current)
    merged["notify"] = notify
    return merged
