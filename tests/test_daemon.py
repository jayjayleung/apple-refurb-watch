import os

import pytest

from apple_refurb_watch.daemon import (
    CREATE_BREAKAWAY_FROM_JOB,
    CREATE_NEW_PROCESS_GROUP,
    CREATE_NO_WINDOW,
    windows_creationflags,
    windows_hidden_kwargs,
)


def test_current_pid_exists():
    from apple_refurb_watch.paths import pid_exists

    assert pid_exists(os.getpid()) is True
    assert pid_exists(-1) is False


def test_acquire_lock_on_empty_file():
    from apple_refurb_watch.daemon import acquire_lock
    from apple_refurb_watch.paths import lock_path

    assert not lock_path().exists() or lock_path().stat().st_size == 0
    handle = acquire_lock()
    try:
        assert lock_path().exists()
        try:
            acquire_lock()
        except RuntimeError as exc:
            assert "已在运行" in str(exc)
        else:
            raise AssertionError("second lock should fail")
    finally:
        handle.close()


def test_windows_flags_break_away_from_job():
    flags = windows_creationflags()
    assert flags[0] & CREATE_BREAKAWAY_FROM_JOB
    assert flags[0] & CREATE_NO_WINDOW
    assert flags[0] & CREATE_NEW_PROCESS_GROUP
    assert flags[1] & CREATE_NO_WINDOW
    assert not (flags[1] & CREATE_BREAKAWAY_FROM_JOB)


def test_windows_hidden_kwargs_hide_console():
    if os.name != "nt":
        assert windows_hidden_kwargs() == {}
        return
    kwargs = windows_hidden_kwargs()
    assert kwargs["creationflags"] & CREATE_NO_WINDOW
    assert kwargs["startupinfo"].wShowWindow == 0


def test_uvicorn_uses_h11_on_windows(monkeypatch) -> None:
    import apple_refurb_watch.web.app as appmod

    monkeypatch.setattr(appmod.sys, "platform", "win32")
    assert appmod.uvicorn_options() == {"http": "h11", "use_colors": False}
    monkeypatch.setattr(appmod.sys, "platform", "linux")
    assert appmod.uvicorn_options() == {"http": "h11", "use_colors": False}


def test_package_root_uses_meipass(tmp_path, monkeypatch) -> None:
    import sys

    from apple_refurb_watch.paths import package_root

    mei = tmp_path / "_MEI"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    assert package_root() == mei / "apple_refurb_watch"


def test_spawn_env_resets_pyinstaller_when_frozen(monkeypatch) -> None:
    from apple_refurb_watch import daemon

    monkeypatch.setattr(daemon, "is_frozen", lambda: True)
    env = daemon.spawn_env()
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    monkeypatch.setattr(daemon, "is_frozen", lambda: False)
    env = daemon.spawn_env()
    assert env.get("PYINSTALLER_RESET_ENVIRONMENT") != "1"


def test_ensure_daemon_frozen_waits_longer(monkeypatch) -> None:
    from apple_refurb_watch import daemon

    monkeypatch.setattr(daemon, "is_frozen", lambda: True)
    monkeypatch.setattr(daemon, "ping_daemon", lambda *a, **k: None)
    monkeypatch.setattr(daemon, "spawn_detached", lambda *a, **k: None)
    captured: dict = {}

    def fake_wait(timeout, base=None):
        captured["timeout"] = timeout
        raise daemon.ApiError("skip")

    monkeypatch.setattr(daemon, "wait_health", fake_wait)
    try:
        daemon.ensure_daemon()
    except daemon.ApiError:
        pass
    assert captured["timeout"] == 60.0


def test_ensure_daemon_unfrozen_default_timeout(monkeypatch) -> None:
    from apple_refurb_watch import daemon

    monkeypatch.setattr(daemon, "is_frozen", lambda: False)
    monkeypatch.setattr(daemon, "ping_daemon", lambda *a, **k: None)
    monkeypatch.setattr(daemon, "spawn_detached", lambda *a, **k: None)
    captured: dict = {}

    def fake_wait(timeout, base=None):
        captured["timeout"] = timeout
        raise daemon.ApiError("skip")

    monkeypatch.setattr(daemon, "wait_health", fake_wait)
    try:
        daemon.ensure_daemon()
    except daemon.ApiError:
        pass
    assert captured["timeout"] == 15.0


def test_embedded_server_starts_and_stops():
    import socket

    import httpx

    from apple_refurb_watch.client import ApiError
    from apple_refurb_watch.db import Database
    from apple_refurb_watch.embedded import EmbeddedServer

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    Database().set_setting("bind_port", port)
    server = EmbeddedServer()
    client = server.start()
    try:
        assert client.health()["ok"] is True
        page = httpx.get(f"{client.base}/", timeout=8)
        assert page.status_code == 200
        assert "官翻监听" in page.text
    finally:
        server.stop()
    try:
        client.health()
        raise AssertionError("stopped server should not answer health")
    except ApiError:
        pass


def test_embedded_start_releases_lock_when_uvicorn_config_fails(monkeypatch) -> None:
    import uvicorn

    from apple_refurb_watch.daemon import acquire_lock
    from apple_refurb_watch.embedded import EmbeddedServer
    from apple_refurb_watch.paths import lock_path

    def boom(*_args, **_kwargs):
        raise ValueError("Unable to configure formatter 'default'")

    monkeypatch.setattr(uvicorn, "Config", boom)
    server = EmbeddedServer()
    try:
        server.start(host="127.0.0.1", port=0)
    except ValueError as exc:
        assert "formatter" in str(exc)
    else:
        raise AssertionError("start should fail")
    handle = acquire_lock()
    try:
        assert lock_path().exists()
    finally:
        handle.close()


def test_embedded_start_survives_none_stdio(monkeypatch) -> None:
    import socket
    import sys

    from apple_refurb_watch.db import Database
    from apple_refurb_watch.embedded import EmbeddedServer

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    Database().set_setting("bind_port", port)
    server = EmbeddedServer()
    client = server.start()
    try:
        assert client.health()["ok"] is True
    finally:
        server.stop()


def test_embedded_start_fails_fast_when_server_run_errors(monkeypatch) -> None:
    import time

    import uvicorn

    from apple_refurb_watch.embedded import EmbeddedServer

    def boom(self):
        raise RuntimeError("bind failed")

    monkeypatch.setattr(uvicorn.Server, "run", boom)
    server = EmbeddedServer()
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="网页服务启动失败"):
        server.start(timeout=15, host="127.0.0.1", port=18901)
    assert time.monotonic() - started < 3


def test_ensure_daemon_forwards_persist_and_uses_db_port(monkeypatch) -> None:
    from apple_refurb_watch import daemon
    from apple_refurb_watch.db import Database

    Database().set_setting("bind_port", 9123)
    captured: dict = {}
    monkeypatch.setattr(daemon, "is_frozen", lambda: False)
    monkeypatch.setattr(daemon, "ping_daemon", lambda *a, **k: None)
    monkeypatch.setattr(daemon, "spawn_detached", lambda cmd, stream: captured.setdefault("cmd", cmd))
    monkeypatch.setattr(
        daemon,
        "wait_health",
        lambda timeout, base=None: captured.setdefault("base", base) or object(),
    )

    daemon.ensure_daemon(host="0.0.0.0", persist=True)
    assert "--persist" in captured["cmd"]
    assert "--host" in captured["cmd"]
    assert "--port" not in captured["cmd"]
    assert captured["base"] == "http://127.0.0.1:9123"


def test_write_runtime_skips_live_foreign_pid(monkeypatch) -> None:
    from apple_refurb_watch import paths

    paths.write_runtime({"pid": 4242, "url": "http://keep"})

    def alive(runtime):
        return int((runtime or {}).get("pid") or 0) == 4242

    monkeypatch.setattr(paths, "runtime_is_alive", alive)
    paths.write_runtime({"pid": 9999, "url": "http://clobber"})
    data = paths.read_runtime()
    assert data["pid"] == 4242
    assert data["url"] == "http://keep"
    paths.clear_runtime(9999)
    assert paths.read_runtime()["pid"] == 4242
    paths.write_runtime({"pid": 4242, "url": "http://updated"})
    assert paths.read_runtime()["url"] == "http://updated"


def test_pid_is_ours_checks_command_on_all_platforms(monkeypatch) -> None:
    from apple_refurb_watch import daemon, paths

    monkeypatch.setattr(paths, "pid_exists", lambda _pid: True)
    monkeypatch.setattr(paths, "process_command_line", lambda _pid: "/usr/sbin/nginx")
    assert daemon._pid_is_ours(1) is False
    monkeypatch.setattr(paths, "process_command_line", lambda _pid: "python -m apple_refurb_watch serve")
    assert daemon._pid_is_ours(1) is True


def test_runtime_is_alive_win32_does_not_os_kill(monkeypatch) -> None:
    from apple_refurb_watch import paths

    killed: list = []
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setattr(paths.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(paths, "pid_exists", lambda _pid: True)
    monkeypatch.setattr(paths, "process_command_line", lambda _pid: r"C:\app\apple-refurb-watch.exe")
    assert paths.runtime_is_alive({"pid": 123}) is True
    assert killed == []
