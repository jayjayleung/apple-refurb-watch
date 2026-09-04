from __future__ import annotations

import ipaddress
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from apple_refurb_watch.paths import read_runtime, runtime_is_alive
from apple_refurb_watch.storage.schema import DEFAULT_BIND_PORT


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _is_local_endpoint(base: str) -> bool:
    """Whether ``base`` points at the local machine rather than a remote host."""

    try:
        host = (urlparse(base).hostname or "").strip().lower().rstrip(".")
    except ValueError:
        return False
    if host in {"localhost", "localhost.localdomain", "0.0.0.0", "::"}:
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_loopback or address.is_unspecified
    except ValueError:
        return False


def _local_access_token() -> str:
    """Read the access token owned by the local daemon, if one is configured."""

    try:
        from apple_refurb_watch.db import Database

        database = Database()
        try:
            token = database.get_setting("access_token", "")
        finally:
            database.close()
    except Exception:
        return ""
    return str(token or "").strip()


def _resolve_token(token: str | None, base: str, *, base_explicit: bool) -> str:
    if token is not None:
        return token
    env_token = os.environ.get("APPLE_REFURB_WATCH_TOKEN")
    if env_token:
        return env_token
    try:
        from apple_refurb_watch.connection import load_connection

        connection = load_connection()
    except Exception:
        connection = None
    env_url = str(os.environ.get("APPLE_REFURB_WATCH_URL") or "").strip()
    if not base_explicit and env_url and _is_local_endpoint(base):
        return _local_access_token()
    if connection is not None and connection.url:
        # A configured URL is authoritative.  Never attach the local daemon's
        # token to a separately configured remote server, or the remote token
        # to an explicitly selected local endpoint.
        if (not base_explicit and not env_url) or base.rstrip("/") == connection.url.rstrip("/"):
            return connection.token or ""
        return ""
    if not base_explicit and env_url and not _is_local_endpoint(base):
        # APPLE_REFURB_WATCH_URL explicitly selects a remote endpoint.  The
        # local SQLite token belongs to the local daemon and must not be sent.
        return ""
    if not base_explicit or _is_local_endpoint(base):
        # The local access token lives in the daemon's SQLite settings, not in
        # the remote connection.token file used by ``connect``.
        return _local_access_token()
    # An explicitly supplied non-local endpoint must opt into its own token.
    return ""


def default_base() -> str:
    env = os.environ.get("APPLE_REFURB_WATCH_URL")
    if env:
        return env.rstrip("/")
    try:
        from apple_refurb_watch.connection import load_connection

        conn = load_connection()
        if conn.url:
            return conn.url
    except Exception:
        pass
    runtime = read_runtime()
    # Runtime metadata is only authoritative while its owning process is
    # demonstrably alive.  Once it is stale, discard *all* of its connection
    # fields; falling back to a dead process's old port could hit an unrelated
    # service on the same machine.
    live_runtime = runtime if runtime_is_alive(runtime) else None
    if live_runtime and live_runtime.get("url"):
        return str(live_runtime["url"]).rstrip("/")
    # Runtime metadata is intentionally treated as a hint, not authority.  A
    # stopped service must not make the CLI hit an unrelated process that
    # happens to own the old port.
    try:
        from apple_refurb_watch.db import Database

        database = Database()
        settings = database.settings()
        database.close()
    except Exception:
        settings = {}
    port = settings.get("bind_port") or (live_runtime or {}).get("port") or DEFAULT_BIND_PORT
    host = settings.get("bind_host") or (live_runtime or {}).get("host") or "127.0.0.1"
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{port}"


class ApiClient:
    def __init__(
        self,
        base: str | None = None,
        token: str | None = None,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        base_explicit = base is not None
        self.base = (base or default_base()).rstrip("/")
        self.token = _resolve_token(token, self.base, base_explicit=base_explicit) or ""
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout, transport=transport)
        self._closed = False

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._closed:
            raise ApiError("客户端已关闭")
        url = f"{self.base}{path}"
        headers = self._headers()
        supplied_headers = kwargs.pop("headers", None)
        if supplied_headers:
            headers.update(dict(supplied_headers))
        try:
            response = self._client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(f"无法连接 daemon（{self.base}）：{exc}") from exc
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail") or detail
            except Exception:
                pass
            raise ApiError(str(detail), response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except (TypeError, ValueError) as exc:
            raise ApiError(f"daemon 返回了无效 JSON（HTTP {response.status_code}）", response.status_code) from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def health(self) -> dict:
        return self.request("GET", "/api/health")

    def listings(self, **params: Any) -> dict:
        all_pages = bool(params.pop("all_pages", False))
        dim_filters = params.pop("dim_filters", None) or {}
        limit = params.pop("limit", 500)
        offset = params.pop("offset", 0)
        if limit is not None:
            try:
                limit = min(500, max(1, int(limit)))
            except (TypeError, ValueError):
                limit = 500
            query: list[tuple[str, Any]] = [("limit", limit)]
            try:
                offset = max(0, int(offset))
            except (TypeError, ValueError):
                offset = 0
            if offset:
                query.append(("offset", offset))
        else:
            query = []
        query.extend((key, value) for key, value in params.items() if value not in (None, ""))
        for key, values in dim_filters.items():
            if isinstance(values, str):
                values = [values]
            for value in values or []:
                if value in (None, ""):
                    continue
                query.append((f"d_{key}", value))
        result = self.request("GET", "/api/listings", params=query)
        if not all_pages or limit is None or not isinstance(result, dict) or not result.get("has_more"):
            return result

        items = list(result.get("items") or [])
        try:
            total = max(0, int(result.get("count")))
        except (TypeError, ValueError):
            total = len(items)
        try:
            current_offset = max(0, int(result.get("offset", offset)))
        except (TypeError, ValueError):
            current_offset = offset
        start_offset = current_offset
        page_limit = int(limit)
        first_page = result
        while result.get("has_more") and start_offset + len(items) < total:
            next_offset = current_offset + page_limit
            if next_offset <= current_offset:
                break
            page_params = dict(params)
            page_params.update(
                {
                    "dim_filters": dim_filters,
                    "limit": page_limit,
                    "offset": next_offset,
                }
            )
            result = self.listings(**page_params)
            if not isinstance(result, dict):
                break
            page_items = list(result.get("items") or [])
            if not page_items:
                break
            items.extend(page_items)
            try:
                returned_offset = max(0, int(result.get("offset", next_offset)))
            except (TypeError, ValueError):
                returned_offset = next_offset
            # A malformed server must not make an all-pages request loop on
            # the same offset forever.
            current_offset = max(next_offset, returned_offset)
        merged = dict(first_page)
        merged["items"] = items
        merged["has_more"] = start_offset + len(items) < total
        return merged

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

    def submit_scan(self) -> dict:
        """Queue a scan through the run-resource API."""
        return self.request("POST", "/api/scans")

    # Descriptive aliases for callers that model scans as resources.
    start_scan = submit_scan

    def scans(self, limit: int = 50) -> list:
        return self.request("GET", "/api/scans", params={"limit": limit})

    def scan_run(self, run_id: int) -> dict:
        return self.request("GET", f"/api/scans/{int(run_id)}")

    get_scan_run = scan_run

    def events(self, limit: int = 50, *, after_id: int | None = None, type: str | None = None) -> list:
        params: dict[str, Any] = {"limit": limit}
        if after_id is not None:
            params["after_id"] = after_id
        if type:
            params["type"] = type
        return self.request("GET", "/api/events", params=params)

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
    deadline = time.monotonic() + max(0.0, float(timeout))
    last = None
    client = ApiClient(base, timeout=1.0)
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            client.request("GET", "/api/health", timeout=max(0.05, min(1.0, remaining)))
            return client
        except ApiError as exc:
            last = exc
        time.sleep(min(0.35, max(0.0, deadline - time.monotonic())))
    client.close()
    raise ApiError(f"daemon 未就绪: {last}")
