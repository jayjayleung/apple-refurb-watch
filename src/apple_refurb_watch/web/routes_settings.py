from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from apple_refurb_watch.fetch import fetch_html
from apple_refurb_watch.filters import sync_filter_catalog
from apple_refurb_watch.notify import CHANNELS, NotifyError, send_test
from apple_refurb_watch.web.settings_public import form_settings, safe_next

router = APIRouter()


def _safe_channel(raw: str | None) -> str | None:
    name = str(raw or "").strip()
    return name if name in CHANNELS else None


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, flash: str | None = None, channel: str | None = None) -> HTMLResponse:
    return request.app.state.render(
        "settings.html",
        request,
        flash=flash,
        channel=_safe_channel(channel),
        revealed_token=None,
    )


@router.post("/settings", response_model=None)
async def settings_save(request: Request) -> Response:
    form = await request.form()
    payload = {key: form.get(key) for key in form.keys()}
    database = request.app.state.db
    before = database.settings()
    patch = form_settings(payload, before)
    updated = database.update_settings(patch)
    if "interval_seconds" in patch or "listen_enabled" in patch:
        request.app.state.reschedule()
    generated = ""
    typed = str(payload.get("access_token") or "").strip()
    if patch.get("lan_enabled") and not before.get("access_token") and updated.get("access_token") and not typed:
        generated = str(updated.get("access_token") or "")
    if generated:
        return request.app.state.render(
            "settings.html",
            request,
            flash="lan-token",
            channel=None,
            revealed_token=generated,
        )
    return RedirectResponse("/settings?flash=saved", status_code=303)


@router.post("/settings/listen")
async def settings_listen(request: Request) -> RedirectResponse:
    form = await request.form()
    enabled = str(form.get("enabled") or "") in {"1", "on", "true", "yes"}
    request.app.state.db.update_settings({"listen_enabled": enabled})
    request.app.state.reschedule()
    return RedirectResponse(safe_next(str(form.get("next") or "/")), status_code=303)


@router.post("/settings/sync-catalog")
def settings_sync_catalog() -> RedirectResponse:
    try:
        sync_filter_catalog(fetch_html)
        return RedirectResponse("/settings?flash=catalog-ok", status_code=303)
    except Exception:  # noqa: BLE001
        return RedirectResponse("/settings?flash=catalog-fail", status_code=303)


@router.post("/settings/scan")
async def settings_scan(request: Request) -> RedirectResponse:
    """Queue a manual scan without holding the browser request open."""

    service = request.app.state.scan_service
    submit = getattr(service, "submit", None)
    if callable(submit):
        # The reservation is small, but run it off the event loop as the
        # service owns a synchronous SQLite connection.
        result = await run_in_threadpool(submit)
        if not isinstance(result, dict) or not result.get("accepted", True):
            return RedirectResponse("/events?flash=scan-busy", status_code=303)
        try:
            run_id = int(result.get("scan_run_id") or result.get("id"))
        except (TypeError, ValueError):
            return RedirectResponse("/events?flash=scan-queued", status_code=303)
        return RedirectResponse(
            f"/events?flash=scan-queued&scan_run_id={run_id}",
            status_code=303,
        )

    # Keep lightweight integrations that inject the pre-resource service
    # working while they migrate.  The real service above always takes the
    # asynchronous path.
    run_once = getattr(service, "run_once", None)
    if not callable(run_once):
        return RedirectResponse("/events?flash=scan-busy", status_code=303)
    result = await run_in_threadpool(run_once)
    if isinstance(result, dict) and result.get("message") == "已有扫描在进行":
        return RedirectResponse("/events?flash=scan-busy", status_code=303)
    return RedirectResponse("/events?flash=scan-done", status_code=303)


@router.post("/settings/notify-test")
async def settings_notify_test(request: Request) -> RedirectResponse:
    form = await request.form()
    channel = _safe_channel(str(form.get("channel") or ""))
    suffix = f"&channel={channel}" if channel else ""
    try:
        send_test(request.app.state.db.settings(), channel=channel)
        return RedirectResponse(f"/settings?flash=notify-ok{suffix}", status_code=303)
    except NotifyError:
        return RedirectResponse(f"/settings?flash=notify-fail{suffix}", status_code=303)
