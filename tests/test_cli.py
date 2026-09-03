import json

from typer.testing import CliRunner

from apple_refurb_watch.cli import app
from apple_refurb_watch.db import Database

runner = CliRunner()


def invoke(args, **kwargs):
    # GitHub Actions 默认 80 列，Rich 会把 --help 画进窄框，选项名被截掉。
    env = {"COLUMNS": "120", "NO_COLOR": "1", "TERM": "dumb"}
    env.update(kwargs.pop("env", None) or {})
    return runner.invoke(app, args, env=env, color=False, **kwargs)


class FakeClient:
    def __init__(self) -> None:
        self.created: dict | None = None
        self.patched: dict | None = None

    def listings(self, **params):
        self.listed = params
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

    def watches(self):
        return [
            {
                "id": 3,
                "enabled": True,
                "mode": "condition",
                "name": "14 MBP",
                "listing_key": "mac",
                "dim_filters": {"chip": ["m5"]},
            },
            {"id": 4, "enabled": False, "mode": "sku", "name": "SKU X", "sku": "XXXX4CH/A"},
        ]

    def events(self, limit: int = 50):
        return [
            {
                "type": "appeared",
                "created_at": "2026-08-29T07:00:00+00:00",
                "title": "翻新 MacBook Pro",
                "message": None,
                "watch_id": 3,
            },
            {
                "type": "scan_ok",
                "created_at": "2026-08-29T06:45:00+00:00",
                "title": None,
                "message": "完成扫描",
            },
        ]

    def settings(self):
        return {
            "listen_enabled": True,
            "interval_seconds": 300,
            "bind_host": "0.0.0.0",
            "bind_port": 8766,
            "lan_enabled": True,
            "listings": ["macbook-pro"],
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

    def sync_catalog(self):
        return {"ok": True}


def test_home_prints_data_dir(tmp_path, monkeypatch) -> None:
    result = invoke(["home"])
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
    result = invoke(["list", "--local"])
    assert result.exit_code == 0
    assert "¥15,000" in result.stdout
    assert "24GB" in result.stdout
    assert "1TB" in result.stdout
    assert "RMB" not in result.stdout
    json_out = invoke(["list", "--local", "--json"])
    assert json_out.exit_code == 0
    items = json.loads(json_out.stdout)
    assert items[0]["sku"] == "AAAA4CH/A"


def test_list_local_listen_scope_sort_and_dim() -> None:
    db = Database()
    db.update_settings({"listings": ["mac"]})
    db.upsert_products(
        [
            {
                "sku": "PRO1CH/A",
                "title": "翻新 MacBook Pro",
                "url": "https://www.apple.com.cn/shop/product/PRO1CH/A",
                "price": 15000,
                "listing_key": "mac",
                "ram_gb": 24,
                "storage_gb": 1024,
                "extra": {"dims": {"tsMemorySize": "24gb"}},
            },
            {
                "sku": "AIR1CH/A",
                "title": "翻新 MacBook Air",
                "url": "https://www.apple.com.cn/shop/product/AIR1CH/A",
                "price": 8000,
                "listing_key": "mac",
                "ram_gb": 16,
                "extra": {"dims": {"tsMemorySize": "16gb"}},
            },
            {
                "sku": "PAD1CH/A",
                "title": "翻新 iPad",
                "url": "https://www.apple.com.cn/shop/product/PAD1CH/A",
                "price": 4000,
                "listing_key": "ipad",
            },
        ]
    )
    shown = invoke(["list", "--local"])
    assert shown.exit_code == 0
    assert "PRO1CH/A" in shown.stdout
    assert "AIR1CH/A" in shown.stdout
    assert "PAD1CH/A" not in shown.stdout
    assert shown.stdout.index("AIR1CH/A") < shown.stdout.index("PRO1CH/A")
    desc = invoke(["list", "--local", "--sort", "-price"])
    assert desc.stdout.index("PRO1CH/A") < desc.stdout.index("AIR1CH/A")
    dimmed = invoke(["list", "--local", "--dim", "tsMemorySize=24gb"])
    assert "PRO1CH/A" in dimmed.stdout
    assert "AIR1CH/A" not in dimmed.stdout


def test_watch_ls_events_settings_and_dim(monkeypatch) -> None:
    fake = FakeClient()
    monkeypatch.setattr("apple_refurb_watch.cli._client", lambda: fake)

    ls = invoke(["watch", "ls"])
    assert ls.exit_code == 0
    assert "启用" in ls.stdout
    assert "暂停" in ls.stdout
    assert "精确 SKU" in ls.stdout
    assert "在售" in ls.stdout
    assert "Mac" in ls.stdout
    assert "on " not in ls.stdout

    ls_json = invoke(["watch", "ls", "--json"])
    assert json.loads(ls_json.stdout)[0]["id"] == 3

    events = invoke(["events"])
    assert events.exit_code == 0
    assert "2026-08-29 14:45" in events.stdout
    assert "扫描完成" in events.stdout
    assert "上新 · 14 MBP" in events.stdout

    events_json = invoke(["events", "--json"])
    payload = json.loads(events_json.stdout)
    assert payload[0]["type"] == "appeared"
    assert payload[0]["created_at"] == "2026-08-29T07:00:00+00:00"

    settings = invoke(["settings", "get"])
    assert settings.exit_code == 0
    assert "监听  开" in settings.stdout
    assert "8766" in settings.stdout
    assert "分类  Mac" in settings.stdout
    assert "MacBook Pro" not in settings.stdout

    cleared = invoke(["events", "clear"])
    assert cleared.exit_code == 0
    assert "已清除 2 条记录" in cleared.stdout

    added = invoke(
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

    bad = invoke(["watch", "add", "--name", "x", "--dim", "chip"])
    assert bad.exit_code == 2
    assert "key=value" in bad.stderr

    scan = invoke(["scan"])
    assert scan.exit_code == 0
    assert json.loads(scan.stdout)["ok"] is True

    listed = invoke(["list", "--listing", "mac", "--sort", "-price", "--dim", "chip=m5"])
    assert listed.exit_code == 0
    assert fake.listed["listing_key"] == "mac"
    assert fake.listed["sort"] == "-price"
    assert fake.listed["dim_filters"] == {"chip": ["m5"]}
    assert "Mac" in listed.stdout

    patched = invoke(["settings", "set", "--interval", "120", "--no-listen"])
    assert patched.exit_code == 0
    assert fake.patched == {"interval_seconds": 120, "listen_enabled": False}

    lan = invoke(["settings", "set", "--lan"])
    assert lan.exit_code == 0
    assert fake.patched == {"lan_enabled": True}

    synced = invoke(["settings", "sync-catalog"])
    assert synced.exit_code == 0
    assert "已从官网同步筛选词条" in synced.stdout

    empty = invoke(["settings", "set"])
    assert empty.exit_code == 1


def test_list_local_refuses_remote() -> None:
    from apple_refurb_watch.connection import save_connection

    save_connection("http://127.0.0.1:9999", "x")
    result = invoke(["list", "--local"])
    assert result.exit_code == 2
    assert "--local" in result.stderr


def test_connect_and_disconnect(monkeypatch) -> None:
    monkeypatch.delenv("APPLE_REFURB_WATCH_URL", raising=False)
    monkeypatch.delenv("APPLE_REFURB_WATCH_TOKEN", raising=False)
    connected = invoke(["connect", "http://10.0.0.5:8765", "--token", "abc"])
    assert connected.exit_code == 0
    assert "10.0.0.5" in connected.stdout
    from apple_refurb_watch.connection import load_connection

    assert load_connection().token == "abc"
    gone = invoke(["disconnect"])
    assert gone.exit_code == 0
    assert load_connection().mode == "local"


def test_desktop_help() -> None:
    result = invoke(["desktop", "--help"])
    assert result.exit_code == 0
    assert "--hidden" in result.stdout
    assert "--probe" in result.stdout


def test_service_install_help() -> None:
    result = invoke(["service", "install", "--help"])
    assert result.exit_code == 0
    assert "--serve" in result.stdout
    assert "--tray" in result.stdout


def test_service_start_help() -> None:
    result = invoke(["service", "start", "--help"])
    assert result.exit_code == 0
    result = invoke(["service", "--help"])
    assert "start" in result.stdout
    assert "stop" in result.stdout
    assert "restart" in result.stdout


def test_service_start_without_install(monkeypatch) -> None:
    monkeypatch.setattr("apple_refurb_watch.service.is_service_installed", lambda: False)
    result = invoke(["service", "start"])
    assert result.exit_code == 1
    assert "service install" in result.stderr


def test_maintenance_commands_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("APPLE_REFURB_WATCH_URL", raising=False)
    monkeypatch.delenv("APPLE_REFURB_WATCH_TOKEN", raising=False)

    db = Database(tmp_path / "home" / "app.db")
    db.set_setting("interval_seconds", 180)
    db.create_watch({"name": "CLI rule", "listing_key": "mac"})
    db.close()

    exported = tmp_path / "config.json"
    result = invoke(["config", "export", str(exported)])
    assert result.exit_code == 0
    assert exported.exists()

    backup = tmp_path / "snapshot.db"
    result = invoke(["backup", "--output", str(backup), "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["backup"] == str(backup)

    result = invoke(["doctor"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["ok"] is True

    result = invoke(["config", "import", str(exported), "--replace-watches"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["watches_imported"] == 1


def test_local_maintenance_refuses_remote_connection(tmp_path, monkeypatch) -> None:
    from apple_refurb_watch.connection import save_connection

    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    save_connection("http://10.0.0.8:8765", "remote-token")
    result = invoke(["backup", "--json"])
    assert result.exit_code == 2
    assert "远端服务" in result.stderr


def test_restore_and_import_refuse_while_daemon_is_running(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("apple_refurb_watch.cli.is_running", lambda: True)
    backup = tmp_path / "backup.db"
    config = tmp_path / "config.json"
    backup.write_bytes(b"placeholder")
    config.write_text("{}", encoding="utf-8")
    restored = invoke(["restore", str(backup)])
    assert restored.exit_code == 2
    assert "先停止" in restored.stderr
    imported = invoke(["config", "import", str(config)])
    assert imported.exit_code == 2
    assert "先停止" in imported.stderr
    compacted = invoke(["compact"])
    assert compacted.exit_code == 2
    assert "先停止" in compacted.stderr


def test_config_import_output_redacts_retained_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "home" / "app.db")
    db.update_settings(
        {
            "access_token": "local-secret",
            "notify": {"bark": {"enabled": True, "url": "https://api.day.app/local-secret"}},
        }
    )
    db.close()
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "format": "apple-refurb-watch.config",
                "version": 1,
                "settings": {"interval_seconds": 120},
                "watches": [],
            }
        ),
        encoding="utf-8",
    )
    result = invoke(["config", "import", str(config)])
    assert result.exit_code == 0
    assert "local-secret" not in result.stdout
    assert "api.day.app" not in result.stdout


def test_serve_host_override_is_ephemeral_unless_persist(tmp_path) -> None:
    from apple_refurb_watch.cli import apply_serve_bind

    db = Database(tmp_path / "app.db")
    db.set_setting("bind_host", "127.0.0.1")
    db.set_setting("bind_port", 8766)
    host, port = apply_serve_bind(db, "0.0.0.0", 9999, persist=False)
    assert host == "0.0.0.0"
    assert port == 9999
    assert db.settings()["bind_host"] == "127.0.0.1"
    assert db.settings()["bind_port"] == 8766
    apply_serve_bind(db, "0.0.0.0", 9999, persist=True)
    assert db.settings()["bind_host"] == "0.0.0.0"
    assert db.settings()["bind_port"] == 9999
    db.close()


def test_env_access_token_bootstraps_empty_database(tmp_path, monkeypatch) -> None:
    from apple_refurb_watch.cli import apply_env_access_token

    monkeypatch.setenv("APPLE_REFURB_WATCH_ACCESS_TOKEN", "from-env")
    db = Database(tmp_path / "app.db")
    apply_env_access_token(db)
    assert db.settings()["access_token"] == "from-env"
    monkeypatch.setenv("APPLE_REFURB_WATCH_ACCESS_TOKEN", "other")
    apply_env_access_token(db)
    assert db.settings()["access_token"] == "from-env"
    db.close()


def test_tui_import_error_is_friendly(monkeypatch) -> None:
    def boom() -> None:
        raise ImportError("textual")

    monkeypatch.setattr("apple_refurb_watch.tui_app.run_tui", boom)
    result = invoke(["tui"])
    assert result.exit_code == 1
    assert "TUI" in (result.stderr or result.stdout)
