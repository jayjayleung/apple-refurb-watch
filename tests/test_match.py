from apple_refurb_watch.match import listing_matches, matches_watch
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


def test_screensize_dim_does_not_match_other_inch() -> None:
    item = {
        "title": "翻新 16 英寸 MacBook Pro Apple M5 Max 芯片 (配备 18 核中央处理器和 40 核图形处理器) 和纳米纹理显示屏 - 深空黑色",
        "listing_key": "mac",
        "model_key": "macbookpro",
        "screensize": "16inch",
        "ram_gb": 128,
        "extra": {
            "dims": {
                "refurbClearModel": "macbookpro",
                "dimensionScreensize": "16inch",
                "dimensionCapacity": "4tb",
            }
        },
    }
    watch = {
        "mode": "condition",
        "listing_key": "macbook-pro",
        "dim_filters": {
            "refurbClearModel": ["macbookpro"],
            "chip": ["m5_max"],
            "dimensionScreensize": ["14inch"],
        },
        "min_ram_gb": 64,
    }
    assert not matches_watch(item, watch)
    item["screensize"] = "14inch"
    item["extra"]["dims"]["dimensionScreensize"] = "14inch"
    item["title"] = item["title"].replace("16 英寸", "14 英寸")
    assert matches_watch(item, watch)


def test_dim_filters_from_bootstrap(listing_html: str) -> None:
    product = _pro(listing_html)
    assert matches_watch(
        product,
        {"mode": "condition", "dim_filters": {"refurbClearModel": ["macbookpro"], "tsMemorySize": ["24gb"]}},
    )
    assert not matches_watch(product, {"mode": "condition", "dim_filters": {"tsMemorySize": ["48gb"]}})


def test_mac_family_includes_studio_display() -> None:
    item = {
        "title": "翻新 Studio Display - 标准玻璃面板 - 可调倾斜度及高度的支架",
        "listing_key": "accessories",
        "model_key": "display",
    }
    assert listing_matches({"listing_key": "mac"}, item)
    assert listing_matches({"listing_key": "accessories"}, item)
    assert not listing_matches({"listing_key": "ipad"}, item)
