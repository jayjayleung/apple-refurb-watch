from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from apple_refurb_watch.fetch import fetch_html
from apple_refurb_watch.filters import live_catalog_path, load_catalog, sync_filter_catalog, user_catalog_path
from apple_refurb_watch.listing import filter_products, listing_filters, products_in_listen_scope, sort_products
from apple_refurb_watch.notify import NotifyError, send_test
from apple_refurb_watch.scanner import run_scan
from apple_refurb_watch.settings import normalize_settings_patch, public_settings
from apple_refurb_watch.status_view import load_status
from apple_refurb_watch.web.schemas import SettingsPatch, WatchIn, WatchPatch

router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    return {"ok": True}


@router.get("/api/status")
def status(request: Request) -> dict:
    return load_status(request.app.state.db)


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
    database = request.app.state.db
    listings = database.settings().get("listings")
    filters = listing_filters(request.query_params)
    stock = products_in_listen_scope(database.list_products(in_stock=True), listings)
    items = sort_products(filter_products(stock, **filters), request.query_params.get("sort"))
    return {"items": items, "count": len(items)}


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
def api_events(request: Request, limit: int = Query(80, ge=1, le=500)) -> list:
    return request.app.state.db.list_events(limit)


@router.delete("/api/events")
def api_clear_events(request: Request) -> dict:
    deleted = request.app.state.db.clear_events()
    return {"ok": True, "deleted": deleted}


@router.get("/api/settings")
def api_settings(request: Request) -> dict:
    return public_settings(request.app.state.db.settings())


@router.patch("/api/settings")
def api_patch_settings(request: Request, payload: SettingsPatch) -> dict:
    database = request.app.state.db
    patch = normalize_settings_patch(payload.model_dump(exclude_unset=True), database.settings())
    updated = database.update_settings(patch)
    if "interval_seconds" in patch or "listen_enabled" in patch:
        request.app.state.reschedule()
    return public_settings(updated)


@router.post("/api/notify/test")
def api_notify_test(request: Request) -> dict:
    try:
        errors = send_test(request.app.state.db.settings())
    except NotifyError as exc:
        raise HTTPException(400, str(exc)) from exc
    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True}
