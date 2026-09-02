from apple_refurb_watch import __version__
from apple_refurb_watch.desktop import (
    desktop_app_title,
    desktop_setup_uri,
    desktop_window_options,
    gui_import_status,
    local_health_is_current,
    tray_menu_labels,
    version_key,
)
from apple_refurb_watch.paths import package_root


def test_tray_menu_covers_connect_notify_autostart() -> None:
    labels = tray_menu_labels(listening=True)
    assert labels[0] == "打开"
    assert "停止监听" in labels
    assert "连接服务器…" in labels
    assert "电脑通知" in labels
    assert "开机自启" in labels
    assert "退出" in labels
    assert "开始监听" in tray_menu_labels(listening=False)


def test_setup_page_is_packaged() -> None:
    assert "desktop-setup.html" in desktop_setup_uri()
    html = package_root() / "web" / "static" / "desktop-setup.html"
    assert html.is_file()
    text = html.read_text(encoding="utf-8")
    assert "连接服务器" in text
    assert "pywebview" in text
    assert "改回本机" in text
    assert "setup-update" in text
    assert "打开下载页" in text
    assert "update-dismiss" in text
    assert "update-banner" not in text


def test_gui_import_status_reports_keys() -> None:
    notes = gui_import_status()
    assert set(notes) == {"webview", "tray"}
    for value in notes.values():
        assert value


def test_desktop_api_can_send_computer_notify(monkeypatch) -> None:
    from apple_refurb_watch.desktop import DesktopApi

    calls = []
    monkeypatch.setattr("apple_refurb_watch.desktop.notify_os", lambda *args, **kwargs: calls.append(args))
    assert DesktopApi(None).test_computer_notify() == {"ok": True}
    assert calls


def test_tray_icon_loads_packaged_png() -> None:
    from apple_refurb_watch.desktop import load_tray_image, tray_icon_path

    path = tray_icon_path()
    assert path.is_file()
    assert path.stat().st_size > 200

    class FakeImage:
        @staticmethod
        def open(opened):
            class Handle:
                def convert(self, mode):
                    return ("opened", str(opened), mode)

            return Handle()

        @staticmethod
        def new(mode, size, color):
            return ("new", mode, size, color)

    assert load_tray_image(FakeImage) == ("opened", str(path), "RGBA")


def test_version_key_orders_semver() -> None:
    assert version_key(None) < version_key("0.2.3")
    assert version_key("0.1.3") < version_key("0.2.3")
    assert version_key("0.2.0") < version_key(__version__)


def test_local_health_rejects_old_server() -> None:
    assert not local_health_is_current(None)
    assert not local_health_is_current({"ok": True})
    assert not local_health_is_current({"ok": True, "server_version": "0.1.3"})
    assert local_health_is_current({"ok": True, "server_version": __version__})


def test_desktop_app_title_includes_version() -> None:
    assert desktop_app_title() == f"官翻监听 {__version__}"


def test_desktop_state_exposes_client_version_and_update() -> None:
    from apple_refurb_watch.desktop import DesktopSession, _update_hint_js

    session = DesktopSession(hidden=True)
    state = session.public_state()
    assert state["client_version"] == __version__
    assert state["update"] is None
    session.update = {
        "ok": True,
        "current": __version__,
        "latest": "9.9.9",
        "newer": True,
        "url": "https://github.com/jayjayleung/apple-refurb-watch/releases/latest",
    }
    assert session.public_state()["update"]["latest"] == "9.9.9"
    js = _update_hint_js("9.9.9", "https://example.invalid/latest")
    assert "9.9.9" in js
    assert "https://example.invalid/latest" in js
    assert "打开下载页" in js
    assert "__arwShowUpdate" in js
    assert "arw_update_dismissed" in js
    assert "update-banner" not in js


def test_hidden_desktop_creates_hidden_window() -> None:
    from apple_refurb_watch.desktop import create_session_window

    assert desktop_window_options(hidden=True)["hidden"] is True
    assert desktop_window_options(hidden=False)["hidden"] is False

    captured: dict = {}

    class FakeWebview:
        @staticmethod
        def create_window(title, url, js_api=None, **kwargs):
            captured.update(kwargs)
            captured["title"] = title
            captured["url"] = url
            captured["js_api"] = js_api
            return "window"

    class FakeSession:
        hidden = True

        def start_url(self):
            return "http://127.0.0.1:8765"

    assert create_session_window(FakeWebview, FakeSession(), api="api") == "window"
    assert captured["hidden"] is True
    assert captured["title"] == desktop_app_title()
    assert captured["title"] == f"官翻监听 {__version__}"
    assert captured["url"] == "http://127.0.0.1:8765"


def test_create_session_window_without_hidden_kw() -> None:
    from apple_refurb_watch.desktop import create_session_window

    class OldWebview:
        @staticmethod
        def create_window(title, url, js_api=None, **kwargs):
            if "hidden" in kwargs:
                raise TypeError("unexpected hidden")
            return "ok"

    class FakeSession:
        hidden = True

        def start_url(self):
            return "http://127.0.0.1:8765"

    assert create_session_window(OldWebview, FakeSession(), api=None) == "ok"


def test_windows_toast_hides_console(monkeypatch) -> None:
    from apple_refurb_watch.daemon import CREATE_NO_WINDOW
    from apple_refurb_watch import desktop_notify

    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(desktop_notify.subprocess, "run", fake_run)
    monkeypatch.setattr(
        desktop_notify,
        "windows_hidden_kwargs",
        lambda: {"creationflags": CREATE_NO_WINDOW},
    )
    desktop_notify._windows_toast("标题", "正文")
    assert seen["cmd"][0] == "powershell"
    assert "-WindowStyle" in seen["cmd"]
    assert "Hidden" in seen["cmd"]
    assert seen["kwargs"]["creationflags"] == CREATE_NO_WINDOW
    assert seen["kwargs"]["capture_output"] is True


def test_stop_pid_taskkill_hides_console(monkeypatch) -> None:
    from apple_refurb_watch.daemon import CREATE_NO_WINDOW
    from apple_refurb_watch.desktop import stop_pid
    from apple_refurb_watch import desktop as desktop_mod

    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(desktop_mod.os, "name", "nt")
    monkeypatch.setattr(desktop_mod.os, "kill", lambda *args, **kwargs: None)
    monkeypatch.setattr(desktop_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(
        desktop_mod,
        "windows_hidden_kwargs",
        lambda: {"creationflags": CREATE_NO_WINDOW},
    )
    stop_pid(1234)
    assert seen["cmd"][:3] == ["taskkill", "/PID", "1234"]
    assert seen["kwargs"]["creationflags"] == CREATE_NO_WINDOW
