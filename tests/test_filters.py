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
    restrict_dims,
    selected_dims,
    sync_filter_catalog,
)
from apple_refurb_watch.match import matches_watch


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
    assert label_for("cpu_cores", "12core") == "12 核中央处理器"
    assert label_for("gpu_cores", "16core") == "16 核图形处理器"
    assert label_for("cores", "12core_16core") == "12 核 / 16 核"
    item = {
        "title": "翻新 14 英寸 MacBook Pro Apple M5 Pro 芯片 (配备 12 核中央处理器和 16 核图形处理器) - 银色",
        "listing_key": "mac",
        "extra": {"dims": {"refurbClearModel": "macbookpro"}},
    }
    assert product_dims(item)["cpu_cores"] == "12core"
    assert product_dims(item)["gpu_cores"] == "16core"
    assert product_dims(item)["cores"] == "12core_16core"
    assert dims_match(item, {"cpu_cores": ["12core"]})
    assert dims_match(item, {"cores": ["12core_16core"]})
    assert not dims_match(item, {"cpu_cores": ["10core"]})
    assert not dims_match(item, {"cores": ["10core_10core"]})
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


def test_family_facets_match_official_listings() -> None:
    assert facet_groups([], None, {}, include_catalog=True, include_chip=False, include_cores=False) == []
    mac = {
        g["key"]: g
        for g in facet_groups([], "mac", {}, include_catalog=True, include_chip=False, include_cores=False)
    }
    assert list(mac) == [
        "refurbClearModel",
        "dimensionScreensize",
        "dimensionRelYear",
        "dimensionColor",
        "tsMemorySize",
        "dimensionCapacity",
    ]
    models = {opt["value"] for opt in mac["refurbClearModel"]["options"]}
    assert {"macbookair", "macbookpro", "imac", "macmini", "macstudio", "macpro", "macbookneo", "display"} <= models
    assert "ipadpro_13" not in models
    assert "watchseries11" not in models
    sizes = {opt["value"] for opt in mac["dimensionScreensize"]["options"]}
    assert {"13inch", "14inch", "15inch", "16inch", "24inch", "27inch"} <= sizes
    assert "8_3inch" not in sizes
    assert "11inch" not in sizes
    colors = {opt["value"] for opt in mac["dimensionColor"]["options"]}
    assert "blush" in colors
    assert "spaceblack" in colors
    assert "rosegold" not in colors
    years = {opt["value"] for opt in mac["dimensionRelYear"]["options"]}
    assert "2019" in years
    assert "2026" in years
    caps = {opt["value"] for opt in mac["dimensionCapacity"]["options"]}
    assert "8tb" in caps
    assert "32gb" not in caps
    ipad = {
        g["key"]: g
        for g in facet_groups([], "ipad", {}, include_catalog=True, include_chip=False, include_cores=False)
    }
    assert list(ipad) == [
        "refurbClearModel",
        "dimensionColor",
        "dimensionScreensize",
        "dimensionCapacity",
        "dimensionconnectivity",
        "dimensionRelYear",
    ]
    ipad_models = {opt["value"] for opt in ipad["refurbClearModel"]["options"]}
    assert "ipadpro_13" in ipad_models
    assert "ipadair_11" in ipad_models
    assert "macbookpro" not in ipad_models
    ipad_sizes = {opt["value"] for opt in ipad["dimensionScreensize"]["options"]}
    assert {"8_3inch", "10_9inch", "11inch", "13inch"} <= ipad_sizes
    assert "14inch" not in ipad_sizes
    assert "24inch" not in ipad_sizes
    ipad_colors = {opt["value"] for opt in ipad["dimensionColor"]["options"]}
    assert "rosegold" in ipad_colors
    assert "blush" not in ipad_colors
    ipad_years = {opt["value"] for opt in ipad["dimensionRelYear"]["options"]}
    assert "2019" not in ipad_years
    assert "2026" not in ipad_years
    ipad_caps = {opt["value"] for opt in ipad["dimensionCapacity"]["options"]}
    assert "32gb" in ipad_caps
    assert "8tb" not in ipad_caps
    watch = {g["key"]: g for g in facet_groups([], "watch", {}, include_catalog=True)}
    assert list(watch) == [
        "refurbClearModel",
        "dimensionCaseSize",
        "dimensionCaseMaterial",
        "dimensionConnection",
    ]
    assert "watchultra3" in {opt["value"] for opt in watch["refurbClearModel"]["options"]}
    assert "49mm" in {opt["value"] for opt in watch["dimensionCaseSize"]["options"]}
    assert "stainless" in {opt["value"] for opt in watch["dimensionCaseMaterial"]["options"]}
    airpods = {g["key"]: g for g in facet_groups([], "airpods", {}, include_catalog=True)}
    assert list(airpods) == ["heroAirPods"]
    assert "airpodspro2023" in {opt["value"] for opt in airpods["heroAirPods"]["options"]}
    homepod = {
        g["key"]: g
        for g in facet_groups([], "homepod", {}, include_catalog=True, include_chip=False, include_cores=False)
    }
    assert list(homepod) == ["dimensionColor"]
    assert {opt["value"] for opt in homepod["dimensionColor"]["options"]} == {"midnight", "white"}
    accessories = {
        g["key"]: g
        for g in facet_groups([], "accessories", {}, include_catalog=True, include_chip=False, include_cores=False)
    }
    assert list(accessories) == ["refurbClearModel"]
    assert accessories["refurbClearModel"]["legend"] == "类别"
    acc_models = {opt["value"] for opt in accessories["refurbClearModel"]["options"]}
    assert {"ipadaccessories", "display", "airpods", "homepod"} <= acc_models
    assert "macbookpro" not in acc_models


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
    assert "cores" not in watch_keys
    assert "cpu_cores" not in watch_keys
    assert "gpu_cores" not in watch_keys
    pruned = prune_cascade_dims(
        "mac",
        {"refurbClearModel": ["macbookpro"], "tsMemorySize": ["4gb", "128gb"], "dimensionScreensize": ["13inch", "14inch"]},
    )
    assert pruned["tsMemorySize"] == ["128gb"]
    assert pruned["dimensionScreensize"] == ["14inch"]
    assert restrict_dims(
        {"refurbClearModel": ["macbookpro", "watchseries11"]},
        "watch",
    ) == {"refurbClearModel": ["watchseries11"]}
    assert restrict_dims({"refurbClearModel": ["macbookpro"]}, "mac") == {
        "refurbClearModel": ["macbookpro"]
    }


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
    assert "cpu_cores" not in groups
    assert "gpu_cores" not in groups
    assert "cores" not in groups
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
    assert {opt["value"] for opt in m5_pro["chip"]["options"]} == {"m5_pro", "m5_max"}
    cores = {
        g["key"]: g
        for g in facet_groups(
            products,
            "mac",
            {"cores": ["18core_40core"]},
            include_catalog=False,
            show_counts=True,
            refine=True,
        )
    }
    assert {opt["value"] for opt in cores["refurbClearModel"]["options"]} == {"macbookpro"}
    assert {opt["value"] for opt in cores["chip"]["options"]} == {"m5_max"}


def test_watch_cores_use_official_phrase() -> None:
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
        for g in facet_groups(products, "mac", {}, include_catalog=True, show_counts=True, cascade=True)
    }
    cores = {opt["value"]: opt for opt in groups["cores"]["options"]}
    assert cores["12core_16core"]["label"] == "12 核 / 16 核"
    assert cores["18core_40core"]["label"] == "18 核 / 40 核"
    assert cores["10core_8core"]["label"] == "10 核 / 8 核"
    assert groups["cores"]["legend"] == "中央处理器 / 图形处理器"
    assert groups["cores"]["layout"] == "chips"
    pro = {
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
    assert {opt["value"] for opt in pro["cores"]["options"]} == {"12core_16core"}
    assert {opt["label"] for opt in pro["cores"]["options"]} == {"12 核 / 16 核"}


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


def test_shop_in_stock_display_and_homepod_color_not_disabled() -> None:
    products = [
        {
            "title": "翻新 Studio Display - 标准玻璃面板 - 可调倾斜度及高度的支架",
            "listing_key": "accessories",
            "model_key": "display",
            "extra": {"dims": {"refurbClearModel": "display"}},
        },
        {
            "title": "翻新 HomePod (第二代) - 午夜色",
            "listing_key": "accessories",
            "model_key": "homepod",
            "color_label": "午夜色",
            "extra": {"dims": {"refurbClearModel": "homepod"}},
        },
        {
            "title": "翻新 HomePod (第二代) - 白色",
            "listing_key": "accessories",
            "model_key": "homepod",
            "color_label": "白色",
            "extra": {"dims": {"refurbClearModel": "homepod"}},
        },
    ]
    assert product_dims(products[1])["dimensionColor"] == "midnight"
    assert product_dims(products[2])["dimensionColor"] == "white"
    assert "dimensionColor" not in product_dims(products[0])
    mac = {g["key"]: g for g in facet_groups(products, "mac", {}, include_catalog=True, include_chip=False, include_cores=False, show_counts=True, refine=True)}
    display = next(opt for opt in mac["refurbClearModel"]["options"] if opt["value"] == "display")
    assert display["count"] == 1
    homepod = {
        g["key"]: g
        for g in facet_groups(
            products, "homepod", {}, include_catalog=True, include_chip=False, include_cores=False, show_counts=True, refine=True
        )
    }
    colors = {opt["value"]: opt for opt in homepod["dimensionColor"]["options"]}
    assert colors["midnight"]["count"] == 1
    assert colors["white"]["count"] == 1
