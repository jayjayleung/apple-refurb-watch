import pytest

from apple_refurb_watch.service import (
    SERVICE_NAME,
    autostart_argv,
    control_commands,
    desktop_autostart_preferred,
    start_service,
)


def test_frozen_windows_autostart_is_hidden_desktop() -> None:
    assert desktop_autostart_preferred(frozen=True, platform="win32")
    assert desktop_autostart_preferred(frozen=True, platform="darwin")
    assert autostart_argv(frozen=True, platform="win32", executable=r"C:\app.exe") == [
        r"C:\app.exe",
        "desktop",
        "--hidden",
    ]
    assert autostart_argv(frozen=True, platform="darwin", executable="/App") == ["/App", "desktop", "--hidden"]


def test_linux_or_source_autostart_is_serve() -> None:
    assert not desktop_autostart_preferred(frozen=True, platform="linux")
    assert not desktop_autostart_preferred(frozen=False, platform="win32")
    assert autostart_argv(frozen=True, platform="linux", executable="/opt/arw") == ["/opt/arw", "serve"]
    argv = autostart_argv(frozen=False, platform="win32", executable="/usr/bin/python")
    assert argv[-1] == "serve"
    assert "-m" in argv


def test_explicit_desktop_flag_overrides_platform() -> None:
    argv = autostart_argv(desktop=True, frozen=False, executable="/usr/bin/python")
    assert argv[-2:] == ["desktop", "--hidden"]


def test_explicit_serve_flag_on_frozen_windows() -> None:
    assert autostart_argv(desktop=False, frozen=True, platform="win32", executable=r"C:\app.exe") == [
        r"C:\app.exe",
        "serve",
    ]


def test_control_commands_linux_macos_windows() -> None:
    assert control_commands("start", platform="linux") == [["systemctl", "--user", "start", SERVICE_NAME]]
    assert control_commands("stop", platform="linux") == [["systemctl", "--user", "stop", SERVICE_NAME]]
    assert control_commands("restart", platform="linux") == [["systemctl", "--user", "restart", SERVICE_NAME]]
    assert control_commands("start", platform="darwin", plist="/tmp/x.plist") == [["launchctl", "load", "/tmp/x.plist"]]
    assert control_commands("stop", platform="darwin", plist="/tmp/x.plist") == [["launchctl", "unload", "/tmp/x.plist"]]
    assert control_commands("restart", platform="darwin", plist="/tmp/x.plist") == [
        ["launchctl", "unload", "/tmp/x.plist"],
        ["launchctl", "load", "/tmp/x.plist"],
    ]
    assert control_commands("start", platform="win32") == [["schtasks", "/Run", "/TN", SERVICE_NAME]]
    assert control_commands("stop", platform="win32") == [["schtasks", "/End", "/TN", SERVICE_NAME]]
    assert control_commands("restart", platform="win32") == [
        ["schtasks", "/End", "/TN", SERVICE_NAME],
        ["schtasks", "/Run", "/TN", SERVICE_NAME],
    ]


def test_start_requires_install(monkeypatch) -> None:
    monkeypatch.setattr("apple_refurb_watch.service.is_service_installed", lambda: False)
    with pytest.raises(RuntimeError, match="service install"):
        start_service()
