from apple_refurb_watch.status_view import (
    format_interval,
    format_localtime,
    format_reltime,
    present_event_days,
    present_status,
)


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
