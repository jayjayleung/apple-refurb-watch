from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import Request

from apple_refurb_watch.filters import label_for
from apple_refurb_watch.listing import listing_filters

PAGE_SIZE = 24


def query_filters(request: Request) -> dict[str, Any]:
    return listing_filters(request.query_params)


def page_offset(request: Request) -> int:
    try:
        return max(0, int(request.query_params.get("offset") or 0))
    except (TypeError, ValueError):
        return 0


def listings_path(request: Request, offset: int) -> str:
    pairs = [(key, value) for key, value in request.query_params.multi_items() if key != "offset"]
    if offset:
        pairs.append(("offset", str(offset)))
    query = urlencode(pairs)
    return f"/?{query}" if query else "/"


def omit_query(request: Request, drop_key: str, drop_value: str | None = None) -> str:
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


def filter_chips(request: Request, filters: dict[str, Any]) -> list[dict[str, str]]:
    chips: list[dict[str, str]] = []
    for key, values in (filters.get("dim_filters") or {}).items():
        for value in values:
            chips.append({"label": label_for(key, value), "href": omit_query(request, f"d_{key}", value)})
    if filters.get("q"):
        chips.append({"label": str(filters["q"]), "href": omit_query(request, "q")})
    if filters.get("max_price") is not None:
        chips.append({"label": f"≤ ¥{int(filters['max_price']):,}", "href": omit_query(request, "max_price")})
    if filters.get("min_ram_gb") is not None:
        chips.append({"label": f"内存 ≥ {filters['min_ram_gb']}GB", "href": omit_query(request, "min_ram_gb")})
    if filters.get("min_storage_gb") is not None:
        chips.append({"label": f"硬盘 ≥ {filters['min_storage_gb']}GB", "href": omit_query(request, "min_storage_gb")})
    return chips
