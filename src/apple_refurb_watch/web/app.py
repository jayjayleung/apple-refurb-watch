from __future__ import annotations

import html
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from apple_refurb_watch.db import Database
from apple_refurb_watch.paths import write_runtime
from apple_refurb_watch.scanner import run_scan
from apple_refurb_watch.web.auth import AuthMiddleware
from apple_refurb_watch.web.render import WEB_DIR, PageRenderer, templates
from apple_refurb_watch.web.routes_api import router as api_router
from apple_refurb_watch.web.routes_pages import router as pages_router
from apple_refurb_watch.web.routes_settings import router as settings_router
from apple_refurb_watch.web.routes_watches import router as watches_router
from apple_refurb_watch.settings import public_url


def uvicorn_options() -> dict[str, Any]:
    # Windows 默认 ProactorEventLoop 不支持 httptools 的 add_reader。
    if sys.platform == "win32":
        return {"http": "h11"}
    return {}


def create_app(db: Database | None = None, *, with_scheduler: bool = True) -> FastAPI:
    database = db or Database()
    jinja = templates()
    scheduler = BackgroundScheduler()
    renderer = PageRenderer(database, jinja)

    def reschedule() -> None:
        if not with_scheduler:
            return
        settings = database.settings()
        if not settings.get("listen_enabled", True):
            if scheduler.get_job("scan"):
                scheduler.remove_job("scan")
            return
        interval = max(60, int(settings.get("interval_seconds") or 300))
        scheduler.add_job(
            lambda: run_scan(database),
            "interval",
            seconds=interval,
            id="scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now() + timedelta(seconds=4),
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        settings = database.settings()
        write_runtime(
            {
                "pid": __import__("os").getpid(),
                "host": settings.get("bind_host") or "127.0.0.1",
                "port": settings.get("bind_port") or 8765,
                "url": public_url(settings),
            }
        )
        if with_scheduler:
            reschedule()
            scheduler.start()
        yield
        if with_scheduler and scheduler.running:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="苹果官翻监听", lifespan=lifespan)
    app.state.db = database
    app.state.scheduler = scheduler
    app.state.reschedule = reschedule
    app.state.render = renderer
    app.state.jinja = jinja
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
    app.add_middleware(AuthMiddleware, db=database)
    app.include_router(api_router)
    app.include_router(pages_router)
    app.include_router(watches_router)
    app.include_router(settings_router)

    @app.exception_handler(HTTPException)
    async def http_exc(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/") or "application/json" in (request.headers.get("accept") or ""):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        if exc.status_code in {401, 403}:
            return RedirectResponse("/login")
        detail = html.escape(str(exc.detail))
        return HTMLResponse(f"<p>{detail}</p><p><a href='/'>返回</a></p>", status_code=exc.status_code)

    return app
