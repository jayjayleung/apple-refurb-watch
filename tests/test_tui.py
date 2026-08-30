import asyncio

from apple_refurb_watch.tui_app import create_tui
from apple_refurb_watch.watches import watch_from_product


class FakeTuiClient:
    def listings(self, **params):
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
        return {
            "view": {"label": "已停止"},
            "watch_count": 1,
            "watch_total": 1,
            "in_stock": 1,
        }

    def watches(self):
        return [{"id": 3, "enabled": True, "mode": "condition", "name": "14 MBP"}]

    def events(self, limit: int = 80):
        return [
            {
                "type": "scan_ok",
                "created_at": "2026-08-29T06:45:00+00:00",
                "title": None,
                "message": "完成扫描",
            }
        ]

    def settings(self):
        return {
            "listen_enabled": False,
            "interval_seconds": 300,
            "bind_host": "127.0.0.1",
            "bind_port": 8790,
            "listings": ["mac"],
        }

    def create_watch(self, data: dict):
        return {"id": 9, **data}

    def update_watch(self, watch_id: int, data: dict):
        return {"id": watch_id, **data}

    def delete_watch(self, watch_id: int):
        return None

    def update_settings(self, data: dict):
        return data

    def notify_test(self):
        return {"ok": True}

    def scan(self):
        return {"count": 1, "message": "扫描完成"}

    def clear_events(self):
        return {"ok": True, "deleted": 1}


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


def test_tui_four_panes_load() -> None:
    async def go() -> None:
        app = create_tui(FakeTuiClient())
        async with app.run_test() as pilot:
            await pilot.pause()
            assert {pane.id for pane in app.query("TabPane")} == {
                "listings",
                "watches",
                "events",
                "settings",
            }
            table = app.query_one("#table")
            assert table.row_count == 1
            assert "¥15,000" in str(table.get_row_at(0))
            assert app.query_one("#watch-table").row_count == 1
            assert app.query_one("#event-table").row_count == 1
            assert "已停止" in str(app.query_one("#status").render())
            listings = str(app.query_one("#settings-listings").render())
            assert "电脑" in listings
            assert "Mac" in listings
            assert "平板" in listings

            await pilot.press("n")
            await pilot.pause()
            assert type(app.screen).__name__ == "WatchForm"
            await pilot.press("escape")
            await pilot.pause()
            assert type(app.screen).__name__ != "WatchForm"

    asyncio.run(go())
