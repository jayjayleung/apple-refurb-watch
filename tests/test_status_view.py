from apple_refurb_watch.status_view import (
    format_interval,
    format_localtime,
    format_reltime,
    paginate_event_days,
    present_event_days,
    present_status,
)
from apple_refurb_watch.watches import appeared_message, present_watch_hits, watch_condition_chips


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
    assert [item["label"] for item in days[0]["entries"]] == ["扫描完成", "上新", "扫描完成"]
    named = present_event_days(
        [
            {
                "type": "appeared",
                "watch_id": 6,
                "title": "翻新 16 英寸 MacBook Pro",
                "created_at": "2026-08-30T15:44:46+00:00",
            }
        ],
        watch_names={6: "16 寸 M5 Max"},
    )
    assert named[0]["entries"][0]["label"] == "上新 · 16 寸 M5 Max"
    assert days[0]["entries"][0]["when_local"] == "2026-08-29 16:00"
    assert days[0]["entries"][1]["kind"] == "appear"
    assert days[0]["entries"][1]["when_local"] == "2026-08-29 15:00"
    assert days[0]["entries"][2]["when_local"] == "2026-08-29 14:45"
    assert not any("次扫描" in str(item.get("message") or "") for item in days[0]["entries"])
    collapsed = present_event_days(
        [
            {
                "type": "scan_ok",
                "message": "扫描完成：2 件在售",
                "created_at": "2026-08-29T08:00:00+00:00",
            },
            {
                "type": "appeared",
                "title": "翻新 MacBook Pro",
                "created_at": "2026-08-29T07:00:00+00:00",
            },
            {
                "type": "scan_ok",
                "message": "扫描完成：1 件在售",
                "created_at": "2026-08-29T06:45:00+00:00",
            },
        ],
        collapse_scans=True,
    )
    assert len(collapsed) == 1
    assert [item["kind"] for item in collapsed[0]["entries"]] == ["routine", "appear"]
    assert collapsed[0]["entries"][1]["title"] == "翻新 MacBook Pro"
    assert "2 次扫描 · 最近 16:00" in collapsed[0]["entries"][0]["message"]
    later_appear = present_event_days(
        [
            {
                "type": "appeared",
                "title": "翻新 MacBook Pro",
                "created_at": "2026-08-29T09:00:00+00:00",
            },
            {
                "type": "scan_ok",
                "message": "扫描完成：1 件在售",
                "created_at": "2026-08-29T08:00:00+00:00",
            },
        ],
        collapse_scans=True,
    )
    assert [item["kind"] for item in later_appear[0]["entries"]] == ["routine", "appear"]


def test_paginate_event_days_splits_entries() -> None:
    days = present_event_days(
        [
            {"type": "scan_ok", "message": f"scan {i}", "created_at": f"2026-08-29T08:{i:02d}:00+00:00"}
            for i in range(21)
        ]
    )
    first = paginate_event_days(days, 1, page_size=20)
    second = paginate_event_days(days, 2, page_size=20)
    overflow = paginate_event_days(days, 99, page_size=20)
    assert first["event_total"] == 21
    assert first["event_pages"] == 2
    assert first["has_next"] is True
    assert first["has_prev"] is False
    assert len(first["event_days"][0]["entries"]) == 20
    assert len(second["event_days"][0]["entries"]) == 1
    assert second["event_page"] == 2
    assert overflow["event_page"] == 2
    empty = paginate_event_days([], "nope")
    assert empty["event_page"] == 1
    assert empty["event_total"] == 0
    assert empty["event_day_total"] == 0
    assert empty["event_days"] == []


def test_paginate_all_records_is_newest_first() -> None:
    events = [
        {"type": "scan_ok", "message": f"scan {i}", "created_at": f"2026-08-31T08:{i:02d}:00+00:00"}
        for i in range(20)
    ]
    events.append(
        {
            "type": "appeared",
            "title": "翻新 16 英寸 MacBook Pro",
            "created_at": "2026-08-30T15:44:00+00:00",
        }
    )
    days = present_event_days(events)
    first = paginate_event_days(days, 1, page_size=20)
    second = paginate_event_days(days, 2, page_size=20)
    times = [item.get("when_local") for day in first["event_days"] for item in day["entries"]]
    kinds = [item.get("kind") for day in first["event_days"] for item in day["entries"]]
    assert kinds[0] == "routine"
    assert times == sorted(times, reverse=True)
    titles = [item.get("title") for day in second["event_days"] for item in day["entries"]]
    assert "翻新 16 英寸 MacBook Pro" in titles


def test_paginate_event_days_by_day_keeps_days_whole() -> None:
    days = present_event_days(
        [
            {"type": "scan_ok", "message": f"day {d}", "created_at": f"2026-08-{d:02d}T08:00:00+00:00"}
            for d in range(22, 30)
        ]
        + [
            {"type": "appeared", "title": "上新", "created_at": "2026-08-29T09:00:00+00:00"},
        ]
    )
    assert len(days) == 8
    first = paginate_event_days(days, 1, by_day=True, page_size=7)
    second = paginate_event_days(days, 2, by_day=True, page_size=7)
    assert first["event_day_total"] == 8
    assert first["event_pages"] == 2
    assert first["event_total"] == 9
    assert [day["day"] for day in first["event_days"]] == [
        "2026-08-29",
        "2026-08-28",
        "2026-08-27",
        "2026-08-26",
        "2026-08-25",
        "2026-08-24",
        "2026-08-23",
    ]
    assert [day["day"] for day in second["event_days"]] == ["2026-08-22"]
    assert len(first["event_days"][0]["entries"]) == 2


def test_format_localtime_utc_to_shanghai() -> None:
    assert format_localtime("2026-08-29T06:45:00+00:00") == "2026-08-29 14:45"
    assert format_localtime("2026-08-29T06:45:00Z") == "2026-08-29 14:45"
    assert format_localtime("2026-08-29T06:45:00") == "2026-08-29 14:45"
    assert format_localtime("") == ""
    assert format_localtime("not-a-time") == "not-a-time"


def test_display_tz_falls_back_without_iana(monkeypatch) -> None:
    import apple_refurb_watch.status_view as status_mod
    from datetime import timedelta, timezone
    from zoneinfo import ZoneInfoNotFoundError

    def boom(_key):
        raise ZoneInfoNotFoundError("Asia/Shanghai")

    monkeypatch.setattr(status_mod, "ZoneInfo", boom)
    assert status_mod._display_tz() == timezone(timedelta(hours=8))


def test_format_reltime_old_uses_shanghai() -> None:
    assert format_reltime("2026-08-27T06:45:00+00:00") == "08-27 14:45"


def test_present_event_shows_specs_and_watch_chips() -> None:
    watch = {
        "id": 4,
        "name": "14 寸 M5 Max",
        "listing_key": "macbook-pro",
        "dim_filters": {"chip": ["m5_max"], "dimensionScreensize": ["14inch"]},
        "min_ram_gb": 64,
    }
    days = present_event_days(
        [
            {
                "type": "appeared",
                "watch_id": 4,
                "title": "翻新 14 英寸 MacBook Pro",
                "price": 45499,
                "ram_gb": 128,
                "storage_gb": 2048,
                "sku": "G1MN4CH/A",
                "message": appeared_message(
                    title="翻新 14 英寸 MacBook Pro",
                    sku="G1MN4CH/A",
                    ram_gb=128,
                    storage_gb=2048,
                    price=45499,
                    watch=watch,
                ),
                "created_at": "2026-09-01T06:16:12+00:00",
            }
        ],
        watches={4: watch},
    )
    entry = days[0]["entries"][0]
    assert entry["label"] == "上新 · 14 寸 M5 Max"
    assert entry["spec_line"] == "128GB 内存 · 2TB 硬盘 · RMB 45,499"
    assert "MacBook Pro" in entry["watch_chips"]
    assert "M5 Max" in entry["watch_chips"]
    assert any("64" in chip for chip in entry["watch_chips"])
    assert "命中：" in (entry["message"] or "")


def test_present_event_keeps_message_specs_when_fields_missing() -> None:
    days = present_event_days(
        [
            {
                "type": "appeared",
                "title": "翻新 14 英寸 MacBook Pro Apple M5 Max 芯片 和纳米纹理显示屏 - 银色",
                "price": 46399,
                "sku": "G1MK5CH/A",
                "message": (
                    "翻新 14 英寸 MacBook Pro Apple M5 Max 芯片 和纳米纹理显示屏 - 银色\n"
                    "128GB 内存 · 2TB 硬盘 · RMB 46,399\n"
                    "G1MK5CH/A"
                ),
                "created_at": "2026-09-01T06:16:12+00:00",
            }
        ]
    )
    assert days[0]["entries"][0]["spec_line"] == "128GB 内存 · 2TB 硬盘 · RMB 46,399"


def test_appeared_message_and_chips_match_watch_page() -> None:
    watch = {
        "listing_key": "macbook-pro",
        "dim_filters": {"chip": ["m5_max"]},
        "min_ram_gb": 64,
    }
    body = appeared_message(
        title="翻新 MacBook Pro",
        sku="G1MK7CH/A",
        ram_gb=64,
        storage_gb=1024,
        price=18999,
        watch=watch,
    )
    assert "命中：" in body
    assert "RMB 18,999" in body
    chips = watch_condition_chips(watch)
    assert chips[0] == "MacBook Pro"
    assert "M5 Max" in chips


def test_present_watch_hits_puts_in_stock_first() -> None:
    hits = present_watch_hits(
        [
            {
                "sku": "G1MK5CH/A",
                "in_stock": 0,
                "title": "已下架",
                "price": 100,
                "url": "https://www.apple.com.cn/shop/product/g1mk5ch/a",
            },
            {
                "sku": "G1MK7CH/A",
                "in_stock": 1,
                "title": "在售",
                "price": 200,
                "url": "https://www.apple.com.cn/shop/product/g1mk7ch/a",
            },
        ]
    )
    assert [item["sku"] for item in hits] == ["G1MK7CH/A", "G1MK5CH/A"]
    assert hits[0]["in_stock"] is True
    assert hits[1]["in_stock"] is False
    assert hits[0]["url"].endswith("/g1mk7ch/a")


def test_paginate_watch_hits_clamps_page() -> None:
    from apple_refurb_watch.watches import paginate_watch_hits, watch_hits_url

    rows = [{"sku": f"SKU{i:02d}", "in_stock": 0, "title": f"T{i:02d}"} for i in range(21)]
    first = paginate_watch_hits(present_watch_hits(rows), 1, page_size=20)
    second = paginate_watch_hits(present_watch_hits(rows), 99, page_size=20)
    empty = paginate_watch_hits([], "nope")
    assert first["hit_page"] == 1
    assert first["hit_pages"] == 2
    assert first["has_next"] is True
    assert len(first["hits"]) == 20
    assert second["hit_page"] == 2
    assert len(second["hits"]) == 1
    assert empty["hit_page"] == 1
    assert empty["hit_total"] == 0
    assert watch_hits_url(4, 1) == "/watches/4"
    assert watch_hits_url(4, 2) == "/watches/4?page=2"


def test_listen_stock_count_caches_until_scan_stamp_changes(tmp_path) -> None:
    from apple_refurb_watch.db import Database
    from apple_refurb_watch.status_view import clear_listen_stock_cache, load_status

    clear_listen_stock_cache()
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["macbook-pro"])
    db.set_setting("last_scan_at", "2026-09-04T00:00:00+00:00")
    db.set_setting("last_product_count", 1)
    db.upsert_products(
        [
            {
                "sku": "PRO1CH/A",
                "title": "翻新 MacBook Pro",
                "url": "https://www.apple.com.cn/shop/product/PRO1CH/A",
                "price": 9999,
                "listing_key": "macbook-pro",
            }
        ]
    )
    calls = {"n": 0}
    orig = db.list_products

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        return orig(*args, **kwargs)

    db.list_products = wrapped
    assert load_status(db)["in_stock"] == 1
    assert load_status(db)["in_stock"] == 1
    assert calls["n"] == 1
    db.set_setting("last_scan_at", "2026-09-04T01:00:00+00:00")
    assert load_status(db)["in_stock"] == 1
    assert calls["n"] == 2
    clear_listen_stock_cache()


def test_listen_stock_count_caches_sql_count(tmp_path) -> None:
    from apple_refurb_watch.db import Database
    from apple_refurb_watch.status_view import clear_listen_stock_cache, load_status

    clear_listen_stock_cache()
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["ipad"])
    db.set_setting("last_scan_at", "2026-09-04T00:00:00+00:00")
    calls = {"n": 0}
    orig = db.count_products

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        return orig(*args, **kwargs)

    db.count_products = wrapped
    load_status(db)
    load_status(db)
    assert calls["n"] == 1
    db.set_setting("last_product_count", 9)
    load_status(db)
    assert calls["n"] == 2
    clear_listen_stock_cache()
