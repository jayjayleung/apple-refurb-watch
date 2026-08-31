from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from apple_refurb_watch.paths import read_runtime


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def default_base() -> str:
    env = os.environ.get("APPLE_REFURB_WATCH_URL")
    if env:
        return env.rstrip("/")
    runtime = read_runtime()
    if runtime and runtime.get("url"):
        return str(runtime["url"]).rstrip("/")
    port = (runtime or {}).get("port") or 8765
    host = (runtime or {}).get("host") or "127.0.0.1"
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{port}"


class ApiClient:
    def __init__(self, base: str | None = None, token: str | None = None) -> None:
        self.base = (base or default_base()).rstrip("/")
        self.token = token or os.environ.get("APPLE_REFURB_WATCH_TOKEN") or ""

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base}{path}"
        try:
            with httpx.Client(timeout=30.0, headers=self._headers()) as client:
                response = client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(f"无法连接 daemon（{self.base}）：{exc}") from exc
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail") or detail
            except Exception:  # noqa: BLE001
                pass
            raise ApiError(str(detail), response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def health(self) -> dict:
        return self.request("GET", "/api/health")

    def listings(self, **params: Any) -> dict:
        dim_filters = params.pop("dim_filters", None) or {}
        query: list[tuple[str, Any]] = [(key, value) for key, value in params.items() if value not in (None, "")]
        for key, values in dim_filters.items():
            for value in values:
                query.append((f"d_{key}", value))
        return self.request("GET", "/api/listings", params=query)

    def watches(self) -> list:
        return self.request("GET", "/api/watches")

    def create_watch(self, data: dict) -> dict:
        return self.request("POST", "/api/watches", json=data)

    def update_watch(self, watch_id: int, data: dict) -> dict:
        return self.request("PATCH", f"/api/watches/{watch_id}", json=data)

    def delete_watch(self, watch_id: int) -> None:
        self.request("DELETE", f"/api/watches/{watch_id}")

    def scan(self) -> dict:
        return self.request("POST", "/api/scan")

    def events(self, limit: int = 50) -> list:
        return self.request("GET", "/api/events", params={"limit": limit})

    def clear_events(self) -> dict:
        return self.request("DELETE", "/api/events")

    def settings(self) -> dict:
        return self.request("GET", "/api/settings")

    def update_settings(self, data: dict) -> dict:
        return self.request("PATCH", "/api/settings", json=data)

    def notify_test(self) -> dict:
        return self.request("POST", "/api/notify/test")

    def status(self) -> dict:
        return self.request("GET", "/api/status")

    def filter_catalog(self) -> dict:
        return self.request("GET", "/api/filter-catalog")

    def sync_catalog(self) -> dict:
        return self.request("POST", "/api/filter-catalog/sync")


def wait_health(timeout: float = 15.0, base: str | None = None) -> ApiClient:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        client = ApiClient(base)
        try:
            client.health()
            return client
        except ApiError as exc:
            last = exc
            time.sleep(0.35)
    raise ApiError(f"daemon 未就绪: {last}")
