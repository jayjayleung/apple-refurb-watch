from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from apple_refurb_watch.categories import canonical_shop_listing_key
from apple_refurb_watch.listing import shop_listings_url
from apple_refurb_watch.usecases import list_shop, present_events
from apple_refurb_watch.web.auth import clear_session_cookie, set_session_cookie, token_ok
from apple_refurb_watch.web.listing import (
    PAGE_SIZE,
    filter_chips,
    listings_path,
    page_offset,
    query_filters,
)

router = APIRouter()


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def events_url(*, page: int = 1, digest: bool = True, kind: str = "all") -> str:
    pairs: list[tuple[str, str]] = []
    if kind and kind != "all":
        pairs.append(("kind", kind))
    if not digest:
        pairs.append(("all", "1"))
    if page > 1:
        pairs.append(("page", str(page)))
    query = urlencode(pairs)
    return f"/events?{query}" if query else "/events"


def _event_digest(params) -> bool:
    if _truthy(params.get("all")):
        return False
    raw = params.get("digest")
    if raw is None or str(raw).strip() == "":
        return True
    return _truthy(raw)


def _event_context(request: Request) -> dict:
    kind = (request.query_params.get("kind") or "all").strip() or "all"
    digest = _event_digest(request.query_params)
    try:
        page = int(request.query_params.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    paged = present_events(request.app.state.db, digest=digest, kind=kind, page=page)
    scan_run_id = None
    try:
        raw_run_id = request.query_params.get("scan_run_id")
        if raw_run_id:
            parsed_run_id = int(raw_run_id)
            if parsed_run_id > 0:
                scan_run_id = parsed_run_id
    except (TypeError, ValueError):
        scan_run_id = None
    return {
        **paged,
        "flash": request.query_params.get("flash") or "",
        "scan_run_id": scan_run_id,
        "events_url_all": events_url(digest=False, kind=kind),
        "events_url_digest": events_url(digest=True, kind=kind),
        "events_url_prev": events_url(page=paged["event_page"] - 1, digest=digest, kind=kind),
        "events_url_next": events_url(page=paged["event_page"] + 1, digest=digest, kind=kind),
    }


@router.get("/", response_class=HTMLResponse, response_model=None)
def home(request: Request) -> HTMLResponse | RedirectResponse:
    database = request.app.state.db
    render = request.app.state.render
    listings = database.settings().get("listings")
    requested = (request.query_params.get("listing_key") or "").strip()
    canonical = canonical_shop_listing_key(requested, listings)
    if requested != canonical:
        sort = (request.query_params.get("sort") or "").strip()
        return RedirectResponse(shop_listings_url(canonical, sort or None), status_code=302)
    filters = query_filters(request)
    hx_request = bool(request.headers.get("HX-Request"))
    hx_target = (request.headers.get("HX-Target") or "").lstrip("#")
    offset = page_offset(request) if hx_request and hx_target == "product-grid" else 0
    shop = list_shop(database, filters, request.query_params.get("sort"), offset=offset, page_size=PAGE_SIZE)
    ctx = {
        "items": shop["items"],
        "total_count": shop["total_count"],
        "sort": shop["sort"],
        "q": filters["q"] or "",
        "listing_key": filters["listing_key"] or "",
        "color": filters["color"] or "",
        "max_price": filters["max_price"] if filters["max_price"] is not None else "",
        "min_ram_gb": filters["min_ram_gb"] if filters["min_ram_gb"] is not None else "",
        "min_storage_gb": filters["min_storage_gb"] if filters["min_storage_gb"] is not None else "",
        "facets": shop["facets"],
        "selected_dims": shop["selected_dims"],
        "filter_chips": filter_chips(request, filters),
        "has_more": shop["has_more"],
        "remaining": shop["remaining"],
        "more_url": listings_path(request, offset + PAGE_SIZE) if shop["has_more"] else "",
        "offset": shop["offset"],
        "oob_more": hx_target == "product-grid",
        "stock_count": shop["stock_count"],
        "active_families": shop["active_families"],
        "show_shop_all": shop["show_shop_all"],
    }
    if hx_request:
        if hx_target == "product-grid":
            return render("_product_more.html", request, **ctx)
        return render("_shop.html", request, **ctx)
    return render("listings.html", request, **ctx)


@router.get("/events", response_class=HTMLResponse)
def events_page(request: Request) -> HTMLResponse:
    ctx = _event_context(request)
    hx_request = bool(request.headers.get("HX-Request"))
    hx_target = (request.headers.get("HX-Target") or "").lstrip("#")
    if hx_request and hx_target == "event-feed":
        return request.app.state.render("_event_feed.html", request, **ctx)
    return request.app.state.render("events.html", request, **ctx)


@router.post("/events/clear")
def events_clear(request: Request) -> RedirectResponse:
    request.app.state.db.clear_events()
    return RedirectResponse("/events", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str | None = None) -> HTMLResponse:
    html_body = request.app.state.jinja.get_template("login.html").render(request=request, error=error)
    return HTMLResponse(html_body)


@router.post("/login")
async def login_submit(request: Request) -> RedirectResponse:
    form = dict(await request.form())

    def work() -> RedirectResponse:
        token = str(form.get("token") or "")
        expected = request.app.state.db.settings().get("access_token") or ""
        if not token_ok(token, expected):
            return RedirectResponse("/login?error=1", status_code=303)
        response = RedirectResponse("/", status_code=303)
        set_session_cookie(response, expected, secure=request.url.scheme == "https")
        return response

    return await run_in_threadpool(work)


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookie(response)
    return response
