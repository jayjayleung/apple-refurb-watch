from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from apple_refurb_watch.filters import facet_groups
from apple_refurb_watch.match import matches_watch
from apple_refurb_watch.watches import (
    decorate_watches,
    form_watch,
    paginate_watch_hits,
    present_watch_hits,
    watch_facet_groups,
    watch_from_filters_payload,
    watch_from_product as payload_from_product,
    watch_hits_url,
)

router = APIRouter()


@router.get("/watches", response_class=HTMLResponse)
def watches_page(request: Request) -> HTMLResponse:
    database = request.app.state.db
    stock = database.list_products(in_stock=True)
    raw_new = str(request.query_params.get("new") or "").strip().lower()
    return request.app.state.render(
        "watches.html",
        request,
        watches=decorate_watches(stock, database.list_watches()),
        watch_facets=facet_groups(stock, "mac", {}, include_catalog=True, show_counts=True, cascade=True),
        open_create=raw_new in {"1", "true", "yes"},
    )


@router.post("/watches", response_class=HTMLResponse)
async def watches_create(request: Request) -> RedirectResponse:
    form = await request.form()
    request.app.state.db.create_watch(form_watch(form))
    return RedirectResponse("/watches", status_code=303)


@router.post("/watches/from-product", response_class=HTMLResponse)
async def watch_from_product_route(request: Request) -> RedirectResponse:
    form = dict(await request.form())
    sku = str(form.get("sku") or "")
    mode = str(form.get("mode") or "condition")
    products = [p for p in request.app.state.db.list_products(in_stock=True) if p["sku"] == sku]
    if not products:
        raise HTTPException(404, "商品不在当前在售列表")
    request.app.state.db.create_watch(payload_from_product(products[0], mode))
    return RedirectResponse("/watches", status_code=303)


@router.post("/watches/from-filters", response_class=HTMLResponse)
async def watch_from_filters(request: Request) -> RedirectResponse:
    form = await request.form()
    request.app.state.db.create_watch(watch_from_filters_payload(form))
    return RedirectResponse("/watches", status_code=303)


@router.post("/watches/cascade", response_class=HTMLResponse)
async def watch_cascade(request: Request) -> HTMLResponse:
    form = await request.form()
    stock = request.app.state.db.list_products(in_stock=True)
    return request.app.state.render("_watch_facets.html", request, facets=watch_facet_groups(form, stock))


@router.post("/watches/preview", response_class=HTMLResponse)
async def watch_preview(request: Request) -> HTMLResponse:
    watch = form_watch(await request.form())
    stock = request.app.state.db.list_products(in_stock=True)
    matched = sum(1 for item in stock if matches_watch(item, watch))
    if watch.get("mode") == "sku" and not watch.get("sku"):
        text = "请输入 SKU。"
    elif matched:
        text = f"当前 {matched} 件在售。"
    else:
        text = "当前缺货，上新时将通知。"
    return HTMLResponse(text)


@router.get("/watches/{watch_id}", response_class=HTMLResponse)
def watch_hits_page(request: Request, watch_id: int) -> HTMLResponse:
    database = request.app.state.db
    watch = database.get_watch(watch_id)
    if not watch:
        raise HTTPException(404, "规则不存在")
    all_hits = present_watch_hits(database.list_watch_skus(watch_id))
    paged = paginate_watch_hits(all_hits, request.query_params.get("page") or 1)
    return request.app.state.render(
        "watch_hits.html",
        request,
        watch=watch,
        hits=paged["hits"],
        in_stock_count=sum(1 for hit in all_hits if hit["in_stock"]),
        sold_count=sum(1 for hit in all_hits if not hit["in_stock"]),
        hit_total=paged["hit_total"],
        hit_page=paged["hit_page"],
        hit_pages=paged["hit_pages"],
        has_prev=paged["has_prev"],
        has_next=paged["has_next"],
        hits_url_prev=watch_hits_url(watch_id, paged["hit_page"] - 1),
        hits_url_next=watch_hits_url(watch_id, paged["hit_page"] + 1),
    )


@router.post("/watches/{watch_id}/hits/delete")
async def watch_hit_delete(request: Request, watch_id: int) -> RedirectResponse:
    database = request.app.state.db
    watch = database.get_watch(watch_id)
    if not watch:
        raise HTTPException(404, "规则不存在")
    form = await request.form()
    sku = str(form.get("sku") or "").strip()
    if not sku:
        raise HTTPException(400, "缺少 SKU")
    state = database.watch_sku_state(watch_id, sku)
    if state and state.get("in_stock"):
        raise HTTPException(400, "在售命中不能删除")
    database.delete_watch_sku(watch_id, sku)
    try:
        page = int(form.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    remaining = paginate_watch_hits(present_watch_hits(database.list_watch_skus(watch_id)), page)
    return RedirectResponse(watch_hits_url(watch_id, remaining["hit_page"]), status_code=303)


@router.post("/watches/{watch_id}/toggle")
async def watch_toggle(request: Request, watch_id: int) -> RedirectResponse:
    watch = request.app.state.db.get_watch(watch_id)
    if not watch:
        raise HTTPException(404, "规则不存在")
    request.app.state.db.update_watch(watch_id, {"enabled": not watch["enabled"]})
    return RedirectResponse("/watches", status_code=303)


@router.post("/watches/{watch_id}/delete")
async def watch_delete(request: Request, watch_id: int) -> RedirectResponse:
    request.app.state.db.delete_watch(watch_id)
    return RedirectResponse("/watches", status_code=303)
