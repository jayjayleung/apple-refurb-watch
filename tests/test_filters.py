import json

from apple_refurb_watch.filters import (
    catalog_from_bootstrap,
    dims_match,
    facet_groups,
    format_dim_value,
    ingest_bootstrap_catalog,
    label_for,
    live_catalog_path,
    load_catalog,
    product_dims,
    selected_dims,
    sync_filter_catalog,
)
from apple_refurb_watch.match import matches_watch
from apple_refurb_watch.status_view import format_interval, present_status


def test_catalog_has_official_dimensions() -> None:
    catalog = load_catalog()
    mac = catalog["listing_dimensions"]["mac"]
    assert mac == [
        "refurbClearModel",
        "dimensionScreensize",
        "dimensionRelYear",
        "dimensionColor",
        "tsMemorySize",
        "dimensionCapacity",
    ]
    ram = catalog["dimensions"]["tsMemorySize"]["values"]
    assert ram["128gb"] == "128GB"
    assert ram["18gb"] == "18GB"
    assert ram["192gb"] == "192GB"
    assert label_for("dimensionColor", "silver") == "银色"
    assert label_for("dimensionColor", "blush") == "腮红色"
    assert label_for("tsMemorySize", "24gb") == "24GB"
    assert label_for("tsMemorySize", "128gb") == "128GB"
    assert label_for("dimensionconnectivity", "wifi") == "无线局域网"
    assert format_dim_value("13inch") == "13 英寸"
    assert format_dim_value("8_3inch") == "8.3 英寸"
    assert format_dim_value("wificell") == "无线局域网 + 蜂窝网络"
    assert format_dim_value("1_5tb") == "1.5TB"
    assert format_dim_value("1point5tb") == "1.5TB"


def test_catalog_overlay(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path))
    from apple_refurb_watch import filters as filters_mod

    filters_mod._cache["sig"] = None
    (tmp_path / "filter_catalog.json").write_text(
        json.dumps({"dimensions": {"dimensionColor": {"values": {"foobar": "测试色"}}}}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert label_for("dimensionColor", "foobar") == "测试色"
    assert label_for("dimensionColor", "silver") == "银色"
    filters_mod._cache["sig"] = None


def test_dim_filters_and_or() -> None:
    item = {
        "title": "翻新 14 英寸 MacBook Pro",
        "listing_key": "mac",
        "extra": {"dims": {"refurbClearModel": "macbookpro", "tsMemorySize": "24gb", "dimensionColor": "silver"}},
    }
    assert dims_match(item, {"tsMemorySize": ["24gb", "32gb"], "refurbClearModel": ["macbookpro"]})
    assert not dims_match(item, {"tsMemorySize": ["48gb"]})
    assert not dims_match(item, {"dimensionColor": ["spaceblack"]})
    gray = {"title": "iPad", "listing_key": "ipad", "extra": {"dims": {"dimensionColor": "spacegray"}}}
    assert dims_match(gray, {"dimensionColor": ["space_gray"]})
    assert matches_watch(item, {"mode": "condition", "dim_filters": {"tsMemorySize": ["24gb"]}})
    assert not matches_watch(item, {"mode": "condition", "dim_filters": {"tsMemorySize": ["64gb"]}})


def test_missing_dim_does_not_match() -> None:
    item = {"title": "翻新 MacBook Pro", "listing_key": "mac", "extra": {}}
    assert not dims_match(item, {"tsMemorySize": ["24gb"]})
    assert product_dims({"ram_gb": 24, "extra": {}})["tsMemorySize"] == "24gb"


def test_listing_facets_use_live_values() -> None:
    products = [
        {
            "title": "A",
            "listing_key": "mac",
            "extra": {"dims": {"refurbClearModel": "macbookpro", "tsMemorySize": "24gb"}},
        },
        {
            "title": "B",
            "listing_key": "mac",
            "extra": {"dims": {"refurbClearModel": "macbookair", "tsMemorySize": "16gb"}},
        },
    ]
    groups = {g["key"]: g for g in facet_groups(products, "mac", {"tsMemorySize": ["24gb"]}, include_catalog=False)}
    ram = {opt["value"]: opt for opt in groups["tsMemorySize"]["options"]}
    assert ram["24gb"]["checked"] is True
    assert ram["16gb"]["count"] == 1
    models = {g["key"]: g for g in facet_groups(products, "mac", {}, include_catalog=True, show_counts=False)}
    pro = next(opt for opt in models["refurbClearModel"]["options"] if opt["value"] == "macbookpro")
    assert "mac" in pro["listings"]
    ipad = next(opt for opt in models["refurbClearModel"]["options"] if opt["value"] == "ipadpro_13")
    assert ipad["listings"] == ["ipad"]
    assert "8tb" not in {opt["value"] for opt in groups.get("dimensionCapacity", {}).get("options", [])}


def test_selected_dims_from_query() -> None:
    class Params:
        def multi_items(self):
            return [("d_refurbClearModel", "macbookpro"), ("d_tsMemorySize", "24gb"), ("q", "M5")]

    assert selected_dims(Params()) == {"refurbClearModel": ["macbookpro"], "tsMemorySize": ["24gb"]}


def test_status_view_idle_and_ok() -> None:
    idle = present_status(
        {"scanning": False, "last_error": None, "last_success_at": None, "baseline_done": False},
        {"interval_seconds": 300},
        in_stock=0,
        watch_enabled=0,
        watch_total=0,
    )
    assert idle["label"] == "尚未扫描"
    assert idle["interval_label"] == "每 5 分钟"
    ok = present_status(
        {
            "scanning": False,
            "last_error": None,
            "last_success_at": "2026-08-28T08:00:00+00:00",
            "baseline_done": True,
        },
        {"interval_seconds": 120},
        in_stock=12,
        watch_enabled=2,
        watch_total=3,
    )
    assert ok["label"] == "监听中"
    assert ok["watch_enabled"] == 2
    assert format_interval(60) == "每 1 分钟"


def test_status_view_stopped() -> None:
    stopped = present_status(
        {
            "scanning": False,
            "last_error": None,
            "last_success_at": "2026-08-28T08:00:00+00:00",
            "baseline_done": True,
        },
        {"interval_seconds": 300, "listen_enabled": False},
        in_stock=12,
        watch_enabled=2,
        watch_total=3,
    )
    assert stopped["label"] == "已停止"
    assert stopped["state"] == "stopped"
    assert stopped["listen_enabled"] is False


def test_catalog_includes_oos_memory() -> None:
    groups = {g["key"]: g for g in facet_groups([], "mac", {}, include_catalog=True, show_counts=True)}
    rams = {opt["value"]: opt for opt in groups["tsMemorySize"]["options"]}
    assert rams["128gb"]["label"] == "128GB"
    assert rams["128gb"]["count"] == 0
    assert "18gb" in rams
    assert "192gb" in rams


def test_catalog_from_bootstrap_and_ingest(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path))
    from apple_refurb_watch import filters as filters_mod

    filters_mod._cache["sig"] = None
    bootstrap = {
        "dimensions": [
            {"key": "tsMemorySize", "legend": "内存", "sortOrder": 1},
            {"key": "dimensionColor", "legend": "外观", "sortOrder": 2},
        ],
        "dictionaries": {
            "dimensions": {
                "tsMemorySize": {
                    "24gb": {"sortOrder": 1, "text": "24GB"},
                    "128gb": {"sortOrder": 2, "text": "128GB"},
                },
                "dimensionColor": {
                    "blush": {"sortOrder": 1, "text": "腮红色"},
                },
            }
        },
    }
    fragment = catalog_from_bootstrap(bootstrap, "mac")
    assert fragment["listing_dimensions"]["mac"] == ["tsMemorySize", "dimensionColor"]
    assert fragment["dimensions"]["tsMemorySize"]["values"]["128gb"] == "128GB"
    assert fragment["listing_legends"]["mac"]["tsMemorySize"] == "内存"
    assert catalog_from_bootstrap({"dimensions": [{"key": "tsMemorySize"}]}, "mac") == {}

    ingest_bootstrap_catalog(bootstrap, "mac")
    assert live_catalog_path().exists()
    html = "<script>window.REFURB_GRID_BOOTSTRAP = " + json.dumps(bootstrap) + ";</script>"
    synced = sync_filter_catalog(lambda _url: html)
    assert synced["listing_legends"]["mac"]["tsMemorySize"] == "内存"
    assert synced["dimensions"]["tsMemorySize"]["values"]["128gb"] == "128GB"
    filters_mod._cache["sig"] = None
