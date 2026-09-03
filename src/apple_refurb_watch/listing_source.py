from __future__ import annotations

import logging
from typing import Callable

from apple_refurb_watch.categories import listing_url
from apple_refurb_watch.fetch import HtmlFetcher
from apple_refurb_watch.parse import Product, extract_bootstrap, parse_detail_specs, parse_listing_html

FetchFn = Callable[[str], str]
log = logging.getLogger(__name__)


class ListingSource:
    """苹果站点适配器。官网改版只动这里和 catalog / fixtures。"""

    def __init__(
        self,
        fetch_listing: FetchFn | None = None,
        fetch_detail: FetchFn | None = None,
        *,
        fetcher: HtmlFetcher | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._fetch_listing = fetch_listing
        self._fetch_detail = fetch_detail
        if self._fetch_listing is None or self._fetch_detail is None:
            self._fetcher = self._fetcher or HtmlFetcher()
            self._fetch_listing = self._fetch_listing or self._fetcher
            self._fetch_detail = self._fetch_detail or self._fetcher

    def close(self) -> None:
        if self._fetcher is not None:
            self._fetcher.close()
            self._fetcher = None

    def fetch_listing(self, key: str) -> list[Product]:
        url = listing_url(key)
        html = self._fetch_listing(url)
        products = parse_listing_html(html, key, url)
        try:
            from apple_refurb_watch.filters import ingest_bootstrap_catalog

            ingest_bootstrap_catalog(extract_bootstrap(html), key)
        except Exception:
            log.debug("写入筛选词条缓存失败", exc_info=True)
        return products

    def fetch_detail(self, url: str) -> dict:
        return parse_detail_specs(self._fetch_detail(url))

    def fetch_catalog(self, key: str):
        from apple_refurb_watch.filters import catalog_from_bootstrap

        url = listing_url(key)
        html = self._fetch_listing(url)
        return catalog_from_bootstrap(extract_bootstrap(html), key)
