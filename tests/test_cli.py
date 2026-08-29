import json

from typer.testing import CliRunner

from apple_refurb_watch.cli import app
from apple_refurb_watch.db import Database

runner = CliRunner()


class FakeClient:
    def __init__(self) -> None:
        self.created: dict | None = None
        self.patched: dict | None = None

    def listings(self, **params):
        return {
            "items": [
                {
                    "sku": "AAAA4CH/A",
                    "title": "翻新 MacBook Pro",
                    "price": 15000,
                    "ram_gb": 24,
                    "storage_gb": 1024,
                }
            ]
        }

    def watches(self):
        return [
            {"id": 3, "enabled": True, "mode": "condition", "name": "14 MBP"},
            {"id": 4, "enabled": False, "mode": "sku", "name": "SKU X"},
        ]

    def events(self, limit: int = 50):
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
            "listen_enabled": True,
            "interval_seconds": 300,
            "bind_host": "0.0.0.0",
            "bind_port": 8766,
            "lan_enabled": True,
            "listings": ["mac"],
            "access_token": "",
        }

    def create_watch(self, data: dict):
        self.created = data
        return {"id": 9, **data}

    def update_settings(self, data: dict):
        self.patched = data
        return {**self.settings(), **data}

    def scan(self):
        return {"ok": True, "count": 2}

    def clear_events(self):
        return {"ok": True, "deleted": 2}


def test_home_prints_data_dir(tmp_path, monkeypatch) -> None:
    result = runner.invoke(app, ["home"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_list_local_human_table() -> None:
    db = Database()
    db.upsert_products(
        [
            {
                "sku": "AAAA4CH/A",
                "title": "翻新 MacBook Pro",
                "url": "https://www.apple.com.cn/shop/product/AAAA4CH/A",
                "price": 15000,
                "listing_key": "mac",
                "ram_gb": 24,
                "storage_gb": 1024,
            }
        ]
    )
    result = runner.invoke(app, ["list", "--local"])
    assert result.exit_code == 0
    assert "¥15,000" in result.stdout
    assert "24GB" in result.stdout
    assert "1TB" in result.stdout
    assert "RMB" not in result.stdout
    json_out = runner.invoke(app, ["list", "--local", "--json"])
    assert json_out.exit_code == 0
    items = json.loads(json_out.stdout)
    assert items[0]["sku"] == "AAAA4CH/A"


def test_watch_ls_events_settings_and_dim(monkeypatch) -> None:
    fake = FakeClient()
    monkeypatch.setattr("apple_refurb_watch.cli._client", lambda: fake)

    ls = runner.invoke(app, ["watch", "ls"])
    assert ls.exit_code == 0
    assert "启用" in ls.stdout
    assert "暂停" in ls.stdout
    assert "精确 SKU" in ls.stdout
    assert "on " not in ls.stdout

    ls_json = runner.invoke(app, ["watch", "ls", "--json"])
    assert json.loads(ls_json.stdout)[0]["id"] == 3

    events = runner.invoke(app, ["events"])
    assert events.exit_code == 0
    assert "2026-08-29 14:45" in events.stdout
    assert "扫描完成" in events.stdout

    events_json = runner.invoke(app, ["events", "--json"])
    payload = json.loads(events_json.stdout)
    assert payload[0]["created_at"] == "2026-08-29T06:45:00+00:00"

    settings = runner.invoke(app, ["settings", "get"])
    assert settings.exit_code == 0
    assert "监听  开" in settings.stdout
    assert "8766" in settings.stdout
    assert "分类  Mac" in settings.stdout

    cleared = runner.invoke(app, ["events", "clear"])
    assert cleared.exit_code == 0
    assert "已清除 2 条记录" in cleared.stdout

    added = runner.invoke(
        app,
        [
            "watch",
            "add",
            "--name",
            "M5 24G",
            "--dim",
            "chip=m5",
            "--dim",
            "tsMemorySize=24gb",
        ],
    )
    assert added.exit_code == 0
    assert fake.created is not None
    assert fake.created["dim_filters"] == {"chip": ["m5"], "tsMemorySize": ["24gb"]}
    assert json.loads(added.stdout)["name"] == "M5 24G"

    bad = runner.invoke(app, ["watch", "add", "--name", "x", "--dim", "chip"])
    assert bad.exit_code == 2
    assert "key=value" in bad.stderr

    scan = runner.invoke(app, ["scan"])
    assert scan.exit_code == 0
    assert json.loads(scan.stdout)["ok"] is True

    patched = runner.invoke(app, ["settings", "set", "--interval", "120", "--no-listen"])
    assert patched.exit_code == 0
    assert fake.patched == {"interval_seconds": 120, "listen_enabled": False}

    empty = runner.invoke(app, ["settings", "set"])
    assert empty.exit_code == 1
