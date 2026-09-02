from apple_refurb_watch import DESKTOP_USER_AGENT_PREFIX, __version__
from apple_refurb_watch.desktop import (
    desktop_app_title,
    desktop_setup_uri,
    desktop_user_agent,
    desktop_window_options,
    gui_import_status,
    local_health_is_current,
    start_desktop_webview,
    tray_app_title,
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


def test_desktop_chrome_does_not_repeat_app_title() -> None:
    templates = package_root() / "web" / "templates"
    base = (templates / "base.html").read_text(encoding="utf-8")
    login = (templates / "login.html").read_text(encoding="utf-8")
    mark = (templates / "_desktop_mark.html").read_text(encoding="utf-8")
    settings = (templates / "settings.html").read_text(encoding="utf-8")
    css = (package_root() / "web" / "static" / "style.css").read_text(encoding="utf-8")
    assert 'class="brand-name"' in base
    assert 'aria-label="官翻监听"' in base
    assert f'startswith("{DESKTOP_USER_AGENT_PREFIX}")' in base
    assert f'startswith("{DESKTOP_USER_AGENT_PREFIX}")' in login
    assert '_desktop_mark.html' in base
    assert '_desktop_mark.html' in login
    assert "arw_desktop" in mark
    assert "sessionStorage" in mark
    assert f'startsWith("{DESKTOP_USER_AGENT_PREFIX}")' in mark
    assert 'classList.add("desktop")' in mark
    assert "pywebviewready" in mark
    assert 'class="brand-name"' in login
    assert "{{ app_version }}" not in base
    assert "{{ app_version }}" not in login
    assert 'id="nav-settings"' in base
    assert 'class="nav-update-dot"' in base
    assert 'id="ver-pop"' not in base
    assert ".ver-pop" not in mark
    assert "html.desktop .brand" in mark
    assert "html.desktop .login-mark" in mark
    assert "html.desktop .brand" in css
    assert "html.desktop .login-mark" in css
    assert "#nav-settings.has-update .nav-update-dot" in css
    assert "desktop-update-dismiss" not in settings
    assert 'id="server-update"' in settings
    assert "服务 {{ app_version }}" in settings
    assert '"桌面 " + s.client_version' in base
    assert ">有更新</a>" in settings
    assert '$(isDesktopShell() ? "desktop-update" : "server-update")' in base
    bridge_wait = 'if (document.documentElement.classList.contains("desktop")) return;'
    assert bridge_wait in base
    assert base.index(bridge_wait) < base.index("bootTimer = setTimeout")


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


def test_desktop_app_title_omits_version() -> None:
    assert desktop_app_title() == "官翻监听"


def test_linux_tray_title_is_x11_safe() -> None:
    assert tray_app_title(platform="linux") == "Apple Refurb Watch"
    assert tray_app_title(platform="win32") == desktop_app_title()
    assert tray_app_title(platform="darwin") == desktop_app_title()


def test_desktop_webview_uses_versioned_user_agent() -> None:
    captured: dict = {}

    class FakeWebview:
        @staticmethod
        def start(**kwargs):
            captured.update(kwargs)

    assert desktop_user_agent() == f"{DESKTOP_USER_AGENT_PREFIX}{__version__}"
    start_desktop_webview(FakeWebview)
    assert captured == {"user_agent": desktop_user_agent()}


def test_desktop_state_exposes_client_version_and_update() -> None:
    from apple_refurb_watch.desktop import DesktopSession, _update_hint_js

    session = DesktopSession(hidden=True)
    state = session.public_state()
    assert state["client_version"] == __version__
    assert state["update"] is None
    assert state["update_checked"] is False
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
    assert "nav-settings" in js
    assert "desktop-update" in js
    assert "server-update" in js
    assert "__arwShowUpdate" in js
    assert "arw_update_dismissed" not in js
    assert "update-banner" not in js


def test_desktop_update_check_bypasses_cache(monkeypatch) -> None:
    from apple_refurb_watch.desktop import DesktopSession

    seen: dict = {}

    def fake_info(**kwargs):
        seen.update(kwargs)
        return {
            "ok": True,
            "current": "0.3.5",
            "latest": "0.3.6",
            "newer": True,
            "url": "https://github.com/jayjayleung/apple-refurb-watch/releases/latest",
        }

    monkeypatch.setattr("apple_refurb_watch.desktop.latest_release_info", fake_info)
    session = DesktopSession(hidden=True)
    injected: list[str] = []
    session.window = type("Window", (), {"evaluate_js": lambda self, js: injected.append(js)})()
    session.check_for_update()
    assert seen.get("refresh") is True
    assert seen.get("current") == __version__
    assert session.update_checked is True
    assert session.update["latest"] == "0.3.6"
    assert injected
    assert "0.3.6" in injected[0]


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
    assert captured["title"] == "官翻监听"
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


class _FakeWindow:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def hide(self) -> None:
        self.ops.append("hide")

    def show(self) -> None:
        self.ops.append("show")

    def restore(self) -> None:
        self.ops.append("restore")

    def minimize(self) -> None:
        self.ops.append("minimize")

    def destroy(self) -> None:
        self.ops.append("destroy")


class _FakeTray:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def test_window_close_hides_to_tray_by_default() -> None:
    from apple_refurb_watch.desktop import DesktopSession, handle_window_closing

    session = DesktopSession(hidden=False)
    session.window = _FakeWindow()
    session.tray_icon = _FakeTray()
    assert handle_window_closing(session) is False
    assert session.window.ops == ["hide"]
    assert session.cleaned is False
    assert session.tray_icon.stopped is False


def test_tray_quit_destroys_window_instead_of_hiding() -> None:
    from apple_refurb_watch.desktop import DesktopSession, handle_window_closing

    session = DesktopSession(hidden=False)
    session.window = _FakeWindow()
    session.tray_icon = _FakeTray()
    session.quit_app(force_after=0)
    assert session.exiting is True
    assert session.hide is False
    assert session.window.ops == ["destroy"]
    assert session.tray_icon.stopped is False
    assert handle_window_closing(session) is True
    assert session.cleaned is True
    assert session.tray_icon.stopped is True


def test_window_close_exits_when_hide_to_tray_disabled() -> None:
    from apple_refurb_watch.desktop import DesktopSession, handle_window_closing

    session = DesktopSession(hidden=False)
    session.window = _FakeWindow()
    session.tray_icon = _FakeTray()
    session.hide = False
    assert handle_window_closing(session) is True
    assert session.window.ops == []
    assert session.cleaned is True
    assert session.tray_icon.stopped is True


def test_attach_runtime_local_failure_does_not_occupy(monkeypatch) -> None:
    from apple_refurb_watch.daemon import acquire_lock
    from apple_refurb_watch.desktop import DesktopSession
    from apple_refurb_watch.embedded import EmbeddedServer

    def boom(self, *args, **kwargs):
        raise ValueError("Unable to configure formatter 'default'")

    monkeypatch.setattr(EmbeddedServer, "start", boom)
    session = DesktopSession(hidden=False)
    session.attach_runtime()
    assert session.client is None
    assert session.owned is False
    assert session.embedded is None
    assert "无法启动本机服务" in (session.error or "")
    handle = acquire_lock()
    handle.close()


def test_disconnect_relaunch_stops_before_respawn(monkeypatch) -> None:
    import time

    from apple_refurb_watch.desktop import DesktopSession

    order: list[str] = []
    monkeypatch.setattr(
        "apple_refurb_watch.desktop.relaunch_desktop",
        lambda **kwargs: order.append("relaunch"),
    )
    session = DesktopSession(hidden=False)
    session.window = _FakeWindow()
    session.owned = False
    original = session.cleanup

    def tracked_cleanup(*, stop_runtime: bool) -> None:
        order.append("cleanup")
        original(stop_runtime=stop_runtime)

    session.cleanup = tracked_cleanup  # type: ignore[method-assign]
    session.schedule_relaunch(hidden=False)
    deadline = time.monotonic() + 2.0
    while "relaunch" not in order and time.monotonic() < deadline:
        time.sleep(0.05)
    assert session.window.ops == ["destroy"]
    assert order == ["cleanup", "relaunch"]


def test_frozen_quit_arms_force_exit(monkeypatch) -> None:
    from apple_refurb_watch import desktop as desktop_mod
    from apple_refurb_watch.desktop import DesktopSession

    armed: list[float] = []
    monkeypatch.setattr(desktop_mod, "is_frozen", lambda: True)
    session = DesktopSession(hidden=False)
    session.window = _FakeWindow()
    session._arm_force_exit = lambda delay, exit_fn=None: armed.append(delay)
    session.quit_app()
    assert armed == [desktop_mod.FORCE_EXIT_SECONDS]
    assert session.window.ops == ["destroy"]


def test_connect_relaunch_keeps_window_visible() -> None:
    from apple_refurb_watch.desktop import DesktopSession

    seen: list[bool] = []
    session = DesktopSession(hidden=False)
    session.schedule_relaunch = lambda *, hidden: seen.append(hidden)  # type: ignore[method-assign]
    assert session.connect_server("http://192.168.1.8:8765", "token")["relaunch"] is True
    assert session.disconnect_server()["relaunch"] is True
    assert seen == [False, False]


def test_visible_start_shows_window_hidden_start_stays_tray() -> None:
    from apple_refurb_watch.desktop import DesktopSession, handle_window_shown

    visible = DesktopSession(hidden=False)
    visible.window = _FakeWindow()
    handle_window_shown(visible)
    assert visible.window.ops == ["show", "restore"]

    hidden = DesktopSession(hidden=True)
    hidden.window = _FakeWindow()
    handle_window_shown(hidden)
    assert hidden.window.ops == ["hide"]
    assert hidden.hidden is False
    assert hidden.start_hidden is True


def test_visible_relaunch_does_not_pass_sw_hide(monkeypatch) -> None:
    from apple_refurb_watch import desktop as desktop_mod
    from apple_refurb_watch.desktop import relaunch_desktop

    seen: dict = {}

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

        class Proc:
            pass

        return Proc()

    monkeypatch.setattr(desktop_mod.os, "name", "nt")
    monkeypatch.setattr(desktop_mod, "windows_creationflags", lambda: [0x1])
    monkeypatch.setattr(desktop_mod.subprocess, "Popen", fake_popen)
    relaunch_desktop(hidden=False)
    assert seen["cmd"][-1] == "desktop"
    assert "--hidden" not in seen["cmd"]
    assert "startupinfo" not in seen["kwargs"]


def test_hidden_relaunch_adds_flag_without_sw_hide(monkeypatch) -> None:
    from apple_refurb_watch import desktop as desktop_mod
    from apple_refurb_watch.desktop import relaunch_desktop

    seen: dict = {}

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

        class Proc:
            pass

        return Proc()

    monkeypatch.setattr(desktop_mod.os, "name", "nt")
    monkeypatch.setattr(desktop_mod, "windows_creationflags", lambda: [0x1])
    monkeypatch.setattr(desktop_mod.subprocess, "Popen", fake_popen)
    relaunch_desktop(hidden=True)
    assert seen["cmd"][-2:] == ["desktop", "--hidden"]
    assert "startupinfo" not in seen["kwargs"]


def test_desktop_lock_retries_before_signaling(monkeypatch) -> None:
    import threading
    import time

    from apple_refurb_watch.daemon import acquire_lock
    from apple_refurb_watch.desktop import stamp_desktop_lock, take_desktop_lock
    from apple_refurb_watch.paths import desktop_lock_path

    signaled: list[float] = []
    monkeypatch.setattr(
        "apple_refurb_watch.desktop.signal_existing_window",
        lambda: signaled.append(1.0),
    )
    holder = acquire_lock(desktop_lock_path(), label="桌面窗口")
    stamp_desktop_lock(holder)
    try:
        def release() -> None:
            time.sleep(0.2)
            holder.close()

        threading.Thread(target=release, daemon=True).start()
        handle = take_desktop_lock()
        assert handle is not None
        assert signaled == []
        handle.close()
    finally:
        try:
            holder.close()
        except Exception:
            pass
