from __future__ import annotations

import sys
import webbrowser

from apple_refurb_watch.argv import is_frozen
from apple_refurb_watch.client import ApiClient
from apple_refurb_watch.daemon import ensure_daemon, ping_daemon, stop_daemon
from apple_refurb_watch.embedded import EmbeddedServer


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


def _keep_after_close(client: ApiClient) -> bool:
    try:
        settings = client.settings()
        return bool(settings.get("close_window_keeps_daemon", True))
    except Exception:  # noqa: BLE001
        return True


def run_desktop() -> None:
    embedded: EmbeddedServer | None = None
    owned = False
    client = ping_daemon(stable=True)
    if client is None:
        embedded = EmbeddedServer()
        client = embedded.start()
        owned = True

    try:
        import webview
    except ImportError as exc:
        if is_frozen():
            _open_in_browser(client.base)
            return
        if owned and embedded is not None:
            embedded.stop()
        raise RuntimeError("请先安装桌面依赖：pip install -e '.[desktop]'") from exc

    _hide_console_if_frozen()
    keep = _keep_after_close(client)
    cleaned = False

    def cleanup() -> None:
        nonlocal cleaned
        if cleaned:
            return
        cleaned = True
        if owned and embedded is not None:
            embedded.stop()
            if keep:
                try:
                    ensure_daemon()
                except Exception:  # noqa: BLE001
                    pass
        elif not keep:
            stop_daemon()

    window = webview.create_window("官翻监听", client.base, width=1180, height=800)

    def on_shown() -> None:
        try:
            window.load_url(client.base)
        except Exception:  # noqa: BLE001
            pass

    def on_closing() -> bool:
        cleanup()
        return True

    try:
        window.events.shown += on_shown
    except Exception:  # noqa: BLE001
        pass
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
    finally:
        cleanup()
