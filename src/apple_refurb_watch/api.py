from __future__ import annotations

import html
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from apple_refurb_watch.categories import CATEGORIES, listing_url
from apple_refurb_watch.db import Database
from apple_refurb_watch.fetch import fetch_html
from apple_refurb_watch.filters import (
    facet_groups,
    label_for,
    live_catalog_path,
    load_catalog,
    product_dims,
    prune_cascade_dims,
    restrict_dims,
    selected_dims,
    summarize_dims,
    sync_filter_catalog,
    user_catalog_path,
)
from apple_refurb_watch.match import matches_watch
from apple_refurb_watch.notify import NotifyError, send_all
from apple_refurb_watch.argv import is_frozen
from apple_refurb_watch.paths import write_runtime
from apple_refurb_watch.scanner import run_scan
from apple_refurb_watch.status_view import format_localtime, present_event_days, present_status

WEB_DIR = Path(__file__).parent / "web"
PAGE_SIZE = 24


class WatchIn(BaseModel):
    name: str = "未命名规则"
    enabled: bool = True
    mode: str = "condition"
    sku: str | None = None
    listing_key: str | None = None
    all_of: list[str] | str | None = None
    none_of: list[str] | str | None = None
    colors: list[str] | str | None = None
    min_ram_gb: int | None = None
    min_storage_gb: int | None = None
    min_price: float | None = None
    max_price: float | None = None
    dim_filters: dict[str, list[str]] | None = None


class WatchPatch(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    mode: str | None = None
    sku: str | None = None
    listing_key: str | None = None
    all_of: list[str] | str | None = None
    none_of: list[str] | str | None = None
    colors: list[str] | str | None = None
    min_ram_gb: int | None = Field(default=None)
    min_storage_gb: int | None = Field(default=None)
    min_price: float | None = Field(default=None)
    max_price: float | None = Field(default=None)
    dim_filters: dict[str, list[str]] | None = None


class SettingsPatch(BaseModel):
    interval_seconds: int | None = None
    bind_host: str | None = None
    bind_port: int | None = None
    lan_enabled: bool | None = None
    access_token: str | None = None
    listings: list[str] | None = None
    detail_delay_seconds: float | None = None
    close_window_keeps_daemon: bool | None = None
    listen_enabled: bool | None = None
    notify: dict[str, Any] | None = None


def thumb_url(url: str | None, width: int = 400) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    host = (parsed.netloc or "").lower()
    if "apple.com" not in host and "cdn-apple.com" not in host:
        return text
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "wid" not in query and "hei" not in query:
        return text
    query["wid"] = str(width)
    query["hei"] = str(width)
    query.setdefault("fmt", "jpeg")
    query.setdefault("qlt", "80")
    return urlunparse(parsed._replace(query=urlencode(query)))


def _templates() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(WEB_DIR / "templates")),
        autoescape=select_autoescape(["html"]),
        auto_reload=not is_frozen(),
    )
    env.globals["categories"] = CATEGORIES
    env.globals["dim_summary"] = summarize_dims
    env.globals["label_for"] = label_for
    env.filters["cny"] = lambda v: "" if v is None else f"{v:,.0f}"
    env.filters["gb"] = lambda v: "" if v is None else (f"{v // 1024}TB" if v >= 1024 and v % 1024 == 0 else f"{v}GB")
    env.filters["thumb"] = thumb_url
    env.filters["localtime"] = format_localtime
    return env


def create_app(db: Database | None = None, *, with_scheduler: bool = True) -> FastAPI:
    database = db or Database()
    jinja = _templates()
    scheduler = BackgroundScheduler()

    def reschedule() -> None:
        if not with_scheduler:
            return
        settings = database.settings()
        if not settings.get("listen_enabled", True):
            if scheduler.get_job("scan"):
                scheduler.remove_job("scan")
            return
        interval = max(60, int(settings.get("interval_seconds") or 300))
        scheduler.add_job(
            lambda: run_scan(database),
            "interval",
            seconds=interval,
            id="scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now() + timedelta(seconds=4),
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        settings = database.settings()
        write_runtime(
            {
                "pid": __import__("os").getpid(),
                "host": settings.get("bind_host") or "127.0.0.1",
                "port": settings.get("bind_port") or 8765,
                "url": _public_url(settings),
            }
        )
        if with_scheduler:
            reschedule()
            scheduler.start()
        yield
        if with_scheduler and scheduler.running:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="苹果官翻监听", lifespan=lifespan)
    app.state.db = database
    app.state.scheduler = scheduler
    app.state.reschedule = reschedule
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
    app.add_middleware(AuthMiddleware, db=database)

    def render(name: str, request: Request, **ctx: Any) -> HTMLResponse:
        settings = _public_settings(database.settings())
        status = database.scan_status()
        watch_enabled = database.count_watches(enabled=True)
        watch_total = database.count_watches()
        status_view = present_status(
            status,
            settings,
            in_stock=database.count_products(in_stock=True),
            watch_enabled=watch_enabled,
            watch_total=watch_total,
        )
        html_body = jinja.get_template(name).render(
            request=request,
            settings=settings,
            status=status,
            status_view=status_view,
            watch_count=watch_enabled,
            user_catalog_path=str(user_catalog_path()),
            live_catalog_path=str(live_catalog_path()),
            **ctx,
        )
        return HTMLResponse(html_body)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/status")
    def status() -> dict:
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

    @app.get("/api/filter-catalog")
    def api_filter_catalog() -> dict:
        catalog = load_catalog()
        return {
            "catalog": catalog,
            "user_catalog_path": str(user_catalog_path()),
            "live_catalog_path": str(live_catalog_path()),
        }

    @app.get("/api/listings")
    def api_listings(request: Request) -> dict:
        filters = _query_filters(request)
        items = _filter_products(database.list_products(in_stock=True), **filters)
        return {"items": items, "count": len(items)}

    @app.get("/api/watches")
    def api_watches() -> list:
        return database.list_watches()

    @app.post("/api/watches")
    def api_create_watch(payload: WatchIn) -> dict:
        return database.create_watch(payload.model_dump())

    @app.patch("/api/watches/{watch_id}")
    def api_patch_watch(watch_id: int, payload: WatchPatch) -> dict:
        data = payload.model_dump(exclude_unset=True)
        updated = database.update_watch(watch_id, data)
        if not updated:
            raise HTTPException(404, "规则不存在")
        return updated

    @app.delete("/api/watches/{watch_id}")
    def api_delete_watch(watch_id: int) -> dict:
        if not database.delete_watch(watch_id):
            raise HTTPException(404, "规则不存在")
        return {"ok": True}

    @app.post("/api/scan")
    def api_scan() -> dict:
        return run_scan(database)

    @app.get("/api/events")
    def api_events(limit: int = Query(80, ge=1, le=500)) -> list:
        return database.list_events(limit)

    @app.get("/api/settings")
    def api_settings() -> dict:
        data = database.settings()
        return _public_settings(data)

    @app.patch("/api/settings")
    def api_patch_settings(payload: SettingsPatch) -> dict:
        patch = payload.model_dump(exclude_unset=True)
        current = database.settings()
        if "access_token" in patch:
            token = str(patch.get("access_token") or "").strip()
            if token:
                patch["access_token"] = token
            else:
                patch.pop("access_token", None)
        if "listings" in patch and patch["listings"] is not None:
            patch["listings"] = _safe_listings(patch["listings"])
        if patch.get("lan_enabled") and not (patch.get("access_token") or current.get("access_token")):
            patch["access_token"] = secrets.token_urlsafe(16)
        if patch.get("lan_enabled"):
            patch.setdefault("bind_host", "0.0.0.0")
        if patch.get("lan_enabled") is False:
            patch.setdefault("bind_host", "127.0.0.1")
        updated = database.update_settings(patch)
        if "interval_seconds" in patch or "listen_enabled" in patch:
            reschedule()
        return _public_settings(updated)

    @app.post("/api/notify/test")
    def api_notify_test() -> dict:
        settings = database.settings()
        try:
            errors = send_all(settings, "官翻监听测试", "通知通道已接通。", "https://www.apple.com.cn/shop/refurbished")
        except NotifyError as exc:
            raise HTTPException(400, str(exc)) from exc
        if errors:
            return {"ok": False, "errors": errors}
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        stock = database.list_products(in_stock=True)
        filters = _query_filters(request)
        listing_only = _filter_products(
            stock,
            listing_key=filters["listing_key"],
            q=None,
            color=None,
            max_price=None,
            min_ram_gb=None,
            min_storage_gb=None,
            dim_filters={},
        )
        items = _filter_products(stock, **filters)
        hx_request = bool(request.headers.get("HX-Request"))
        hx_target = (request.headers.get("HX-Target") or "").lstrip("#")
        offset = _page_offset(request) if hx_request and hx_target == "product-grid" else 0
        total_count = len(items)
        page_items = items[offset : offset + PAGE_SIZE]
        has_more = offset + PAGE_SIZE < total_count
        ctx = {
            "items": page_items,
            "total_count": total_count,
            "q": filters["q"] or "",
            "listing_key": filters["listing_key"] or "",
            "color": filters["color"] or "",
            "max_price": filters["max_price"] if filters["max_price"] is not None else "",
            "min_ram_gb": filters["min_ram_gb"] if filters["min_ram_gb"] is not None else "",
            "min_storage_gb": filters["min_storage_gb"] if filters["min_storage_gb"] is not None else "",
            "facets": facet_groups(
                listing_only,
                filters["listing_key"],
                filters["dim_filters"],
                include_catalog=False,
                show_counts=True,
                refine=True,
            ),
            "selected_dims": filters["dim_filters"],
            "filter_chips": _filter_chips(request, filters),
            "has_more": has_more,
            "remaining": max(0, total_count - offset - len(page_items)),
            "more_url": _listings_path(request, offset + PAGE_SIZE) if has_more else "",
            "offset": offset,
            "oob_more": hx_target == "product-grid",
            "stock_count": len(stock),
        }
        if hx_request:
            if hx_target == "product-grid":
                return render("_product_more.html", request, **ctx)
            return render("_shop.html", request, **ctx)
        return render("listings.html", request, **ctx)

    @app.get("/watches", response_class=HTMLResponse)
    def watches_page(request: Request) -> HTMLResponse:
        stock = database.list_products(in_stock=True)
        watches = database.list_watches()
        for watch in watches:
            watch["in_stock_matches"] = sum(1 for item in stock if matches_watch(item, watch))
        return render(
            "watches.html",
            request,
            watches=watches,
            watch_facets=facet_groups(
                stock, "mac", {}, include_catalog=True, show_counts=True, cascade=True
            ),
        )

    @app.post("/watches", response_class=HTMLResponse)
    async def watches_create(request: Request) -> RedirectResponse:
        form = await request.form()
        database.create_watch(_form_watch(form))
        return RedirectResponse("/watches", status_code=303)

    @app.post("/watches/from-product", response_class=HTMLResponse)
    async def watch_from_product(request: Request) -> RedirectResponse:
        form = dict(await request.form())
        sku = str(form.get("sku") or "")
        mode = str(form.get("mode") or "condition")
        products = [p for p in database.list_products(in_stock=True) if p["sku"] == sku]
        if not products:
            raise HTTPException(404, "商品不在当前在售列表")
        product = products[0]
        if mode == "sku":
            database.create_watch(
                {
                    "name": f"SKU {sku}",
                    "mode": "sku",
                    "sku": sku,
                    "listing_key": product.get("listing_key"),
                }
            )
        else:
            dims = product_dims(product)
            dim_filters = {key: [value] for key, value in dims.items() if value}
            database.create_watch(
                {
                    "name": (product.get("title") or sku)[:40],
                    "mode": "condition",
                    "listing_key": product.get("listing_key"),
                    "dim_filters": dim_filters,
                    "max_price": product.get("price"),
                }
            )
        return RedirectResponse("/watches", status_code=303)

    @app.post("/watches/from-filters", response_class=HTMLResponse)
    async def watch_from_filters(request: Request) -> RedirectResponse:
        form = await request.form()
        listing_key = str(form.get("listing_key") or "").strip() or None
        dim_filters = restrict_dims(selected_dims(form), listing_key)
        q = str(form.get("q") or "").strip()
        payload = {
            "listing_key": listing_key,
            "all_of": [q] if q else [],
            "dim_filters": dim_filters,
            "max_price": _opt_number(str(form.get("max_price") or ""), float),
            "min_ram_gb": _opt_number(str(form.get("min_ram_gb") or ""), int),
            "min_storage_gb": _opt_number(str(form.get("min_storage_gb") or ""), int),
        }
        payload["name"] = _watch_name_from_filters(payload, q)
        database.create_watch({"mode": "condition", **payload})
        return RedirectResponse("/watches", status_code=303)

    @app.post("/watches/cascade", response_class=HTMLResponse)
    async def watch_cascade(request: Request) -> HTMLResponse:
        form = await request.form()
        stock = database.list_products(in_stock=True)
        return render("_watch_facets.html", request, facets=_watch_facet_groups(form, stock))

    @app.post("/watches/preview", response_class=HTMLResponse)
    async def watch_preview(request: Request) -> HTMLResponse:
        watch = _form_watch(await request.form())
        stock = database.list_products(in_stock=True)
        matched = sum(1 for item in stock if matches_watch(item, watch))
        if watch.get("mode") == "sku" and not watch.get("sku"):
            text = "填入 SKU 后保存，该货号上新会通知。"
        elif matched:
            text = f"当前 {matched} 件在售。保存后也会继续盯之后的上新。"
        else:
            text = "当前缺货。保存后，符合条件的上新会通知。"
        return HTMLResponse(text)

    @app.post("/watches/{watch_id}/toggle")
    async def watch_toggle(watch_id: int) -> RedirectResponse:
        watch = database.get_watch(watch_id)
        if not watch:
            raise HTTPException(404, "规则不存在")
        database.update_watch(watch_id, {"enabled": not watch["enabled"]})
        return RedirectResponse("/watches", status_code=303)

    @app.post("/watches/{watch_id}/delete")
    async def watch_delete(watch_id: int) -> RedirectResponse:
        database.delete_watch(watch_id)
        return RedirectResponse("/watches", status_code=303)

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, flash: str | None = None) -> HTMLResponse:
        return render("settings.html", request, flash=flash)

    @app.post("/settings")
    async def settings_save(request: Request) -> RedirectResponse:
        form = await request.form()
        payload = {key: form.get(key) for key in form.keys()}
        payload["listings"] = form.getlist("listings")
        patch = _form_settings(payload, database.settings())
        database.update_settings(patch)
        if "interval_seconds" in patch or "listen_enabled" in patch:
            reschedule()
        return RedirectResponse("/settings?flash=saved", status_code=303)

    @app.post("/settings/listen")
    async def settings_listen(request: Request) -> RedirectResponse:
        form = await request.form()
        enabled = str(form.get("enabled") or "") in {"1", "on", "true", "yes"}
        database.update_settings({"listen_enabled": enabled})
        reschedule()
        return RedirectResponse(_safe_next(str(form.get("next") or "/")), status_code=303)

    @app.post("/settings/sync-catalog")
    def settings_sync_catalog() -> RedirectResponse:
        try:
            sync_filter_catalog(fetch_html)
            return RedirectResponse("/settings?flash=catalog-ok", status_code=303)
        except Exception:  # noqa: BLE001
            return RedirectResponse("/settings?flash=catalog-fail", status_code=303)

    @app.post("/settings/scan")
    def settings_scan() -> RedirectResponse:
        run_scan(database)
        return RedirectResponse("/events", status_code=303)

    @app.post("/settings/notify-test")
    def settings_notify_test() -> RedirectResponse:
        try:
            send_all(database.settings(), "官翻监听测试", "通知通道已接通。", "https://www.apple.com.cn/shop/refurbished")
            return RedirectResponse("/settings?flash=notify-ok", status_code=303)
        except NotifyError:
            return RedirectResponse("/settings?flash=notify-fail", status_code=303)

    @app.get("/events", response_class=HTMLResponse)
    def events_page(request: Request) -> HTMLResponse:
        return render("events.html", request, event_days=present_event_days(database.list_events(120)))

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, error: str | None = None) -> HTMLResponse:
        html_body = jinja.get_template("login.html").render(request=request, error=error)
        return HTMLResponse(html_body)

    @app.post("/login")
    async def login_submit(request: Request) -> RedirectResponse:
        form = dict(await request.form())
        token = str(form.get("token") or "")
        expected = database.settings().get("access_token") or ""
        if not _token_ok(token, expected):
            return RedirectResponse("/login?error=1", status_code=303)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("arw_token", token, httponly=True, samesite="lax", max_age=30 * 24 * 3600)
        return response

    @app.exception_handler(HTTPException)
    async def http_exc(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/") or "application/json" in (request.headers.get("accept") or ""):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        if exc.status_code in {401, 403}:
            return RedirectResponse("/login")
        detail = html.escape(str(exc.detail))
        return HTMLResponse(f"<p>{detail}</p><p><a href='/'>返回</a></p>", status_code=exc.status_code)

    return app


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, db: Database) -> None:
        super().__init__(app)
        self.db = db

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not _origin_ok(request):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "拒绝跨站请求"}, status_code=403)
            return HTMLResponse("<p>拒绝跨站请求</p>", status_code=403)
        if path.startswith("/static") or path in {"/login", "/api/health"}:
            return await call_next(request)
        settings = self.db.settings()
        if not _needs_auth(request, settings):
            return await call_next(request)
        token = settings.get("access_token") or ""
        provided = (
            request.cookies.get("arw_token")
            or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            or request.headers.get("X-Token", "")
        )
        if token and _token_ok(provided, token):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "未授权"}, status_code=401)
        return RedirectResponse("/login")


def _token_ok(provided: str, expected: str) -> bool:
    if not expected or not provided:
        return False
    left = provided.encode("utf-8")
    right = expected.encode("utf-8")
    if len(left) != len(right):
        secrets.compare_digest(right, right)
        return False
    return secrets.compare_digest(left, right)


def _origin_ok(request: Request) -> bool:
    origin = request.headers.get("origin") or ""
    referer = request.headers.get("referer") or ""
    source = origin or referer
    if not source:
        return True
    incoming = (urlparse(source).netloc or "").lower()
    host = (request.headers.get("host") or "").lower()
    return bool(incoming) and incoming == host


def _needs_auth(request: Request, settings: dict) -> bool:
    if not settings.get("lan_enabled"):
        return False
    bind = settings.get("bind_host") or "127.0.0.1"
    if bind in {"127.0.0.1", "localhost", "::1"}:
        return False
    host = request.client.host if request.client else ""
    if host in {"127.0.0.1", "::1", "localhost"}:
        return False
    return bool(settings.get("access_token"))


def _public_url(settings: dict) -> str:
    host = settings.get("bind_host") or "127.0.0.1"
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = settings.get("bind_port") or 8765
    return f"http://{host}:{port}"


_SECRET_NOTIFY_KEYS = ("password", "bot_token", "sendkey", "token", "secret", "webhook", "url")


def _public_settings(settings: dict) -> dict:
    data = {
        key: settings.get(key)
        for key in (
            "interval_seconds",
            "bind_host",
            "bind_port",
            "lan_enabled",
            "listings",
            "detail_delay_seconds",
            "close_window_keeps_daemon",
            "listen_enabled",
        )
    }
    notify = {}
    for name, conf in (settings.get("notify") or {}).items():
        safe = dict(conf)
        for secret_key in _SECRET_NOTIFY_KEYS:
            if safe.get(secret_key):
                safe[secret_key + "_set"] = True
                safe[secret_key] = ""
        notify[name] = safe
    data["notify"] = notify
    data["access_token"] = ""
    data["access_token_set"] = bool(settings.get("access_token"))
    return data


def _safe_listings(keys: list[str]) -> list[str]:
    out: list[str] = []
    for key in keys:
        try:
            listing_url(str(key))
        except KeyError:
            continue
        out.append(str(key))
    return out or ["mac"]


def _page_offset(request: Request) -> int:
    try:
        return max(0, int(request.query_params.get("offset") or 0))
    except (TypeError, ValueError):
        return 0


def _listings_path(request: Request, offset: int) -> str:
    pairs = [(key, value) for key, value in request.query_params.multi_items() if key != "offset"]
    if offset:
        pairs.append(("offset", str(offset)))
    query = urlencode(pairs)
    return f"/?{query}" if query else "/"


def _omit_query(request: Request, drop_key: str, drop_value: str | None = None) -> str:
    pairs: list[tuple[str, str]] = []
    skipped = False
    for key, value in request.query_params.multi_items():
        if key == "offset":
            continue
        if key == drop_key:
            if drop_value is None:
                continue
            if value == drop_value and not skipped:
                skipped = True
                continue
        pairs.append((key, value))
    query = urlencode(pairs)
    return f"/?{query}" if query else "/"


def _filter_chips(request: Request, filters: dict[str, Any]) -> list[dict[str, str]]:
    chips: list[dict[str, str]] = []
    listing_key = filters.get("listing_key") or ""
    if listing_key:
        name = CATEGORIES[listing_key]["name"] if listing_key in CATEGORIES else listing_key
        chips.append({"label": name, "href": _omit_query(request, "listing_key")})
    for key, values in (filters.get("dim_filters") or {}).items():
        for value in values:
            chips.append({"label": label_for(key, value), "href": _omit_query(request, f"d_{key}", value)})
    if filters.get("q"):
        chips.append({"label": str(filters["q"]), "href": _omit_query(request, "q")})
    if filters.get("max_price") is not None:
        chips.append({"label": f"≤ ¥{int(filters['max_price']):,}", "href": _omit_query(request, "max_price")})
    if filters.get("min_ram_gb") is not None:
        chips.append({"label": f"内存 ≥ {filters['min_ram_gb']}GB", "href": _omit_query(request, "min_ram_gb")})
    if filters.get("min_storage_gb") is not None:
        chips.append({"label": f"硬盘 ≥ {filters['min_storage_gb']}GB", "href": _omit_query(request, "min_storage_gb")})
    return chips


def _watch_name_from_filters(payload: Mapping[str, Any], q: str = "") -> str:
    parts: list[str] = []
    listing_key = payload.get("listing_key")
    if listing_key and listing_key in CATEGORIES:
        parts.append(CATEGORIES[listing_key]["name"])
    parts.extend(summarize_dims(payload.get("dim_filters")))
    if q:
        parts.append(q)
    if payload.get("min_ram_gb"):
        parts.append(f"≥{payload['min_ram_gb']}GB 内存")
    if payload.get("min_storage_gb"):
        parts.append(f"≥{payload['min_storage_gb']}GB 硬盘")
    if payload.get("max_price") not in (None, ""):
        parts.append(f"≤ ¥{int(float(payload['max_price'])):,}")
    name = " · ".join(parts) if parts else "未命名规则"
    return name[:60]


def _query_filters(request: Request) -> dict[str, Any]:
    params = request.query_params
    listing_key = (params.get("listing_key") or "").strip() or None
    dim_filters = restrict_dims(selected_dims(params), listing_key)
    color = (params.get("color") or "").strip() or None
    return {
        "q": (params.get("q") or "").strip() or None,
        "listing_key": listing_key,
        "color": color,
        "max_price": _opt_number(params.get("max_price"), float),
        "min_ram_gb": _opt_number(params.get("min_ram_gb"), int),
        "min_storage_gb": _opt_number(params.get("min_storage_gb"), int),
        "dim_filters": dim_filters,
    }


def _safe_next(raw: str | None, fallback: str = "/") -> str:
    text = str(raw or "").strip()
    if not text:
        return fallback
    if "://" in text:
        parsed = urlparse(text)
        text = parsed.path + (("?" + parsed.query) if parsed.query else "")
    if not text.startswith("/") or text.startswith("//"):
        return fallback
    return text


def _opt_number(raw: str | None, caster):
    if raw in (None, ""):
        return None
    try:
        return caster(raw)
    except (TypeError, ValueError):
        return None


def _filter_products(
    items: list[dict],
    *,
    q: str | None,
    listing_key: str | None,
    color: str | None,
    max_price: float | None,
    min_ram_gb: int | None,
    min_storage_gb: int | None,
    dim_filters: dict | None = None,
) -> list[dict]:
    fake_watch = {
        "mode": "condition",
        "listing_key": listing_key or None,
        "all_of": [q] if q else [],
        "none_of": [],
        "colors": [color] if color else [],
        "max_price": max_price,
        "min_ram_gb": min_ram_gb,
        "min_storage_gb": min_storage_gb,
        "dim_filters": dim_filters or {},
    }
    return [item for item in items if matches_watch(item, fake_watch)]


def _watch_facet_groups(form: Any, stock: list) -> list[dict[str, Any]]:
    listing_key = str(form.get("listing_key") or "").strip() or None
    selected = prune_cascade_dims(listing_key, selected_dims(form), stock)
    return facet_groups(
        stock,
        listing_key,
        selected,
        include_catalog=True,
        show_counts=True,
        cascade=True,
    )


def _form_watch(form: Any) -> dict:
    def split(value: str) -> list[str]:
        return [p.strip() for p in value.replace("\n", ",").split(",") if p.strip()]

    def get(name: str, default: str = "") -> str:
        return str(form.get(name) or default)

    listing_key = get("listing_key") or None
    payload = {
        "name": get("name"),
        "enabled": True,
        "mode": get("mode") or "condition",
        "sku": get("sku") or None,
        "listing_key": listing_key,
        "all_of": split(get("all_of")),
        "none_of": split(get("none_of")),
        "colors": split(get("colors")),
        "min_ram_gb": get("min_ram_gb") or None,
        "min_storage_gb": get("min_storage_gb") or None,
        "min_price": get("min_price") or None,
        "max_price": get("max_price") or None,
        "dim_filters": restrict_dims(selected_dims(form), listing_key),
    }
    if not payload["name"]:
        if payload["mode"] == "sku" and payload["sku"]:
            payload["name"] = f"SKU {payload['sku']}"
        else:
            extra = " / ".join(payload["all_of"])
            payload["name"] = _watch_name_from_filters(payload, extra)
    return payload


def _form_settings(form: dict, current: dict) -> dict:
    listings = form.get("listings")
    if isinstance(listings, str):
        listing_keys = [listings]
    elif listings:
        listing_keys = list(listings)
    else:
        listing_keys = current.get("listings") or ["mac"]
    listing_keys = _safe_listings(listing_keys)
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
    elif lan and not current.get("access_token"):
        patch["access_token"] = secrets.token_urlsafe(16)
    notify = current.get("notify") or {}
    for name, conf in notify.items():
        enabled = form.get(f"notify_{name}_enabled") in {"1", "on", "true"}
        updated = {**conf, "enabled": enabled}
        for field in ("url", "sendkey", "token", "webhook", "secret", "bot_token", "chat_id", "smtp_host", "username", "password", "to"):
            key = f"notify_{name}_{field}"
            if key in form and str(form[key]).strip():
                updated[field] = str(form[key]).strip()
        if f"notify_{name}_smtp_port" in form and form[f"notify_{name}_smtp_port"]:
            updated["smtp_port"] = int(form[f"notify_{name}_smtp_port"])
        notify[name] = updated
    patch["notify"] = notify
    return patch
