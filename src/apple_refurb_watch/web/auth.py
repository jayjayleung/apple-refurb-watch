from __future__ import annotations

import secrets
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from apple_refurb_watch.db import Database


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, db: Database) -> None:
        super().__init__(app)
        self.db = db

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not origin_ok(request):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "拒绝跨站请求"}, status_code=403)
            return HTMLResponse("<p>拒绝跨站请求</p>", status_code=403)
        if path.startswith("/static") or path in {"/login", "/api/health"}:
            return await call_next(request)
        settings = self.db.settings()
        if not needs_auth(request, settings):
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
    if not settings.get("lan_enabled"):
        return False
    bind = settings.get("bind_host") or "127.0.0.1"
    if bind in {"127.0.0.1", "localhost", "::1"}:
        return False
    host = request.client.host if request.client else ""
    if host in {"127.0.0.1", "::1", "localhost"}:
        return False
    return bool(settings.get("access_token"))
