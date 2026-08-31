from apple_refurb_watch.categories import listing_item_matches
from apple_refurb_watch.query import ProductQuery


def test_product_query_matches_watch_fields(listing_html: str) -> None:
    from apple_refurb_watch.parse import parse_listing_html

    product = parse_listing_html(listing_html, "mac", "https://www.apple.com.cn/shop/refurbished/mac")[0]
    query = ProductQuery.from_watch(
        {
            "mode": "condition",
            "all_of": ["14 英寸", "MacBook Pro", "M5 Pro"],
            "none_of": ["纳米纹理"],
            "colors": ["银色"],
            "min_ram_gb": 24,
            "min_storage_gb": 1024,
            "max_price": 18000,
        }
    )
    assert query.matches(product)
    assert not ProductQuery.from_watch({"max_price": 1000}).matches(product)


def test_product_query_from_nested_query() -> None:
    query = ProductQuery.from_watch(
        {
            "name": "规则",
            "query": {"listing_key": "mac", "dims": {"chip": ["m5"]}, "min_ram_gb": 24},
            "max_price": 18000,
        }
    )
    assert query.listing_key == "mac"
    assert query.dims["chip"] == ["m5"]
    assert query.min_ram_gb == 24
    assert query.max_price == 18000


def test_listing_item_matches_studio_display() -> None:
    item = {
        "title": "翻新 Studio Display - 标准玻璃面板 - 可调倾斜度及高度的支架",
        "listing_key": "accessories",
        "model_key": "display",
    }
    assert listing_item_matches("mac", item)
    assert listing_item_matches("accessories", item)
    assert not listing_item_matches("ipad", item)
