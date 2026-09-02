from apple_refurb_watch.argv import desktop_hides_console, ensure_stdio, invoke_argv, with_frozen_default_command


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


def test_ensure_stdio_replaces_none_streams(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)
    ensure_stdio()
    import sys

    assert sys.stdout is not None
    assert sys.stderr is not None
    sys.stdout.write("")
    sys.stderr.write("")
    sys.stdout.flush()
    sys.stderr.flush()
    # Windows 会把 nul 报成 TTY，不能靠 isatty() 判断。


def test_uvicorn_config_survives_missing_stdio(monkeypatch) -> None:
    import sys

    import uvicorn
    from fastapi import FastAPI

    from apple_refurb_watch.web.app import uvicorn_options

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    ensure_stdio()
    options = uvicorn_options()
    assert options["http"] == "h11"
    assert options["use_colors"] is False
    uvicorn.Config(
        FastAPI(),
        host="127.0.0.1",
        port=0,
        log_level="warning",
        access_log=False,
        log_config=None,
        **options,
    )
