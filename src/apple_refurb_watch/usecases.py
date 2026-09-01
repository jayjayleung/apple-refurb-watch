from __future__ import annotations

from typing import Any

from apple_refurb_watch import __version__
from apple_refurb_watch.categories import shop_families_for
from apple_refurb_watch.db import EVENT_KEEP, Database
from apple_refurb_watch.filters import facet_groups
from apple_refurb_watch.listing import PAGE_SIZE, filter_products, products_in_listen_scope, sort_products
from apple_refurb_watch.settings import normalize_settings_patch, public_settings
from apple_refurb_watch.status_view import filter_event_days, load_status, paginate_event_days, present_event_days

API_REVISION = 2
CAPABILITIES = [
    "listings",
    "watches",
    "events",
    "scans",
    "events.after_id",
    "notify.deliveries",
    "filter-catalog",
    "listen",
]


def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "server_version": __version__,
        "api_revision": API_REVISION,
        "capabilities": list(CAPABILITIES),
    }


def list_shop(
    db: Database,
    filters: dict[str, Any],
    sort: str | None = None,
    *,
    offset: int = 0,
    page_size: int | None = PAGE_SIZE,
) -> dict[str, Any]:
    listings = db.settings().get("listings")
    stock = products_in_listen_scope(db.list_products(in_stock=True), listings)
    listing_only = filter_products(
        stock,
        listing_key=filters.get("listing_key"),
        q=None,
        color=None,
        max_price=None,
        min_ram_gb=None,
        min_storage_gb=None,
        dim_filters={},
    )
    items = sort_products(filter_products(stock, **filters), sort)
    total_count = len(items)
    if page_size is None:
        page_items = items
        has_more = False
        remaining = 0
        offset = 0
    else:
        page_items = items[offset : offset + page_size]
        has_more = offset + page_size < total_count
        remaining = max(0, total_count - offset - len(page_items))
    families = shop_families_for(listings)
    return {
        "stock": stock,
        "listing_only": listing_only,
        "items": page_items,
        "all_items": items,
        "total_count": total_count,
        "facets": facet_groups(
            listing_only,
            filters.get("listing_key"),
            filters.get("dim_filters") or {},
            include_catalog=True,
            include_chip=False,
            include_cores=False,
            show_counts=True,
            refine=True,
        ),
        "selected_dims": filters.get("dim_filters") or {},
        "has_more": has_more,
        "remaining": remaining,
        "offset": offset,
        "stock_count": len(stock),
        "active_families": families,
        "show_shop_all": len(families) > 1,
        "filters": filters,
        "sort": (sort or "price").strip() or "price",
    }


def present_events(db: Database, *, digest: bool = True, kind: str = "all", page: int = 1) -> dict[str, Any]:
    thumbs = {
        str(item.get("sku") or ""): item.get("image_url")
        for item in db.list_products()
        if item.get("sku") and item.get("image_url")
    }
    watch_names = {int(item["id"]): str(item.get("name") or "") for item in db.list_watches() if item.get("id")}
    days = filter_event_days(
        present_event_days(db.list_events(EVENT_KEEP), collapse_scans=digest, watch_names=watch_names),
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
    }


def patch_settings(db: Database, patch: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_settings_patch(patch, db.settings())
    return db.update_settings(normalized)


def public_status(db: Database) -> dict[str, Any]:
    return load_status(db)


def public_settings_view(db: Database) -> dict[str, Any]:
    return public_settings(db.settings())
