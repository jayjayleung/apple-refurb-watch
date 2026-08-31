from apple_refurb_watch.categories import (
    compact_listings,
    canonical_shop_listing_key,
    listing_family_name,
    listings_family_names,
    shop_families_for,
    shop_family_key,
)


def test_compact_listings_drops_mac_children_when_mac_selected() -> None:
    assert compact_listings(["mac", "macbook-pro", "ipad"]) == ["mac", "ipad"]
    assert compact_listings(["macbook-pro", "mac"]) == ["mac"]
    assert compact_listings(["macbook-pro", "macbook-air"]) == ["macbook-pro", "macbook-air"]
    assert compact_listings(["mac", "mac", "watch"]) == ["mac", "watch"]
    assert compact_listings(None) == []


def test_shop_family_key_groups_mac_children() -> None:
    assert shop_family_key(None) == ""
    assert shop_family_key("") == ""
    assert shop_family_key("mac") == "mac"
    assert shop_family_key("macbook-pro") == "mac"
    assert shop_family_key("macbook-air") == "mac"
    assert shop_family_key("ipad") == "ipad"
    assert shop_family_key("watch") == "watch"
    assert shop_family_key("homepod") == "homepod"
    assert shop_family_key("accessories") == "accessories"


def test_shop_families_for_listen_scope() -> None:
    assert [item["key"] for item in shop_families_for(["macbook-pro"])] == ["mac"]
    assert [item["key"] for item in shop_families_for(["mac", "ipad"])] == ["mac", "ipad"]
    assert [item["key"] for item in shop_families_for(["macbook-pro", "ipad", "watch"])] == [
        "mac",
        "ipad",
        "watch",
    ]
    assert "watch" not in {item["key"] for item in shop_families_for(["mac", "ipad"])}


def test_canonical_shop_listing_key() -> None:
    assert canonical_shop_listing_key(None, ["macbook-pro"]) == "mac"
    assert canonical_shop_listing_key("", ["macbook-pro"]) == "mac"
    assert canonical_shop_listing_key("ipad", ["macbook-pro"]) == "mac"
    assert canonical_shop_listing_key("macbook-pro", ["macbook-pro"]) == "mac"
    assert canonical_shop_listing_key(None, ["mac", "ipad"]) == ""
    assert canonical_shop_listing_key("watch", ["mac", "ipad"]) == ""
    assert canonical_shop_listing_key("mac", ["mac", "ipad"]) == "mac"
    assert canonical_shop_listing_key("macbook-pro", ["mac", "ipad"]) == "mac"


def test_listing_family_names() -> None:
    assert listing_family_name("macbook-pro") == "Mac"
    assert listing_family_name("watch") == "Watch"
    assert listing_family_name("accessories") == "配件"
    assert listings_family_names(["macbook-pro", "ipad", "mac"]) == ["Mac", "iPad"]
    assert listings_family_names([]) == []

