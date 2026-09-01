from __future__ import annotations

from typing import Any, Mapping

from apple_refurb_watch.categories import CATEGORIES, listing_family_name, listing_name
from apple_refurb_watch.filters import (
    facet_groups,
    label_for,
    normalize_dim_filters,
    product_dims,
    prune_cascade_dims,
    restrict_dims,
    selected_dims,
    summarize_dims,
)
from apple_refurb_watch.listing import format_cny, format_gb, opt_number
from apple_refurb_watch.filters.tokens import CPU_CORE_KEY, GPU_CORE_KEY
from apple_refurb_watch.match import matches_watch
from apple_refurb_watch.parse import product_page_url


def watch_from_product(item: Mapping[str, Any], mode: str) -> dict:
    sku = str(item.get("sku") or "")
    if mode == "sku":
        return {
            "name": f"SKU {sku}",
            "mode": "sku",
            "sku": sku,
            "listing_key": item.get("listing_key"),
        }
    dims = product_dims(item)
    return {
        "name": (item.get("title") or sku)[:40],
        "mode": "condition",
        "listing_key": item.get("listing_key"),
        "dim_filters": {
            key: [value]
            for key, value in dims.items()
            if value and key not in {CPU_CORE_KEY, GPU_CORE_KEY}
        },
        "max_price": item.get("price"),
    }


def watch_name_from_filters(payload: Mapping[str, Any], q: str = "") -> str:
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


def watch_facet_groups(form: Any, stock: list) -> list[dict[str, Any]]:
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


def form_watch(form: Any) -> dict:
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
            payload["name"] = watch_name_from_filters(payload, extra)
    return payload


def watch_from_filters_payload(form: Any) -> dict:
    listing_key = str(form.get("listing_key") or "").strip() or None
    dim_filters = restrict_dims(selected_dims(form), listing_key)
    q = str(form.get("q") or "").strip()
    payload = {
        "listing_key": listing_key,
        "all_of": [q] if q else [],
        "dim_filters": dim_filters,
        "max_price": opt_number(str(form.get("max_price") or ""), float),
        "min_ram_gb": opt_number(str(form.get("min_ram_gb") or ""), int),
        "min_storage_gb": opt_number(str(form.get("min_storage_gb") or ""), int),
    }
    payload["name"] = watch_name_from_filters(payload, q)
    return {"mode": "condition", **payload}


def decorate_watches(stock: list, watches: list) -> list:
    for watch in watches:
        watch["in_stock_matches"] = sum(1 for item in stock if matches_watch(item, watch))
    return watches


def present_watch_hits(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for row in rows:
        sku = str(row.get("sku") or "")
        in_stock = bool(int(row.get("in_stock") or 0))
        hits.append(
            {
                "sku": sku,
                "title": row.get("title") or sku,
                "url": product_page_url(sku, row.get("url")),
                "image_url": row.get("image_url"),
                "in_stock": in_stock,
                "spec_line": appeared_spec_line(
                    ram_gb=row.get("ram_gb"),
                    storage_gb=row.get("storage_gb"),
                    price=row.get("price"),
                ),
            }
        )
    hits.sort(key=lambda item: (not item["in_stock"], str(item.get("title") or "")))
    return hits


HIT_PAGE_SIZE = 20


def paginate_watch_hits(
    hits: list[dict[str, Any]],
    page: int | str = 1,
    page_size: int = HIT_PAGE_SIZE,
) -> dict[str, Any]:
    page_size = max(1, int(page_size))
    total = len(hits)
    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    try:
        page_i = int(page)
    except (TypeError, ValueError):
        page_i = 1
    page_i = min(max(1, page_i), pages)
    start = (page_i - 1) * page_size
    return {
        "hits": hits[start : start + page_size],
        "hit_total": total,
        "hit_page": page_i,
        "hit_pages": pages,
        "has_prev": page_i > 1,
        "has_next": page_i < pages,
    }


def watch_hits_url(watch_id: int, page: int = 1) -> str:
    if int(page) <= 1:
        return f"/watches/{watch_id}"
    return f"/watches/{watch_id}?page={int(page)}"


def watch_condition_chips(watch: Mapping[str, Any] | None) -> list[str]:
    if not watch:
        return []
    chips: list[str] = []
    listing_key = str(watch.get("listing_key") or "").strip()
    if listing_key:
        chips.append(listing_name(listing_key))
    if watch.get("mode") == "sku" and watch.get("sku"):
        chips.append(str(watch["sku"]))
    for key, values in normalize_dim_filters(watch.get("dim_filters")).items():
        for value in values:
            label = label_for(key, value)
            if label:
                chips.append(label)
    all_of = watch.get("all_of") or []
    if isinstance(all_of, str):
        all_of = [all_of]
    if all_of:
        chips.append("包含 " + " / ".join(str(item) for item in all_of if item))
    none_of = watch.get("none_of") or []
    if isinstance(none_of, str):
        none_of = [none_of]
    if none_of:
        chips.append("排除 " + " / ".join(str(item) for item in none_of if item))
    if watch.get("min_ram_gb"):
        chips.append(f"内存 ≥ {watch['min_ram_gb']}GB")
    if watch.get("min_storage_gb"):
        chips.append(f"硬盘 ≥ {format_gb(watch['min_storage_gb'])}")
    if watch.get("max_price") not in (None, ""):
        chips.append(f"≤ ¥{format_cny(watch['max_price'])}")
    for color in watch.get("colors") or []:
        if color:
            chips.append(str(color))
    return chips


def watch_condition_label(watch: Mapping[str, Any]) -> str:
    parts: list[str] = []
    family = listing_family_name(watch.get("listing_key"))
    if family:
        parts.append(family)
    if watch.get("mode") == "sku" and watch.get("sku"):
        parts.append(str(watch["sku"]))
    parts.extend(summarize_dims(watch.get("dim_filters")))
    all_of = watch.get("all_of") or []
    if isinstance(all_of, str):
        all_of = [all_of]
    if all_of:
        parts.append("包含 " + " / ".join(str(item) for item in all_of if item))
    none_of = watch.get("none_of") or []
    if isinstance(none_of, str):
        none_of = [none_of]
    if none_of:
        parts.append("排除 " + " / ".join(str(item) for item in none_of if item))
    if watch.get("min_ram_gb"):
        parts.append(f"内存 ≥ {watch['min_ram_gb']}GB")
    if watch.get("min_storage_gb"):
        parts.append(f"硬盘 ≥ {watch['min_storage_gb']}GB")
    if watch.get("max_price") not in (None, ""):
        parts.append(f"≤ ¥{int(float(watch['max_price'])):,}")
    return " · ".join(parts)


def appeared_spec_line(*, ram_gb: Any = None, storage_gb: Any = None, price: Any = None) -> str:
    parts: list[str] = []
    if ram_gb:
        parts.append(f"{int(ram_gb)}GB 内存")
    if storage_gb:
        parts.append(f"{format_gb(storage_gb)} 硬盘")
    if price not in (None, ""):
        parts.append(f"RMB {format_cny(price)}")
    return " · ".join(parts)


def appeared_message(
    *,
    title: str | None,
    sku: str | None,
    ram_gb: Any = None,
    storage_gb: Any = None,
    price: Any = None,
    watch: Mapping[str, Any] | None = None,
) -> str:
    lines = [str(title or "").strip()]
    specs = appeared_spec_line(ram_gb=ram_gb, storage_gb=storage_gb, price=price)
    if specs:
        lines.append(specs)
    if sku:
        lines.append(str(sku))
    cond = watch_condition_label(watch) if watch else ""
    if cond:
        lines.append(f"命中：{cond}")
    return "\n".join(line for line in lines if line)


def spec_line_from_message(message: str | None) -> str:
    for line in str(message or "").splitlines():
        text = line.strip()
        if not text or text.startswith("命中："):
            continue
        if "内存" in text or "硬盘" in text or text.startswith("RMB "):
            return text
    return ""
