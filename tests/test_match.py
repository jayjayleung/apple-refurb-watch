from apple_refurb_watch.match import matches_watch
from apple_refurb_watch.parse import parse_listing_html


def _pro(listing_html: str):
    return parse_listing_html(listing_html, "mac", "https://www.apple.com.cn/shop/refurbished/mac")[0]


def test_condition_match(listing_html: str) -> None:
    product = _pro(listing_html)
    watch = {
        "mode": "condition",
        "all_of": ["14 英寸", "MacBook Pro", "M5 Pro"],
        "none_of": ["纳米纹理"],
        "colors": ["银色"],
        "min_ram_gb": 24,
        "min_storage_gb": 1024,
        "max_price": 18000,
    }
    assert matches_watch(product, watch)


def test_exclude_and_price(listing_html: str) -> None:
    product = _pro(listing_html)
    assert not matches_watch(product, {"mode": "condition", "none_of": ["MacBook Pro"]})
    assert not matches_watch(product, {"mode": "condition", "max_price": 1000})
    assert not matches_watch(product, {"mode": "condition", "min_ram_gb": 48})


def test_sku_mode(listing_html: str) -> None:
    product = _pro(listing_html)
    assert matches_watch(product, {"mode": "sku", "sku": "fgdn4ch/a"})
    assert not matches_watch(product, {"mode": "sku", "sku": "AAAA4CH/A"})


def test_color_is_not_substring(listing_html: str) -> None:
    product = _pro(listing_html)
    assert matches_watch(product, {"mode": "condition", "colors": ["银色"]})
    assert matches_watch(product, {"mode": "condition", "colors": ["silver"]})
    assert not matches_watch(product, {"mode": "condition", "colors": ["黑色"]})
    sky = dict(product.__dict__)
    sky["color_key"] = "skyblue"
    sky["color_label"] = "天蓝色"
    sky["title"] = "翻新 MacBook Air - 天蓝色"
    assert not matches_watch(sky, {"mode": "condition", "colors": ["blue"]})
    assert not matches_watch(sky, {"mode": "condition", "colors": ["蓝色"]})
    assert matches_watch(sky, {"mode": "condition", "colors": ["天蓝色"]})


def test_missing_price_fails_budget() -> None:
    item = {"title": "翻新 MacBook Pro", "price": None, "listing_key": "mac"}
    assert not matches_watch(item, {"mode": "condition", "max_price": 18000})
    assert not matches_watch(item, {"mode": "condition", "min_price": 1000})
    item["price"] = 15000
    assert matches_watch(item, {"mode": "condition", "max_price": 18000})


def test_dim_filters_from_bootstrap(listing_html: str) -> None:
    product = _pro(listing_html)
    assert matches_watch(
        product,
        {"mode": "condition", "dim_filters": {"refurbClearModel": ["macbookpro"], "tsMemorySize": ["24gb"]}},
    )
    assert not matches_watch(product, {"mode": "condition", "dim_filters": {"tsMemorySize": ["48gb"]}})
