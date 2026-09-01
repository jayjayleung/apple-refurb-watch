from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable

from apple_refurb_watch.db import Database
from apple_refurb_watch.notify import CHANNELS, NotifyError, send_channel
from apple_refurb_watch.parse import product_page_url

HOOK_CHANNEL = "hook"
HookFn = Callable[[dict, str, str, str | None], list[str]]
SendFn = Callable[[str, dict, dict[str, Any], str, str, str | None], str | None]


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


class OutboxWorker:
    """Lease and deliver persisted notifications outside scan transactions."""

    def __init__(
        self,
        db: Database,
        *,
        hook: HookFn | None = None,
        batch_size: int = 20,
        lease_seconds: int = 60,
        poll_interval: float = 5.0,
        worker_id: str | None = None,
        send_fn: SendFn | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        self.db = db
        self.hook = hook
        self.batch_size = max(1, int(batch_size))
        self.lease_seconds = max(1, int(lease_seconds))
        self.poll_interval = max(0.1, float(poll_interval))
        self.worker_id = worker_id or f"notify-{uuid.uuid4().hex}"
        self.send_fn = send_fn or self._send
        self.settings_override = settings
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _send(
        self,
        channel: str,
        conf: dict,
        settings: dict[str, Any],
        title: str,
        body: str,
        url: str | None,
    ) -> str | None:
        return _try_send(channel, conf, settings, title, body, url, self.hook)

    def run_once(self) -> int:
        self.db.release_expired_leases()
        # A unique token per claim prevents a late ACK from an expired attempt
        # from completing a newer attempt by the same worker process.
        lease_token = f"{self.worker_id}-{uuid.uuid4().hex}"
        rows = self.db.claim_pending_deliveries(
            limit=self.batch_size,
            lease_seconds=self.lease_seconds,
            lease_token=lease_token,
        )
        if not rows:
            return 0
        settings = self.settings_override or self.db.settings()
        sent = 0
        for row in rows:
            event_id = int(row["event_id"])
            channel = str(row["channel"])
            event = self.db.get_event(event_id)
            if not event:
                self.db.complete_delivery(
                    event_id,
                    channel,
                    lease_token=str(row.get("lease_token") or lease_token),
                    ok=False,
                    last_error="event missing",
                )
                continue
            title = _notify_title(self.db, event)
            body = str(event.get("message") or event.get("title") or "")
            url = product_page_url(event.get("sku"), event.get("url"))
            conf: dict[str, Any] = {}
            if self.hook is None:
                notify = settings.get("notify") or {}
                conf = dict(notify.get(channel) or {})
                if not conf.get("enabled"):
                    self.db.release_delivery(
                        event_id,
                        channel,
                        lease_token=str(row.get("lease_token") or lease_token),
                        retry_after=max(5.0, self.poll_interval),
                    )
                    continue
            error = self.send_fn(channel, conf, settings, title, body, url)
            acknowledged = self.db.complete_delivery(
                event_id,
                channel,
                lease_token=str(row.get("lease_token") or lease_token),
                ok=error is None,
                last_error=error,
                # Test hooks are intentionally deterministic and historically
                # retried on the next scan; real providers use exponential
                # backoff in the repository default.
                retry_after=0 if self.hook is not None and error is not None else None,
            )
            if error is None and acknowledged:
                sent += 1
        return sent

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    self.run_once()
                except Exception:  # noqa: BLE001
                    # A transient database/provider failure must not kill the
                    # worker; the lease will expire and be retried.
                    pass
                self._stop.wait(self.poll_interval)

        self._thread = threading.Thread(target=loop, name="arw-notify-outbox", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 8.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=max(0.1, float(timeout)))
        self._thread = None


def retry_pending_deliveries(db: Database, settings: dict[str, Any], hook: HookFn | None = None) -> int:
    # Keep the historical helper for CLI/tests while using the same lease and
    # backoff semantics as the long-lived worker.
    return OutboxWorker(db, hook=hook, settings=settings, poll_interval=0).run_once()


__all__ = [
    "OutboxWorker",
    "deliver_event",
    "enabled_channels",
    "retry_pending_deliveries",
]
