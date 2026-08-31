from __future__ import annotations

from typing import Any, Callable

from apple_refurb_watch.db import Database
from apple_refurb_watch.notify import CHANNELS, NotifyError, send_channel

HOOK_CHANNEL = "hook"
HookFn = Callable[[dict, str, str, str | None], list[str]]


def enabled_channels(settings: dict[str, Any], hook: HookFn | None = None) -> list[tuple[str, dict]]:
    if hook is not None:
        return [(HOOK_CHANNEL, {})]
    items: list[tuple[str, dict]] = []
    for name, conf in (settings.get("notify") or {}).items():
        if isinstance(conf, dict) and conf.get("enabled") and name in CHANNELS:
            items.append((name, conf))
    return items


def _notify_title(db: Database, event: dict) -> str:
    watch_id = event.get("watch_id")
    if watch_id:
        watch = db.get_watch(int(watch_id))
        if watch and watch.get("name"):
            return f"官翻上线：{watch['name']}"
    return str(event.get("title") or "官翻上线")


def _try_send(
    channel: str,
    conf: dict,
    settings: dict[str, Any],
    title: str,
    body: str,
    url: str | None,
    hook: HookFn | None,
) -> str | None:
    try:
        if hook is not None and channel == HOOK_CHANNEL:
            errors = hook(settings, title, body, url) or []
            return "; ".join(str(item) for item in errors) if errors else None
        send_channel(channel, conf, title, body, url)
        return None
    except NotifyError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def deliver_event(
    db: Database,
    event_id: int,
    settings: dict[str, Any],
    title: str,
    body: str,
    url: str | None,
    hook: HookFn | None = None,
) -> int:
    channels = enabled_channels(settings, hook)
    if not channels:
        return 0
    sent = 0
    for name, conf in channels:
        db.enqueue_delivery(event_id, name)
        error = _try_send(name, conf, settings, title, body, url, hook)
        db.mark_delivery(event_id, name, ok=error is None, last_error=error)
        if error is None:
            sent += 1
    return sent


def retry_pending_deliveries(db: Database, settings: dict[str, Any], hook: HookFn | None = None) -> int:
    sent = 0
    for row in db.list_pending_deliveries():
        event = db.get_event(int(row["event_id"]))
        if not event:
            db.mark_delivery(int(row["event_id"]), row["channel"], ok=False, last_error="event missing")
            continue
        title = _notify_title(db, event)
        body = str(event.get("message") or event.get("title") or "")
        url = event.get("url")
        conf = {}
        if hook is None:
            notify = settings.get("notify") or {}
            conf = dict(notify.get(row["channel"]) or {})
            if not conf.get("enabled"):
                continue
        error = _try_send(row["channel"], conf, settings, title, body, url, hook)
        db.mark_delivery(int(row["event_id"]), row["channel"], ok=error is None, last_error=error)
        if error is None:
            sent += 1
    return sent
