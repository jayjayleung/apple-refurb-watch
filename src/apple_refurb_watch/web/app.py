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
from apple_refurb_watch.deliveries import OutboxWorker
from apple_refurb_watch.paths import clear_runtime, log_path, write_runtime
from apple_refurb_watch.scanner import ScanService
from apple_refurb_watch.web.auth import AuthMiddleware
from apple_refurb_watch.web.render import PageRenderer, templates, web_dir
from apple_refurb_watch.web.routes_api import router as api_router
from apple_refurb_watch.web.routes_pages import router as pages_router
from apple_refurb_watch.web.routes_settings import router as settings_router
from apple_refurb_watch.web.routes_watches import router as watches_router
from apple_refurb_watch.settings import public_url


def uvicorn_options() -> dict[str, Any]:
    # 钉死 h11，避免 uvicorn[standard] 在 Windows 上选 httptools + ProactorEventLoop。
    return {"http": "h11"}


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


def create_app(
    db: Database | None = None,
    *,
    with_scheduler: bool = True,
    scan_service: ScanService | None = None,
    close_database: bool | None = None,
    listener_host: str | None = None,
    listener_port: int | None = None,
) -> FastAPI:
    owns_database = db is None if close_database is None else bool(close_database)
    database = db if db is not None else Database()
    jinja = templates()
    scheduler = BackgroundScheduler()
    renderer = PageRenderer(database, jinja)
    service = scan_service if scan_service is not None else ScanService(database)
    owns_service = scan_service is None
    outbox_worker = OutboxWorker(database)

    # The socket binding is decided by the process entry point.  Settings may
    # be changed while that process is alive, but those changes take effect
    # only after a restart; runtime metadata must describe this actual socket.
    configured = database.settings()
    bound_host = listener_host or configured.get("bind_host") or "127.0.0.1"
    bound_port = int(listener_port if listener_port is not None else (configured.get("bind_port") or 8765))

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
            service.run_once,
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
        runtime_pid = __import__("os").getpid()
        try:
            settings = database.settings()
            write_runtime(
                {
                    "pid": runtime_pid,
                    "host": bound_host,
                    "port": bound_port,
                    "url": public_url({**settings, "bind_host": bound_host, "bind_port": bound_port}),
                }
            )
            if with_scheduler:
                reschedule()
                scheduler.start()
                # Notification delivery is independent from scan execution;
                # a provider outage or process restart leaves work in the
                # durable outbox for this worker to reclaim.
                outbox_worker.start()
            yield
        finally:
            try:
                if with_scheduler:
                    outbox_worker.stop()
            finally:
                try:
                    if with_scheduler and scheduler.running:
                        # Wait for an in-flight scan before closing its database.
                        scheduler.shutdown(wait=True)
                finally:
                    try:
                        if owns_service:
                            service.close()
                    finally:
                        if owns_database:
                            database.close()
            clear_runtime(runtime_pid)

    app = FastAPI(title="苹果官翻监听", lifespan=lifespan)
    app.state.db = database
    app.state.scheduler = scheduler
    app.state.reschedule = reschedule
    app.state.scan_service = service
    app.state.outbox_worker = outbox_worker
    app.state.render = renderer
    app.state.jinja = jinja
    app.state.bound_host = bound_host
    app.state.bound_port = bound_port
    static_dir = web_dir() / "static"
    if not static_dir.is_dir():
        raise RuntimeError(f"安装包缺少网页静态文件: {static_dir}")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.add_middleware(AuthMiddleware, db=database, bound_host=app.state.bound_host)
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
