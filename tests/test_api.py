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
        assert 'class="shop-families"' in home.text
        assert "<summary>分类</summary>" not in home.text
        assert "listing_key=macbook-pro" not in home.text
        assert "listing_key=macbook-air" not in home.text
        assert "listing_key=homepod" not in home.text
        assert "listing_key=accessories" not in home.text
        assert "listing_key=airpods" not in home.text
        assert ">Mac<" in home.text
        assert ">iPad<" in home.text
        assert ">Watch<" in home.text
        assert ">AirPods<" not in home.text
        assert ">HomePod<" not in home.text
        assert ">配件<" not in home.text
        assert "<select" in home.text
        assert "价格： 由低至高" in home.text
        assert "盯住你要的那一台" not in home.text
        assert "kicker" not in home.text
        assert "status-bar" not in home.text
        assert 'id="filter-open"' in home.text
        assert "filter-rail" in home.text
        assert "按此条件听" not in home.text
        assert "认证的翻新产品" not in home.text
        assert "浏览全部" not in home.text
        assert 'class="dock"' not in home.text
        assert 'class="top"' in home.text
        mac = client.get("/?listing_key=mac")
        assert "filter-rail" in mac.text
        assert 'class="shop-families"' in mac.text
        assert 'listing_key=mac&' in mac.text or 'listing_key=mac"' in mac.text
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
    db.set_setting(
        "listings",
        ["mac", "ipad", "watch", "airpods", "homepod", "accessories"],
    )
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
        assert "<summary>机型</summary>" not in home.text
        assert "<summary>表壳尺寸</summary>" not in home.text
        assert "<summary>内存</summary>" not in home.text
        assert "listing_key=homepod" in home.text
        assert "listing_key=accessories" in home.text
        assert ">Watch<" in home.text
        assert "listing_key=macbook-pro" not in home.text
        assert "按配置听" in home.text
        assert "听配置" not in home.text
        assert "RMB 15,000" in home.text
        assert home.text.index("RMB 8,000") < home.text.index("RMB 15,000")
        priced = client.get("/?sort=-price")
        assert priced.text.index("RMB 15,000") < priced.text.index("RMB 8,000")
        assert "价格： 由高至低" in priced.text
        assert 'hx-include="#shop-filter"' in priced.text
        assert 'name="sort"' in priced.text
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
        watch_pills = watches_page.text.split('aria-label="分类"', 1)[1].split("</div>", 1)[0]
        assert 'value="mac"' in watch_pills
        assert 'value="ipad"' in watch_pills
        assert 'value="watch"' in watch_pills
        assert 'value="homepod"' in watch_pills
        assert 'value="accessories"' in watch_pills
        assert 'value="macbook-pro"' not in watch_pills
        assert 'value="macbook-air"' not in watch_pills
        assert "128GB" in watches_page.text
        assert "腮红色" in watches_page.text
        assert "缺货" in watches_page.text
        assert 'class="facet-oos"' not in watches_page.text
        assert "在售 " in watches_page.text
        assert "先点型号" in watches_page.text
        assert "M5 Pro" in watches_page.text
        assert "芯片" in watches_page.text
        assert 'name="d_cores"' in watches_page.text
        assert "中央处理器 / 图形处理器" in watches_page.text
        assert "12 核 / 16 核" in watches_page.text
        assert 'value="8_3inch"' not in watches_page.text
        assert 'value="macbookpro"' in watches_page.text
        assert 'value="macbookair"' in watches_page.text
        assert "删除这条规则？" in watches_page.text
        mac_page = client.get("/?listing_key=mac")
        assert "机型" in mac_page.text
        assert "MacBook Air" in mac_page.text
        assert "iMac" in mac_page.text
        assert 'value="24gb"' in mac_page.text
        assert 'value="128gb"' in mac_page.text
        assert 'value="8_3inch"' not in mac_page.text
        assert 'value="m5_pro"' not in mac_page.text
        assert 'name="d_chip"' not in mac_page.text
        assert 'name="d_cores"' not in mac_page.text
        assert 'name="d_cpu_cores"' not in mac_page.text
        assert 'name="d_gpu_cores"' not in mac_page.text
        assert "按配置听" in mac_page.text
        assert 'value="macbookair"' in mac_page.text
        mac_rail = mac_page.text.split('id="shop-filter"')[1].split("</form>")[0]
        assert 'class="facet-oos"' not in mac_rail
        air_input = next(
            tag for tag in mac_rail.split("<input") if 'value="macbookair"' in tag
        )
        pro_input = next(tag for tag in mac_rail.split("<input") if 'value="macbookpro"' in tag)
        imac_input = next(tag for tag in mac_rail.split("<input") if 'value="imac"' in tag)
        assert "disabled" not in air_input.split(">")[0]
        assert "disabled" not in pro_input.split(">")[0]
        assert "disabled" in imac_input.split(">")[0]
        ipad_page = client.get("/?listing_key=ipad")
        assert "<summary>屏幕尺寸</summary>" in ipad_page.text
        assert "<summary>表壳尺寸</summary>" not in ipad_page.text
        assert 'value="8_3inch"' in ipad_page.text
        assert 'value="14inch"' not in ipad_page.text
        assert 'name="d_chip"' not in ipad_page.text
        watch_page = client.get("/?listing_key=watch")
        assert "<summary>表壳尺寸</summary>" in watch_page.text
        assert "<summary>内存</summary>" not in watch_page.text
        airpods_page = client.get("/?listing_key=airpods")
        assert "<summary>机型</summary>" in airpods_page.text
        assert 'open>\n      <summary>机型</summary>' in airpods_page.text or 'open>\n  <summary>机型</summary>' in airpods_page.text
        assert "AirPods Pro 2" in airpods_page.text
        homepod_page = client.get("/?listing_key=homepod")
        assert "<summary>颜色</summary>" in homepod_page.text
        assert 'value="midnight"' in homepod_page.text
        assert 'value="white"' in homepod_page.text
        homepod_rail = homepod_page.text.split('id="shop-filter"')[1].split("</form>")[0]
        assert "disabled" in next(
            tag for tag in homepod_rail.split("<input") if 'value="midnight"' in tag
        ).split(">")[0]
        accessories_page = client.get("/?listing_key=accessories")
        assert "<summary>类别</summary>" in accessories_page.text
        assert 'value="ipadaccessories"' in accessories_page.text
        assert 'value="homepod"' in accessories_page.text
        assert 'value="display"' in accessories_page.text
        chipped = client.get("/?listing_key=mac&d_tsMemorySize=24gb")
        assert "chip-x" in chipped.text
        assert "24" in chipped.text
        oos = client.get("/?listing_key=macbook-pro&d_tsMemorySize=128gb", follow_redirects=False)
        assert oos.status_code == 302
        assert oos.headers["location"] == "/?listing_key=mac"
        empty = client.get("/?listing_key=mac&d_tsMemorySize=128gb")
        assert empty.status_code == 200
        assert "没有符合条件的商品" in empty.text
        assert 'value="128gb"' in empty.text
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
        assert "12 核 / 16 核" in chip_cascade.text
        assert 'value="12core_16core"' in chip_cascade.text
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
        assert "监听分类" in settings_page.text
        assert "这些分类会抓取，在售只展示它们" in settings_page.text
        assert "关闭桌面窗口后继续后台扫描" in settings_page.text
        assert "close_window_keeps_daemon" in settings_page.text
        form_html = settings_page.text.split('id="settings-form"', 1)[1].split("保存设置", 1)[0]
        assert 'value="mac"' in form_html
        assert 'value="ipad"' in form_html
        assert 'value="homepod"' in form_html
        assert 'value="macbook-pro"' not in form_html
        assert 'value="macbook-air"' not in form_html
        assert "只要 MacBook Pro" not in settings_page.text
        assert "<form" not in form_html
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
    rows = [
        ("scan_ok", "第一次扫描", "2026-08-29T06:45:00+00:00"),
        ("appeared", "翻新 MacBook Pro", "2026-08-29T07:00:00+00:00"),
        ("scan_ok", "第二次扫描", "2026-08-29T08:10:00+00:00"),
    ]
    for kind, message, created in rows:
        db.conn.execute(
            """
            INSERT INTO events(type, sku, watch_id, title, price, url, message, created_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (kind, None, None, message if kind == "appeared" else None, None, None, message, created),
        )
    db.conn.commit()
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        page = client.get("/events")
        assert page.status_code == 200
        assert "每日动态" in page.text
        assert "全部记录" in page.text
        assert "按日合并" not in page.text
        assert "2026-08-29 15:00" in page.text
        assert "2 次扫描" in page.text
        assert "第一次扫描" not in page.text
        assert "翻新 MacBook Pro" in page.text
        assert page.text.index("2 次扫描") < page.text.index("翻新 MacBook Pro")
        assert "N 次扫描" not in page.text
        assert "<strong>scan</strong>" not in page.text
        assert "上新排在下面" in page.text
        assert "上新按天排在前面" not in page.text
        assert "时间按上海时区显示" in page.text
        assert "kind-seg" not in page.text
        assert "timeline" in page.text
        full = client.get("/events?all=1")
        assert full.status_code == 200
        assert "2026-08-29 14:45" in full.text
        assert "2026-08-29 15:00" in full.text
        assert "2026-08-29 16:10" in full.text
        assert full.text.count("扫描完成") == 2
        assert "第一次扫描" in full.text
        assert "第二次扫描" in full.text
        assert "翻新 MacBook Pro" in full.text
        assert "2 次扫描" not in full.text
        assert full.text.index("2026-08-29 16:10") < full.text.index("2026-08-29 15:00") < full.text.index("2026-08-29 14:45")
        assert "按时间从新到旧" in full.text
        assert "上新排在下面" not in full.text
        digest = client.get("/events?digest=1")
        assert digest.status_code == 200
        assert "2 次扫描" in digest.text
        assert "第一次扫描" not in digest.text
        assert "翻新 MacBook Pro" in digest.text
        appear = client.get("/events?kind=appear")
        assert appear.status_code == 200
        assert "翻新 MacBook Pro" in appear.text
        assert "第一次扫描" not in appear.text
        api = client.get("/api/events").json()
        assert len(api) == 3
        assert api[0]["created_at"] == "2026-08-29T08:10:00+00:00"


def test_events_page_paginates(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    for i in range(21):
        db.conn.execute(
            """
            INSERT INTO events(type, sku, watch_id, title, price, url, message, created_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            ("scan_ok", None, None, None, None, None, f"扫描 {i}", f"2026-08-29T08:{i:02d}:00+00:00"),
        )
    db.conn.commit()
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        first = client.get("/events?all=1")
        assert first.status_code == 200
        assert first.text.count("<li class=") == 20
        assert "第 1 / 2 页" in first.text
        assert "下一页" in first.text
        second = client.get("/events?all=1&page=2")
        assert second.text.count("<li class=") == 1
        assert "第 2 / 2 页" in second.text
        digest = client.get("/events")
        assert "21 次扫描" in digest.text
        assert digest.text.count("<li class=") == 1
        assert "1 天" in digest.text
        assert "第 1 / 2 页" not in digest.text
        assert client.get("/events?digest=1").text.count("<li class=") == 1


def test_events_digest_pages_by_day(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    for day in range(22, 30):
        db.conn.execute(
            """
            INSERT INTO events(type, sku, watch_id, title, price, url, message, created_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            ("scan_ok", None, None, None, None, None, f"扫描 {day}", f"2026-08-{day:02d}T08:00:00+00:00"),
        )
    db.conn.commit()
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        first = client.get("/events")
        assert first.status_code == 200
        assert "每日动态" in first.text
        assert "8 天 · 第 1 / 2 页" in first.text
        assert first.text.count('class="event-day"') == 7
        assert "2026-08-29" in first.text
        assert "2026-08-22" not in first.text
        second = client.get("/events?page=2")
        assert "第 2 / 2 页" in second.text
        assert second.text.count('class="event-day"') == 1
        assert "2026-08-22" in second.text
        assert "2026-08-29" not in second.text
        alias = client.get("/events?digest=1")
        assert alias.text.count('class="event-day"') == 7


def test_clear_events_api_and_page(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.add_event(type="scan_ok", message="完成扫描")
    db.add_event(type="appeared", title="翻新 MacBook Pro")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        listed = client.get("/api/events").json()
        assert len(listed) == 2
        cleared = client.delete("/api/events")
        assert cleared.status_code == 200
        assert cleared.json()["ok"] is True
        assert cleared.json()["deleted"] == 2
        assert client.get("/api/events").json() == []
        db.add_event(type="scan_ok", message="又扫了一次")
        page_clear = client.post("/events/clear", follow_redirects=False)
        assert page_clear.status_code == 303
        assert page_clear.headers["location"] == "/events"
        empty = client.get("/events")
        assert "还没有记录" in empty.text
        assert client.get("/api/events").json() == []


def test_listings_compact_when_mac_selected(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        data = client.patch(
            "/api/settings",
            json={"listings": ["mac", "macbook-pro", "macbook-air", "ipad"]},
        ).json()
        assert data["listings"] == ["mac", "ipad"]
        assert data["close_window_keeps_daemon"] is True
        public = client.get("/api/settings").json()
        assert public["close_window_keeps_daemon"] is True


def test_settings_page_uses_shop_families(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["macbook-pro", "ipad"])
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        page = client.get("/settings")
        form_html = page.text.split('id="settings-form"', 1)[1].split("保存设置", 1)[0]
        assert 'value="macbook-pro"' not in form_html
        assert 'value="macbook-air"' not in form_html
        mac_tag = next(tag for tag in form_html.split("<input") if 'name="listings"' in tag and 'value="mac"' in tag)
        ipad_tag = next(tag for tag in form_html.split("<input") if 'name="listings"' in tag and 'value="ipad"' in tag)
        assert "checked" in mac_tag.split(">")[0]
        assert "checked" in ipad_tag.split(">")[0]
        saved = client.post(
            "/settings",
            data={
                "interval_seconds": "300",
                "bind_port": "8765",
                "listings": ["mac", "ipad"],
                "listen_enabled": "on",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert db.settings()["listings"] == ["mac", "ipad"]


def _shop_product(sku: str, title: str, listing_key: str, price: int, extra: dict | None = None) -> dict:
    return {
        "sku": sku,
        "title": title,
        "url": f"https://www.apple.com.cn/shop/product/{sku}",
        "price": price,
        "listing_key": listing_key,
        "extra": extra or {},
    }


def test_shop_follows_listen_listings(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.upsert_products(
        [
            _shop_product(
                "PRO1CH/A",
                "翻新 MacBook Pro",
                "mac",
                15000,
                {"dims": {"refurbClearModel": "macbookpro"}},
            ),
            _shop_product(
                "AIR1CH/A",
                "翻新 MacBook Air",
                "mac",
                8000,
                {"dims": {"refurbClearModel": "macbookair"}},
            ),
            _shop_product("PAD1CH/A", "翻新 iPad", "ipad", 4000),
            _shop_product("WAT1CH/A", "翻新 Apple Watch", "watch", 2000),
        ]
    )
    db.set_setting("listings", ["macbook-pro"])
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        bounced = client.get("/", follow_redirects=False)
        assert bounced.status_code == 302
        assert bounced.headers["location"] == "/?listing_key=mac"
        home = client.get("/?listing_key=mac")
        assert home.status_code == 200
        nav = home.text.split('class="shop-families"', 1)[1].split("</nav>", 1)[0]
        assert "全部" not in nav
        assert ">Mac<" in nav
        assert "listing_key=ipad" not in home.text
        assert "listing_key=watch" not in home.text
        assert "MacBook Pro" in home.text
        grid = home.text.split('id="product-grid"', 1)[1].split("grid-skeleton", 1)[0]
        assert "翻新 MacBook Pro" in grid
        assert "翻新 MacBook Air" not in grid
        assert "1 件" in home.text
        ipad = client.get("/?listing_key=ipad", follow_redirects=False)
        assert ipad.status_code == 302
        assert ipad.headers["location"] == "/?listing_key=mac"
        listed = client.get("/api/listings").json()
        assert listed["count"] == 1
        assert listed["items"][0]["sku"] == "PRO1CH/A"
        status = client.get("/api/status").json()
        assert status["in_stock"] == 1
    db.set_setting("listings", ["mac", "ipad"])
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        nav = home.text.split('class="shop-families"', 1)[1].split("</nav>", 1)[0]
        assert "全部" in nav
        assert ">Mac<" in nav
        assert ">iPad<" in nav
        assert ">Watch<" not in nav
        assert "listing_key=watch" not in home.text
        assert "MacBook Pro" in home.text
        assert "iPad" in home.text
        assert "Apple Watch" not in home.text
        listed = client.get("/api/listings").json()
        assert listed["count"] == 3
        status = client.get("/api/status").json()
        assert status["in_stock"] == 3


