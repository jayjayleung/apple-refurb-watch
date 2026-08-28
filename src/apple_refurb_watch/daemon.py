from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from apple_refurb_watch.argv import invoke_argv
from apple_refurb_watch.client import ApiClient, ApiError, wait_health
from apple_refurb_watch.paths import lock_path, log_path, runtime_path


def acquire_lock():
    path = lock_path()
    handle = open(path, "a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RuntimeError("daemon 已在运行") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def ensure_daemon(timeout: float = 15.0, host: str | None = None, port: int | None = None) -> ApiClient:
    base = _wait_base(host, port)
    client = ApiClient(base)
    try:
        client.health()
        return client
    except ApiError:
        pass
    log = log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = invoke_argv("serve", "--detach-child")
    if host:
        cmd.extend(["--host", str(host)])
    if port is not None:
        cmd.extend(["--port", str(port)])
    popen_kwargs: dict = {
        "stdout": None,
        "stderr": None,
        "cwd": None,
    }
    creationflags = 0
    if os.name == "nt":
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if creationflags:
            popen_kwargs["creationflags"] = creationflags
    else:
        popen_kwargs["start_new_session"] = True
    with open(log, "a", encoding="utf-8") as stream:
        popen_kwargs["stdout"] = stream
        popen_kwargs["stderr"] = stream
        subprocess.Popen(cmd, **popen_kwargs)
    return wait_health(timeout, base=base)


def _wait_base(host: str | None, port: int | None) -> str | None:
    if host is None and port is None:
        return None
    wait_host = host or "127.0.0.1"
    if wait_host in {"0.0.0.0", "::"}:
        wait_host = "127.0.0.1"
    return f"http://{wait_host}:{port or 8765}"


def is_running() -> bool:
    try:
        ApiClient().health()
        return True
    except ApiError:
        return False


def _pid_is_ours(pid: int) -> bool:
    if sys.platform.startswith("linux"):
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            return False
        return "apple_refurb_watch" in cmd or "apple-refurb-watch" in cmd
    return True


def stop_daemon() -> bool:
    runtime = None
    try:
        if runtime_path().exists():
            runtime = json.loads(runtime_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        runtime = None
    pid = (runtime or {}).get("pid")
    if not pid:
        return False
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return False
    if not _pid_is_ours(pid_i):
        return False
    try:
        os.kill(pid_i, 15)
        time.sleep(0.4)
        return True
    except OSError:
        return False
