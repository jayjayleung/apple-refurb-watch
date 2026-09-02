import os

from apple_refurb_watch.daemon import (
    CREATE_BREAKAWAY_FROM_JOB,
    CREATE_NEW_PROCESS_GROUP,
    CREATE_NO_WINDOW,
    pid_is_alive,
    windows_creationflags,
    windows_hidden_kwargs,
)


def test_current_pid_is_alive():
    assert pid_is_alive(os.getpid()) is True
    assert pid_is_alive(-1) is False


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

    monkeypatch.setattr(daemon.sys, "frozen", True, raising=False)
    env = daemon.spawn_env()
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    monkeypatch.setattr(daemon.sys, "frozen", False, raising=False)
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
