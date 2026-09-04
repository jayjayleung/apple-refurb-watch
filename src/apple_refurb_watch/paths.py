from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from platformdirs import user_data_dir, user_log_dir

APP_NAME = "apple-refurb-watch"


def package_root() -> Path:
    """源码包目录；冻结 exe 用 PyInstaller 的 _MEIPASS，不要信 __file__.resolve()。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "apple_refurb_watch"
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    override = os.environ.get("APPLE_REFURB_WATCH_HOME")
    path = Path(override) if override else Path(user_data_dir(APP_NAME, APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    override = os.environ.get("APPLE_REFURB_WATCH_LOG")
    path = Path(override) if override else Path(user_log_dir(APP_NAME, APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "app.db"


def lock_path() -> Path:
    return data_dir() / "daemon.lock"


def desktop_lock_path() -> Path:
    return data_dir() / "desktop.lock"


def desktop_signal_path() -> Path:
    return data_dir() / "desktop.signal"


def runtime_path() -> Path:
    return data_dir() / "daemon.json"


def log_path() -> Path:
    return log_dir() / "daemon.log"


def _runtime_pid(payload: dict | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    try:
        pid = int(payload.get("pid"))
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def write_runtime(payload: dict) -> None:
    """Record listener metadata unless another live process already owns the file."""

    incoming = _runtime_pid(payload)
    current = read_runtime()
    if current and runtime_is_alive(current):
        owner = _runtime_pid(current)
        if owner is not None and owner != incoming:
            return
    target = runtime_path()
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)


def clear_runtime(pid: int | None = None) -> None:
    """Remove runtime metadata, optionally only when owned by ``pid``."""

    target = runtime_path()
    current = read_runtime()
    if pid is not None:
        try:
            if int((current or {}).get("pid")) != int(pid):
                return
        except (TypeError, ValueError):
            return
    elif current and runtime_is_alive(current):
        owner = _runtime_pid(current)
        if owner is not None and owner != os.getpid():
            return
    try:
        target.unlink()
    except OSError:
        pass


def read_runtime() -> dict | None:
    path = runtime_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def pid_exists(pid: int) -> bool:
    """Whether ``pid`` still exists. Windows avoids ``os.kill(pid, 0)``."""

    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_pid_exists(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_pid_exists(pid: int) -> bool:
    import ctypes

    kernel32 = ctypes.windll.kernel32
    process_query_limited_information = 0x1000
    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def process_command_line(pid: int) -> str | None:
    """Best-effort process command line. ``None`` means it could not be read."""

    if pid <= 0:
        return None
    if sys.platform.startswith("linux"):
        try:
            return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            return None
    if sys.platform == "darwin":
        import subprocess

        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        text = (result.stdout or "").strip()
        return text or None
    if sys.platform == "win32":
        return _windows_process_image(pid)
    return None


def _windows_process_image(pid: int) -> str | None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    process_query_limited_information = 0x1000
    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return None
    try:
        query = kernel32.QueryFullProcessImageNameW
        query.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        query.restype = wintypes.BOOL
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if query(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(handle)


def command_looks_like_ours(command: str | None) -> bool:
    if not command:
        return False
    low = command.lower().replace("\\", "/")
    return "apple_refurb_watch" in low or "apple-refurb-watch" in low


def pid_is_our_process(pid: int) -> bool:
    """True when ``pid`` looks like this project's live process."""

    if not pid_exists(pid):
        return False
    command = process_command_line(pid)
    if command:
        if command_looks_like_ours(command):
            return True
        basename = command.lower().replace("\\", "/").rsplit("/", 1)[-1]
        if basename.startswith("python"):
            return True
        return False
    return not sys.platform.startswith("linux")


def runtime_is_alive(runtime: dict | None) -> bool:
    """Return whether runtime metadata points at this project's live process."""

    pid = _runtime_pid(runtime)
    if pid is None:
        return False
    return pid_is_our_process(pid)
