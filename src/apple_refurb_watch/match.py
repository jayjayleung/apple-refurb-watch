from __future__ import annotations

from dataclasses import asdict, is_dataclass

from apple_refurb_watch.parse import Product, color_from_title, normalize_sku
from apple_refurb_watch.textutil import norm_text

COLOR_ALIASES: dict[str, list[str]] = {
    "silver": ["银色", "silver"],
    "spaceblack": ["深空黑色", "深空黑", "spaceblack", "space black"],
    "starlight": ["星光色", "starlight"],
    "midnight": ["午夜色", "midnight"],
    "skyblue": ["天蓝色", "skyblue"],
    "blue": ["蓝色", "blue", "靛蓝色"],
    "purple": ["紫色", "purple"],
    "pink": ["粉色", "桃粉色", "pink"],
    "yellow": ["黄色", "yellow"],
    "orange": ["柑橘黄色", "橙色", "orange"],
    "spacegray": ["深空灰色", "深空灰", "spacegray", "space grey", "spacegray"],
    "black": ["黑色", "black"],
    "gold": ["金色", "gold"],
    "natural": ["原色", "natural"],
    "indigo": ["靛蓝色", "indigo"],
    "green": ["绿色", "green"],
    "white": ["白色", "white"],
}





def _product_dict(product: Product | dict) -> dict:
    if is_dataclass(product):
        return asdict(product)
    return dict(product)


def _color_candidates(token: str) -> list[str]:
    token = token.strip()
    if not token:
        return []
    candidates = [token]
    lower = token.lower()
    if lower in COLOR_ALIASES:
        candidates.extend([lower, *COLOR_ALIASES[lower]])
    for key, names in COLOR_ALIASES.items():
        name_n = {norm_text(n) for n in names}
        if norm_text(token) in name_n or lower == key:
            candidates.extend([key, *names])
    return candidates


def color_matches(wanted: list[str], product: dict) -> bool:
    if not wanted:
        return True
    fields = {
        norm_text(product.get("color_key")),
        norm_text(product.get("color_label")),
        norm_text(color_from_title(product.get("title") or "") or ""),
    }
    fields.discard("")
    for item in wanted:
        candidates = {norm_text(c) for c in _color_candidates(item) if c}
        candidates.discard("")
        if fields & candidates:
            return True
    return False


def listing_matches(watch: dict, item: dict) -> bool:
    key = watch.get("listing_key")
    if not key:
        return True
    prod = str(item.get("listing_key") or "")
    model = str(item.get("model_key") or "")
    title = str(item.get("title") or "")
    if key == prod:
        return True
    if key == "mac" and (prod.startswith("mac") or "Mac" in title):
        return True
    if key == "ipad" and (prod.startswith("ipad") or "iPad" in title or "Pencil" in title):
        return True
    if key == "watch" and (prod.startswith("watch") or "Watch" in title):
        return True
    if key == "airpods" and (prod == "airpods" or "AirPods" in title):
        return True
    if key == "macbook-pro" and ("macbookpro" in model or "MacBook Pro" in title):
        return True
    if key == "macbook-air" and ("macbookair" in model or "MacBook Air" in title):
        return True
    return False


def matches_watch(
    product: Product | dict,
    watch: dict,
    *,
    ignore_ram: bool = False,
    ignore_storage: bool = False,
) -> bool:
    item = _product_dict(product)
    if not listing_matches(watch, item):
        return False
    mode = watch.get("mode") or "condition"
    if mode == "sku":
        want = normalize_sku(watch.get("sku") or "")
        return bool(want) and normalize_sku(item.get("sku") or "") == want

    title_n = norm_text(item.get("title"))
    for token in watch.get("all_of") or []:
        if norm_text(token) not in title_n:
            return False
    for token in watch.get("none_of") or []:
        if norm_text(token) and norm_text(token) in title_n:
            return False
    if watch.get("min_price") is not None:
        if item.get("price") is None or float(item["price"]) < float(watch["min_price"]):
            return False
    if watch.get("max_price") is not None:
        if item.get("price") is None or float(item["price"]) > float(watch["max_price"]):
            return False
    if not ignore_ram and watch.get("min_ram_gb") is not None:
        ram = item.get("ram_gb")
        if ram is None or int(ram) < int(watch["min_ram_gb"]):
            return False
    if not ignore_storage and watch.get("min_storage_gb") is not None:
        storage = item.get("storage_gb")
        if storage is None or int(storage) < int(watch["min_storage_gb"]):
            return False
    if not color_matches(watch.get("colors") or [], item):
        return False
    from apple_refurb_watch.filters import dims_match

    if not dims_match(item, watch.get("dim_filters") or {}):
        return False
    return True


def needs_ram(watch: dict) -> bool:
    return watch.get("min_ram_gb") is not None


def needs_storage(watch: dict) -> bool:
    return watch.get("min_storage_gb") is not None
