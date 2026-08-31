from __future__ import annotations

from apple_refurb_watch.categories import listing_item_matches
from apple_refurb_watch.parse import Product, color_from_title
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
    return listing_item_matches(watch.get("listing_key"), item)


def matches_watch(
    product: Product | dict,
    watch: dict,
    *,
    ignore_ram: bool = False,
    ignore_storage: bool = False,
) -> bool:
    from apple_refurb_watch.query import ProductQuery

    return ProductQuery.from_watch(watch).matches(product, ignore_ram=ignore_ram, ignore_storage=ignore_storage)


def needs_ram(watch: dict) -> bool:
    return watch.get("min_ram_gb") is not None


def needs_storage(watch: dict) -> bool:
    return watch.get("min_storage_gb") is not None
