from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Query, Request

from apple_refurb_watch.filters import live_catalog_path, load_catalog, user_catalog_path
from apple_refurb_watch.notify import NotifyError, send_test
from apple_refurb_watch.scanner import run_scan
from apple_refurb_watch.status_view import present_status
from apple_refurb_watch.web.listing import filter_products, query_filters
from apple_refurb_watch.web.schemas import SettingsPatch, WatchIn, WatchPatch
from apple_refurb_watch.web.settings_public import public_settings, safe_listings

router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    return {"ok": True}


@router.get("/api/status")
def status(request: Request) -> dict:
    database = request.app.state.db
    settings = database.settings()
    data = database.scan_status()
    watch_enabled = database.count_watches(enabled=True)
    watch_total = database.count_watches()
    data["settings"] = {
        k: settings[k]
        for k in ("interval_seconds", "bind_host", "bind_port", "lan_enabled", "listings", "listen_enabled")
    }
    data["watch_count"] = watch_enabled
    data["watch_total"] = watch_total
    data["in_stock"] = database.count_products(in_stock=True)
    data["view"] = present_status(
        data,
        settings,
        in_stock=data["in_stock"],
        watch_enabled=watch_enabled,
        watch_total=watch_total,
    )
    return data


@router.get("/api/filter-catalog")
def api_filter_catalog() -> dict:
    catalog = load_catalog()
    return {
        "catalog": catalog,
        "user_catalog_path": str(user_catalog_path()),
        "live_catalog_path": str(live_catalog_path()),
    }


@router.get("/api/listings")
def api_listings(request: Request) -> dict:
    database = request.app.state.db
    filters = query_filters(request)
    items = filter_products(database.list_products(in_stock=True), **filters)
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


@router.get("/api/settings")
def api_settings(request: Request) -> dict:
    return public_settings(request.app.state.db.settings())


@router.patch("/api/settings")
def api_patch_settings(request: Request, payload: SettingsPatch) -> dict:
    database = request.app.state.db
    patch = payload.model_dump(exclude_unset=True)
    current = database.settings()
    if "access_token" in patch:
        token = str(patch.get("access_token") or "").strip()
        if token:
            patch["access_token"] = token
        else:
            patch.pop("access_token", None)
    if "listings" in patch and patch["listings"] is not None:
        patch["listings"] = safe_listings(patch["listings"])
    if patch.get("lan_enabled") and not (patch.get("access_token") or current.get("access_token")):
        patch["access_token"] = secrets.token_urlsafe(16)
    if patch.get("lan_enabled"):
        patch.setdefault("bind_host", "0.0.0.0")
    if patch.get("lan_enabled") is False:
        patch.setdefault("bind_host", "127.0.0.1")
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
