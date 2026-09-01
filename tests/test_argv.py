from apple_refurb_watch.argv import desktop_hides_console, invoke_argv, with_frozen_default_command


def test_frozen_windows_no_args_opens_desktop():
    assert with_frozen_default_command(["app.exe"], frozen=True, platform="win32") == [
        "app.exe",
        "desktop",
    ]


def test_frozen_macos_no_args_opens_desktop():
    assert with_frozen_default_command(["arw"], frozen=True, platform="darwin") == ["arw", "desktop"]


def test_frozen_linux_no_args_stays_cli():
    assert with_frozen_default_command(["arw"], frozen=True, platform="linux") == ["arw"]


def test_source_tree_no_args_unchanged():
    assert with_frozen_default_command(["arw"], frozen=False, platform="win32") == ["arw"]


def test_explicit_command_kept():
    assert with_frozen_default_command(
        ["app.exe", "serve", "--detach"],
        frozen=True,
        platform="win32",
    ) == ["app.exe", "serve", "--detach"]


def test_source_uses_module_flag():
    assert invoke_argv("serve", "--detach-child", frozen=False, executable="/usr/bin/python") == [
        "/usr/bin/python",
        "-m",
        "apple_refurb_watch",
        "serve",
        "--detach-child",
    ]


def test_frozen_calls_exe_directly():
    assert invoke_argv("serve", "--detach-child", frozen=True, executable=r"C:\app.exe") == [
        r"C:\app.exe",
        "serve",
        "--detach-child",
    ]


def test_desktop_hides_console_for_window_not_probe():
    assert desktop_hides_console(["app.exe", "desktop"]) is True
    assert desktop_hides_console(["app.exe", "desktop", "--hidden"]) is True
    assert desktop_hides_console(["app.exe", "desktop", "--probe"]) is False
    assert desktop_hides_console(["app.exe", "serve"]) is False
    assert desktop_hides_console(["python", "-m", "apple_refurb_watch", "desktop"]) is False
