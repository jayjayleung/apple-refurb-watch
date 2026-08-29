from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from apple_refurb_watch.filters import facet_groups
from apple_refurb_watch.status_view import present_event_days
from apple_refurb_watch.web.auth import token_ok
from apple_refurb_watch.web.listing import (
    PAGE_SIZE,
    filter_chips,
    filter_products,
    listings_path,
    page_offset,
    query_filters,
)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    database = request.app.state.db
    render = request.app.state.render
    stock = database.list_products(in_stock=True)
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
    hx_request = bool(request.headers.get("HX-Request"))
    hx_target = (request.headers.get("HX-Target") or "").lstrip("#")
    offset = page_offset(request) if hx_request and hx_target == "product-grid" else 0
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
        "filter_chips": filter_chips(request, filters),
        "has_more": has_more,
        "remaining": max(0, total_count - offset - len(page_items)),
        "more_url": listings_path(request, offset + PAGE_SIZE) if has_more else "",
        "offset": offset,
        "oob_more": hx_target == "product-grid",
        "stock_count": len(stock),
    }
    if hx_request:
        if hx_target == "product-grid":
            return render("_product_more.html", request, **ctx)
        return render("_shop.html", request, **ctx)
    return render("listings.html", request, **ctx)


@router.get("/events", response_class=HTMLResponse)
def events_page(request: Request) -> HTMLResponse:
    return request.app.state.render(
        "events.html", request, event_days=present_event_days(request.app.state.db.list_events(120))
    )


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
