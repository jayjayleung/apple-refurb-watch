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
