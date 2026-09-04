from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apple_refurb_watch.api import create_app
from apple_refurb_watch.db import Database
from apple_refurb_watch.paths import read_runtime
from apple_refurb_watch.settings import normalize_settings_patch
from apple_refurb_watch.web.auth import host_allowed, session_digest, validate_listener_security


def test_loopback_listener_can_run_without_token(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings({"bind_host": "127.0.0.1", "lan_enabled": True, "access_token": ""})
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        assert client.get("/api/status").status_code == 200


def test_non_loopback_listener_requires_token_even_when_lan_flag_is_off(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings({"bind_host": "0.0.0.0", "lan_enabled": False, "access_token": "secret"})
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        assert client.get("/api/status").status_code == 401
        assert client.get("/api/status", headers={"Authorization": "Bearer secret"}).status_code == 200


def test_loopback_proxy_connection_cannot_bypass_remote_auth(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings({"bind_host": "0.0.0.0", "access_token": "secret"})
    app = create_app(db, with_scheduler=False)
    # The ASGI peer is loopback, as it would be for a local reverse proxy.  The
    # listener address, rather than request.client, still determines auth.
    with TestClient(app, client=("127.0.0.1", 43123)) as client:
        assert client.get("/api/status", headers={"X-Forwarded-For": "203.0.113.8"}).status_code == 401


def test_health_is_public_for_remote_listener(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings({"bind_host": "0.0.0.0", "access_token": "secret"})
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/update").status_code == 200


def test_remote_listener_without_token_is_rejected_before_startup() -> None:
    with pytest.raises(RuntimeError, match="必须先配置访问口令"):
        validate_listener_security({"bind_host": "0.0.0.0", "access_token": ""})
    validate_listener_security({"bind_host": "127.0.0.1", "access_token": ""})


def test_normalizing_remote_settings_generates_token() -> None:
    patch = normalize_settings_patch({"lan_enabled": True}, {"bind_host": "127.0.0.1", "access_token": ""})
    assert patch["bind_host"] == "0.0.0.0"
    assert patch["access_token"]


def test_runtime_metadata_uses_actual_listener_override(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings({"bind_host": "127.0.0.1", "bind_port": 8765, "access_token": "secret"})
    app = create_app(
        db,
        with_scheduler=False,
        listener_host="0.0.0.0",
        listener_port=9911,
    )
    with TestClient(app):
        runtime = read_runtime()
        assert runtime["host"] == "0.0.0.0"
        assert runtime["port"] == 9911
        assert runtime["url"] == "http://127.0.0.1:9911"


def _remote_client(tmp_path, token: str = "secret"):
    db = Database(tmp_path / "app.db")
    db.update_settings({"bind_host": "0.0.0.0", "access_token": token})
    app = create_app(db, with_scheduler=False)
    return db, app


def test_unauthenticated_html_uses_see_other_and_htmx_redirect(tmp_path) -> None:
    _db, app = _remote_client(tmp_path)
    with TestClient(app) as client:
        page = client.get("/watches", follow_redirects=False)
        assert page.status_code == 303
        assert page.headers["location"].endswith("/login")
        hx = client.get("/watches", headers={"HX-Request": "true"}, follow_redirects=False)
        assert hx.status_code == 204
        assert hx.headers["hx-redirect"] == "/login"


def test_session_cookie_is_hmac_derived_and_logout_clears_it(tmp_path) -> None:
    _db, app = _remote_client(tmp_path)
    with TestClient(app) as client:
        login = client.post("/login", data={"token": "secret"}, follow_redirects=False)
        assert login.status_code == 303
        cookie = login.cookies.get("arw_token")
        assert cookie == session_digest("secret")
        assert cookie != "secret"
        assert client.get("/api/status").status_code == 200
        assert client.get("/api/status", headers={"Authorization": "Bearer secret"}).status_code == 200
        logged_out = client.post("/logout", follow_redirects=False)
        assert logged_out.status_code == 303
        assert client.get("/api/status").status_code == 401


def test_changing_access_token_invalidates_session_cookie(tmp_path) -> None:
    db, app = _remote_client(tmp_path)
    with TestClient(app) as client:
        client.post("/login", data={"token": "secret"})
        assert client.get("/api/status").status_code == 200
        db.update_settings({"access_token": "rotated"})
        assert client.get("/api/status").status_code == 401
        with TestClient(app) as other:
            assert other.get("/api/status", headers={"Authorization": "Bearer rotated"}).status_code == 200


def test_dns_rebinding_host_is_rejected_lan_ip_is_allowed(tmp_path) -> None:
    _db, app = _remote_client(tmp_path)
    with TestClient(app, base_url="http://evil.example") as client:
        assert client.get("/api/status").status_code == 403
    with TestClient(app, base_url="http://192.168.8.12:8766") as client:
        assert client.get("/api/status", headers={"Authorization": "Bearer secret"}).status_code == 200
        created = client.post("/api/watches", json={"name": "lan"}, headers={"Authorization": "Bearer secret"})
        assert created.status_code == 200


def test_security_headers_are_present(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["referrer-policy"] == "same-origin"


def test_unhandled_error_hides_traceback(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret-file /tmp/hidden\nTraceback (most recent call last):")

    monkeypatch.setattr("apple_refurb_watch.web.routes_pages.list_shop", boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        page = client.get("/")
        assert page.status_code == 500
        assert "Traceback" not in page.text
        assert "RuntimeError" in page.text
        assert "secret-file /tmp/hidden" in page.text


def test_testserver_is_not_a_production_host(monkeypatch) -> None:
    monkeypatch.delenv("APPLE_REFURB_WATCH_ALLOWED_HOSTS", raising=False)
    assert host_allowed("testserver") is False
    assert host_allowed("localhost") is True
    assert host_allowed("192.168.8.12:8766") is True
    assert host_allowed("watch.example.com") is False
    assert host_allowed("watch.example.com", {"allowed_hosts": ["watch.example.com"]}) is True
    assert host_allowed("watch.example.com", {"allowed_hosts": ["127.0.0.1"]}) is False


def test_registered_domain_host_allows_bearer_read_write(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings(
        {
            "bind_host": "0.0.0.0",
            "access_token": "secret",
            "allowed_hosts": ["watch.example.com"],
        }
    )
    app = create_app(db, with_scheduler=False)
    headers = {"Authorization": "Bearer secret"}
    with TestClient(app, base_url="http://watch.example.com") as client:
        assert client.get("/api/status", headers=headers).status_code == 200
        created = client.post(
            "/api/watches",
            json={"name": "via-domain"},
            headers={**headers, "Origin": "http://watch.example.com"},
        )
        assert created.status_code == 200


def test_env_allowed_hosts_are_merged(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_ALLOWED_HOSTS", "from-env.example")
    db = Database(tmp_path / "app.db")
    db.update_settings(
        {
            "bind_host": "0.0.0.0",
            "access_token": "secret",
            "allowed_hosts": ["from-db.example"],
        }
    )
    app = create_app(db, with_scheduler=False)
    headers = {"Authorization": "Bearer secret"}
    with TestClient(app, base_url="http://from-env.example") as client:
        assert client.get("/api/status", headers=headers).status_code == 200
    with TestClient(app, base_url="http://from-db.example") as client:
        assert client.get("/api/status", headers=headers).status_code == 200


def test_loopback_unregistered_hostname_get_ok_same_origin_post_forbidden(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings({"bind_host": "127.0.0.1", "access_token": ""})
    app = create_app(db, with_scheduler=False)
    with TestClient(app, base_url="http://mypc.local") as client:
        assert client.get("/api/status").status_code == 200
        denied = client.post(
            "/api/watches",
            json={"name": "local-host"},
            headers={"Origin": "http://mypc.local"},
        )
        assert denied.status_code == 403
    db.update_settings({"allowed_hosts": ["mypc.local"]})
    with TestClient(app, base_url="http://mypc.local") as client:
        allowed = client.post(
            "/api/watches",
            json={"name": "local-host"},
            headers={"Origin": "http://mypc.local"},
        )
        assert allowed.status_code == 200
        patched = client.patch(
            "/api/settings",
            json={"allowed_hosts": ["mypc.local", "https://watch.example.com:443"]},
        )
        assert patched.status_code == 200
        assert patched.json()["allowed_hosts"] == ["mypc.local", "watch.example.com"]


def test_origin_allowlist_covers_rewritten_host(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings(
        {
            "bind_host": "0.0.0.0",
            "access_token": "secret",
            "allowed_hosts": ["watch.example.com"],
        }
    )
    app = create_app(db, with_scheduler=False)
    with TestClient(app, base_url="http://127.0.0.1:8766") as client:
        created = client.post(
            "/api/watches",
            json={"name": "proxied"},
            headers={
                "Authorization": "Bearer secret",
                "Origin": "https://watch.example.com",
            },
        )
        assert created.status_code == 200


def test_clearing_token_while_bound_remotely_is_conflict(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.update_settings({"bind_host": "0.0.0.0", "lan_enabled": True, "access_token": "secret"})
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        resp = client.post(
            "/settings",
            data={
                "save_access": "1",
                "save_notify": "1",
                "lan_enabled": "on",
                "access_token_clear": "1",
                "interval_seconds": "300",
                "bind_port": "8766",
            },
            headers={"Authorization": "Bearer secret"},
            follow_redirects=False,
        )
        assert resp.status_code == 409
        assert "无法清除口令" in resp.text
        assert db.settings()["access_token"] == "secret"
        page = client.get("/settings", headers={"Authorization": "Bearer secret"})
        assert page.status_code == 200
        assert "先关闭远程访问" in page.text
        assert "确定清除访问口令" in page.text


def test_bearer_beats_invalid_cookie_and_is_case_insensitive(tmp_path) -> None:
    _db, app = _remote_client(tmp_path)
    with TestClient(app) as client:
        client.cookies.set("arw_token", "not-a-valid-session")
        assert client.get("/api/status", headers={"Authorization": "bearer secret"}).status_code == 200
        assert client.get("/api/status", headers={"Authorization": "BEARER secret"}).status_code == 200
        assert client.get("/api/status", headers={"X-Token": "secret"}).status_code == 200
        assert client.get("/api/status").status_code == 401
