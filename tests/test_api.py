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
        assert "全部" in home.text
        assert "<select" in home.text
        assert "盯住你要的那一台" not in home.text
        assert "kicker" not in home.text
        assert "status-bar" not in home.text
        assert 'id="filter-open"' in home.text
        assert "按此条件听" not in home.text
        mac = client.get("/?listing_key=mac")
        assert "filter-rail" in mac.text
        assert "<select" in mac.text
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
                "title": "翻新 14 英寸 MacBook Pro Apple M5 Pro 芯片 (配备 12 核中央处理器和 16 核图形处理器)",
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
                        "dimensionScreensize": "14inch",
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
        assert "按配置听" in home.text
        assert "听配置" not in home.text
        assert "¥15,000" in home.text
        assert "card-hit" in home.text
        assert "精确 SKU" in home.text
        assert "MacBook Pro" in home.text
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
        assert "缺货" in watches_page.text
        assert 'class="facet-oos"' not in watches_page.text
        assert "在售 " in watches_page.text
        assert "先点型号" in watches_page.text
        assert "M5 Pro" in watches_page.text
        assert "芯片" in watches_page.text
        assert 'value="8_3inch"' not in watches_page.text
        mac_page = client.get("/?listing_key=mac")
        assert 'value="24gb"' in mac_page.text
        assert 'value="128gb"' not in mac_page.text
        assert 'value="m5_pro"' in mac_page.text
        assert "12 核" in mac_page.text
        assert "16 核" in mac_page.text
        assert "中央处理器" in mac_page.text
        assert "图形处理器" in mac_page.text
        assert 'class="facet-oos"' not in mac_page.text
        assert "按配置听" in mac_page.text
        oos = client.get("/?listing_key=macbook-pro&d_tsMemorySize=128gb")
        assert oos.status_code == 200
        assert "没有符合条件的商品" in oos.text
        assert 'value="128gb"' in oos.text
        cascade = client.post(
            "/watches/cascade",
            data={"listing_key": "mac", "d_refurbClearModel": "macbookpro"},
        )
        assert cascade.status_code == 200
        assert 'value="128gb"' in cascade.text
        assert "M5 Pro" in cascade.text
        assert "A18 Pro" not in cascade.text
        assert "缺货" in cascade.text
        assert "14 英寸" in cascade.text
        assert "16 英寸" in cascade.text
        assert 'value="4gb"' not in cascade.text
        assert "8.3" not in cascade.text
        assert "腮红" not in cascade.text
        chip_cascade = client.post(
            "/watches/cascade",
            data={"listing_key": "mac", "d_refurbClearModel": "macbookpro", "d_chip": "m5_pro"},
        )
        assert chip_cascade.status_code == 200
        assert 'value="14inch"' in chip_cascade.text
        assert 'value="16inch"' not in chip_cascade.text
        assert 'value="128gb"' in chip_cascade.text
        assert 'value="m5_pro"' in chip_cascade.text
        assert 'value="m5_max"' in chip_cascade.text
        assert "A18 Pro" not in chip_cascade.text
        from_filters = client.post(
            "/watches/from-filters",
            data={"listing_key": "macbook-pro", "d_tsMemorySize": "128gb"},
            follow_redirects=False,
        )
        assert from_filters.status_code == 303
        named_oos = next(
            item for item in client.get("/api/watches").json() if "128GB" in item["name"]
        )
        assert named_oos["listing_key"] == "macbook-pro"
        assert named_oos["dim_filters"]["tsMemorySize"] == ["128gb"]
        auto = client.post(
            "/watches",
            data={"mode": "condition", "listing_key": "macbook-pro", "d_tsMemorySize": "128gb"},
            follow_redirects=False,
        )
        assert auto.status_code == 303
        auto_watch = next(
            item
            for item in client.get("/api/watches").json()
            if item["name"] not in {"24G Pro", "表单规则"} and "128GB" in item["name"]
        )
        assert auto_watch["listing_key"] == "macbook-pro"
        preview = client.post("/watches/preview", data={"listing_key": "mac", "d_tsMemorySize": "24gb"})
        assert preview.status_code == 200
        assert "1 件在售" in preview.text
        chip_preview = client.post(
            "/watches/preview",
            data={"listing_key": "mac", "d_refurbClearModel": "macbookpro", "d_chip": "m5_pro"},
        )
        assert "1 件在售" in chip_preview.text
        empty_preview = client.post(
            "/watches/preview",
            data={"listing_key": "macbook-pro", "d_tsMemorySize": "128gb"},
        )
        assert "缺货" in empty_preview.text


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


def test_thumb_url_rewrites_apple_cdn() -> None:
    from apple_refurb_watch.api import thumb_url

    assert thumb_url("") == ""
    assert thumb_url("https://example.test/a.jpg") == "https://example.test/a.jpg"
    out = thumb_url("https://store.storeimages.cdn-apple.com/is/mbp.jpg?wid=2000")
    assert "wid=400" in out
    assert "qlt=80" in out
    plain = thumb_url("https://store.storeimages.cdn-apple.com/is/mbp.jpg")
    assert plain == "https://store.storeimages.cdn-apple.com/is/mbp.jpg"


def test_home_paginates_and_thumbs_images(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.upsert_products(
        [
            {
                "sku": f"SKU{i:03d}CH/A",
                "title": f"翻新 Mac {i}",
                "url": f"https://www.apple.com.cn/shop/product/SKU{i:03d}CH/A",
                "price": 10000 + i,
                "listing_key": "mac",
                "image_url": "https://store.storeimages.cdn-apple.com/is/mbp.jpg",
                "extra": {},
            }
            for i in range(30)
        ]
    )
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert home.text.count('class="card"') == 24
        assert "还有 6 件" in home.text
        assert "wid=400" not in home.text
        assert "store.storeimages.cdn-apple.com/is/mbp.jpg" in home.text
        more = client.get(
            "/?offset=24",
            headers={"HX-Request": "true", "HX-Target": "product-grid"},
        )
        assert more.status_code == 200
        assert more.text.count('class="card"') == 6
        assert "还有 6 件" not in more.text
        filtered = client.get("/", headers={"HX-Request": "true", "HX-Target": "shop"})
        assert "filter-rail" in filtered.text
        assert filtered.text.count('class="card"') == 24


def test_events_page_shows_shanghai_time(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.conn.execute(
        """
        INSERT INTO events(type, sku, watch_id, title, price, url, message, created_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        ("scan", None, None, None, None, None, "完成扫描", "2026-08-29T06:45:00+00:00"),
    )
    db.conn.commit()
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        page = client.get("/events")
        assert page.status_code == 200
        assert "2026-08-29 14:45" in page.text
        assert "扫描完成" in page.text
        assert "<strong>scan</strong>" not in page.text
        api = client.get("/api/events").json()
        assert api[0]["created_at"] == "2026-08-29T06:45:00+00:00"

