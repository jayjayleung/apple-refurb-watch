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


def write_runtime(payload: dict) -> None:
    runtime_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_runtime() -> dict | None:
    path = runtime_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
