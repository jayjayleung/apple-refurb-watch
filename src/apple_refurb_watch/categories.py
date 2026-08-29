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
}

DEFAULT_LISTINGS = ["mac", "ipad", "watch"]
LISTING_GROUPS = [
    {
        "id": "computers",
        "label": "电脑",
        "options": [
            {"key": "mac", "name": "Mac", "hint": "官翻 Mac 整类，含 Pro 与 Air。勾选后不必再选下面两项。"},
            {"key": "macbook-pro", "name": "只要 MacBook Pro", "hint": "仅抓 Pro 列表。已勾 Mac 时不会同时抓。"},
            {"key": "macbook-air", "name": "只要 MacBook Air", "hint": "仅抓 Air 列表。已勾 Mac 时不会同时抓。"},
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
]
LISTING_MODELS = {
    "macbook-pro": "macbookpro",
    "macbook-air": "macbookair",
}
MAC_CHILD_LISTINGS = frozenset({"macbook-pro", "macbook-air"})


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
