from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from apple_refurb_watch.argv import invoke_argv, is_frozen
from apple_refurb_watch.client import ApiClient, ApiError, wait_health
from apple_refurb_watch.paths import lock_path, log_path, runtime_path

CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000


def acquire_lock(path: Path | None = None, *, label: str = "daemon"):
    path = Path(path) if path else lock_path()
    handle = open(path, "a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt

            # msvcrt.locking 不能锁空文件里还不存在的字节。
            if path.stat().st_size < 1:
                handle.write("0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RuntimeError(f"{label} 已在运行") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def acquire_lock_retry(attempts: int = 12, delay: float = 0.25, path: Path | None = None, *, label: str = "daemon"):
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return acquire_lock(path, label=label)
        except RuntimeError as exc:
            last = exc
            time.sleep(delay)
    raise last or RuntimeError(f"{label} 已在运行")


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def lock_pid() -> int | None:
    try:
        text = lock_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def windows_creationflags() -> list[int]:
    """优先脱离 Job，避免关掉桌面窗口时把后台 serve 一起杀掉。"""
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW)
    new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", CREATE_NEW_PROCESS_GROUP)
    return [
        no_window | new_group | CREATE_BREAKAWAY_FROM_JOB,
        no_window | new_group,
    ]


def windows_startupinfo():
    """Windows STARTUPINFO：不显示控制台窗口。"""
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return startupinfo


def windows_hidden_kwargs() -> dict:
    """给 GUI 拉起的 Windows 工具隐藏黑框。"""
    if os.name != "nt":
        return {}
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW),
        "startupinfo": windows_startupinfo(),
    }


def spawn_env() -> dict[str, str]:
    env = os.environ.copy()
    if is_frozen():
        # onefile 子进程要独立解压，否则父进程退出会清掉 _MEIPASS，后台 daemon 立刻死。
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def spawn_detached(cmd: list[str], log_stream):
    env = spawn_env()
    if os.name == "nt":
        hidden = windows_hidden_kwargs()
        last: OSError | None = None
        for flags in windows_creationflags():
            try:
                return subprocess.Popen(
                    cmd,
                    stdout=log_stream,
                    stderr=log_stream,
                    cwd=None,
                    env=env,
                    creationflags=flags,
                    startupinfo=hidden["startupinfo"],
                    close_fds=False,
                )
            except OSError as exc:
                last = exc
        if last:
            raise last
        raise OSError("无法启动后台进程")
    return subprocess.Popen(
        cmd,
        stdout=log_stream,
        stderr=log_stream,
        cwd=None,
        env=env,
        start_new_session=True,
    )


def ping_daemon(base: str | None = None, *, stable: bool = False) -> ApiClient | None:
    client = ApiClient(base)
    try:
        client.health()
    except ApiError:
        client.close()
        return None
    if not stable:
        return client
    time.sleep(0.35)
    try:
        client.health()
    except ApiError:
        client.close()
        return None
    return client


def ensure_daemon(timeout: float | None = None, host: str | None = None, port: int | None = None) -> ApiClient:
    # 冻结 onefile 子进程还要再解压一遍，Windows 上经常超过 15 秒。
    if timeout is None:
        timeout = 60.0 if is_frozen() else 15.0
    base = _wait_base(host, port)
    ready = ping_daemon(base, stable=True)
    if ready:
        return ready
    log = log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = invoke_argv("serve", "--detach-child")
    if host:
        cmd.extend(["--host", str(host)])
    if port is not None:
        cmd.extend(["--port", str(port)])
    with open(log, "a", encoding="utf-8") as stream:
        spawn_detached(cmd, stream)
    return wait_health(timeout, base=base)


def _wait_base(host: str | None, port: int | None) -> str | None:
    if host is None and port is None:
        return None
    wait_host = host or "127.0.0.1"
    if wait_host in {"0.0.0.0", "::"}:
        wait_host = "127.0.0.1"
    return f"http://{wait_host}:{port or 8765}"


def is_running() -> bool:
    client = ApiClient()
    try:
        client.health()
        return True
    except ApiError:
        return False
    finally:
        client.close()


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
