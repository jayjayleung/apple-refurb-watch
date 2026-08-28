from __future__ import annotations

import random
import time

import httpx

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}


class FetchError(RuntimeError):
    pass


def fetch_html(
    url: str,
    *,
    timeout: float = 25.0,
    retries: int = 3,
    referer: str | None = "https://www.apple.com.cn/shop/refurbished",
) -> str:
    headers = dict(DEFAULT_HEADERS)
    if referer:
        headers["Referer"] = referer
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
                response = client.get(url)
                if response.status_code >= 500 or response.status_code in {429}:
                    raise FetchError(f"HTTP {response.status_code} {url}")
                if response.status_code >= 400:
                    raise FetchError(f"HTTP {response.status_code} {url}")
                return response.text
        except (httpx.HTTPError, FetchError) as exc:
            last_error = exc
            sleep = (2**attempt) + random.random()
            time.sleep(sleep)
    raise FetchError(str(last_error) if last_error else f"无法抓取 {url}")
