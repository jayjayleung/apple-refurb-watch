from __future__ import annotations

import httpx
import pytest

import apple_refurb_watch.client as client_module
from apple_refurb_watch.client import ApiClient, ApiError


def test_api_client_reuses_one_httpx_client(monkeypatch) -> None:
    created = []

    class RecordingClient:
        def __init__(self, **kwargs):
            self.requests = []
            self.closed = False
            created.append(self)

        def request(self, method, url, **kwargs):
            self.requests.append((method, url, kwargs))
            return httpx.Response(200, json={"ok": True})

        def close(self):
            self.closed = True

    monkeypatch.setattr(client_module.httpx, "Client", RecordingClient)
    api = ApiClient("http://example.test", token="secret")
    assert api.health() == {"ok": True}
    assert api.health() == {"ok": True}
    assert len(created) == 1
    assert len(created[0].requests) == 2
    assert created[0].requests[0][2]["headers"]["Authorization"] == "Bearer secret"
    api.close()
    assert created[0].closed is True


def test_closed_api_client_rejects_requests() -> None:
    api = ApiClient("http://example.test", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))
    api.close()
    with pytest.raises(ApiError, match="客户端已关闭"):
        api.health()


def test_wait_health_timeout_closes_client(monkeypatch) -> None:
    created = []

    class NeverReady:
        def __init__(self, base=None):
            self.closed = False
            created.append(self)

        def health(self):
            raise ApiError("not ready")

        def close(self):
            self.closed = True

    monkeypatch.setattr(client_module, "ApiClient", NeverReady)
    with pytest.raises(ApiError, match="daemon 未就绪"):
        client_module.wait_health(timeout=0)
    assert created and created[0].closed is True


def test_listings_normalizes_page_and_dimension_values() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"items": [], "count": 0})

    api = ApiClient("http://example.test", transport=httpx.MockTransport(handler))
    api.listings(limit=9999, offset=-2, dim_filters={"chip": "m5", "ram": ["16gb", ""]})
    params = dict(seen[0].url.params.multi_items())
    assert params["limit"] == "500"
    assert "offset" not in params
    assert params["d_chip"] == "m5"
    assert params["d_ram"] == "16gb"
    api.close()


def test_listings_all_pages_collects_explicitly() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        offset = int(request.url.params.get("offset", "0"))
        if offset == 0:
            return httpx.Response(
                200,
                json={"items": [{"sku": "A"}], "count": 2, "offset": 0, "limit": 1, "has_more": True},
            )
        return httpx.Response(
            200,
            json={"items": [{"sku": "B"}], "count": 2, "offset": 1, "limit": 1, "has_more": False},
        )

    api = ApiClient("http://example.test", transport=httpx.MockTransport(handler))
    payload = api.listings(limit=1, all_pages=True)
    assert [item["sku"] for item in payload["items"]] == ["A", "B"]
    assert payload["has_more"] is False
    assert len(calls) == 2
    api.close()


def test_listings_all_pages_handles_nonzero_offset() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        if offset == 2:
            return httpx.Response(
                200,
                json={"items": [{"sku": "C"}], "count": 3, "offset": 2, "limit": 1, "has_more": False},
            )
        return httpx.Response(
            200,
            json={"items": [{"sku": "B"}], "count": 3, "offset": 1, "limit": 1, "has_more": True},
        )

    api = ApiClient("http://example.test", transport=httpx.MockTransport(handler))
    payload = api.listings(limit=1, offset=1, all_pages=True)
    assert [item["sku"] for item in payload["items"]] == ["B", "C"]
    assert payload["has_more"] is False
    api.close()


def test_default_base_ignores_stale_runtime_port(tmp_path, monkeypatch) -> None:
    from apple_refurb_watch import client as client_module
    from apple_refurb_watch.db import Database

    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    db = Database()
    db.set_setting("bind_port", 8766)
    db.close()
    monkeypatch.setattr(
        client_module,
        "read_runtime",
        lambda: {"pid": 999999, "host": "127.0.0.1", "port": 8794, "url": "http://127.0.0.1:8794"},
    )
    monkeypatch.setattr(client_module, "runtime_is_alive", lambda _runtime: False)
    assert client_module.default_base() == "http://127.0.0.1:8766"
