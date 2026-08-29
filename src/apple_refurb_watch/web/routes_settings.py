from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from apple_refurb_watch.fetch import fetch_html
from apple_refurb_watch.filters import sync_filter_catalog
from apple_refurb_watch.notify import NotifyError, send_test
from apple_refurb_watch.scanner import run_scan
from apple_refurb_watch.web.settings_public import form_settings, safe_next

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, flash: str | None = None) -> HTMLResponse:
    return request.app.state.render("settings.html", request, flash=flash)


@router.post("/settings")
async def settings_save(request: Request) -> RedirectResponse:
    form = await request.form()
    payload = {key: form.get(key) for key in form.keys()}
    payload["listings"] = form.getlist("listings")
    database = request.app.state.db
    patch = form_settings(payload, database.settings())
    database.update_settings(patch)
    if "interval_seconds" in patch or "listen_enabled" in patch:
        request.app.state.reschedule()
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
def settings_scan(request: Request) -> RedirectResponse:
    run_scan(request.app.state.db)
    return RedirectResponse("/events", status_code=303)


@router.post("/settings/notify-test")
def settings_notify_test(request: Request) -> RedirectResponse:
    try:
        send_test(request.app.state.db.settings())
        return RedirectResponse("/settings?flash=notify-ok", status_code=303)
    except NotifyError:
        return RedirectResponse("/settings?flash=notify-fail", status_code=303)
