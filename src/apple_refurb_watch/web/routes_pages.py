from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from apple_refurb_watch.categories import canonical_shop_listing_key, shop_families_for
from apple_refurb_watch.db import EVENT_KEEP
from apple_refurb_watch.filters import facet_groups
from apple_refurb_watch.listing import filter_products, products_in_listen_scope, shop_listings_url, sort_products
from apple_refurb_watch.status_view import filter_event_days, paginate_event_days, present_event_days
from apple_refurb_watch.web.auth import token_ok
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
    database = request.app.state.db
    kind = (request.query_params.get("kind") or "all").strip() or "all"
    digest = _event_digest(request.query_params)
    try:
        page = int(request.query_params.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    thumbs = {
        str(item.get("sku") or ""): item.get("image_url")
        for item in database.list_products()
        if item.get("sku") and item.get("image_url")
    }
    watch_names = {int(item["id"]): str(item.get("name") or "") for item in database.list_watches() if item.get("id")}
    days = filter_event_days(
        present_event_days(database.list_events(EVENT_KEEP), collapse_scans=digest, watch_names=watch_names),
        kind,
    )
    paged = paginate_event_days(days, page, by_day=digest)
    for day in paged["event_days"]:
        for event in day["entries"]:
            sku = str(event.get("sku") or "")
            if sku and thumbs.get(sku):
                event["image_url"] = thumbs[sku]
    return {
        **paged,
        "event_kind": kind,
        "event_digest": digest,
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
    stock = products_in_listen_scope(database.list_products(in_stock=True), listings)
    filters = query_filters(request)
    listing_only = filter_products(
        stock,
        listing_key=filters["listing_key"],
        q=None,
        color=None,
        max_price=None,
        min_ram_gb=None,
        min_storage_gb=None,
        dim_filters={},
    )
    items = filter_products(stock, **filters)
    items = sort_products(items, request.query_params.get("sort"))
    hx_request = bool(request.headers.get("HX-Request"))
    hx_target = (request.headers.get("HX-Target") or "").lstrip("#")
    offset = page_offset(request) if hx_request and hx_target == "product-grid" else 0
    total_count = len(items)
    page_items = items[offset : offset + PAGE_SIZE]
    has_more = offset + PAGE_SIZE < total_count
    families = shop_families_for(listings)
    ctx = {
        "items": page_items,
        "total_count": total_count,
        "sort": (request.query_params.get("sort") or "price").strip() or "price",
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
            include_catalog=True,
            include_chip=False,
            include_cores=False,
            show_counts=True,
            refine=True,
        ),
        "selected_dims": filters["dim_filters"],
        "filter_chips": filter_chips(request, filters),
        "has_more": has_more,
        "remaining": max(0, total_count - offset - len(page_items)),
        "more_url": listings_path(request, offset + PAGE_SIZE) if has_more else "",
        "offset": offset,
        "oob_more": hx_target == "product-grid",
        "stock_count": len(stock),
        "active_families": families,
        "show_shop_all": len(families) > 1,
    }
    if hx_request:
        if hx_target == "product-grid":
            return render("_product_more.html", request, **ctx)
        return render("_shop.html", request, **ctx)
    return render("listings.html", request, **ctx)


@router.get("/events", response_class=HTMLResponse)
def events_page(request: Request) -> HTMLResponse:
    ctx = _event_context(request)
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
    token = str(form.get("token") or "")
    expected = request.app.state.db.settings().get("access_token") or ""
    if not token_ok(token, expected):
        return RedirectResponse("/login?error=1", status_code=303)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("arw_token", token, httponly=True, samesite="lax", max_age=30 * 24 * 3600)
    return response
