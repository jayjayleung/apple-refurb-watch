from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from apple_refurb_watch.fetch import fetch_html
from apple_refurb_watch.filters import live_catalog_path, load_catalog, sync_filter_catalog, user_catalog_path
from apple_refurb_watch.listing import listing_filters
from apple_refurb_watch.notify import NotifyError, send_test
from apple_refurb_watch.scanner import run_scan
from apple_refurb_watch.settings import public_settings
from apple_refurb_watch.usecases import health_payload, list_shop, patch_settings, public_settings_view, public_status
from apple_refurb_watch.web.schemas import AutostartPatch, NotifyTestIn, SettingsPatch, WatchIn, WatchPatch

router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    return health_payload()


@router.get("/api/status")
def status(request: Request) -> dict:
    return public_status(request.app.state.db)


@router.get("/api/filter-catalog")
def api_filter_catalog() -> dict:
    catalog = load_catalog()
    return {
        "catalog": catalog,
        "user_catalog_path": str(user_catalog_path()),
        "live_catalog_path": str(live_catalog_path()),
    }


@router.post("/api/filter-catalog/sync")
def api_sync_catalog() -> dict:
    try:
        sync_filter_catalog(fetch_html)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"同步筛选词条失败: {exc}") from exc
    return {
        "ok": True,
        "user_catalog_path": str(user_catalog_path()),
        "live_catalog_path": str(live_catalog_path()),
    }


@router.get("/api/listings")
def api_listings(request: Request) -> dict:
    filters = listing_filters(request.query_params)
    result = list_shop(request.app.state.db, filters, request.query_params.get("sort"), page_size=None)
    return {"items": result["all_items"], "count": result["total_count"]}


@router.get("/api/watches")
def api_watches(request: Request) -> list:
    return request.app.state.db.list_watches()


@router.post("/api/watches")
def api_create_watch(request: Request, payload: WatchIn) -> dict:
    return request.app.state.db.create_watch(payload.model_dump())


@router.patch("/api/watches/{watch_id}")
def api_patch_watch(request: Request, watch_id: int, payload: WatchPatch) -> dict:
    data = payload.model_dump(exclude_unset=True)
    updated = request.app.state.db.update_watch(watch_id, data)
    if not updated:
        raise HTTPException(404, "规则不存在")
    return updated


@router.delete("/api/watches/{watch_id}")
def api_delete_watch(request: Request, watch_id: int) -> dict:
    if not request.app.state.db.delete_watch(watch_id):
        raise HTTPException(404, "规则不存在")
    return {"ok": True}


@router.post("/api/scan")
def api_scan(request: Request) -> dict:
    return run_scan(request.app.state.db)


@router.get("/api/events")
def api_events(
    request: Request,
    limit: int = Query(80, ge=1, le=500),
    after_id: int | None = Query(None, ge=0),
    type: str | None = Query(None),
) -> list:
    return request.app.state.db.list_events(limit, after_id=after_id, type=type)


@router.delete("/api/events")
def api_clear_events(request: Request) -> dict:
    deleted = request.app.state.db.clear_events()
    return {"ok": True, "deleted": deleted}


@router.get("/api/settings")
def api_settings(request: Request) -> dict:
    return public_settings_view(request.app.state.db)


@router.patch("/api/settings")
def api_patch_settings(request: Request, payload: SettingsPatch) -> dict:
    database = request.app.state.db
    patch = payload.model_dump(exclude_unset=True)
    updated = patch_settings(database, patch)
    if "interval_seconds" in patch or "listen_enabled" in patch:
        request.app.state.reschedule()
    return public_settings(updated)


@router.get("/api/autostart")
def api_autostart_get() -> dict:
    from apple_refurb_watch.service import autostart_status

    return autostart_status(desktop=False)


@router.post("/api/autostart")
def api_autostart_set(payload: AutostartPatch) -> dict:
    from apple_refurb_watch.service import set_autostart

    return set_autostart(payload.enabled, desktop=False)


@router.post("/api/notify/test")
async def api_notify_test(request: Request) -> dict:
    channel = None
    content_type = (request.headers.get("content-type") or "").lower()
    if content_type.startswith("application/json"):
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = None
        if isinstance(body, dict):
            channel = body.get("channel")
        elif body is not None:
            payload = NotifyTestIn.model_validate(body)
            channel = payload.channel
    channel = channel or request.query_params.get("channel")
    try:
        errors = send_test(request.app.state.db.settings(), channel=channel)
    except NotifyError as exc:
        raise HTTPException(400, str(exc)) from exc
    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True}