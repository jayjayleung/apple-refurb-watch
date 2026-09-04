from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from apple_refurb_watch.parse import normalize_sku
from apple_refurb_watch.paths import data_dir

MAX_THUMB_BYTES = 512 * 1024
_IMAGE_TYPES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"GIF8": "image/gif",
}


class ThumbError(RuntimeError):
    def __init__(self, message: str, status: int = 404) -> None:
        super().__init__(message)
        self.status = status


def apple_image_host_ok(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = (parsed.netloc or "").lower()
    if not host:
        return False
    return host.endswith(".cdn-apple.com") or host.endswith(".apple.com") or host.endswith(".apple.com.cn")


def product_thumb_src(item: dict | None) -> str:
    if not isinstance(item, dict):
        return ""
    sku = str(item.get("sku") or "").strip()
    url = str(item.get("image_url") or "").strip()
    if not sku or not url:
        return ""
    return f"/media/thumb?sku={quote(sku, safe='')}"


def thumb_cache_path(sku: str) -> Path:
    safe = (normalize_sku(sku) or sku).replace("/", "_")
    return data_dir() / "thumbs" / f"{safe}.img"


def sniff_image_type(data: bytes) -> str | None:
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    for magic, mime in _IMAGE_TYPES.items():
        if data.startswith(magic):
            return mime
    return None


def load_product_thumb(db, sku: str, *, client: httpx.Client | None = None) -> tuple[bytes, str]:
    code = normalize_sku(sku) or str(sku or "").strip()
    if not code:
        raise ThumbError("缺少 SKU", 400)
    row = db.get_product(code)
    if row is None and code != sku:
        row = db.get_product(str(sku).strip())
    url = str((row or {}).get("image_url") or "").strip()
    if not url:
        raise ThumbError("没有缩略图", 404)
    if not apple_image_host_ok(url):
        raise ThumbError("拒绝非苹果图片", 404)
    cache = thumb_cache_path(code)
    if cache.is_file():
        data = cache.read_bytes()
        mime = sniff_image_type(data)
        if mime:
            return data, mime
    data, mime = fetch_apple_thumb(url, client=client)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data, mime


def fetch_apple_thumb(
    url: str,
    *,
    client: httpx.Client | None = None,
    attempts: int = 3,
) -> tuple[bytes, str]:
    if not apple_image_host_ok(url):
        raise ThumbError("拒绝非苹果图片", 404)
    owns = client is None
    http = client or httpx.Client(timeout=8.0, follow_redirects=True, headers={"Accept": "image/*,*/*;q=0.8"})
    last: ThumbError | None = None
    try:
        total = max(1, int(attempts))
        for attempt in range(total):
            try:
                return _download_apple_thumb(http, url)
            except ThumbError as exc:
                last = exc
                if exc.status == 404 or attempt >= total - 1:
                    raise
                time.sleep(0.2 * (attempt + 1))
        raise last or ThumbError("下载缩略图失败", 502)
    finally:
        if owns:
            http.close()


def _download_apple_thumb(http: httpx.Client, url: str) -> tuple[bytes, str]:
    try:
        response = http.get(url)
    except httpx.HTTPError as exc:
        raise ThumbError("下载缩略图失败", 502) from exc
    if response.status_code >= 400:
        raise ThumbError("下载缩略图失败", 502)
    if not apple_image_host_ok(str(response.url)):
        raise ThumbError("拒绝非苹果图片", 404)
    data = response.content or b""
    if not data or len(data) > MAX_THUMB_BYTES:
        raise ThumbError("缩略图无效", 502)
    mime = sniff_image_type(data)
    if not mime:
        raise ThumbError("缩略图无效", 502)
    return data, mime
