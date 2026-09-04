from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from apple_refurb_watch.fetch import fetch_html
from apple_refurb_watch.filters import live_catalog_path, load_catalog, sync_filter_catalog, user_catalog_path
from apple_refurb_watch.listing import listing_filters
from apple_refurb_watch.notify import NotifyError, send_test
from apple_refurb_watch.settings import SettingsValueError, public_settings
from apple_refurb_watch.usecases import health_payload, list_shop, patch_settings, public_settings_view, public_status
from apple_refurb_watch.web.schemas import AutostartPatch, NotifyTestIn, SettingsPatch, WatchIn, WatchPatch

router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    return health_payload()


@router.get("/api/update")
def api_update() -> dict:
    from apple_refurb_watch.update_check import latest_release_info

    return latest_release_info()


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
    except Exception as exc:
        raise HTTPException(502, f"同步筛选词条失败: {exc}") from exc
    return {
        "ok": True,
        "user_catalog_path": str(user_catalog_path()),
        "live_catalog_path": str(live_catalog_path()),
    }


@router.get("/api/listings")
def api_listings(request: Request) -> dict:
    filters = listing_filters(request.query_params)
    try:
        limit = min(500, max(1, int(request.query_params.get("limit") or 500)))
    except (TypeError, ValueError):
        limit = 500
    try:
        offset = max(0, int(request.query_params.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0
    result = list_shop(
        request.app.state.db,
        filters,
        request.query_params.get("sort"),
        offset=offset,
        page_size=limit,
    )
    return {
        "items": result["items"],
        "count": result["total_count"],
        "offset": result["offset"],
        "limit": limit,
        "has_more": result["has_more"],
    }


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
    return request.app.state.scan_service.run_once()


@router.post("/api/scans")
def api_scans_create(request: Request):
    """Queue a scan and return its durable run resource.

    ``ScanService.submit`` is used by the real application.  The synchronous
    fallback keeps lightweight integrations that inject an older service
    object compatible while they migrate to the run-resource API.
    """

    service = request.app.state.scan_service
    submit = getattr(service, "submit", None)
    if callable(submit):
        result = submit()
        if not isinstance(result, dict):
            result = {"accepted": True, "ok": True, "result": result}
        if not result.get("accepted", True):
            raise HTTPException(409, result.get("message") or "已有扫描在进行")
        headers = {}
        try:
            run_id = int(result.get("scan_run_id") or result.get("id"))
        except (TypeError, ValueError):
            run_id = 0
        if run_id > 0:
            headers["Location"] = f"/api/scans/{run_id}"
        return JSONResponse(result, status_code=202, headers=headers)
    result = service.run_once()
    if not isinstance(result, dict):
        result = {"ok": True, "result": result}
    result.setdefault("accepted", True)
    result.setdefault("status", result.get("scan_status") or "succeeded")
    return result


@router.get("/api/scans")
def api_scans(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
) -> list:
    return request.app.state.db.list_scan_runs(limit)


@router.get("/api/scans/{run_id}")
def api_scan_run(request: Request, run_id: int) -> dict:
    run = request.app.state.db.get_scan_run(run_id)
    if not run:
        raise HTTPException(404, "扫描记录不存在")
    return run


@router.get("/api/events")
def api_events(
    request: Request,
    limit: int = Query(80, ge=1, le=500),
    after_id: int | None = Query(None, ge=0),
    type: str | None = Query(None),
) -> list:
    rows = request.app.state.db.list_events(limit, after_id=after_id, type=type)
    names = {
        int(item["id"]): str(item.get("name") or "")
        for item in request.app.state.db.list_watches()
        if item.get("id")
    }
    decorated = []
    for row in rows:
        item = dict(row)
        watch_id = item.get("watch_id")
        try:
            item["watch_name"] = names.get(int(watch_id)) if watch_id is not None else None
        except (TypeError, ValueError):
            item["watch_name"] = None
        decorated.append(item)
    return decorated


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
    try:
        updated = patch_settings(database, patch)
    except SettingsValueError as exc:
        raise HTTPException(400, str(exc)) from exc
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
        except Exception as exc:
            raise HTTPException(400, "JSON 无法解析") from exc
        if isinstance(body, dict):
            try:
                payload = NotifyTestIn.model_validate(body)
            except Exception as exc:
                raise HTTPException(400, "请求体无效") from exc
            channel = payload.channel
        elif body is not None:
            raise HTTPException(400, "请求体必须是对象")
    elif content_type.startswith("multipart/") or content_type.startswith("application/x-www-form-urlencoded"):
        try:
            form = await request.form()
        except Exception as exc:
            raise HTTPException(400, "表单无法解析") from exc
        channel = form.get("channel")
    channel = channel or request.query_params.get("channel")

    def work():
        return send_test(request.app.state.db.settings(), channel)

    try:
        errors = await run_in_threadpool(work)
    except NotifyError as exc:
        raise HTTPException(400, str(exc)) from exc
    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True}
