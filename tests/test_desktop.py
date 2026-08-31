from apple_refurb_watch import __version__
from apple_refurb_watch.desktop import desktop_setup_uri, gui_import_status, local_health_is_current, tray_menu_labels, version_key
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


def test_version_key_orders_semver() -> None:
    assert version_key(None) < version_key("0.2.3")
    assert version_key("0.1.3") < version_key("0.2.3")
    assert version_key("0.2.0") < version_key(__version__)


def test_local_health_rejects_old_server() -> None:
    assert not local_health_is_current(None)
    assert not local_health_is_current({"ok": True})
    assert not local_health_is_current({"ok": True, "server_version": "0.1.3"})
    assert local_health_is_current({"ok": True, "server_version": __version__})
