from __future__ import annotations

import sys
from collections.abc import Sequence


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


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
