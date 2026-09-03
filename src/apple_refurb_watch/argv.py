from __future__ import annotations

import os
import sys
from collections.abc import Sequence


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def ensure_stdio() -> None:
    """无控制台的安装包里 stdout/stderr 可能是 None，uvicorn 配日志会崩。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is not None and callable(getattr(stream, "isatty", None)):
            continue
        setattr(sys, name, open(os.devnull, "w", encoding="utf-8", errors="replace"))


def with_frozen_default_command(
    argv: Sequence[str],
    *,
    frozen: bool,
    platform: str,
) -> list[str]:
    """安装包双击（无参数）时打开桌面窗口；源码和 Linux 包仍走 CLI 帮助。"""
    args = list(argv)
    if len(args) != 1 or not frozen:
        return args
    if platform in {"win32", "darwin"}:
        return args + ["desktop"]
    return args


def desktop_hides_console(argv: Sequence[str]) -> bool:
    """Frozen GUI launches should not keep a console; probe/CLI still should."""

    args = list(argv[1:])
    if not args or args[0] != "desktop":
        return False
    return "--probe" not in args


def apply_windows_console(
    argv: Sequence[str],
    *,
    frozen: bool,
    platform: str,
) -> None:
    """GUI-subsystem EXEs: hide console for the window, attach for CLI/probe."""

    if platform != "win32" or not frozen:
        ensure_stdio()
        return
    try:
        import ctypes
        import io

        kernel32 = ctypes.windll.kernel32
        if desktop_hides_console(argv):
            kernel32.FreeConsole()
            return
        if kernel32.AttachConsole(-1):
            sys.stdout = io.TextIOWrapper(open("CONOUT$", "wb"), encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(open("CONOUT$", "wb"), encoding="utf-8", errors="replace")
    except Exception:
        pass
    finally:
        ensure_stdio()


def invoke_argv(
    *args: str,
    frozen: bool | None = None,
    executable: str | None = None,
) -> list[str]:
    """生成拉起本程序的命令。冻结后不能再用 python -m。"""
    frozen = is_frozen() if frozen is None else frozen
    executable = sys.executable if executable is None else executable
    if frozen:
        return [executable, *args]
    return [executable, "-m", "apple_refurb_watch", *args]
