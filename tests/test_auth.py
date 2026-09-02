from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apple_refurb_watch.api import create_app
from apple_refurb_watch.db import Database
from apple_refurb_watch.paths import read_runtime
from apple_refurb_watch.settings import normalize_settings_patch
from apple_refurb_watch.web.auth import validate_listener_security


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
