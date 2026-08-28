from __future__ import annotations

import sys
import webbrowser

from apple_refurb_watch.argv import is_frozen
from apple_refurb_watch.daemon import ensure_daemon


def _hide_console_if_frozen() -> None:
    if sys.platform != "win32" or not is_frozen():
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:  # noqa: BLE001
        return


def _open_in_browser(url: str) -> None:
    webbrowser.open(url)


def run_desktop() -> None:
    client = ensure_daemon()
    try:
        import webview
    except ImportError as exc:
        if is_frozen():
            _open_in_browser(client.base)
            return
        raise RuntimeError("请先安装桌面依赖：pip install -e '.[desktop]'") from exc

    _hide_console_if_frozen()
    window = webview.create_window("官翻监听", client.base, width=1180, height=800)
    keep = True
    try:
        settings = client.settings()
        keep = bool(settings.get("close_window_keeps_daemon", True))
    except Exception:  # noqa: BLE001
        keep = True

    def on_closing() -> bool:
        if not keep:
            from apple_refurb_watch.daemon import stop_daemon

            stop_daemon()
        return True

    try:
        window.events.closing += on_closing
    except Exception:  # noqa: BLE001
        pass
    try:
        webview.start()
    except Exception:
        _open_in_browser(client.base)
        if not is_frozen():
            raise
