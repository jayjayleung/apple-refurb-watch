from fastapi.testclient import TestClient

from apple_refurb_watch.api import create_app
from apple_refurb_watch.db import Database


def test_pages_and_watch_api(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "官翻监听" in home.text
        assert "停止监听" in home.text
        assert "128GB" in home.text
        created = client.post("/api/watches", json={"name": "测试", "all_of": ["MacBook Pro"]})
        assert created.status_code == 200
        assert created.json()["name"] == "测试"
        watches = client.get("/api/watches")
        assert len(watches.json()) == 1
        settings = client.get("/api/settings")
        assert settings.status_code == 200
        assert settings.json()["bind_port"] == 8765


def test_settings_redact_secrets(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings(
        {
            "access_token": "super-secret-token",
            "notify": {"telegram": {"enabled": True, "bot_token": "123:ABC", "chat_id": "99"}},
        }
    )
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        data = client.get("/api/settings").json()
        assert data["access_token"] == ""
        assert data["access_token_set"] is True
        assert data["notify"]["telegram"]["bot_token"] == ""
        assert data["notify"]["telegram"]["bot_token_set"] is True
        assert data["notify"]["telegram"]["chat_id"] == "99"
        page = client.get("/settings")
        assert "123:ABC" not in page.text
        assert "super-secret-token" not in page.text


def test_empty_access_token_does_not_clear(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("access_token", "keep-me")
    db.set_setting("lan_enabled", True)
    db.set_setting("bind_host", "0.0.0.0")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        client.patch("/api/settings", json={"access_token": ""}, headers={"X-Token": "keep-me"})
        assert db.settings()["access_token"] == "keep-me"


def test_csrf_origin_rejected(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        bad = client.post(
            "/api/watches",
            json={"name": "hack"},
            headers={"Origin": "https://evil.example"},
        )
        assert bad.status_code == 403
        ok = client.post("/api/watches", json={"name": "ok"})
        assert ok.status_code == 200


def test_listings_reject_ssrf(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        data = client.patch("/api/settings", json={"listings": ["https://evil.example/x", "mac"]}).json()
        assert data["listings"] == ["mac"]


def test_html_http_error(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        resp = client.post("/watches/from-product", data={"sku": "NOPE", "mode": "sku"})
        assert resp.status_code == 404
        assert "text/html" in resp.headers.get("content-type", "")
        assert "不在当前在售" in resp.text


def test_login_page_has_no_app_chrome(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        page = client.get("/login")
        assert page.status_code == 200
        assert "输入访问口令" in page.text
        assert "login-shell" in page.text
        assert 'href="/watches"' not in page.text
        assert "status-bar" not in page.text


def test_status_and_dim_watch_api(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.upsert_products(
        [
            {
                "sku": "AAAA4CH/A",
                "title": "翻新 14 英寸 MacBook Pro",
                "url": "https://www.apple.com.cn/shop/product/AAAA4CH/A",
                "price": 15000,
                "listing_key": "mac",
                "ram_gb": 24,
                "storage_gb": 1024,
                "extra": {
                    "dims": {
                        "refurbClearModel": "macbookpro",
                        "tsMemorySize": "24gb",
                        "dimensionColor": "silver",
                    }
                },
            },
            {
                "sku": "BBBB4CH/A",
                "title": "翻新 MacBook Air",
                "url": "https://www.apple.com.cn/shop/product/BBBB4CH/A",
                "price": 8000,
                "listing_key": "mac",
                "ram_gb": 16,
                "extra": {"dims": {"refurbClearModel": "macbookair", "tsMemorySize": "16gb"}},
            },
        ]
    )
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        status = client.get("/api/status").json()
        assert status["view"]["label"] == "尚未扫描"
        assert status["in_stock"] == 2
        created = client.post(
            "/api/watches",
            json={"name": "24G Pro", "dim_filters": {"tsMemorySize": ["24gb"], "refurbClearModel": ["macbookpro"]}},
        )
        assert created.status_code == 200
        assert created.json()["dim_filters"]["tsMemorySize"] == ["24gb"]
        filtered = client.get("/api/listings", params=[("d_tsMemorySize", "24gb")])
        assert filtered.json()["count"] == 1
        assert filtered.json()["items"][0]["sku"] == "AAAA4CH/A"
        home = client.get("/")
        assert "filter-rail" in home.text
        assert "官网筛选" not in home.text or "机型" in home.text
        assert "监听中" in home.text or "尚未扫描" in home.text
        form = client.post(
            "/watches",
            data={"name": "表单规则", "mode": "condition", "d_tsMemorySize": ["24gb", "32gb"]},
            follow_redirects=False,
        )
        assert form.status_code == 303
        watches = client.get("/api/watches").json()
        named = next(item for item in watches if item["name"] == "表单规则")
        assert named["dim_filters"]["tsMemorySize"] == ["24gb", "32gb"]
        watches_page = client.get("/watches")
        assert "128GB" in watches_page.text
        assert "腮红色" in watches_page.text


def test_listen_toggle_form_and_api(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        stopped = client.post(
            "/settings/listen",
            data={"enabled": "0", "next": "/watches"},
            follow_redirects=False,
        )
        assert stopped.status_code == 303
        assert stopped.headers["location"] == "/watches"
        assert db.settings()["listen_enabled"] is False
        page = client.get("/")
        assert "已停止" in page.text
        assert "开始监听" in page.text
        patched = client.patch("/api/settings", json={"listen_enabled": True}).json()
        assert patched["listen_enabled"] is True
        assert db.settings()["listen_enabled"] is True
        settings_page = client.get("/settings")
        assert "定时监听官网" in settings_page.text
        assert "从官网同步筛选词条" in settings_page.text
        saved = client.post(
            "/settings",
            data={
                "interval_seconds": "300",
                "bind_port": "8765",
                "listings": ["mac"],
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert db.settings()["listen_enabled"] is False
