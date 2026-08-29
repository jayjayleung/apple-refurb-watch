import json

from apple_refurb_watch.filters import (
    catalog_from_bootstrap,
    chip_from_title,
    cores_from_title,
    dims_match,
    facet_groups,
    format_dim_value,
    ingest_bootstrap_catalog,
    label_for,
    live_catalog_path,
    load_catalog,
    product_dims,
    prune_cascade_dims,
    selected_dims,
    sync_filter_catalog,
)
from apple_refurb_watch.match import matches_watch
from apple_refurb_watch.status_view import (
    format_interval,
    format_localtime,
    format_reltime,
    present_event_days,
    present_status,
)


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


def test_chip_from_title_prefers_longer_token() -> None:
    assert chip_from_title("翻新 14 英寸 MacBook Pro Apple M5 Pro 芯片") == "m5_pro"
    assert chip_from_title("翻新 MacBook Air Apple M5 芯片") == "m5"
    assert chip_from_title("翻新 11 英寸 iPad Air (M3) 无线局域网机型") == "m3"
    assert chip_from_title("翻新 iPad (A16) 无线局域网机型") == "a16"
    assert chip_from_title("翻新 MacBook Neo (Apple A18 Pro 芯片)") == "a18_pro"
    assert chip_from_title("翻新 14 英寸 MacBook Pro Apple M6 Pro 芯片") == "m6_pro"
    assert chip_from_title("翻新 Apple Watch Series 11") is None
    assert label_for("chip", "m6_pro") == "M6 Pro"
    assert cores_from_title("翻新 14 英寸 MacBook Pro Apple M5 Pro 芯片 (配备 12 核中央处理器和 16 核图形处理器) - 银色") == (
        "12core",
        "16core",
    )
    assert cores_from_title("芯片 (配\u200d备 10 核中央处理器和 10 核图形处理器)") == ("10core", "10core")
    assert cores_from_title("翻新 MacBook Neo (Apple A18 Pro 芯片) - 银色") == (None, None)
    assert label_for("cpu_cores", "12core") == "12 核"
    item = {
        "title": "翻新 14 英寸 MacBook Pro Apple M5 Pro 芯片 (配备 12 核中央处理器和 16 核图形处理器) - 银色",
        "listing_key": "mac",
        "extra": {"dims": {"refurbClearModel": "macbookpro"}},
    }
    assert product_dims(item)["cpu_cores"] == "12core"
    assert product_dims(item)["gpu_cores"] == "16core"
    assert dims_match(item, {"cpu_cores": ["12core"]})
    assert not dims_match(item, {"cpu_cores": ["10core"]})
    item = {
        "title": "翻新 14 英寸 MacBook Pro Apple M5 Pro 芯片",
        "listing_key": "mac",
        "extra": {"dims": {"refurbClearModel": "macbookpro"}},
    }
    assert product_dims(item)["chip"] == "m5_pro"
    assert dims_match(item, {"chip": ["m5_pro"]})
    assert not dims_match(item, {"chip": ["m5"]})


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
    model_values = {opt["value"] for opt in models["refurbClearModel"]["options"]}
    assert "ipadpro_13" not in model_values
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


def test_present_event_days_groups_and_labels() -> None:
    days = present_event_days(
        [
            {
                "type": "scan_ok",
                "message": "扫描完成：1 件在售",
                "created_at": "2026-08-29T06:45:00+00:00",
            },
            {
                "type": "appeared",
                "title": "翻新 MacBook Pro",
                "url": "https://www.apple.com.cn/shop/product/X",
                "created_at": "2026-08-29T07:00:00+00:00",
            },
            {
                "type": "scan_ok",
                "message": "扫描完成：2 件在售",
                "created_at": "2026-08-29T08:00:00+00:00",
            },
        ]
    )
    assert len(days) == 1
    assert days[0]["day"] == "2026-08-29"
    assert days[0]["entries"][0]["label"] == "上新"
    assert days[0]["entries"][0]["kind"] == "appear"
    assert days[0]["entries"][1]["label"] == "扫描完成"
    assert days[0]["entries"][1]["kind"] == "routine"
    assert days[0]["entries"][1]["message"].startswith("2 次扫描")


def test_format_localtime_utc_to_shanghai() -> None:
    assert format_localtime("2026-08-29T06:45:00+00:00") == "2026-08-29 14:45"
    assert format_localtime("2026-08-29T06:45:00Z") == "2026-08-29 14:45"
    assert format_localtime("2026-08-29T06:45:00") == "2026-08-29 14:45"
    assert format_localtime("") == ""
    assert format_localtime("not-a-time") == "not-a-time"


def test_format_reltime_old_uses_shanghai() -> None:
    assert format_reltime("2026-08-27T06:45:00+00:00") == "08-27 14:45"


def test_catalog_includes_oos_memory() -> None:
    groups = {g["key"]: g for g in facet_groups([], "mac", {}, include_catalog=True, show_counts=True)}
    rams = {opt["value"]: opt for opt in groups["tsMemorySize"]["options"]}
    assert rams["128gb"]["label"] == "128GB"
    assert rams["128gb"]["count"] == 0
    assert "18gb" in rams
    assert "192gb" in rams
    mac_sizes = {opt["value"] for opt in groups["dimensionScreensize"]["options"]}
    assert "14inch" in mac_sizes
    assert "8_3inch" not in mac_sizes
    mbp = {g["key"]: g for g in facet_groups([], "macbook-pro", {}, include_catalog=True, show_counts=True)}
    mbp_sizes = {opt["value"] for opt in mbp["dimensionScreensize"]["options"]}
    assert "14inch" in mbp_sizes
    assert "16inch" in mbp_sizes
    assert "8_3inch" not in mbp_sizes
    assert any(opt["value"] == "128gb" for opt in mbp["tsMemorySize"]["options"])
    mbp_models = {opt["value"] for opt in mbp["refurbClearModel"]["options"]}
    assert mbp_models == {"macbookpro"}


def test_model_cascade_keeps_oos_memory() -> None:
    products = [
        {
            "title": "翻新 14 英寸 MacBook Pro Apple M5 Pro 芯片",
            "listing_key": "mac",
            "extra": {"dims": {"refurbClearModel": "macbookpro", "tsMemorySize": "24gb", "dimensionScreensize": "14inch"}},
        },
        {
            "title": "翻新 MacBook Air Apple M4 芯片",
            "listing_key": "mac",
            "extra": {"dims": {"refurbClearModel": "macbookair", "tsMemorySize": "16gb", "dimensionScreensize": "13inch"}},
        },
    ]
    groups = {
        g["key"]: g
        for g in facet_groups(
            products,
            "mac",
            {"refurbClearModel": ["macbookpro"]},
            include_catalog=True,
            show_counts=True,
            cascade=True,
        )
    }
    rams = {opt["value"]: opt for opt in groups["tsMemorySize"]["options"]}
    assert "128gb" in rams
    assert rams["128gb"]["count"] == 0
    assert "24gb" in rams
    assert rams["24gb"]["count"] == 1
    assert "4gb" not in rams
    models = {opt["value"]: opt for opt in groups["refurbClearModel"]["options"]}
    assert models["macbookpro"]["checked"] is True
    assert models["macbookpro"]["count"] == 1
    assert models["macbookair"]["count"] == 1
    sizes = {opt["value"] for opt in groups["dimensionScreensize"]["options"]}
    assert "14inch" in sizes
    assert "16inch" in sizes
    assert "13inch" not in sizes
    assert "8_3inch" not in sizes
    colors = {opt["value"] for opt in groups["dimensionColor"]["options"]}
    assert "silver" in colors
    assert "blush" not in colors
    chips = {opt["value"]: opt for opt in groups["chip"]["options"]}
    assert chips["m5_pro"]["count"] == 1
    assert chips["m5_pro"]["label"] == "M5 Pro"
    assert "m4" in chips
    assert "a18_pro" not in chips
    assert "a16" not in chips
    implied = {
        g["key"]: g
        for g in facet_groups([], "macbook-pro", {}, include_catalog=True, show_counts=True, cascade=True)
    }
    assert any(opt["checked"] for opt in implied["refurbClearModel"]["options"] if opt["value"] == "macbookpro")
    assert "128gb" in {opt["value"] for opt in implied["tsMemorySize"]["options"]}
    assert "m5_pro" in {opt["value"] for opt in implied["chip"]["options"]}
    watch_keys = {g["key"] for g in facet_groups([], "watch", {}, include_catalog=True)}
    assert "chip" not in watch_keys
    assert "cpu_cores" not in watch_keys
    assert "gpu_cores" not in watch_keys
    pruned = prune_cascade_dims(
        "mac",
        {"refurbClearModel": ["macbookpro"], "tsMemorySize": ["4gb", "128gb"], "dimensionScreensize": ["13inch", "14inch"]},
    )
    assert pruned["tsMemorySize"] == ["128gb"]
    assert pruned["dimensionScreensize"] == ["14inch"]


def test_chip_cascade_narrows_size_keeps_oos_ram() -> None:
    products = [
        {
            "title": "翻新 14 英寸 MacBook Pro Apple M5 Pro 芯片",
            "listing_key": "mac",
            "extra": {
                "dims": {
                    "refurbClearModel": "macbookpro",
                    "tsMemorySize": "24gb",
                    "dimensionScreensize": "14inch",
                    "dimensionRelYear": "2026",
                }
            },
        },
        {
            "title": "翻新 16 英寸 MacBook Pro Apple M5 Max 芯片",
            "listing_key": "mac",
            "extra": {
                "dims": {
                    "refurbClearModel": "macbookpro",
                    "tsMemorySize": "36gb",
                    "dimensionScreensize": "16inch",
                    "dimensionRelYear": "2026",
                }
            },
        },
        {
            "title": "翻新 14 英寸 MacBook Pro Apple M6 Pro 芯片",
            "listing_key": "mac",
            "extra": {
                "dims": {
                    "refurbClearModel": "macbookpro",
                    "tsMemorySize": "48gb",
                    "dimensionScreensize": "14inch",
                }
            },
        },
    ]
    groups = {
        g["key"]: g
        for g in facet_groups(
            products,
            "mac",
            {"refurbClearModel": ["macbookpro"], "chip": ["m5_pro"]},
            include_catalog=True,
            show_counts=True,
            cascade=True,
        )
    }
    sizes = {opt["value"] for opt in groups["dimensionScreensize"]["options"]}
    assert sizes == {"14inch"}
    years = {opt["value"] for opt in groups["dimensionRelYear"]["options"]}
    assert years == {"2026"}
    rams = {opt["value"]: opt for opt in groups["tsMemorySize"]["options"]}
    assert "128gb" in rams
    assert rams["128gb"]["count"] == 0
    assert rams["24gb"]["count"] == 1
    chips = {opt["value"]: opt for opt in groups["chip"]["options"]}
    assert chips["m5_pro"]["checked"] is True
    assert chips["m5_pro"]["count"] == 1
    assert chips["m5_max"]["count"] == 1
    assert "m6_pro" in chips
    assert chips["m6_pro"]["label"] == "M6 Pro"
    assert "a18_pro" not in chips
    max_groups = {
        g["key"]: g
        for g in facet_groups(
            products,
            "mac",
            {"refurbClearModel": ["macbookpro"], "chip": ["m5_max"]},
            include_catalog=True,
            show_counts=True,
            cascade=True,
        )
    }
    max_sizes = {opt["value"] for opt in max_groups["dimensionScreensize"]["options"]}
    assert max_sizes == {"16inch"}
    pruned = prune_cascade_dims(
        "mac",
        {
            "refurbClearModel": ["macbookpro"],
            "chip": ["m5_pro"],
            "dimensionScreensize": ["14inch", "16inch"],
            "tsMemorySize": ["128gb"],
        },
        products,
    )
    assert pruned["dimensionScreensize"] == ["14inch"]
    assert pruned["tsMemorySize"] == ["128gb"]
    assert pruned["chip"] == ["m5_pro"]


def test_shop_refine_matches_in_stock_like_official() -> None:
    products = [
        {
            "title": "翻新 14 英寸 MacBook Pro Apple M5 Pro 芯片 (配备 12 核中央处理器和 16 核图形处理器)",
            "listing_key": "mac",
            "extra": {
                "dims": {
                    "refurbClearModel": "macbookpro",
                    "tsMemorySize": "24gb",
                    "dimensionScreensize": "14inch",
                }
            },
        },
        {
            "title": "翻新 16 英寸 MacBook Pro Apple M5 Max 芯片 (配备 18 核中央处理器和 40 核图形处理器)",
            "listing_key": "mac",
            "extra": {
                "dims": {
                    "refurbClearModel": "macbookpro",
                    "tsMemorySize": "36gb",
                    "dimensionScreensize": "16inch",
                }
            },
        },
        {
            "title": "翻新 MacBook Air Apple M4 芯片 (配备 10 核中央处理器和 8 核图形处理器)",
            "listing_key": "mac",
            "extra": {
                "dims": {
                    "refurbClearModel": "macbookair",
                    "tsMemorySize": "16gb",
                    "dimensionScreensize": "13inch",
                }
            },
        },
    ]
    groups = {
        g["key"]: g
        for g in facet_groups(products, "mac", {}, include_catalog=False, show_counts=True, refine=True)
    }
    rams = {opt["value"] for opt in groups["tsMemorySize"]["options"]}
    assert rams == {"24gb", "36gb", "16gb"}
    assert "128gb" not in rams
    assert {opt["value"] for opt in groups["cpu_cores"]["options"]} == {"12core", "18core", "10core"}
    assert {opt["label"] for opt in groups["gpu_cores"]["options"]} == {"16 核", "40 核", "8 核"}
    pro = {
        g["key"]: g
        for g in facet_groups(
            products,
            "mac",
            {"refurbClearModel": ["macbookpro"]},
            include_catalog=False,
            show_counts=True,
            refine=True,
        )
    }
    assert {opt["value"] for opt in pro["dimensionScreensize"]["options"]} == {"14inch", "16inch"}
    assert {opt["value"] for opt in pro["cpu_cores"]["options"]} == {"12core", "18core"}
    assert "macbookair" in {opt["value"] for opt in pro["refurbClearModel"]["options"]}
    m5_pro = {
        g["key"]: g
        for g in facet_groups(
            products,
            "mac",
            {"refurbClearModel": ["macbookpro"], "chip": ["m5_pro"]},
            include_catalog=False,
            show_counts=True,
            refine=True,
        )
    }
    assert {opt["value"] for opt in m5_pro["dimensionScreensize"]["options"]} == {"14inch"}
    assert {opt["value"] for opt in m5_pro["cpu_cores"]["options"]} == {"12core"}
    assert {opt["value"] for opt in m5_pro["chip"]["options"]} == {"m5_pro", "m5_max"}
    cores = {
        g["key"]: g
        for g in facet_groups(
            products,
            "mac",
            {"cpu_cores": ["18core"]},
            include_catalog=False,
            show_counts=True,
            refine=True,
        )
    }
    assert {opt["value"] for opt in cores["refurbClearModel"]["options"]} == {"macbookpro"}
    assert {opt["value"] for opt in cores["chip"]["options"]} == {"m5_max"}


def test_listing_facets_ignore_other_category_stock() -> None:
    products = [
        {
            "title": "iPad mini",
            "listing_key": "ipad",
            "extra": {"dims": {"refurbClearModel": "ipadmini6", "dimensionScreensize": "8_3inch"}},
        },
        {
            "title": "翻新 MacBook Pro",
            "listing_key": "mac",
            "extra": {"dims": {"refurbClearModel": "macbookpro", "dimensionScreensize": "14inch"}},
        },
    ]
    groups = {
        g["key"]: g
        for g in facet_groups(products, "mac", {}, include_catalog=True, show_counts=True, cascade=True)
    }
    sizes = {opt["value"] for opt in groups["dimensionScreensize"]["options"]}
    assert "14inch" in sizes
    assert "8_3inch" not in sizes


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
