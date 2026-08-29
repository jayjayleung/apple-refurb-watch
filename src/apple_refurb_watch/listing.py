from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from apple_refurb_watch.filters import restrict_dims, selected_dims
from apple_refurb_watch.match import matches_watch

PAGE_SIZE = 24


def format_cny(value) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):,.0f}"


def format_gb(value) -> str:
    if value is None or value == "":
        return ""
    amount = int(value)
    if amount >= 1024 and amount % 1024 == 0:
        return f"{amount // 1024}TB"
    return f"{amount}GB"


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


def sort_products(items: list[dict], sort: str | None) -> list[dict]:
    key = (sort or "price").strip() or "price"

    def price_key(item: dict, reverse: bool = False) -> tuple:
        price = item.get("price")
        missing = price is None
        value = 0.0 if price is None else float(price)
        if reverse:
            value = -value
        return (missing, value, str(item.get("sku") or ""))

    if key in {"price", "price_asc", "asc"}:
        return sorted(items, key=lambda item: price_key(item))
    if key in {"-price", "price_desc", "desc"}:
        return sorted(items, key=lambda item: price_key(item, reverse=True))
    return list(items)


def listing_filters(params: Any) -> dict[str, Any]:
    listing_key = (str(params.get("listing_key") or "")).strip() or None
    dim_filters = restrict_dims(selected_dims(params), listing_key)
    color = (str(params.get("color") or "")).strip() or None
    return {
        "q": (str(params.get("q") or "")).strip() or None,
        "listing_key": listing_key,
        "color": color,
        "max_price": opt_number(params.get("max_price"), float),
        "min_ram_gb": opt_number(params.get("min_ram_gb"), int),
        "min_storage_gb": opt_number(params.get("min_storage_gb"), int),
        "dim_filters": dim_filters,
    }
