from __future__ import annotations

import random
import time
from urllib.parse import urljoin, urlparse

import httpx

from apple_refurb_watch.categories import host_ok

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 12


class FetchError(RuntimeError):
    pass


def _redirect_key(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


class HtmlFetcher:
    def __init__(self, *, timeout: float = 25.0, transport=None):
        kwargs: dict = {
            "headers": DEFAULT_HEADERS,
            "timeout": timeout,
            "follow_redirects": False,
        }
        if transport is not None:
            kwargs["transport"] = transport
        self._client = httpx.Client(**kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HtmlFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __call__(
        self,
        url: str,
        *,
        retries: int = 3,
        referer: str | None = "https://www.apple.com.cn/shop/refurbished",
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                response = self._get(url, referer=referer)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= retries - 1:
                    break
                time.sleep((2**attempt) + random.random())
                continue
            if 400 <= response.status_code < 500 and response.status_code != 429:
                raise FetchError(f"HTTP {response.status_code} {url}")
            if response.status_code >= 500 or response.status_code == 429:
                last_error = FetchError(f"HTTP {response.status_code} {url}")
                if attempt >= retries - 1:
                    break
                time.sleep((2**attempt) + random.random())
                continue
            return response.text
        raise FetchError(str(last_error) if last_error else f"无法抓取 {url}")

    def _get(self, url: str, *, referer: str | None) -> httpx.Response:
        headers = {"Referer": referer} if referer else {}
        current = url
        seen: set[str] = set()
        last = None
        for _ in range(MAX_REDIRECTS):
            last = self._client.get(current, headers=headers, follow_redirects=False)
            if last.status_code not in REDIRECT_STATUSES:
                return last
            location = last.headers.get("location")
            if not location:
                return last
            nxt = urljoin(str(last.url), location)
            if not host_ok(nxt):
                raise FetchError(f"拒绝跳转到非苹果域名: {nxt}")
            key = _redirect_key(nxt)
            if key in seen or key == _redirect_key(str(last.url)):
                break
            seen.add(key)
            current = nxt
        for candidate in (url, current):
            retry = self._client.get(candidate, headers=headers, follow_redirects=False)
            if retry.status_code not in REDIRECT_STATUSES:
                return retry
        raise FetchError(f"Exceeded maximum allowed redirects for {url}")


def fetch_html(
    url: str,
    *,
    timeout: float = 25.0,
    retries: int = 3,
    referer: str | None = "https://www.apple.com.cn/shop/refurbished",
    transport=None,
) -> str:
    with HtmlFetcher(timeout=timeout, transport=transport) as fetcher:
        return fetcher(url, retries=retries, referer=referer)
