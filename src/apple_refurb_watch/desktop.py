from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import webbrowser

from apple_refurb_watch import DESKTOP_USER_AGENT_PREFIX, __version__
from apple_refurb_watch.argv import invoke_argv, is_frozen
from apple_refurb_watch.client import ApiClient, ApiError
from apple_refurb_watch.connection import (
    ENV_URL,
    check_client_compat,
    clear_connection,
    compat_notice,
    has_capability,
    inferred_capabilities,
    load_connection,
    save_computer_notify,
    save_connection,
)
from apple_refurb_watch.daemon import (
    acquire_lock,
    ping_daemon,
    spawn_env,
    stop_daemon,
    windows_creationflags,
    windows_hidden_kwargs,
)
from apple_refurb_watch.desktop_adapter import DesktopAdapter
from apple_refurb_watch.desktop_notify import notify_os
from apple_refurb_watch.embedded import EmbeddedServer
from apple_refurb_watch.parse import product_page_url
from apple_refurb_watch.paths import desktop_lock_path, desktop_signal_path, package_root
from apple_refurb_watch.update_check import latest_release_info, version_key
from apple_refurb_watch.service import (
    desktop_autostart_preferred,
    install_service,
    is_service_installed,
    uninstall_service,
)


def _close_client(client: object | None) -> None:
    """Close an API client when it supports explicit lifecycle cleanup.

    Desktop tests and integrations sometimes provide a small client double;
    keeping this helper defensive preserves that calling convention while the
    production ``ApiClient`` gets deterministic connection cleanup.
    """
    close = getattr(client, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:  # noqa: BLE001
        pass


FORCE_EXIT_SECONDS = 2.0


def hide_to_tray_enabled(settings: dict | None) -> bool:
    if not settings:
        return True
    return bool(settings.get("close_window_keeps_daemon", True))


def local_health_is_current(health: dict | None) -> bool:
    if not isinstance(health, dict) or not health.get("ok"):
        return False
    return version_key(str(health.get("server_version") or "")) >= version_key(__version__)


def read_desktop_lock_meta() -> tuple[int | None, str | None]:
    try:
        text = desktop_lock_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None, None
    parts = text.split()
    pid = int(parts[0]) if parts and parts[0].isdigit() else None
    ver = parts[1] if len(parts) > 1 else None
    return pid, ver


def stamp_desktop_lock(handle) -> None:
    handle.seek(0)
    handle.truncate()
    handle.write(f"{os.getpid()} {__version__}")
    handle.flush()


def alert_quit_old_desktop(running_ver: str | None) -> None:
    extra = f"托盘里是 {running_ver}，这一包是 {__version__}。" if running_ver else f"这一包是 {__version__}。"
    message = "已经有旧版官翻监听在运行。请右键托盘图标点「退出」，再打开这个新安装包。" + extra
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "官翻监听", 0x30)
            return
        except Exception:  # noqa: BLE001
            pass
    print(message, file=sys.stderr)


def stop_pid(pid: int) -> None:
    try:
        os.kill(pid, 15)
    except OSError:
        pass
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            **windows_hidden_kwargs(),
        )


def take_desktop_lock():
    try:
        handle = acquire_lock(desktop_lock_path(), label="桌面窗口")
    except RuntimeError:
        pid, running_ver = read_desktop_lock_meta()
        if version_key(running_ver) < version_key(__version__) and pid:
            stop_pid(pid)
            time.sleep(0.8)
            try:
                handle = acquire_lock(desktop_lock_path(), label="桌面窗口")
            except RuntimeError:
                alert_quit_old_desktop(running_ver)
                return None
        else:
            signal_existing_window()
            return None
    stamp_desktop_lock(handle)
    return handle


def signal_existing_window() -> None:
    desktop_signal_path().write_text(str(time.time()), encoding="utf-8")


def desktop_setup_uri() -> str:
    return (package_root() / "web" / "static" / "desktop-setup.html").resolve().as_uri()


def gui_import_status(*, adapter: DesktopAdapter | None = None) -> dict[str, str]:
    """Return optional desktop dependency status without importing at module load."""
    return (adapter or DesktopAdapter()).status()


def desktop_user_agent() -> str:
    return f"{DESKTOP_USER_AGENT_PREFIX}{__version__}"


def desktop_app_title() -> str:
    return "官翻监听"


def tray_app_title(*, platform: str | None = None) -> str:
    current = platform or sys.platform
    return "Apple Refurb Watch" if current.startswith("linux") else desktop_app_title()


def start_desktop_webview(webview) -> None:
    webview.start(user_agent=desktop_user_agent())


def tray_menu_labels(*, listening: bool) -> list[str]:
    return [
        "打开",
        "停止监听" if listening else "开始监听",
        "连接服务器…",
        "电脑通知",
        "开机自启",
        "退出",
    ]


def _free_local_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def relaunch_desktop(*, hidden: bool = False) -> None:
    args = ["desktop"]
    if hidden:
        args.append("--hidden")
    cmd = invoke_argv(*args)
    env = spawn_env()
    if os.name == "nt":
        hidden_kw = windows_hidden_kwargs()
        last: OSError | None = None
        for flags in windows_creationflags():
            try:
                subprocess.Popen(
                    cmd,
                    env=env,
                    close_fds=False,
                    creationflags=flags,
                    startupinfo=hidden_kw.get("startupinfo"),
                )
                return
            except OSError as exc:
                last = exc
        if last:
            raise last
        raise OSError("无法重新打开桌面窗口")
    subprocess.Popen(cmd, env=env, start_new_session=True, close_fds=True)


def probe_runtime(*, require_gui: bool | None = None) -> dict:
    """不打开窗口：拉起本机服务、检查首页，并报告桌面/托盘依赖。"""
    import httpx

    adapter = DesktopAdapter()
    notes = gui_import_status(adapter=adapter)
    if require_gui is None:
        require_gui = is_frozen() and sys.platform in {"win32", "darwin"}
    if require_gui and notes.get("webview") != "ok":
        raise RuntimeError(f"桌面窗口依赖缺失：{notes.get('webview')}")
    if require_gui and notes.get("tray") != "ok":
        raise RuntimeError(f"托盘依赖缺失：{notes.get('tray')}")

    port = _free_local_port()
    embedded = EmbeddedServer()
    client = embedded.start(host="127.0.0.1", port=port)
    try:
        health = client.health()
        if not health.get("ok"):
            raise RuntimeError("health 未就绪")
        response = httpx.get(f"{client.base}/", timeout=15.0, follow_redirects=True)
        if response.status_code != 200 or "官翻监听" not in response.text:
            raise RuntimeError(f"GET / 失败：HTTP {response.status_code}")
        return {"ok": True, "notes": notes, "health": health, "home": response.status_code}
    finally:
        _close_client(client)
        embedded.stop()


def tray_icon_path():
    return package_root() / "web" / "static" / "icon-64.png"


def load_tray_image(image_module):
    path = tray_icon_path()
    if path.is_file():
        try:
            return image_module.open(path).convert("RGBA")
        except Exception:  # noqa: BLE001
            pass
    return image_module.new("RGBA", (64, 64), (0, 113, 227, 255))


def _open_in_browser(url: str) -> None:
    webbrowser.open(url)


def _banner_js(message: str) -> str:
    text = json.dumps(message, ensure_ascii=False)
    return (
        "(function(){"
        "var el=document.getElementById('compat-banner');"
        "if(!el){el=document.createElement('p');el.id='compat-banner';"
        "el.setAttribute('role','status');"
        "el.style.cssText='margin:0.75rem 1rem 0;padding:0.7rem 0.9rem;border-radius:12px;"
        "background:#fff4d6;color:#9a6b00;';"
        "var main=document.getElementById('main')||document.body;"
        "main.insertBefore(el, main.firstChild);}"
        "el.hidden=false;el.textContent=" + text + ";})();"
    )


def _update_hint_js(latest: str, url: str) -> str:
    latest_js = json.dumps(str(latest), ensure_ascii=False)
    url_js = json.dumps(str(url), ensure_ascii=False)
    return (
        "(function(){"
        "var latest=" + latest_js + ",url=" + url_js + ";"
        "try{if(localStorage.getItem('arw_update_dismissed')===String(latest))return;}catch(e){}"
        "if(window.__arwShowUpdate){window.__arwShowUpdate(latest,url);return;}"
        "var pop=document.getElementById('ver-pop');"
        "if(!pop)return;"
        "var ver=pop.querySelector('.update-ver'); if(ver) ver.textContent=latest;"
        "var a=document.getElementById('update-open')||pop.querySelector('a');"
        "if(a){if(url)a.href=url;a.textContent='打开下载页';}"
        "pop.classList.add('has-update');"
        "})();"
    )


def _poll_appeared(client: ApiClient, enabled: threading.Event, stop: threading.Event) -> None:
    cursor = 0
    try:
        latest = client.events(limit=1, type="appeared") or []
        if latest:
            cursor = int(latest[0].get("id") or 0)
    except Exception:  # noqa: BLE001
        cursor = 0
    while not stop.wait(12):
        if not enabled.is_set():
            continue
        try:
            rows = client.events(limit=50, after_id=cursor, type="appeared") or []
        except Exception:  # noqa: BLE001
            continue
        for event in rows:
            event_id = int(event.get("id") or 0)
            if event_id <= cursor:
                continue
            name = str(event.get("watch_name") or "").strip()
            title = f"官翻上线：{name}" if name else str(event.get("title") or "官翻上线")
            notify_os(
                title,
                str(event.get("message") or ""),
                product_page_url(event.get("sku"), event.get("url")),
            )
            cursor = max(cursor, event_id)


class DesktopSession:
    def __init__(self, *, hidden: bool) -> None:
        self.hidden = hidden
        self.client: ApiClient | None = None
        self.health: dict | None = None
        self.embedded: EmbeddedServer | None = None
        self.owned = False
        self.error: str | None = None
        self.notice: str | None = None
        self.update: dict | None = None
        self.update_checked = False
        self.window = None
        self.tray_icon = None
        self.desk_lock = None
        self.cleaned = False
        self.hide = True
        self.exiting = False
        self.settings: dict = {}
        self.stop_poll = threading.Event()
        self.notify_on = threading.Event()
        self.autostart_on = False

    def public_state(self) -> dict:
        conn = load_connection()
        return {
            "mode": conn.mode,
            "url": conn.url or "",
            "has_token": bool(conn.token),
            "allow_insecure": conn.allow_insecure,
            "computer_notify": conn.computer_notify,
            "autostart": self.autostart_on,
            "autostart_kind": "tray" if desktop_autostart_preferred() else "serve",
            "env_locked": bool(os.environ.get(ENV_URL)),
            "error": self.error,
            "notice": self.notice,
            "client_version": __version__,
            "update": self.update,
            "update_checked": self.update_checked,
            "capabilities": sorted(inferred_capabilities(self.health)),
            "can_notify": has_capability(self.health, "events.after_id") if self.health else False,
            "connected": self.client is not None and not self.error,
        }

    def attach_runtime(self) -> None:
        conn = load_connection()
        self.error = None
        self.notice = None
        self.health = None
        if self.client is not None:
            _close_client(self.client)
        self.client = None
        if conn.url:
            client = ApiClient(conn.url, conn.token)
            try:
                health = client.health()
            except ApiError as exc:
                _close_client(client)
                self.error = f"无法连接服务器 {conn.url}：{exc}"
                return
            hard = check_client_compat(health)
            if hard:
                _close_client(client)
                self.error = hard
                return
            self.client = client
            self.health = health
            self.notice = compat_notice(health)
            return
        client = ping_daemon(stable=True)
        health = None
        if client is not None:
            try:
                health = client.health()
            except ApiError:
                health = None
            if not local_health_is_current(health):
                stop_daemon()
                time.sleep(0.6)
                _close_client(client)
                client = None
                health = None
        if client is None:
            self.embedded = EmbeddedServer()
            client = self.embedded.start()
            self.owned = True
        try:
            if health is None:
                health = client.health()
        except ApiError as exc:
            self.client = client
            _close_client(client)
            self.client = None
            self.error = str(exc)
            return
        hard = check_client_compat(health)
        if hard:
            self.error = hard
            _close_client(client)
            if self.owned and self.embedded is not None:
                self.embedded.stop()
                self.owned = False
                self.embedded = None
                self.client = None
            return
        self.client = client
        self.health = health
        self.notice = compat_notice(health)

    def start_url(self) -> str:
        if self.client is not None and not self.error:
            return self.client.base
        return desktop_setup_uri()

    def apply_notify_preference(self) -> None:
        conn = load_connection()
        if conn.computer_notify and self.client is not None and has_capability(self.health, "events.after_id"):
            self.notify_on.set()
        else:
            self.notify_on.clear()

    def show_window(self) -> None:
        window = self.window
        if window is None:
            return
        for method in ("show", "restore"):
            try:
                getattr(window, method)()
            except Exception:  # noqa: BLE001
                pass

    def hide_window(self) -> None:
        window = self.window
        if window is None:
            return
        try:
            window.hide()
            return
        except Exception:  # noqa: BLE001
            pass
        try:
            window.minimize()
        except Exception:  # noqa: BLE001
            pass

    def load_url(self, url: str) -> None:
        window = self.window
        if window is None:
            return
        try:
            window.load_url(url)
        except Exception:  # noqa: BLE001
            pass

    def show_setup(self) -> None:
        self.show_window()
        self.load_url(desktop_setup_uri())

    def show_app(self) -> dict:
        if self.client is None or self.error:
            return {"ok": False, "error": self.error or "尚未连接到服务"}
        self.load_url(self.client.base)
        return {"ok": True}

    def toggle_listen(self) -> None:
        if self.client is None:
            return
        try:
            current = self.client.settings()
            enabled = not bool(current.get("listen_enabled"))
            self.client.update_settings({"listen_enabled": enabled})
            self.settings["listen_enabled"] = enabled
        except Exception:  # noqa: BLE001
            return

    def set_computer_notify(self, enabled: bool) -> dict:
        if enabled and not has_capability(self.health, "events.after_id"):
            return {"ok": False, "error": "服务器不支持电脑通知轮询，请升级服务器"}
        save_computer_notify(bool(enabled))
        if enabled:
            self.notify_on.set()
        else:
            self.notify_on.clear()
        return {"ok": True}

    def set_autostart(self, enabled: bool) -> dict:
        try:
            if enabled:
                message = install_service()
            else:
                message = uninstall_service()
            self.autostart_on = is_service_installed()
            return {"ok": True, "message": message, "autostart": self.autostart_on}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def connect_server(self, url: str, token: str = "", insecure: bool = False) -> dict:
        if os.environ.get(ENV_URL):
            return {"ok": False, "error": "已用环境变量 APPLE_REFURB_WATCH_URL，请先去掉再改连接"}
        try:
            prev = load_connection()
            save_connection(url, token or prev.token, allow_insecure=bool(insecure))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        self.schedule_relaunch(hidden=False)
        return {"ok": True, "relaunch": True}

    def disconnect_server(self) -> dict:
        if os.environ.get(ENV_URL):
            return {"ok": False, "error": "已用环境变量 APPLE_REFURB_WATCH_URL，请先去掉再改连接"}
        clear_connection()
        self.schedule_relaunch(hidden=False)
        return {"ok": True, "relaunch": True}

    def request_exit(self) -> None:
        self.exiting = True
        self.hide = False

    def schedule_relaunch(self, *, hidden: bool) -> None:
        def _run() -> None:
            time.sleep(0.25)
            self.request_exit()
            self.cleanup(stop_runtime=self.owned)
            try:
                relaunch_desktop(hidden=hidden)
            except Exception:  # noqa: BLE001
                pass
            window = self.window
            if window is not None:
                try:
                    window.destroy()
                except Exception:  # noqa: BLE001
                    pass

        threading.Thread(target=_run, name="arw-relaunch", daemon=True).start()

    def quit_app(self, *, force_after: float | None = None) -> None:
        self.request_exit()
        window = self.window
        if window is not None:
            try:
                window.destroy()
            except Exception:  # noqa: BLE001
                pass
        else:
            self.cleanup(stop_runtime=self.owned)
        delay = FORCE_EXIT_SECONDS if force_after is None else force_after
        if delay > 0 and is_frozen():
            self._arm_force_exit(delay)

    def _arm_force_exit(self, delay: float, exit_fn=os._exit) -> None:
        def _run() -> None:
            time.sleep(delay)
            try:
                self.cleanup(stop_runtime=self.owned)
            except Exception:  # noqa: BLE001
                pass
            exit_fn(0)

        threading.Thread(target=_run, name="arw-force-exit", daemon=True).start()

    def cleanup(self, *, stop_runtime: bool) -> None:
        if self.cleaned:
            return
        self.cleaned = True
        self.stop_poll.set()
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:  # noqa: BLE001
                pass
        if stop_runtime and self.owned and self.embedded is not None:
            self.embedded.stop()
        if self.desk_lock is not None:
            try:
                self.desk_lock.close()
            except Exception:  # noqa: BLE001
                pass
        if self.client is not None:
            _close_client(self.client)
            self.client = None

    def inject_notice(self) -> None:
        if not self.notice or self.window is None:
            return
        try:
            self.window.evaluate_js(_banner_js(self.notice))
        except Exception:  # noqa: BLE001
            pass

    def inject_update(self) -> None:
        info = self.update
        if not info or not info.get("newer") or self.window is None:
            return
        latest = str(info.get("latest") or "")
        url = str(info.get("url") or "")
        if not latest or not url:
            return
        try:
            self.window.evaluate_js(_update_hint_js(latest, url))
        except Exception:  # noqa: BLE001
            pass

    def check_for_update(self) -> None:
        try:
            self.update = latest_release_info(current=__version__, refresh=True)
        except Exception:  # noqa: BLE001
            self.update_checked = True
            return
        self.update_checked = True
        self.inject_update()

    def start_update_check(self) -> None:
        threading.Thread(target=self.check_for_update, name="arw-update", daemon=True).start()


def handle_window_closing(session: DesktopSession) -> bool:
    """关窗时是否真正退出。False 表示只藏到托盘。"""
    if session.hide and not session.exiting:
        session.hide_window()
        return False
    session.cleanup(stop_runtime=session.owned)
    return True


class DesktopApi:
    def __init__(self, session: DesktopSession) -> None:
        self._session = session

    def state(self) -> dict:
        return self._session.public_state()

    def connect(self, url: str, token: str = "", insecure: bool = False) -> dict:
        return self._session.connect_server(str(url or ""), str(token or ""), bool(insecure))

    def disconnect(self) -> dict:
        return self._session.disconnect_server()

    def open_app(self) -> dict:
        return self._session.show_app()

    def set_computer_notify(self, enabled: bool) -> dict:
        return self._session.set_computer_notify(bool(enabled))

    def set_autostart(self, enabled: bool) -> dict:
        return self._session.set_autostart(bool(enabled))

    def test_computer_notify(self) -> dict:
        from apple_refurb_watch.notify import TEST_BODY, TEST_TITLE

        notify_os(TEST_TITLE, TEST_BODY, None)
        return {"ok": True}


def desktop_window_options(*, hidden: bool) -> dict:
    return {
        "width": 1180,
        "height": 800,
        "min_size": (960, 640),
        "hidden": bool(hidden),
    }


def create_session_window(webview, session: DesktopSession, api: DesktopApi):
    url = session.start_url()
    options = desktop_window_options(hidden=session.hidden)
    try:
        return webview.create_window(desktop_app_title(), url, js_api=api, **options)
    except TypeError:
        options.pop("hidden", None)
        return webview.create_window(desktop_app_title(), url, js_api=api, **options)


def _start_tray(session: DesktopSession, *, adapter: DesktopAdapter | None = None):
    try:
        pystray, image_module = (adapter or DesktopAdapter()).require_tray()
    except RuntimeError:
        return None

    image = load_tray_image(image_module)
    listen_state = {"on": bool(session.settings.get("listen_enabled", True))}

    def listen_label(item):  # noqa: ARG001
        return "停止监听" if listen_state["on"] else "开始监听"

    def on_toggle(icon, item):  # noqa: ARG001
        session.toggle_listen()
        listen_state["on"] = not listen_state["on"]
        try:
            icon.update_menu()
        except Exception:  # noqa: BLE001
            pass

    def on_notify(icon, item):  # noqa: ARG001
        session.set_computer_notify(not session.notify_on.is_set())
        try:
            icon.update_menu()
        except Exception:  # noqa: BLE001
            pass

    def on_autostart(icon, item):  # noqa: ARG001
        session.set_autostart(not session.autostart_on)
        try:
            icon.update_menu()
        except Exception:  # noqa: BLE001
            pass

    def on_quit(*_args) -> None:
        threading.Thread(target=session.quit_app, name="arw-quit", daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem("打开", lambda *_: session.show_window(), default=True),
        pystray.MenuItem(listen_label, on_toggle),
        pystray.MenuItem("连接服务器…", lambda *_: session.show_setup()),
        pystray.MenuItem("电脑通知", on_notify, checked=lambda item: session.notify_on.is_set()),
        pystray.MenuItem("开机自启", on_autostart, checked=lambda item: session.autostart_on),
        pystray.MenuItem("退出", on_quit),
    )
    icon = pystray.Icon("apple-refurb-watch", image, tray_app_title(), menu)
    try:
        if hasattr(icon, "run_detached"):
            icon.run_detached()
        else:
            threading.Thread(target=icon.run, name="arw-tray", daemon=True).start()
        return icon
    except Exception:  # noqa: BLE001
        return None


def run_desktop(*, hidden: bool = False) -> None:
    desk_lock = take_desktop_lock()
    if desk_lock is None:
        return

    session = DesktopSession(hidden=hidden)
    adapter = DesktopAdapter()
    session.desk_lock = desk_lock
    session.attach_runtime()
    session.autostart_on = is_service_installed()
    if session.client is not None:
        try:
            session.settings = session.client.settings()
        except Exception:  # noqa: BLE001
            session.settings = {}
        session.hide = hide_to_tray_enabled(session.settings)
    session.apply_notify_preference()

    try:
        webview = adapter.require_webview()
    except RuntimeError as exc:
        if session.client is not None:
            _open_in_browser(session.client.base)
            if is_frozen():
                session.cleanup(stop_runtime=False)
                return
        session.cleanup(stop_runtime=session.owned)
        raise RuntimeError("请先安装桌面依赖：pip install -e '.[desktop]'") from exc

    try:
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    except Exception:  # noqa: BLE001
        pass

    api = DesktopApi(session)
    window = create_session_window(webview, session, api)
    session.window = window

    def on_shown() -> None:
        if session.hidden:
            session.hide_window()
            session.hidden = False
        session.inject_notice()
        session.inject_update()

    def on_loaded() -> None:
        session.inject_notice()
        session.inject_update()

    def on_closing() -> bool:
        return handle_window_closing(session)

    def watch_signal() -> None:
        last = 0.0
        path = desktop_signal_path()
        while not session.stop_poll.wait(1.0):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime > last:
                last = mtime
                session.show_window()

    try:
        window.events.shown += on_shown
    except Exception:  # noqa: BLE001
        pass
    try:
        window.events.loaded += on_loaded
    except Exception:  # noqa: BLE001
        pass
    try:
        window.events.closing += on_closing
    except Exception:  # noqa: BLE001
        pass

    threading.Thread(target=watch_signal, name="arw-desktop-signal", daemon=True).start()
    session.start_update_check()
    if session.client is not None and has_capability(session.health, "events.after_id"):
        threading.Thread(
            target=_poll_appeared,
            args=(session.client, session.notify_on, session.stop_poll),
            name="arw-notify",
            daemon=True,
        ).start()
    session.tray_icon = _start_tray(session, adapter=adapter)

    try:
        start_desktop_webview(webview)
    except Exception:
        if session.client is not None:
            _open_in_browser(session.client.base)
        if not is_frozen():
            session.cleanup(stop_runtime=session.owned)
            raise
    finally:
        session.cleanup(stop_runtime=session.owned)
