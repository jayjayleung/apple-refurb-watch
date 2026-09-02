import asyncio
import threading

import pytest

from apple_refurb_watch.client import ApiError
from apple_refurb_watch.tui_app import build_watch_payload, create_tui
from apple_refurb_watch.watches import watch_condition_chips, watch_condition_label, watch_from_product


class FakeTuiClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.listing_params: list[dict] = []
        self.fail_listings = False
        self.fail_settings_update = False
        self.closed = False
        self.settings_data = {
            "listen_enabled": False,
            "interval_seconds": 300,
            "bind_host": "127.0.0.1",
            "bind_port": 8790,
            "listings": ["mac"],
        }
        self.watch_items = [
            {
                "id": 3,
                "enabled": True,
                "mode": "condition",
                "name": "14 MBP",
                "listing_key": "mac",
                "dim_filters": {"chip": ["m5"]},
            }
        ]
        self.event_items = [
            {
                "type": "scan_ok",
                "created_at": "2026-08-29T06:45:00+00:00",
                "title": None,
                "message": "完成扫描",
            }
        ]

    def listings(self, **params):
        self.calls.append("listings")
        self.listing_params.append(dict(params))
        if self.fail_listings:
            raise RuntimeError("在售请求失败")
        return {
            "items": [
                {
                    "sku": "AAAA4CH/A",
                    "title": "翻新 MacBook Pro",
                    "price": 15000,
                    "ram_gb": 24,
                    "storage_gb": 1024,
                    "listing_key": "mac",
                }
            ]
        }

    def status(self):
        self.calls.append("status")
        return {
            "view": {"label": "已停止", "detail": "定时扫描已暂停"},
            "watch_count": 1,
            "watch_total": 1,
            "in_stock": 1,
            "scanning": False,
            "last_success_at": "2026-08-29T06:45:00+00:00",
            "last_error": "",
        }

    def watches(self):
        self.calls.append("watches")
        return list(self.watch_items)

    def events(self, limit: int = 80):
        self.calls.append("events")
        return list(self.event_items)

    def settings(self):
        self.calls.append("settings")
        return dict(self.settings_data)

    def create_watch(self, data: dict):
        self.calls.append("create_watch")
        return {"id": 9, **data}

    def update_watch(self, watch_id: int, data: dict):
        self.calls.append("update_watch")
        return {"id": watch_id, **data}

    def delete_watch(self, watch_id: int):
        self.calls.append("delete_watch")
        return None

    def update_settings(self, data: dict):
        self.calls.append("update_settings")
        if self.fail_settings_update:
            raise RuntimeError("设置保存失败")
        self.settings_data.update(data)
        return dict(self.settings_data)

    def notify_test(self):
        self.calls.append("notify_test")
        return {"ok": True}

    def scan(self):
        self.calls.append("legacy_scan")
        return {"count": 1, "message": "扫描完成"}

    def submit_scan(self):
        self.calls.append("submit_scan")
        return {"accepted": True, "status": "queued", "scan_run_id": 11}

    def scan_run(self, run_id: int):
        self.calls.append(f"scan_run:{run_id}")
        return {"id": run_id, "status": "succeeded", "product_count": 1}

    def clear_events(self):
        self.calls.append("clear_events")
        return {"ok": True, "deleted": 1}

    def sync_catalog(self):
        self.calls.append("sync_catalog")
        return {"ok": True}

    def close(self):
        self.closed = True


async def settle(app, pilot, rounds: int = 2) -> None:
    for _ in range(rounds):
        await pilot.pause(0.03)
        await app.workers.wait_for_complete()
    if getattr(app, "client", None) is None:
        return
    for _ in range(40):
        if getattr(app, "_settings_ready", False):
            return
        await pilot.pause(0.03)
        await app.workers.wait_for_complete()


def test_build_watch_payload_validates_compact_form() -> None:
    payload = build_watch_payload(
        {
            "name": "",
            "listing_key": "mac",
            "mode": "condition",
            "dims": "chip=m5,tsMemorySize=24gb",
            "min_ram_gb": "24",
            "min_storage_gb": "512",
            "max_price": "18000",
        }
    )
    assert payload["name"] != "未命名规则"
    assert payload["dim_filters"] == {"chip": ["m5"], "tsMemorySize": ["24gb"]}
    assert payload["min_ram_gb"] == 24
    assert payload["min_storage_gb"] == 512
    assert payload["max_price"] == 18000

    sku = build_watch_payload({"listing_key": "mac", "mode": "sku", "sku": "aaaa4ch/a"})
    assert sku["name"] == "SKU AAAA4CH/A"
    assert sku["sku"] == "AAAA4CH/A"

    with pytest.raises(ValueError, match="必须填写 SKU"):
        build_watch_payload({"listing_key": "mac", "mode": "sku", "sku": ""})
    with pytest.raises(ValueError, match="最高价必须是数字"):
        build_watch_payload({"listing_key": "mac", "mode": "condition", "max_price": "很多"})
    with pytest.raises(ValueError, match="缺少 ="):
        build_watch_payload({"listing_key": "mac", "mode": "condition", "dims": "chip"})
    with pytest.raises(ValueError, match="未知维度"):
        build_watch_payload({"listing_key": "", "mode": "condition", "dims": "typoKey=value"})
    with pytest.raises(ValueError, match="最高价必须是"):
        build_watch_payload({"listing_key": "mac", "mode": "condition", "max_price": "nan"})
    with pytest.raises(ValueError, match="最高价必须是"):
        build_watch_payload({"listing_key": "mac", "mode": "condition", "max_price": "inf"})


def test_watch_from_product_modes() -> None:
    item = {
        "sku": "AAAA4CH/A",
        "title": "翻新 14 英寸 MacBook Pro Apple M5 Pro 芯片",
        "listing_key": "mac",
        "price": 15000,
        "ram_gb": 24,
        "storage_gb": 1024,
        "extra": {"dims": {"refurbClearModel": "macbookpro", "tsMemorySize": "24gb"}},
    }
    sku = watch_from_product(item, "sku")
    assert sku == {
        "name": "SKU AAAA4CH/A",
        "mode": "sku",
        "sku": "AAAA4CH/A",
        "listing_key": "mac",
    }
    condition = watch_from_product(item, "condition")
    assert condition["mode"] == "condition"
    assert condition["max_price"] == 15000
    assert condition["dim_filters"]["refurbClearModel"] == ["macbookpro"]
    assert condition["dim_filters"]["tsMemorySize"] == ["24gb"]
    assert condition["dim_filters"]["chip"] == ["m5_pro"]
    cored = watch_from_product(
        {
            **item,
            "title": "翻新 14 英寸 MacBook Pro Apple M5 Pro 芯片 (配备 12 核中央处理器和 16 核图形处理器)",
        },
        "condition",
    )
    assert cored["dim_filters"]["cores"] == ["12core_16core"]
    assert "cpu_cores" not in cored["dim_filters"]
    assert "gpu_cores" not in cored["dim_filters"]
    assert "Mac" in watch_condition_label({"listing_key": "macbook-pro", "dim_filters": {"chip": ["m5"]}})
    chips = watch_condition_chips({"listing_key": "macbook-pro", "dim_filters": {"chip": ["m5"]}})
    assert chips[0] == "MacBook Pro"
    assert "M5" in chips


def test_tui_four_panes_load() -> None:
    async def go() -> None:
        app = create_tui(FakeTuiClient())
        async with app.run_test() as pilot:
            await settle(app, pilot)
            assert {pane.id for pane in app.query("TabPane")} == {
                "listings",
                "watches",
                "events",
                "settings",
            }
            table = app.query_one("#table")
            assert table.row_count == 1
            assert "¥15,000" in str(table.get_row_at(0))
            assert "Mac" in str(table.get_row_at(0))
            assert app.query_one("#watch-table").row_count == 1
            assert app.query_one("#event-table").row_count == 1
            assert "已停止" in str(app.query_one("#status").render())
            assert app.query_one("#listing-mac").value is True
            assert app.query_one("#listing-ipad").value is False
            assert "Mac" in str(app.query_one("#family-label").render())
            assert "低→高" in str(app.query_one("#sort-label").render())
            assert "密钥请用网页设置" in str(app.query_one("#settings-note").render())
            assert app.client.listing_params[0]["listing_key"] == "mac"

            await pilot.press("o")
            await settle(app, pilot)
            assert "高→低" in str(app.query_one("#sort-label").render())

            await pilot.press("n")
            await pilot.pause()
            assert type(app.screen).__name__ == "WatchForm"
            await pilot.press("escape")
            await pilot.pause()
            assert type(app.screen).__name__ != "WatchForm"

    asyncio.run(go())


def test_tui_scan_uses_run_resource_and_keeps_ui_responsive() -> None:
    class SlowScanClient(FakeTuiClient):
        def __init__(self) -> None:
            super().__init__()
            self.release = threading.Event()

        def submit_scan(self):
            self.calls.append("submit_scan")
            self.release.wait(2)
            return {"accepted": True, "status": "queued", "scan_run_id": 21}

    async def go() -> None:
        client = SlowScanClient()
        app = create_tui(client)
        async with app.run_test() as pilot:
            await settle(app, pilot)
            await pilot.press("s")
            await pilot.pause(0.05)
            assert app.query_one("#scan").disabled is True
            assert "提交扫描" in str(app.sub_title or "")

            await pilot.press("2")
            await pilot.pause()
            assert app.query_one("TabbedContent").active == "watches"

            client.release.set()
            await settle(app, pilot, rounds=3)
            assert "submit_scan" in client.calls
            assert "scan_run:21" in client.calls
            assert "legacy_scan" not in client.calls
            assert app.query_one("#scan").disabled is False

    asyncio.run(go())


@pytest.mark.parametrize("status", [404, 405])
def test_tui_scan_falls_back_for_legacy_server(status: int) -> None:
    class LegacyClient(FakeTuiClient):
        def submit_scan(self):
            self.calls.append("submit_scan")
            raise ApiError("not found", status)

    async def go() -> None:
        client = LegacyClient()
        app = create_tui(client)
        async with app.run_test() as pilot:
            await settle(app, pilot)
            await pilot.press("s")
            await settle(app, pilot, rounds=3)
            assert "submit_scan" in client.calls
            assert "legacy_scan" in client.calls
            assert app.query_one("#scan").disabled is False

    asyncio.run(go())


def test_tui_scan_busy_does_not_use_legacy_endpoint() -> None:
    class BusyClient(FakeTuiClient):
        def submit_scan(self):
            self.calls.append("submit_scan")
            raise ApiError("已有扫描在进行", 409)

    async def go() -> None:
        client = BusyClient()
        app = create_tui(client)
        async with app.run_test() as pilot:
            await settle(app, pilot)
            await pilot.press("s")
            await settle(app, pilot)
            assert "legacy_scan" not in client.calls
            assert app.query_one("#scan").disabled is False
            assert "已有扫描在进行" in str(app.query_one("#status").render())

    asyncio.run(go())


def test_tui_legacy_busy_scan_is_not_marked_success() -> None:
    class LegacyBusyClient(FakeTuiClient):
        def submit_scan(self):
            self.calls.append("submit_scan")
            raise ApiError("not found", 404)

        def scan(self):
            self.calls.append("legacy_scan")
            return {"ok": False, "message": "已有扫描在进行"}

    async def go() -> None:
        client = LegacyBusyClient()
        app = create_tui(client)
        async with app.run_test() as pilot:
            await settle(app, pilot)
            await pilot.press("s")
            await settle(app, pilot)
            assert "legacy_scan" in client.calls
            assert "扫描完成" not in str(app.sub_title or "")
            assert "已有扫描在进行" in str(app.query_one("#status").render())

    asyncio.run(go())


def test_tui_settings_stay_disabled_until_loaded() -> None:
    async def go() -> None:
        client = FakeTuiClient()
        app = create_tui(client)
        async with app.run_test() as pilot:
            await settle(app, pilot)
            listen = app.query_one("#listen-switch")
            listing = app.query_one("#listing-mac")
            assert listen.disabled is False
            assert listing.value is True

            app._settings_ready = False
            app._set_settings_controls_enabled(False)
            assert listen.disabled is True
            assert listing.disabled is True

            listing.disabled = False
            listing.value = False
            await pilot.pause(0.05)
            await app.workers.wait_for_complete()
            assert listing.value is True
            assert client.settings_data["listings"] == ["mac"]
            assert "update_settings" not in client.calls

    asyncio.run(go())


def test_tui_status_poll_reloads_when_last_success_changes() -> None:
    class StatusClient(FakeTuiClient):
        def __init__(self) -> None:
            super().__init__()
            self.status_payload = {
                "view": {"label": "已停止", "detail": "定时扫描已暂停"},
                "watch_count": 1,
                "watch_total": 1,
                "in_stock": 1,
                "scanning": False,
                "last_success_at": "2026-08-29T06:45:00+00:00",
                "last_error": "",
            }

        def status(self):
            self.calls.append("status")
            return dict(self.status_payload)

    async def go() -> None:
        client = StatusClient()
        app = create_tui(client)
        async with app.run_test() as pilot:
            await settle(app, pilot)
            before = client.calls.count("listings")
            client.status_payload["last_success_at"] = "2026-08-29T07:00:00+00:00"
            app._poll_status()
            for _ in range(30):
                await settle(app, pilot, rounds=1)
                if client.calls.count("listings") > before:
                    break
            else:
                pytest.fail("last_success_at 变化后应刷新在售")

    asyncio.run(go())


def test_tui_failed_refresh_keeps_rows_and_failed_switch_rolls_back() -> None:
    async def go() -> None:
        client = FakeTuiClient()
        app = create_tui(client)
        async with app.run_test() as pilot:
            await settle(app, pilot)
            table = app.query_one("#table")
            assert table.row_count == 1

            client.fail_listings = True
            app.reload_listings()
            await settle(app, pilot)
            assert table.row_count == 1
            client.fail_listings = False

            client.fail_settings_update = True
            switch = app.query_one("#listen-switch")
            switch.value = True
            await settle(app, pilot)
            assert switch.value is False
            assert switch.disabled is False

    asyncio.run(go())


def test_tui_collapses_repeated_scan_events() -> None:
    async def go() -> None:
        client = FakeTuiClient()
        client.event_items.append(
            {
                "type": "scan_ok",
                "created_at": "2026-08-29T07:45:00+00:00",
                "title": None,
                "message": "完成扫描",
            }
        )
        app = create_tui(client)
        async with app.run_test() as pilot:
            await settle(app, pilot)
            assert app.query_one("#event-table").row_count == 1

    asyncio.run(go())


def test_tui_watch_form_shows_validation_error_and_narrow_layout() -> None:
    async def go() -> None:
        app = create_tui(FakeTuiClient())
        async with app.run_test() as pilot:
            await settle(app, pilot)
            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            assert app.screen.has_class("narrow")

            await pilot.press("n")
            await pilot.pause()
            app.screen.query_one("#watch-mode").value = "sku"
            app.screen.query_one("#save").focus()
            await pilot.press("enter")
            await pilot.pause()
            assert type(app.screen).__name__ == "WatchForm"
            assert "必须填写 SKU" in str(app.screen.query_one("#watch-error").render())

            app.screen.query_one("#watch-sku").value = "AAAA4CH/A"
            app.screen.query_one("#save").focus()
            await pilot.press("enter")
            await settle(app, pilot)
            assert type(app.screen).__name__ != "WatchForm"

    asyncio.run(go())


def test_tui_connects_after_mount_and_closes_owned_client() -> None:
    async def go() -> None:
        client = FakeTuiClient()
        release = threading.Event()

        def factory():
            release.wait(2)
            return client

        app = create_tui(client_factory=factory, owns_client=True)
        async with app.run_test() as pilot:
            await pilot.pause(0.05)
            assert "正在连接" in str(app.query_one("#status").render())
            await pilot.press("?")
            await pilot.pause()
            assert type(app.screen).__name__ == "HelpScreen"
            await pilot.press("escape")
            release.set()
            await settle(app, pilot, rounds=3)
            assert app.query_one("#table").row_count == 1
        assert client.closed is True

    asyncio.run(go())
