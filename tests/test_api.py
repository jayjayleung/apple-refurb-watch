import httpx
import respx
from fastapi.testclient import TestClient

from apple_refurb_watch import __version__
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
        assert 'id="filter-toggle"' in home.text
        assert 'id="filter-dialog"' in home.text
        assert "/static/app.js" in home.text
        assert "/static/style.css?v=" in home.text
        assert "/static/icon.svg" in home.text
        assert "/static/favicon.ico" in home.text
        assert "filter-rail" in home.text
        assert "按此条件听" not in home.text
        assert "认证的翻新产品" not in home.text
        assert "浏览全部" not in home.text
        assert 'class="dock"' not in home.text
        assert 'class="top"' in home.text
        assert "https://github.com/jayjayleung/apple-refurb-watch" in home.text
        assert "github-link" in home.text
        assert 'class="site-foot"' not in home.text
        assert home.text.index("github-link") < home.text.index('id="main"')
        assert 'class="brand-name"' in home.text
        assert 'aria-label="官翻监听"' in home.text
        assert "arw_desktop" in home.text
        assert "sessionStorage" in home.text
        assert 'class="brand-ver"' not in home.text
        assert 'id="nav-settings"' in home.text
        assert 'class="nav-update-dot"' in home.text
        assert 'id="ver-pop"' not in home.text
        assert "update-dismiss" not in home.text
        assert 'id="update-banner"' not in home.text
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


def test_static_assets_are_versioned_and_cached(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        home = client.get("/")
        assert "/static/app.js?v=" in home.text
        assert "/static/style.css?v=" in home.text
        js = client.get("/static/app.js")
        assert js.status_code == 200
        assert "max-age=31536000" in js.headers.get("cache-control", "")
        assert "immutable" in js.headers.get("cache-control", "")
        assert "__arwApplyStatus" in js.text
        assert "statusInFlight" in js.text
        css = client.get("/static/style.css")
        assert css.status_code == 200
        assert "max-age=31536000" in css.headers.get("cache-control", "")
        assert ".filter-sheet" in css.text


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
        assert "已保存" in page.text
        assert "已启用" in page.text
        assert "更换" not in page.text
        assert "https://github.com/jayjayleung/apple-refurb-watch" in page.text
        assert f"服务 {__version__}" in page.text
        assert 'id="server-update"' in page.text
        assert ">有更新</a>" in page.text
        assert page.text.index(f"服务 {__version__}") < page.text.index('id="server-update"')
        assert "desktop-update-dismiss" not in page.text


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
        assert "https://github.com/jayjayleung/apple-refurb-watch" in page.text
        assert "/static/icon.svg" in page.text
        assert 'class="brand-icon"' in page.text
        assert 'class="brand-name"' in page.text
        assert 'class="brand-ver"' not in page.text


def test_desktop_user_agent_marks_first_response(tmp_path) -> None:
    from apple_refurb_watch.desktop import desktop_user_agent

    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    headers = {"User-Agent": desktop_user_agent()}
    with TestClient(app) as client:
        browser = client.get("/watches")
        desktop = client.get("/watches", headers=headers)
        desktop_login = client.get("/login", headers=headers)
        assert '<html lang="zh-CN" class="desktop">' not in browser.text
        assert '<html lang="zh-CN" class="desktop">' in desktop.text
        assert '<html lang="zh-CN" class="desktop">' in desktop_login.text


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
        cheapest = client.get("/api/listings", params={"sort": "price"}).json()["items"]
        assert [item["sku"] for item in cheapest] == ["BBBB4CH/A", "AAAA4CH/A"]
        pricey = client.get("/api/listings", params={"sort": "-price"}).json()["items"]
        assert [item["sku"] for item in pricey] == ["AAAA4CH/A", "BBBB4CH/A"]
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
        assert "缺货规格仍可选择" in watches_page.text
        assert "M5 Pro" in watches_page.text
        assert "芯片" in watches_page.text
        assert 'name="d_cores"' in watches_page.text
        assert "中央处理器 / 图形处理器" in watches_page.text
        assert "12 核 / 16 核" in watches_page.text
        assert 'value="8_3inch"' not in watches_page.text
        assert 'value="macbookpro"' in watches_page.text
        assert 'value="macbookair"' in watches_page.text
        assert "删除这条规则？" in watches_page.text
        assert "新建规则" in watches_page.text
        assert watches_page.text.index("表单规则") < watches_page.text.index("新建规则")
        assert '<details class="watch-create panel" id="watch-new">' in watches_page.text
        assert '<details class="watch-create panel" id="watch-new" open>' not in watches_page.text
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
        assert "没有符合筛选条件的商品" in empty.text
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
        assert "定时扫描" in settings_page.text
        assert "定时扫描官网" not in settings_page.text
        assert "从官网同步筛选词条" in settings_page.text
        assert "监听分类" in settings_page.text
        assert "MacBook Pro 与 Air 请在 Mac 中选择。" not in settings_page.text
        assert "仅扫描所选分类" not in settings_page.text
        assert "分类更改立即生效" not in settings_page.text
        assert "系统登录后自动运行此服务" not in settings_page.text
        assert "更改端口或绑定地址后请重新启动" not in settings_page.text
        assert "连接远程服务器。" not in settings_page.text
        assert "关闭窗口到托盘" in settings_page.text
        assert "close_window_keeps_daemon" in settings_page.text
        assert "desktop-this-computer" in settings_page.text
        assert "开机自启" in settings_page.text
        assert "server-autostart" in settings_page.text
        assert "开机后自动运行服务" not in settings_page.text
        assert "发送测试" in settings_page.text
        assert "发送测试通知" not in settings_page.text
        assert "更换" not in settings_page.text
        assert "未配置" in settings_page.text
        assert "先保存密钥" not in settings_page.text
        assert "用当前填写的内容测这一路" not in settings_page.text
        assert "密钥旁标" not in settings_page.text
        assert "要改就填新的再保存" not in settings_page.text
        assert 'formaction="/settings/notify-test"' in settings_page.text
        assert "requestSubmit" in settings_page.text
        assert "startedOpen" in settings_page.text
        assert 'block: "nearest"' in settings_page.text
        assert 'block: "center"' not in settings_page.text
        assert "电脑通知" in settings_page.text
        assert "启用电脑通知" not in settings_page.text
        assert "试一下" not in settings_page.text
        assert "computer-notify-allow" not in settings_page.text
        assert "computer-notify-web-hint" not in settings_page.text
        assert "未授予通知权限。" not in settings_page.text
        assert 'name="channel" value="bark"' in settings_page.text
        assert 'name="channel" value="feishu"' in settings_page.text
        pills = settings_page.text.split('id="listings-pills"', 1)[1].split("</div>", 1)[0]
        assert 'value="mac"' in pills
        assert 'value="ipad"' in pills
        assert 'value="homepod"' in pills
        assert 'value="macbook-pro"' not in pills
        assert 'value="macbook-air"' not in pills
        assert "只要 MacBook Pro" not in settings_page.text
        form_html = settings_page.text.split('id="settings-form"', 1)[1].split("保存设置", 1)[0]
        assert 'name="listings"' not in form_html
        assert "<form" not in form_html
        saved = client.post(
            "/settings",
            data={
                "interval_seconds": "300",
                "bind_port": "8765",
                "save_access": "1",
                "save_notify": "1",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert db.settings()["listen_enabled"] is True


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
        assert "按日期汇总" in page.text
        assert "上新按天排在前面" not in page.text
        assert "时间以中国标准时间为准" in page.text
        assert "kind-seg" not in page.text
        assert "timeline" in page.text
        full = client.get("/events?all=1")
        assert full.status_code == 200
        assert "2026-08-29 14:45" in full.text
        assert "2026-08-29 15:00" in full.text
        assert "2026-08-29 16:10" in full.text
        assert full.text.count("<strong>扫描完成</strong>") == 2
        assert "/api/status" in full.text
        assert "第一次扫描" in full.text
        assert "第二次扫描" in full.text
        assert "翻新 MacBook Pro" in full.text
        assert "2 次扫描" not in full.text
        assert full.text.index("2026-08-29 16:10") < full.text.index("2026-08-29 15:00") < full.text.index("2026-08-29 14:45")
        assert "按时间排列" in full.text
        assert "按日期汇总" not in full.text
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


def test_events_page_shows_hit_details_and_live_fragment(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    watch = db.create_watch(
        {
            "name": "14 寸 M5 Max",
            "listing_key": "macbook-pro",
            "dim_filters": {"chip": ["m5_max"], "dimensionScreensize": ["14inch"]},
            "min_ram_gb": 64,
        }
    )
    db.conn.execute(
        """
        INSERT INTO events(type, sku, watch_id, title, price, url, message, created_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            "appeared",
            "G1MK7CH/A",
            watch["id"],
            "翻新 14 英寸 MacBook Pro",
            52799,
            "https://www.apple.com.cn/shop/product/g1mk7ch/a",
            "翻新 14 英寸 MacBook Pro\n128GB 内存 · 2TB 硬盘 · RMB 52,799\nG1MK7CH/A",
            "2026-09-01T06:16:12+00:00",
        ),
    )
    db.conn.commit()
    db.upsert_products(
        [
            {
                "sku": "G1MK7CH/A",
                "listing_key": "macbook-pro",
                "title": "翻新 14 英寸 MacBook Pro",
                "price": 52799,
                "ram_gb": 128,
                "storage_gb": 2048,
                "url": "https://www.apple.com.cn/shop/product/g1mk7ch/a",
            }
        ]
    )
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        page = client.get("/events")
        assert page.status_code == 200
        assert "上新 · 14 寸 M5 Max" in page.text
        assert "RMB 52,799" in page.text
        assert "128GB 内存" in page.text
        assert "event-specs" in page.text
        assert "M5 Max" in page.text
        assert "内存 ≥ 64GB" not in page.text
        assert "event-conds" not in page.text
        assert "已售出" not in page.text
        assert "shop/product/g1mk7ch/a" in page.text
        assert "/api/status" in page.text
        assert "event-feed" in page.text
        fragment = client.get(
            "/events",
            headers={"HX-Request": "true", "HX-Target": "event-feed"},
        )
        assert fragment.status_code == 200
        assert 'id="event-feed"' in fragment.text
        assert "<html" not in fragment.text.lower()
        assert "上新 · 14 寸 M5 Max" in fragment.text
        assert "RMB 52,799" in fragment.text
        assert "/api/status" not in fragment.text
        listed = client.get("/api/events").json()
        assert listed[0]["watch_name"] == "14 寸 M5 Max"


def test_events_page_shows_specs_for_sold_out_hit(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    watch = db.create_watch(
        {
            "name": "14 寸 M5 Max",
            "listing_key": "macbook-pro",
            "dim_filters": {"chip": ["m5_max"], "dimensionScreensize": ["14inch"]},
            "min_ram_gb": 64,
        }
    )
    db.conn.execute(
        """
        INSERT INTO events(type, sku, watch_id, title, price, url, message, created_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            "appeared",
            "G1MK5CH/A",
            watch["id"],
            "翻新 14 英寸 MacBook Pro",
            46399,
            "https://www.apple.com.cn/shop/product/g1mk5ch/a",
            "翻新 14 英寸 MacBook Pro\n128GB 内存 · 2TB 硬盘 · RMB 46,399\nG1MK5CH/A",
            "2026-09-01T06:16:12+00:00",
        ),
    )
    db.conn.commit()
    db.upsert_products(
        [
            {
                "sku": "G1MK5CH/A",
                "listing_key": "macbook-pro",
                "title": "翻新 14 英寸 MacBook Pro",
                "price": 46399,
                "ram_gb": 128,
                "storage_gb": 2048,
                "url": "https://www.apple.com.cn/shop/product/g1mk5ch/a",
            }
        ]
    )
    db.mark_listing_stock(["macbook-pro"], set())
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        page = client.get("/events")
        assert page.status_code == 200
        assert "128GB 内存" in page.text
        assert "2TB 硬盘" in page.text
        assert "RMB 46,399" in page.text
        assert page.text.index("128GB 内存") < page.text.index("RMB 46,399")
        assert "已售出" in page.text
        assert "is-sold" in page.text
        assert "内存 ≥ 64GB" not in page.text
        assert "event-conds" not in page.text


def test_watches_page_opens_create_only_when_empty_or_requested(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        empty = client.get("/watches")
        assert empty.status_code == 200
        assert "新建规则" in empty.text
        assert '<details class="watch-create panel" id="watch-new" open>' in empty.text
        assert "还没有规则" not in empty.text
        assert "watch-list" not in empty.text
        created = client.post("/api/watches", json={"name": "已有规则"})
        assert created.status_code == 200
        listed = client.get("/watches")
        assert listed.status_code == 200
        assert listed.text.index("已有规则") < listed.text.index("新建规则")
        assert '<details class="watch-create panel" id="watch-new">' in listed.text
        assert '<details class="watch-create panel" id="watch-new" open>' not in listed.text
        forced = client.get("/watches?new=1")
        assert '<details class="watch-create panel" id="watch-new" open>' in forced.text


def test_watch_hits_page_lists_and_deletes_sold(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    watch = db.create_watch(
        {
            "name": "14 寸 M5 Max",
            "listing_key": "macbook-pro",
            "dim_filters": {"chip": ["m5_max"], "dimensionScreensize": ["14inch"]},
            "min_ram_gb": 64,
        }
    )
    db.upsert_products(
        [
            {
                "sku": "G1MK7CH/A",
                "listing_key": "macbook-pro",
                "title": "翻新 14 英寸 MacBook Pro 在售",
                "price": 52799,
                "ram_gb": 128,
                "storage_gb": 2048,
                "url": "https://www.apple.com.cn/shop/product/g1mk7ch/a",
            },
            {
                "sku": "G1MK5CH/A",
                "listing_key": "macbook-pro",
                "title": "翻新 14 英寸 MacBook Pro 已下架",
                "price": 46399,
                "ram_gb": 128,
                "storage_gb": 2048,
                "url": "https://www.apple.com.cn/shop/product/g1mk5ch/a",
            },
        ]
    )
    db.mark_listing_stock(["macbook-pro"], {"G1MK7CH/A"})
    db.set_watch_sku(watch["id"], "G1MK7CH/A", in_stock=True, notified=True)
    db.set_watch_sku(watch["id"], "G1MK5CH/A", in_stock=False, notified=False)
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        listed = client.get("/watches")
        assert listed.status_code == 200
        assert "查看命中" in listed.text
        assert f'href="/watches/{watch["id"]}"' in listed.text
        page = client.get(f"/watches/{watch['id']}")
        assert page.status_code == 200
        assert "在售 1 · 已售出 1" in page.text
        assert "第 1 /" not in page.text
        assert "翻新 14 英寸 MacBook Pro 在售" in page.text
        assert "翻新 14 英寸 MacBook Pro 已下架" in page.text
        assert page.text.index("翻新 14 英寸 MacBook Pro 在售") < page.text.index("翻新 14 英寸 MacBook Pro 已下架")
        assert "shop/product/g1mk7ch/a" in page.text
        assert "shop/product/g1mk5ch/a" in page.text
        assert page.text.count('action="/watches/' + str(watch["id"]) + '/hits/delete"') == 1
        blocked = client.post(
            f"/watches/{watch['id']}/hits/delete",
            data={"sku": "G1MK7CH/A"},
        )
        assert blocked.status_code == 400
        assert "在售命中不能删除" in blocked.text
        removed = client.post(
            f"/watches/{watch['id']}/hits/delete",
            data={"sku": "G1MK5CH/A"},
            follow_redirects=False,
        )
        assert removed.status_code == 303
        after = client.get(f"/watches/{watch['id']}")
        assert "翻新 14 英寸 MacBook Pro 已下架" not in after.text
        assert "翻新 14 英寸 MacBook Pro 在售" in after.text
        assert "已售出 0" in after.text
        assert "第 1 /" not in after.text


def test_watch_hits_page_paginates(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    watch = db.create_watch({"name": "分页规则", "listing_key": "macbook-pro"})
    db.set_watch_sku(watch["id"], "LIVE1CH/A", in_stock=True, notified=True)
    for i in range(20):
        db.set_watch_sku(watch["id"], f"SOLD{i:02d}CH/A", in_stock=False, notified=False)
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        first = client.get(f"/watches/{watch['id']}")
        assert first.status_code == 200
        assert "在售 1 · 已售出 20" in first.text
        assert "21 条 · 第 1 / 2 页" in first.text
        assert first.text.count("<li class=\"watch-hit") == 20
        assert "LIVE1CH/A" in first.text
        assert "SOLD19CH/A" not in first.text
        assert 'href="/watches/' + str(watch["id"]) + '?page=2"' in first.text
        second = client.get(f"/watches/{watch['id']}?page=2")
        assert second.status_code == 200
        assert "第 2 / 2 页" in second.text
        assert "LIVE1CH/A" not in second.text
        assert "SOLD19CH/A" in second.text
        overflow = client.get(f"/watches/{watch['id']}?page=99")
        assert "第 2 / 2 页" in overflow.text
        removed = client.post(
            f"/watches/{watch['id']}/hits/delete",
            data={"sku": "SOLD19CH/A", "page": "2"},
            follow_redirects=False,
        )
        assert removed.status_code == 303
        assert removed.headers["location"] == f"/watches/{watch['id']}"
        after = client.get(removed.headers["location"])
        assert after.status_code == 200
        assert "SOLD19CH/A" not in after.text
        assert "LIVE1CH/A" in after.text
        assert "第 1 / 2 页" not in after.text
        assert "第 2 /" not in after.text


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
    db.upsert_products(
        [
            {
                "sku": "AAAA4CH/A",
                "title": "翻新 MacBook Pro",
                "url": "https://www.apple.com.cn/shop/product/AAAA4CH/A",
                "price": 15000,
                "listing_key": "mac",
            }
        ]
    )
    db.create_watch({"name": "规则", "mode": "condition"})
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
        assert db.count_products(in_stock=True) == 1
        assert db.count_watches() == 1
        db.add_event(type="scan_ok", message="又扫了一次")
        page_clear = client.post("/events/clear", follow_redirects=False)
        assert page_clear.status_code == 303
        assert page_clear.headers["location"] == "/events"
        empty = client.get("/events")
        assert "暂无动态" in empty.text
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
        pills = page.text.split('id="listings-pills"', 1)[1].split("</div>", 1)[0]
        assert 'value="macbook-pro"' not in pills
        assert 'value="macbook-air"' not in pills
        mac_tag = next(tag for tag in pills.split("<input") if 'name="listings"' in tag and 'value="mac"' in tag)
        ipad_tag = next(tag for tag in pills.split("<input") if 'name="listings"' in tag and 'value="ipad"' in tag)
        assert "checked" in mac_tag.split(">")[0]
        assert "checked" in ipad_tag.split(">")[0]
        patched = client.patch("/api/settings", json={"listings": ["mac", "ipad"]}).json()
        assert patched["listings"] == ["mac", "ipad"]
        saved = client.post(
            "/settings",
            data={
                "interval_seconds": "300",
                "bind_port": "8765",
                "save_access": "1",
                "save_notify": "1",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert db.settings()["listings"] == ["mac", "ipad"]
        assert db.settings()["listen_enabled"] is True


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


def test_listings_api_paginates_and_bounds_limit(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.upsert_products(
        [
            {
                "sku": f"PAGE{i}CH/A",
                "title": f"翻新 Mac {i}",
                "url": f"https://www.apple.com.cn/shop/product/PAGE{i}CH/A",
                "price": 1000 + i,
                "listing_key": "mac",
            }
            for i in range(3)
        ]
    )
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        page = client.get("/api/listings", params={"limit": 1, "offset": 1}).json()
        assert page["count"] == 3
        assert page["limit"] == 1
        assert page["offset"] == 1
        assert page["has_more"] is True
        assert [item["sku"] for item in page["items"]] == ["PAGE1CH/A"]

        capped = client.get("/api/listings", params={"limit": 99999}).json()
        assert capped["limit"] == 500
        assert len(capped["items"]) == 3


def test_unhandled_page_error_shows_reason(tmp_path, monkeypatch) -> None:
    import apple_refurb_watch.web.render as render_mod
    from apple_refurb_watch.web import routes_api

    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)

    def boom(_db):
        raise RuntimeError("frozen-home-crash")

    monkeypatch.setattr(render_mod, "load_status", boom)
    monkeypatch.setattr(routes_api, "public_status", boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        home = client.get("/")
        assert home.status_code == 500
        assert "Internal Server Error" not in home.text
        assert "页面出错" in home.text
        assert "frozen-home-crash" in home.text
        api = client.get("/api/status")
        assert api.status_code == 500
        assert api.json()["detail"] == "RuntimeError: frozen-home-crash"
        assert "Traceback" not in home.text


def test_api_sync_catalog(tmp_path, monkeypatch) -> None:
    from apple_refurb_watch.web import routes_api

    calls: list[object] = []

    def fake_sync(fetch) -> dict:
        calls.append(fetch)
        return {}

    monkeypatch.setattr(routes_api, "sync_filter_catalog", fake_sync)
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        ok = client.post("/api/filter-catalog/sync")
        assert ok.status_code == 200
        assert ok.json()["ok"] is True
        assert calls
        monkeypatch.setattr(routes_api, "sync_filter_catalog", lambda fetch: (_ for _ in ()).throw(RuntimeError("offline")))
        bad = client.post("/api/filter-catalog/sync")
        assert bad.status_code == 502
        assert "offline" in bad.json()["detail"]


def test_autostart_api(tmp_path, monkeypatch) -> None:
    state = {"on": False, "desktop": "unset"}

    def fake_status(*, desktop=None):
        return {
            "installed": state["on"],
            "kind": "tray" if desktop else "serve",
            "command": ["serve"],
        }

    def fake_set(enabled, *, desktop=None):
        state["on"] = bool(enabled)
        state["desktop"] = desktop
        info = fake_status(desktop=desktop)
        info["ok"] = True
        info["message"] = "ok"
        return info

    monkeypatch.setattr("apple_refurb_watch.service.autostart_status", fake_status)
    monkeypatch.setattr("apple_refurb_watch.service.set_autostart", fake_set)
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        got = client.get("/api/autostart").json()
        assert got["kind"] == "serve"
        assert got["installed"] is False
        posted = client.post("/api/autostart", json={"enabled": True}).json()
        assert posted["ok"] is True
        assert posted["installed"] is True
        assert posted["kind"] == "serve"
        assert state["desktop"] is False
        gone = client.post("/api/autostart", json={"enabled": False}).json()
        assert gone["installed"] is False


def test_health_capabilities(tmp_path) -> None:
    from apple_refurb_watch import __version__
    from apple_refurb_watch.usecases import API_REVISION, CAPABILITIES

    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        data = client.get("/api/health").json()
        assert data["ok"] is True
        assert data["server_version"] == __version__
        assert data["api_revision"] == API_REVISION
        assert data["capabilities"] == list(CAPABILITIES)


def test_update_api_compares_against_github_tag(tmp_path, monkeypatch) -> None:
    from apple_refurb_watch.update_check import LATEST_RELEASE_URL

    monkeypatch.setattr("apple_refurb_watch.update_check.fetch_latest_tag", lambda: "v9.9.9")
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        data = client.get("/api/update").json()
        assert data["ok"] is True
        assert data["current"] == __version__
        assert data["latest"] == "9.9.9"
        assert data["newer"] is True
        assert data["url"] == LATEST_RELEASE_URL


def test_events_after_id_and_type(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    first = db.add_event(type="scan_ok", message="扫描")
    appeared = db.add_event(type="appeared", title="翻新 MacBook Pro", message="上新")
    later = db.add_event(type="appeared", title="翻新 iPad", message="又上新")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        all_rows = client.get("/api/events").json()
        assert [row["id"] for row in all_rows] == [later, appeared, first]
        typed = client.get("/api/events", params={"type": "appeared"}).json()
        assert [row["type"] for row in typed] == ["appeared", "appeared"]
        after = client.get("/api/events", params={"type": "appeared", "after_id": appeared}).json()
        assert [row["id"] for row in after] == [later]


def test_settings_save_does_not_clobber_listings(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings({"listings": ["mac", "watch"], "listen_enabled": True})
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        saved = client.post(
            "/settings",
            data={
                "interval_seconds": "180",
                "bind_port": "8765",
                "save_access": "1",
                "save_notify": "1",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert db.settings()["interval_seconds"] == 180
        assert db.settings()["listings"] == ["mac", "watch"]
        assert db.settings()["listen_enabled"] is True


def test_clear_notify_secret_and_access_token(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings(
        {
            "access_token": "keep-me",
            "lan_enabled": True,
            "notify": {"bark": {"enabled": True, "url": "https://api.day.app/key"}},
        }
    )
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        client.post(
            "/settings",
            data={
                "interval_seconds": "300",
                "bind_port": "8765",
                "save_access": "1",
                "lan_enabled": "on",
                "save_notify": "1",
                "notify_bark_enabled": "on",
                "notify_bark_url_clear": "1",
            },
            follow_redirects=False,
        )
        assert db.settings()["notify"]["bark"]["url"] == ""
        assert db.settings()["notify"]["bark"]["enabled"] is True
        client.post(
            "/settings",
            data={
                "interval_seconds": "300",
                "bind_port": "8765",
                "save_access": "1",
                "lan_enabled": "on",
                "access_token_clear": "1",
                "save_notify": "1",
                "notify_bark_enabled": "on",
            },
            headers={"X-Token": "keep-me"},
            follow_redirects=False,
        )
        assert db.settings()["access_token"] == ""


def test_lan_enable_reveals_generated_token_once(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        page = client.post(
            "/settings",
            data={
                "interval_seconds": "300",
                "bind_port": "8765",
                "save_access": "1",
                "lan_enabled": "on",
                "save_notify": "1",
            },
        )
        token = db.settings()["access_token"]
        assert token
        assert page.status_code == 200
        assert token in page.text
        assert "访问口令已生成" in page.text
        again = client.get("/settings", headers={"X-Token": token})
        assert token not in again.text
        assert "访问口令已生成" not in again.text


@respx.mock
def test_notify_test_one_channel(tmp_path) -> None:
    bark = respx.post("https://api.day.app/key").mock(
        return_value=httpx.Response(200, json={"code": 200, "message": "success"})
    )
    feishu = respx.post("https://open.feishu.cn/hook").mock(
        return_value=httpx.Response(200, json={"code": 0, "msg": "success"})
    )
    db = Database(tmp_path / "app.db")
    db.update_settings(
        {
            "notify": {
                "bark": {"enabled": False, "url": "https://api.day.app/key"},
                "feishu": {"enabled": True, "webhook": "https://open.feishu.cn/hook"},
            }
        }
    )
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        posted = client.post("/settings/notify-test", data={"channel": "bark"}, follow_redirects=False)
        assert posted.status_code == 303
        assert "channel=bark" in posted.headers["location"]
        assert "notify-ok" in posted.headers["location"]
        assert bark.called
        assert not feishu.called
        page = client.get("/settings?flash=notify-ok&channel=bark")
        assert "测试通知已发出" in page.text
        api_all = client.post("/api/notify/test")
        assert api_all.status_code == 200
        assert feishu.called
        feishu.calls.clear()
        bark.calls.clear()
        one = client.post("/api/notify/test", json={"channel": "bark"})
        assert one.status_code == 200
        assert bark.called
        assert not feishu.called
        db.update_settings({"notify": {"bark": {"enabled": False, "url": ""}}})
        empty = client.post("/api/notify/test", json={"channel": "bark"})
        assert empty.status_code == 400


@respx.mock
def test_notify_test_uses_unsaved_form_values(tmp_path) -> None:
    bark = respx.post("https://api.day.app/draft-key").mock(
        return_value=httpx.Response(200, json={"code": 200, "message": "success"})
    )
    saved = respx.post("https://api.day.app/saved-key").mock(
        return_value=httpx.Response(200, json={"code": 200, "message": "success"})
    )
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        posted = client.post(
            "/settings/notify-test",
            data={
                "channel": "bark",
                "save_notify": "1",
                "notify_bark_url": "https://api.day.app/draft-key",
            },
            follow_redirects=False,
        )
        assert posted.status_code == 303
        assert "notify-ok" in posted.headers["location"]
        assert "channel=bark" in posted.headers["location"]
        assert bark.called
        assert not saved.called
        assert (db.settings().get("notify") or {}).get("bark", {}).get("url") == ""

    db.update_settings({"notify": {"bark": {"enabled": False, "url": "https://api.day.app/saved-key"}}})
    with TestClient(app) as client:
        bark.calls.clear()
        saved.calls.clear()
        posted = client.post(
            "/settings/notify-test",
            data={
                "channel": "bark",
                "save_notify": "1",
                "notify_bark_url": "https://api.day.app/draft-key",
            },
            follow_redirects=False,
        )
        assert posted.status_code == 303
        assert "notify-ok" in posted.headers["location"]
        assert bark.called
        assert not saved.called
        assert db.settings()["notify"]["bark"]["url"] == "https://api.day.app/saved-key"


def test_settings_numeric_range_and_watch_null_and_notify_body(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings({"interval_seconds": 300, "bind_port": 8765})
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        bad_interval = client.patch("/api/settings", json={"interval_seconds": -5})
        assert bad_interval.status_code == 400
        assert db.settings()["interval_seconds"] == 300
        bad_port = client.patch("/api/settings", json={"bind_port": 70000})
        assert bad_port.status_code == 400
        assert db.settings()["bind_port"] == 8765
        form_bad = client.post(
            "/settings",
            data={
                "interval_seconds": "abc",
                "bind_port": "8765",
                "save_access": "1",
                "save_notify": "1",
            },
            follow_redirects=False,
        )
        assert form_bad.status_code == 400
        assert "扫描间隔必须是整数" in form_bad.text
        watch = client.post("/api/watches", json={"name": "预算", "max_price": 1000}).json()
        cleared = client.patch(f"/api/watches/{watch['id']}", json={"max_price": None})
        assert cleared.status_code == 200
        assert cleared.json()["max_price"] is None
        bad_mode = client.patch(f"/api/watches/{watch['id']}", json={"mode": "nope"})
        assert bad_mode.status_code == 400
        listed = client.post("/api/notify/test", json=["bark"])
        assert listed.status_code == 400
        broken = client.post(
            "/api/notify/test",
            content=b"not-a-form",
            headers={"Content-Type": "multipart/form-data; boundary=----broken"},
        )
        assert broken.status_code == 400

