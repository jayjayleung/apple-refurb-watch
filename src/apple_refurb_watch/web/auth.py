from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.datastructures import MutableHeaders

from apple_refurb_watch.db import Database
from apple_refurb_watch.settings import listener_requires_auth, resolved_allowed_hosts

SESSION_COOKIE = "arw_token"
SESSION_SALT = b"arw-session"
_LOCAL_HOSTS = {"localhost", "localhost.localdomain"}


def validate_listener_security(settings: dict) -> None:
    """Reject an externally reachable listener that has no access token.

    The middleware still handles this state as a normal unauthorized request so
    a misconfigured ASGI app fails closed.  The process entry points call this
    validator before binding a socket, preventing an accidentally inaccessible
    or unauthenticated daemon from being started.
    """

    if listener_requires_auth(settings) and not str(settings.get("access_token") or "").strip():
        bind = settings.get("bind_host") or "0.0.0.0"
        raise RuntimeError(f"非本机监听 {bind} 必须先配置访问口令，服务拒绝启动")


def session_digest(access_token: str) -> str:
    return hmac.new(access_token.encode("utf-8"), SESSION_SALT, hashlib.sha256).hexdigest()


def _const_eq(left: str, right: str) -> bool:
    a = left.encode("utf-8")
    b = right.encode("utf-8")
    if len(a) != len(b):
        secrets.compare_digest(b, b)
        return False
    return secrets.compare_digest(a, b)


def token_ok(provided: str, expected: str) -> bool:
    if not expected or not provided:
        return False
    return _const_eq(provided, expected) or _const_eq(provided, session_digest(expected))


def host_name(host_header: str) -> str:
    text = (host_header or "").strip().lower()
    if not text:
        return ""
    if text.startswith("["):
        end = text.find("]")
        return text[1:end] if end > 1 else text
    if text.count(":") == 1:
        return text.split(":", 1)[0]
    return text


def host_allowed(host_header: str, settings: dict | None = None) -> bool:
    hostname = host_name(host_header)
    if not hostname:
        return False
    if hostname in _LOCAL_HOSTS:
        return True
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    return hostname in set(resolved_allowed_hosts(settings))


def origin_ok(request: Request, settings: dict | None = None) -> bool:
    host = (request.headers.get("host") or "").lower()
    if not host_allowed(host, settings):
        return False
    origin = request.headers.get("origin") or ""
    referer = request.headers.get("referer") or ""
    source = origin or referer
    if not source:
        return True
    incoming = (urlparse(source).netloc or "").lower()
    if not incoming:
        return False
    if incoming == host:
        return True
    return host_name(incoming) in set(resolved_allowed_hosts(settings))


def needs_auth(request: Request, settings: dict) -> bool:
    # Do not inspect request.client here.  A reverse proxy commonly connects
    # over loopback while forwarding requests from the LAN or the public net;
    # trusting that address would bypass authentication.
    del request
    return listener_requires_auth(settings)


def login_redirect(request: Request) -> Response:
    if request.headers.get("HX-Request"):
        return HTMLResponse("", status_code=204, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


def set_session_cookie(response: Response, access_token: str, *, secure: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_digest(access_token),
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
        secure=secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


class AuthMiddleware:
    """Pure ASGI auth/CSRF gate with a settings-version cache."""

    def __init__(self, app, db: Database, bound_host: str | None = None) -> None:
        self.app = app
        self.db = db
        # Settings can be edited while the process is running, but changing a
        # bind address only takes effect after restart.  Keep the address that
        # this socket was actually opened on so a token cannot be cleared to
        # expose an already-bound non-loopback listener.
        self.bound_host = bound_host
        self._cache_version = -1
        self._access_token = ""
        self._requires_auth = False
        self._allowed_hosts: list[str] = []

    def _auth_state(self) -> tuple[str, bool, dict]:
        version = int(self.db.settings_version)
        if version != self._cache_version:
            settings = self.db.settings()
            if self.bound_host is not None:
                settings = {**settings, "bind_host": self.bound_host}
            self._access_token = str(settings.get("access_token") or "")
            self._requires_auth = listener_requires_auth(settings)
            self._allowed_hosts = list(settings.get("allowed_hosts") or [])
            self._cache_version = version
        cached = {
            "allowed_hosts": self._allowed_hosts,
            "bind_host": self.bound_host,
            "access_token": self._access_token,
        }
        return self._access_token, self._requires_auth, cached

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        blocked = self._reject(request)
        if blocked is not None:
            await blocked(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _reject(self, request: Request) -> Response | None:
        path = request.url.path
        token, requires_auth, settings = self._auth_state()
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not origin_ok(request, settings):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "拒绝跨站请求"}, status_code=403)
            return HTMLResponse("<p>拒绝跨站请求</p>", status_code=403)
        if path.startswith("/static") or path in {"/login", "/logout", "/api/health", "/api/update"}:
            return None
        if requires_auth and not host_allowed(request.headers.get("host") or "", settings):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "拒绝跨站请求"}, status_code=403)
            return HTMLResponse("<p>拒绝跨站请求</p>", status_code=403)
        if not requires_auth:
            return None
        provided = (
            request.cookies.get(SESSION_COOKIE)
            or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            or request.headers.get("X-Token", "")
        )
        if token and token_ok(provided, token):
            return None
        if path.startswith("/api/"):
            return JSONResponse({"detail": "未授权"}, status_code=401)
        return login_redirect(request)


class SecurityHeadersMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "same-origin")
            await send(message)

        await self.app(scope, receive, send_with_headers)
