from __future__ import annotations

import html
import logging
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from apple_refurb_watch.db import Database
from apple_refurb_watch.paths import log_path, write_runtime
from apple_refurb_watch.scanner import run_scan
from apple_refurb_watch.web.auth import AuthMiddleware
from apple_refurb_watch.web.render import PageRenderer, templates, web_dir
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


def apply_windows_loop_policy() -> None:
    if sys.platform == "win32":
        import asyncio

        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _log_unhandled(exc: BaseException) -> str:
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logging.exception("网页请求失败")
    try:
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
    except OSError:
        pass
    return text


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
    static_dir = web_dir() / "static"
    if not static_dir.is_dir():
        raise RuntimeError(f"安装包缺少网页静态文件: {static_dir}")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
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

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        text = _log_unhandled(exc)
        if request.url.path.startswith("/api/") or "application/json" in (request.headers.get("accept") or ""):
            return JSONResponse({"detail": str(exc)}, status_code=500)
        body = (
            "<h1>页面出错</h1>"
            "<p>后台已启动，但打开页面时崩溃。下面是原因；完整记录在本机日志。</p>"
            f"<pre>{html.escape(text)}</pre>"
            "<p><a href='/'>重试</a></p>"
        )
        return HTMLResponse(body, status_code=500)

    return app
