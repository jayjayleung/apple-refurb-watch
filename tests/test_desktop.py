from apple_refurb_watch.desktop import desktop_setup_uri, gui_import_status, tray_menu_labels
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
