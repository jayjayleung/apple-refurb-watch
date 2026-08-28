from apple_refurb_watch.categories import listing_url
from apple_refurb_watch.parse import first_srcset_url, parse_detail_specs, parse_listing_html, parse_size_gb


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


def test_first_srcset_url() -> None:
    assert first_srcset_url("https://store.example/a.jpg 1x, https://store.example/a@2x.jpg 2x") == "https://store.example/a.jpg"
    assert first_srcset_url("https://store.example/a.jpg") == "https://store.example/a.jpg"
    assert first_srcset_url("") is None


def test_listing_url_rejects_ssrf() -> None:
    import pytest

    with pytest.raises(KeyError):
        listing_url("https://evil.example/steal")
    assert listing_url("mac").startswith("https://www.apple.com.cn/")
    assert listing_url("https://www.apple.com.cn/shop/refurbished/mac").startswith("https://www.apple.com.cn/")


def test_parse_detail_specs(detail_html: str) -> None:
    specs = parse_detail_specs(detail_html)
    assert specs["ram_gb"] == 8
    assert specs["storage_gb"] == 256
