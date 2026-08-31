from __future__ import annotations

import threading
import time

import uvicorn

from apple_refurb_watch.api import create_app
from apple_refurb_watch.client import ApiClient, wait_health
from apple_refurb_watch.daemon import acquire_lock_retry
from apple_refurb_watch.db import Database
from apple_refurb_watch.web.app import apply_windows_loop_policy, uvicorn_options


class EmbeddedServer:
    """在桌面窗口同一进程里跑 FastAPI，避免关掉窗口时把子进程杀掉。"""

    def __init__(self) -> None:
        self._lock = None
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._run_error: BaseException | None = None
        self.host = "127.0.0.1"
        self.port = 8765

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._server and not self._server.should_exit)

    def start(self, timeout: float = 15.0, *, host: str | None = None, port: int | None = None) -> ApiClient:
        self._lock = acquire_lock_retry()
        db = Database()
        settings = db.settings()
        bind_host = host or settings.get("bind_host") or "127.0.0.1"
        bind_port = int(port if port is not None else (settings.get("bind_port") or 8765))
        self.host = "127.0.0.1" if bind_host in {"0.0.0.0", "::"} else bind_host
        self.port = bind_port
        app = create_app(db, with_scheduler=True)
        config = uvicorn.Config(
            app,
            host=bind_host,
            port=bind_port,
            log_level="warning",
            access_log=False,
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
            except BaseException as exc:  # noqa: BLE001
                self._run_error = exc

        thread = threading.Thread(target=_run, name="arw-uvicorn", daemon=True)
        self._thread = thread
        thread.start()
        base = f"http://{self.host}:{self.port}"
        try:
            return wait_health(timeout, base=base)
        except Exception:
            self.stop()
            if self._run_error is not None:
                raise RuntimeError(f"网页服务启动失败: {self._run_error}") from self._run_error
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
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.15)
