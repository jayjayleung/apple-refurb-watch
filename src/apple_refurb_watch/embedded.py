from __future__ import annotations

import threading
import time

import uvicorn

from apple_refurb_watch.api import create_app
from apple_refurb_watch.argv import ensure_stdio
from apple_refurb_watch.client import ApiClient, wait_health
from apple_refurb_watch.daemon import acquire_lock_retry
from apple_refurb_watch.db import Database
from apple_refurb_watch.storage.schema import DEFAULT_BIND_PORT
from apple_refurb_watch.web.app import apply_windows_loop_policy, uvicorn_options
from apple_refurb_watch.web.auth import validate_listener_security


class EmbeddedServer:
    """在桌面窗口同一进程里跑 FastAPI，避免关掉窗口时把子进程杀掉。"""

    def __init__(self) -> None:
        self._lock = None
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._run_error: BaseException | None = None
        self.host = "127.0.0.1"
        self.port = DEFAULT_BIND_PORT

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._server and not self._server.should_exit)

    def start(self, timeout: float = 15.0, *, host: str | None = None, port: int | None = None) -> ApiClient:
        self._lock = acquire_lock_retry()
        db = None
        started = False
        try:
            db = Database()
            settings = db.settings()
            bind_host = host or settings.get("bind_host") or "127.0.0.1"
            bind_port = int(port if port is not None else (settings.get("bind_port") or DEFAULT_BIND_PORT))
            effective_settings = dict(settings)
            effective_settings.update({"bind_host": bind_host, "bind_port": bind_port})
            validate_listener_security(effective_settings)
            self.host = "127.0.0.1" if bind_host in {"0.0.0.0", "::"} else bind_host
            self.port = bind_port
            app = create_app(
                db,
                with_scheduler=True,
                close_database=True,
                listener_host=bind_host,
                listener_port=bind_port,
            )
            ensure_stdio()
            config = uvicorn.Config(
                app,
                host=bind_host,
                port=bind_port,
                log_level="warning",
                access_log=False,
                log_config=None,
                **uvicorn_options(),
            )
            server = uvicorn.Server(config)
            self._server = server
            self._run_error = None

            def _run() -> None:
                try:
                    apply_windows_loop_policy()
                    server.run()
                except SystemExit as exc:
                    self._run_error = RuntimeError(f"uvicorn 退出: {exc.code}")
                except BaseException as exc:
                    self._run_error = exc

            thread = threading.Thread(target=_run, name="arw-uvicorn", daemon=True)
            self._thread = thread
            thread.start()
            started = True
            base = f"http://{self.host}:{self.port}"
            deadline = time.monotonic() + max(0.0, float(timeout))
            last_exc: BaseException | None = None
            while True:
                if self._run_error is not None:
                    self.stop()
                    raise RuntimeError(f"网页服务启动失败: {self._run_error}") from self._run_error
                if thread is not None and not thread.is_alive():
                    err = self._run_error or RuntimeError("网页服务线程已退出")
                    self.stop()
                    raise RuntimeError(f"网页服务启动失败: {err}") from err
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    return wait_health(min(0.45, remaining), base=base)
                except Exception as exc:
                    last_exc = exc
            self.stop()
            if self._run_error is not None:
                raise RuntimeError(f"网页服务启动失败: {self._run_error}") from self._run_error
            if last_exc is not None:
                raise last_exc
            raise RuntimeError("网页服务启动超时")
        except Exception:
            if not started:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass
                self.stop()
            raise

    def stop(self, join_timeout: float = 8.0) -> None:
        server = self._server
        thread = self._thread
        if server is not None:
            server.should_exit = True
        if thread is not None and thread.is_alive():
            thread.join(timeout=join_timeout)
        self._server = None
        self._thread = None
        handle = self._lock
        self._lock = None
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        time.sleep(0.15)
