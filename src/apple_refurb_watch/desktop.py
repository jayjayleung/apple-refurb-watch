from __future__ import annotations

from apple_refurb_watch.client import ApiClient
from apple_refurb_watch.daemon import ensure_daemon


def run_desktop() -> None:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("请先安装桌面依赖：pip install -e '.[desktop]'") from exc

    client = ensure_daemon()
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
    webview.start()
