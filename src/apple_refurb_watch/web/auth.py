from __future__ import annotations

import secrets
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from apple_refurb_watch.db import Database
from apple_refurb_watch.settings import is_loopback_bind, listener_requires_auth


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


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, db: Database, bound_host: str | None = None) -> None:
        super().__init__(app)
        self.db = db
        # Settings can be edited while the process is running, but changing a
        # bind address only takes effect after restart.  Keep the address that
        # this socket was actually opened on so a token cannot be cleared to
        # expose an already-bound non-loopback listener.
        self.bound_host = bound_host

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not origin_ok(request):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "拒绝跨站请求"}, status_code=403)
            return HTMLResponse("<p>拒绝跨站请求</p>", status_code=403)
        if path.startswith("/static") or path in {"/login", "/api/health"}:
            return await call_next(request)
        settings = self.db.settings()
        auth_settings = settings
        if self.bound_host is not None:
            auth_settings = {**settings, "bind_host": self.bound_host}
        if not needs_auth(request, auth_settings):
            return await call_next(request)
        token = settings.get("access_token") or ""
        provided = (
            request.cookies.get("arw_token")
            or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            or request.headers.get("X-Token", "")
        )
        if token and token_ok(provided, token):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "未授权"}, status_code=401)
        return RedirectResponse("/login")


def token_ok(provided: str, expected: str) -> bool:
    if not expected or not provided:
        return False
    left = provided.encode("utf-8")
    right = expected.encode("utf-8")
    if len(left) != len(right):
        secrets.compare_digest(right, right)
        return False
    return secrets.compare_digest(left, right)


def origin_ok(request: Request) -> bool:
    origin = request.headers.get("origin") or ""
    referer = request.headers.get("referer") or ""
    source = origin or referer
    if not source:
        return True
    incoming = (urlparse(source).netloc or "").lower()
    host = (request.headers.get("host") or "").lower()
    return bool(incoming) and incoming == host


def needs_auth(request: Request, settings: dict) -> bool:
    # Do not inspect request.client here.  A reverse proxy commonly connects
    # over loopback while forwarding requests from the LAN or the public net;
    # trusting that address would bypass authentication.
    del request
    return listener_requires_auth(settings)
