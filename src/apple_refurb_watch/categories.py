from __future__ import annotations

from urllib.parse import urlparse

BASE = "https://www.apple.com.cn"

CATEGORIES: dict[str, dict[str, str]] = {
    "mac": {
        "name": "Mac",
        "url": f"{BASE}/shop/refurbished/mac",
    },
    "macbook-pro": {
        "name": "MacBook Pro",
        "url": f"{BASE}/shop/refurbished/mac/macbook-pro",
    },
    "macbook-air": {
        "name": "MacBook Air",
        "url": f"{BASE}/shop/refurbished/mac/macbook-air",
    },
    "ipad": {
        "name": "iPad",
        "url": f"{BASE}/shop/refurbished/ipad",
    },
    "watch": {
        "name": "Apple Watch",
        "url": f"{BASE}/shop/refurbished/watch",
    },
    "airpods": {
        "name": "AirPods",
        "url": f"{BASE}/shop/refurbished/airpods",
    },
    "homepod": {
        "name": "HomePod",
        "url": f"{BASE}/shop/refurbished/homepod",
    },
    "accessories": {
        "name": "配件",
        "url": f"{BASE}/shop/refurbished/accessories",
    },
}

DEFAULT_LISTINGS = ["mac", "ipad", "watch"]
LISTING_GROUPS = [
    {
        "id": "computers",
        "label": "电脑",
        "options": [
            {"key": "mac", "name": "Mac", "hint": "官翻 Mac 整类，含 Pro、Air 与其它机型。"},
        ],
    },
    {
        "id": "tablets",
        "label": "平板",
        "options": [{"key": "ipad", "name": "iPad", "hint": "官翻 iPad 整类。"}],
    },
    {
        "id": "wearables",
        "label": "手表",
        "options": [{"key": "watch", "name": "Apple Watch", "hint": "官翻 Apple Watch。"}],
    },
    {
        "id": "audio",
        "label": "音频",
        "options": [{"key": "airpods", "name": "AirPods", "hint": "官翻 AirPods。"}],
    },
    {
        "id": "home",
        "label": "家居",
        "options": [{"key": "homepod", "name": "HomePod", "hint": "官翻 HomePod。"}],
    },
    {
        "id": "accessories",
        "label": "配件",
        "options": [{"key": "accessories", "name": "配件", "hint": "官翻配件，含 Pencil、显示屏等。"}],
    },
]
LISTING_MODELS = {
    "macbook-pro": "macbookpro",
    "macbook-air": "macbookair",
}
MAC_CHILD_LISTINGS = frozenset({"macbook-pro", "macbook-air"})
SHOP_FAMILIES = [
    {"key": "mac", "name": "Mac"},
    {"key": "ipad", "name": "iPad"},
    {"key": "watch", "name": "Watch"},
    {"key": "airpods", "name": "AirPods"},
    {"key": "homepod", "name": "HomePod"},
    {"key": "accessories", "name": "配件"},
]


def compact_listings(keys: list[str] | None) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for key in keys or []:
        if key and key not in seen:
            unique.append(key)
            seen.add(key)
    if "mac" in seen:
        return [key for key in unique if key not in MAC_CHILD_LISTINGS]
    return unique


def listen_listing_keys(selected: list[str] | None) -> list[str]:
    return compact_listings(list(selected or [])) or list(DEFAULT_LISTINGS)


def shop_families_for(listings: list[str] | None) -> list[dict[str, str]]:
    wanted = {shop_family_key(key) for key in listen_listing_keys(listings)}
    wanted.discard("")
    return [item for item in SHOP_FAMILIES if item["key"] in wanted]


def canonical_shop_listing_key(listing_key: str | None, listings: list[str] | None) -> str:
    families = shop_families_for(listings)
    allowed = {item["key"] for item in families}
    if len(families) == 1:
        return families[0]["key"]
    raw = shop_family_key(listing_key)
    if raw in allowed:
        return raw
    return ""


def host_ok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "apple.com.cn" or host.endswith(".apple.com.cn") or host == "apple.com" or host.endswith(".apple.com")


def listing_url(key: str) -> str:
    if key in CATEGORIES:
        return CATEGORIES[key]["url"]
    if key.startswith("http://") or key.startswith("https://"):
        if not host_ok(key):
            raise KeyError(f"拒绝非苹果域名: {key}")
        return key
    raise KeyError(f"未知分类: {key}")


def listing_name(key: str) -> str:
    if key in CATEGORIES:
        return CATEGORIES[key]["name"]
    return key


def shop_family_key(listing_key: str | None) -> str:
    key = str(listing_key or "").strip()
    if key in MAC_CHILD_LISTINGS:
        return "mac"
    return key
