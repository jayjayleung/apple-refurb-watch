from apple_refurb_watch.categories import compact_listings


def test_compact_listings_drops_mac_children_when_mac_selected() -> None:
    assert compact_listings(["mac", "macbook-pro", "ipad"]) == ["mac", "ipad"]
    assert compact_listings(["macbook-pro", "mac"]) == ["mac"]
    assert compact_listings(["macbook-pro", "macbook-air"]) == ["macbook-pro", "macbook-air"]
    assert compact_listings(["mac", "mac", "watch"]) == ["mac", "watch"]
    assert compact_listings(None) == []
