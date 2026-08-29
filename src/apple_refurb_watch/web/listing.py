from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import Request

from apple_refurb_watch.categories import CATEGORIES
from apple_refurb_watch.filters import label_for, restrict_dims, selected_dims
from apple_refurb_watch.match import matches_watch

PAGE_SIZE = 24


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


def opt_number(raw: str | None, caster):
    if raw in (None, ""):
        return None
    try:
        return caster(raw)
    except (TypeError, ValueError):
        return None


def filter_products(
    items: list[dict],
    *,
    q: str | None = None,
    listing_key: str | None = None,
    color: str | None = None,
    max_price: float | None = None,
    min_ram_gb: int | None = None,
    min_storage_gb: int | None = None,
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


def query_filters(request: Request) -> dict[str, Any]:
    params = request.query_params
    listing_key = (params.get("listing_key") or "").strip() or None
    dim_filters = restrict_dims(selected_dims(params), listing_key)
    color = (params.get("color") or "").strip() or None
    return {
        "q": (params.get("q") or "").strip() or None,
        "listing_key": listing_key,
        "color": color,
        "max_price": opt_number(params.get("max_price"), float),
        "min_ram_gb": opt_number(params.get("min_ram_gb"), int),
        "min_storage_gb": opt_number(params.get("min_storage_gb"), int),
        "dim_filters": dim_filters,
    }


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
    listing_key = filters.get("listing_key") or ""
    if listing_key:
        name = CATEGORIES[listing_key]["name"] if listing_key in CATEGORIES else listing_key
        chips.append({"label": name, "href": omit_query(request, "listing_key")})
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
