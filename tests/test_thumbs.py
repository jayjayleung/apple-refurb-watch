from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from apple_refurb_watch.api import create_app
from apple_refurb_watch.db import Database
from apple_refurb_watch.thumbs import ThumbError, apple_image_host_ok, fetch_apple_thumb, product_thumb_src
from apple_refurb_watch.web.auth import session_digest

JPEG = b"\xff\xd8\xff" + b"jpeg-bytes"


def test_product_thumb_src_uses_same_origin_path() -> None:
    assert product_thumb_src({}) == ""
    assert product_thumb_src({"sku": "FHFA4CH/A"}) == ""
    assert product_thumb_src({"image_url": "https://store.storeimages.cdn-apple.com/is/x.jpg"}) == ""
    assert product_thumb_src(
        {"sku": "FHFA4CH/A", "image_url": "https://store.storeimages.cdn-apple.com/is/x.jpg"}
    ) == "/media/thumb?sku=FHFA4CH%2FA"


def test_apple_image_host_ok() -> None:
    assert apple_image_host_ok("https://store.storeimages.cdn-apple.com/is/x.jpg")
    assert not apple_image_host_ok("http://store.storeimages.cdn-apple.com/is/x.jpg")
    assert not apple_image_host_ok("https://evil.example/x.jpg")


def test_upsert_keeps_existing_image_url(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    row = {
        "sku": "KEEP1CH/A",
        "title": "翻新 Mac",
        "url": "https://www.apple.com.cn/shop/product/keep1ch/a",
        "price": 1000,
        "listing_key": "mac",
        "image_url": "https://store.storeimages.cdn-apple.com/is/keep.jpg",
        "extra": {},
    }
    db.upsert_products([row])
    db.upsert_products([{**row, "image_url": None, "title": "翻新 Mac 更新"}])
    kept = db.get_product("KEEP1CH/A")
    assert kept["title"] == "翻新 Mac 更新"
    assert kept["image_url"] == "https://store.storeimages.cdn-apple.com/is/keep.jpg"
    db.close()


@respx.mock
def test_media_thumb_proxies_apple_cdn(tmp_path) -> None:
    url = "https://store.storeimages.cdn-apple.com/is/mbp.jpg"
    respx.get(url).mock(return_value=httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"}))
    db = Database(tmp_path / "app.db")
    db.upsert_products(
        [
            {
                "sku": "THMB1CH/A",
                "title": "翻新 Mac",
                "url": "https://www.apple.com.cn/shop/product/thmb1ch/a",
                "price": 1000,
                "listing_key": "mac",
                "image_url": url,
                "extra": {},
            }
        ]
    )
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        missing = client.get("/media/thumb", params={"sku": "NOPE1CH/A"})
        assert missing.status_code == 404
        first = client.get("/media/thumb", params={"sku": "THMB1CH/A"})
        assert first.status_code == 200
        assert first.headers["content-type"].startswith("image/jpeg")
        assert first.content == JPEG
        assert respx.calls.call_count == 1
        cached = client.get("/media/thumb", params={"sku": "THMB1CH/A"})
        assert cached.content == JPEG
        assert respx.calls.call_count == 1


@respx.mock
def test_media_thumb_requires_auth_on_remote_listener(tmp_path) -> None:
    url = "https://store.storeimages.cdn-apple.com/is/mbp.jpg"
    respx.get(url).mock(return_value=httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"}))
    db = Database(tmp_path / "app.db")
    db.update_settings({"bind_host": "0.0.0.0", "access_token": "secret"})
    db.upsert_products(
        [
            {
                "sku": "AUTH1CH/A",
                "title": "翻新 Mac",
                "url": "https://www.apple.com.cn/shop/product/auth1ch/a",
                "price": 1000,
                "listing_key": "mac",
                "image_url": url,
                "extra": {},
            }
        ]
    )
    app = create_app(db, with_scheduler=False, listener_host="0.0.0.0")
    with TestClient(app) as client:
        blocked = client.get("/media/thumb", params={"sku": "AUTH1CH/A"})
        assert blocked.status_code == 401
        login = client.post("/login", data={"token": "secret"}, follow_redirects=False)
        assert login.cookies.get("arw_token") == session_digest("secret")
        ok = client.get("/media/thumb", params={"sku": "AUTH1CH/A"})
        assert ok.status_code == 200
        assert ok.content == JPEG


def test_fetch_apple_thumb_retries_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("apple_refurb_watch.thumbs.time.sleep", lambda _seconds: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"})

    data, mime = fetch_apple_thumb(
        "https://store.storeimages.cdn-apple.com/is/x.jpg",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        attempts=3,
    )
    assert data == JPEG
    assert mime == "image/jpeg"
    assert calls["n"] == 2


def test_fetch_apple_thumb_rejects_html() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>no</html>", headers={"Content-Type": "text/html"})

    with pytest.raises(ThumbError):
        fetch_apple_thumb(
            "https://store.storeimages.cdn-apple.com/is/x.jpg",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            attempts=1,
        )
