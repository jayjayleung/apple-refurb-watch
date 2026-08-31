import os

from apple_refurb_watch.daemon import (
    CREATE_BREAKAWAY_FROM_JOB,
    CREATE_NEW_PROCESS_GROUP,
    CREATE_NO_WINDOW,
    pid_is_alive,
    windows_creationflags,
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


def test_uvicorn_uses_h11_on_windows(monkeypatch) -> None:
    import apple_refurb_watch.web.app as appmod

    monkeypatch.setattr(appmod.sys, "platform", "win32")
    assert appmod.uvicorn_options() == {"http": "h11"}
    monkeypatch.setattr(appmod.sys, "platform", "linux")
    assert appmod.uvicorn_options() == {}


def test_package_root_uses_meipass(tmp_path, monkeypatch) -> None:
    import sys

    from apple_refurb_watch.paths import package_root

    mei = tmp_path / "_MEI"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    assert package_root() == mei / "apple_refurb_watch"


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
