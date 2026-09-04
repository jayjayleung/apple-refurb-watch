import httpx
import pytest

from apple_refurb_watch.categories import listing_url
from apple_refurb_watch.fetch import FetchError, fetch_html
from apple_refurb_watch.parse import (
    ParseError,
    first_srcset_url,
    listing_image_url,
    parse_detail_specs,
    parse_listing_html,
    parse_size_gb,
    product_page_url,
    sku_from_url,
)


def test_parse_size_gb() -> None:
    assert parse_size_gb("16gb") == 16
    assert parse_size_gb("1tb") == 1024
    assert parse_size_gb("512GB") == 512
    assert parse_size_gb("1_5tb") == 1536
    assert parse_size_gb("1point5tb") == 1536


def test_parse_listing_bootstrap(listing_html: str) -> None:
    products = parse_listing_html(listing_html, "mac", "https://www.apple.com.cn/shop/refurbished/mac")
    assert len(products) == 3
    pro = next(p for p in products if p.sku == "FGDN4CH/A")
    assert pro.url == "https://www.apple.com.cn/shop/product/fgdn4ch/a"
    assert pro.price == 14999
    assert pro.ram_gb == 24
    assert pro.storage_gb == 1024
    assert pro.color_key == "silver"
    assert "MacBook Pro" in pro.title
    neo = next(p for p in products if p.sku == "FHFA4CH/A")
    assert neo.ram_gb is None
    assert neo.storage_gb == 256
    pro_img = next(p for p in products if p.sku == "FGDN4CH/A")
    assert pro_img.image_url == "https://example.test/mbp.jpg"
    only_pro = parse_listing_html(listing_html, "macbook-pro", "https://www.apple.com.cn/shop/refurbished/mac/macbook-pro")
    assert [p.sku for p in only_pro] == ["FGDN4CH/A"]


def test_parse_listing_empty_bootstrap_tiles_is_empty() -> None:
    html = 'window.REFURB_GRID_BOOTSTRAP = {"tiles": []}'
    assert parse_listing_html(html, "mac", "https://www.apple.com.cn/shop/refurbished/mac") == []


def test_parse_listing_unrecognized_structure_raises() -> None:
    with pytest.raises(ParseError, match="页面结构未识别"):
        parse_listing_html("<html><body>blocked</body></html>", "mac", "https://www.apple.com.cn/shop/refurbished/mac")


def test_first_srcset_url() -> None:
    assert first_srcset_url("https://store.example/a.jpg 1x, https://store.example/a@2x.jpg 2x") == "https://store.example/a.jpg"
    assert first_srcset_url("https://store.example/a.jpg") == "https://store.example/a.jpg"
    assert first_srcset_url("") is None
    signed = "https://store.storeimages.cdn-apple.com/is/x?wid=400&.v=abc,def"
    assert first_srcset_url(signed) == signed


def test_listing_image_url_accepts_relative_and_srcset_key() -> None:
    listing = "https://www.apple.com.cn/shop/refurbished/mac"
    assert listing_image_url("/is/mbp.jpg", listing) == "https://www.apple.com.cn/is/mbp.jpg"
    assert listing_image_url("//store.storeimages.cdn-apple.com/is/mbp.jpg", listing) == (
        "https://store.storeimages.cdn-apple.com/is/mbp.jpg"
    )
    assert listing_image_url({"sources": [{"srcset": "https://example.test/a.jpg 1x"}]}, listing) == (
        "https://example.test/a.jpg"
    )
    assert listing_image_url({"src": "https://example.test/plain.jpg"}, listing) == "https://example.test/plain.jpg"


def test_parse_listing_dom_reads_img() -> None:
    html = """
    <li class="as-producttile">
      <a href="/shop/product/abcd4ch/a">link</a>
      <h3 class="as-producttile-title">翻新 Mac</h3>
      <img src="/shop/images/mac.jpg" srcset="https://example.test/dom.jpg 1x">
    </li>
    """
    products = parse_listing_html(html, "mac", "https://www.apple.com.cn/shop/refurbished/mac")
    assert len(products) == 1
    assert products[0].sku == "ABCD4CH/A"
    assert products[0].image_url == "https://example.test/dom.jpg"


def test_product_page_url_uses_lowercase_sku_and_drops_fnode() -> None:
    assert sku_from_url("/shop/product/g1mk7ch/a?fnode=abc") == "G1MK7CH/A"
    assert sku_from_url("https://www.apple.com.cn/shop/product/feh44ch/b") == "FEH44CH/B"
    assert product_page_url("g1mk7ch/a", "/shop/product/g1mk7ch/a?fnode=deadbeef") == (
        "https://www.apple.com.cn/shop/product/g1mk7ch/a"
    )
    assert product_page_url("G1MK7CH/A", "https://www.apple.com.cn/shop/product/G1MK7CH/A") == (
        "https://www.apple.com.cn/shop/product/g1mk7ch/a"
    )
    assert product_page_url(None, "https://www.apple.com.cn/shop/product/fhfa4ch/a") == (
        "https://www.apple.com.cn/shop/product/fhfa4ch/a"
    )
    assert "?" not in product_page_url("fhfa4ch/a", "/shop/product/fhfa4ch/a?fnode=deadbeef")


def test_listing_url_rejects_ssrf() -> None:
    with pytest.raises(KeyError):
        listing_url("https://evil.example/steal")
    assert listing_url("mac").startswith("https://www.apple.com.cn/")
    assert listing_url("https://www.apple.com.cn/shop/refurbished/mac").startswith("https://www.apple.com.cn/")


def test_parse_detail_specs(detail_html: str) -> None:
    specs = parse_detail_specs(detail_html)
    assert specs["ram_gb"] == 8
    assert specs["storage_gb"] == 256


def test_fetch_html_breaks_cookie_redirect_loop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "geo=" in request.headers.get("cookie", ""):
            return httpx.Response(200, text="<html>ok</html>")
        return httpx.Response(
            302,
            headers={
                "Location": str(request.url),
                "Set-Cookie": "geo=cn; Path=/",
            },
        )

    html = fetch_html(
        "https://www.apple.com.cn/shop/refurbished/mac/macbook-pro",
        retries=1,
        transport=httpx.MockTransport(handler),
    )
    assert html == "<html>ok</html>"


def test_fetch_html_rejects_offsite_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://evil.example/x"})

    with pytest.raises(FetchError, match="非苹果域名"):
        fetch_html(
            "https://www.apple.com.cn/shop/refurbished/mac/macbook-pro",
            retries=1,
            transport=httpx.MockTransport(handler),
        )


def test_fetch_html_does_not_retry_client_errors() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, text="no")

    with pytest.raises(FetchError, match="HTTP 403"):
        fetch_html(
            "https://www.apple.com.cn/shop/refurbished/mac",
            retries=3,
            transport=httpx.MockTransport(handler),
        )
    assert calls["n"] == 1


def test_fetch_html_retries_server_errors_without_sleeping_after_last(monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("apple_refurb_watch.fetch.time.sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr("apple_refurb_watch.fetch.random.random", lambda: 0)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="no")

    with pytest.raises(FetchError, match="HTTP 503"):
        fetch_html(
            "https://www.apple.com.cn/shop/refurbished/mac",
            retries=3,
            transport=httpx.MockTransport(handler),
        )
    assert calls["n"] == 3
    assert len(sleeps) == 2
