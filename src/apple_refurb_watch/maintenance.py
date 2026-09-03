"""Operational safeguards for the single-authority SQLite service."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from apple_refurb_watch.db import Database
from apple_refurb_watch.paths import runtime_is_alive
from apple_refurb_watch.settings import (
    NOTIFY_CHANNEL_UI,
    listener_requires_auth,
    normalize_settings_patch,
)
from apple_refurb_watch.storage.schema import SCHEMA_VERSION, utcnow


EXPORT_VERSION = 1
_SECRET_KEYS = {"password", "bot_token", "sendkey", "token", "secret", "webhook", "url", "access_token"}
_CONFIG_SETTING_KEYS = {
    "interval_seconds",
    "bind_host",
    "bind_port",
    "lan_enabled",
    "access_token",
    "listings",
    "detail_delay_seconds",
    "notify",
    "close_window_keeps_daemon",
    "listen_enabled",
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def integrity_check(path: Path) -> dict[str, Any]:
    """Run SQLite integrity and schema checks without mutating the database."""

    target = Path(path)
    if not target.exists():
        return {"ok": False, "path": str(target), "error": "数据库不存在"}
    try:
        conn = sqlite3.connect(str(target), timeout=30)
        try:
            result = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            version = None
            if row:
                try:
                    version = int(json.loads(row[0]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    version = str(row[0])
        finally:
            conn.close()
        return {"ok": result == "ok", "path": str(target), "integrity": result, "schema_version": version}
    except (OSError, sqlite3.DatabaseError) as exc:
        return {"ok": False, "path": str(target), "error": str(exc)}


def backup_database(
    source: Path | None = None,
    destination: Path | None = None,
    *,
    keep: int | None = 8,
) -> dict[str, Any]:
    """Create a consistent online SQLite backup and verify the snapshot."""

    source_path = Path(source) if source is not None else _default_db_path()
    source_path = source_path.resolve()
    before = integrity_check(source_path)
    if not before.get("ok"):
        raise RuntimeError(f"源数据库完整性检查失败: {before.get('error') or before.get('integrity')}")
    if destination is None:
        destination_dir = source_path.parent / "backups" / _timestamp()
        destination_path = destination_dir / "app.db"
    else:
        destination_path = Path(destination)
        if destination_path.suffix != ".db":
            destination_path = destination_path / "app.db"
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        raise FileExistsError(f"备份目标已存在: {destination_path}")

    # Write through a temporary file, then atomically publish only after the
    # online backup and integrity check have completed.
    fd, temp_name = tempfile.mkstemp(prefix=".app.db.", suffix=".tmp", dir=str(destination_path.parent))
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        src = sqlite3.connect(str(source_path), timeout=30)
        try:
            dst = sqlite3.connect(str(temp_path), timeout=30)
            try:
                src.backup(dst, pages=256, sleep=0.05)
                dst.commit()
            finally:
                dst.close()
        finally:
            src.close()
        checked = integrity_check(temp_path)
        if not checked.get("ok"):
            raise RuntimeError(f"备份完整性检查失败: {checked.get('error') or checked.get('integrity')}")
        os.replace(temp_path, destination_path)
    finally:
        temp_path.unlink(missing_ok=True)

    # Keep a small amount of operational context next to the snapshot. Secrets
    # remain in the database backup itself and are never printed by the CLI.
    config_source = source_path.parent / "daemon.json"
    config_destination = destination_path.parent / "daemon.json"
    if config_source.exists() and config_source.resolve() != config_destination.resolve():
        shutil.copy2(config_source, config_destination)
    if keep is not None:
        _rotate_backup_dirs(source_path.parent / "backups", keep=max(1, int(keep)))
    # ``integrity_check`` ran against the temporary path; expose the published
    # path to callers so a JSON result is directly usable for restore.
    checked["path"] = str(destination_path)
    checked["backup"] = str(destination_path)
    checked["source"] = str(source_path)
    return checked


def restore_database(backup: Path, target: Path | None = None) -> dict[str, Any]:
    """Restore a verified backup via a temporary file and atomic replace."""

    backup_path = Path(backup).resolve()
    target_path = Path(target) if target is not None else _default_db_path()
    target_path = target_path.resolve()
    checked = integrity_check(backup_path)
    if not checked.get("ok"):
        raise RuntimeError(f"备份完整性检查失败: {checked.get('error') or checked.get('integrity')}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    prior: dict[str, Any] | None = None
    if target_path.exists():
        prior = backup_database(target_path, destination=target_path.parent / f"{target_path.name}.pre-restore-{_timestamp()}.db", keep=None)

    fd, temp_name = tempfile.mkstemp(prefix=f".{target_path.name}.", suffix=".restore", dir=str(target_path.parent))
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        src = sqlite3.connect(str(backup_path), timeout=30)
        try:
            dst = sqlite3.connect(str(temp_path), timeout=30)
            try:
                src.backup(dst, pages=256, sleep=0.05)
                dst.commit()
            finally:
                dst.close()
        finally:
            src.close()
        restored = integrity_check(temp_path)
        if not restored.get("ok"):
            raise RuntimeError("恢复临时库完整性检查失败")
        os.replace(temp_path, target_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return {"ok": True, "restored": str(target_path), "backup": str(backup_path), "prior": prior}


def compact_database(source: Path | None = None) -> dict[str, Any]:
    """Backup, VACUUM and verify the local SQLite file to reclaim space."""

    source_path = Path(source) if source is not None else _default_db_path()
    source_path = source_path.resolve()
    try:
        size_before = int(source_path.stat().st_size)
    except OSError:
        size_before = 0
    backup = backup_database(source_path)
    conn = sqlite3.connect(str(source_path), timeout=30)
    try:
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()
    checked = integrity_check(source_path)
    if not checked.get("ok"):
        raise RuntimeError(f"压缩后完整性检查失败: {checked.get('error') or checked.get('integrity')}")
    try:
        size_after = int(source_path.stat().st_size)
    except OSError:
        size_after = 0
    return {
        "ok": True,
        "path": str(source_path),
        "backup": backup.get("backup"),
        "integrity": checked.get("integrity"),
        "bytes_before": size_before,
        "bytes_after": size_after,
    }


def export_config(
    path: Path | None = None,
    *,
    db: Database | None = None,
    include_secrets: bool = False,
) -> dict[str, Any]:
    """Export rules and settings; secrets are omitted unless explicitly asked."""

    owns_db = db is None
    database = db or Database()
    try:
        settings = {
            key: value
            for key, value in database.settings().items()
            if key in _CONFIG_SETTING_KEYS
        }
        for key in ("scanning", "last_scan_at", "last_success_at", "last_error", "last_product_count", "baseline_done"):
            settings.pop(key, None)
        if not include_secrets:
            settings["access_token"] = ""
            notify = {}
            for name, conf in (settings.get("notify") or {}).items():
                safe = dict(conf or {})
                for key in _SECRET_KEYS:
                    if key != "access_token":
                        safe.pop(key, None)
                notify[name] = safe
            settings["notify"] = notify
        payload = {
            "format": "apple-refurb-watch.config",
            "version": EXPORT_VERSION,
            "exported_at": utcnow(),
            "includes_secrets": bool(include_secrets),
            "settings": settings,
            "watches": database.list_watches(),
        }
        if path is not None:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            # Configuration exports can contain credentials when explicitly
            # requested; keep them private on POSIX systems.
            if include_secrets and os.name != "nt":
                try:
                    target.chmod(0o600)
                except OSError:
                    pass
        return payload
    finally:
        if owns_db:
            database.close()


def import_config(
    path: Path,
    *,
    db: Database | None = None,
    include_secrets: bool = False,
    replace_watches: bool = False,
) -> dict[str, Any]:
    """Validate and merge an exported configuration into the local database."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取配置文件: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("format") != "apple-refurb-watch.config":
        raise ValueError("不是 apple-refurb-watch 配置文件")
    if int(payload.get("version") or 0) != EXPORT_VERSION:
        raise ValueError(f"不支持的配置版本: {payload.get('version')}")
    settings = payload.get("settings")
    watches = payload.get("watches")
    if not isinstance(settings, dict) or not isinstance(watches, list):
        raise ValueError("配置文件缺少 settings 或 watches")

    if not isinstance(settings, dict):
        raise ValueError("配置文件中的 settings 必须是对象")
    if not isinstance(watches, list):
        raise ValueError("配置文件中的 watches 必须是数组")

    # Ignore unknown settings from a newer exporter.  This keeps an import
    # from writing arbitrary meta keys while allowing older clients to import
    # a forward-compatible subset.
    settings = {key: value for key, value in settings.items() if key in _CONFIG_SETTING_KEYS}

    owns_db = db is None
    database = db or Database()
    try:
        current = database.settings()
        patch = dict(settings)
        if not include_secrets:
            # Empty/omitted secret fields mean "leave the local secret as-is";
            # only an explicit --include-secrets import may replace them.
            patch.pop("access_token", None)
            if "notify" in patch:
                safe_notify = {}
                for name, conf in (patch.get("notify") or {}).items():
                    if not isinstance(conf, dict):
                        continue
                    safe = dict(conf)
                    for key in _SECRET_KEYS:
                        safe.pop(key, None)
                        safe.pop(f"{key}_set", None)
                    safe_notify[name] = safe
                patch["notify"] = safe_notify
        normalized = normalize_settings_patch(patch, current)

        # Keep the complete migration in one transaction.  A malformed watch
        # or a failed settings write must not leave a half-imported database.
        with database.transaction(immediate=True):
            updated = database.update_settings(normalized)
            if replace_watches:
                for item in database.list_watches():
                    database.delete_watch(int(item["id"]))
            imported = 0
            existing_names = {
                str(item.get("name") or ""): item for item in database.list_watches()
            }
            for raw in watches:
                if not isinstance(raw, dict):
                    raise ValueError("配置文件中的规则必须是对象")
                data = {
                    key: value
                    for key, value in raw.items()
                    if key not in {"id", "created_at", "updated_at", "query"}
                }
                name = str(data.get("name") or "未命名规则")
                if not replace_watches and name in existing_names:
                    imported_watch = database.update_watch(int(existing_names[name]["id"]), data)
                    if imported_watch is None:
                        raise ValueError(f"规则不存在: {name}")
                else:
                    imported_watch = database.create_watch(data)
                    existing_names[name] = imported_watch
                imported += 1
        return {
            "ok": True,
            "settings": updated,
            "watches_imported": imported,
            "replaced_watches": bool(replace_watches),
        }
    finally:
        if owns_db:
            database.close()


def doctor(*, db: Database | None = None, stale_after_minutes: int = 120) -> dict[str, Any]:
    """Report local health and repair only abandoned in-flight records."""

    owns_db = db is None
    database = db or Database()
    try:
        settings = database.settings()
        check = integrity_check(database.path)
        runtime = _read_runtime(database.path.parent / "daemon.json")
        runtime_pid = runtime.get("pid") if runtime else None
        runtime_alive = _pid_alive(runtime_pid)
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max(1, stale_after_minutes))).isoformat()
        # A live daemon may legitimately have a long-running scan (slow source,
        # many detail pages).  Only recover stale ``running`` rows when the
        # recorded daemon is absent/dead; otherwise report them for inspection.
        abandoned = 0
        if not runtime_alive:
            abandoned = database.mark_abandoned_scan_runs(older_than=cutoff)
        scanning_repaired = False
        if bool(settings.get("scanning")) and not runtime_alive:
            database.set_setting("scanning", False)
            scanning_repaired = True
        runs = database.list_scan_runs(limit=20)
        stale_running = [
            run
            for run in runs
            if run.get("status") == "running" and str(run.get("started_at") or "") < cutoff
        ]
        pending = database.list_pending_deliveries()
        listener_ok = not listener_requires_auth(settings) or bool(str(settings.get("access_token") or "").strip())
        schema_ok = check.get("schema_version") == SCHEMA_VERSION
        try:
            database_bytes = int(database.path.stat().st_size)
        except OSError:
            database_bytes = 0
        result = {
            "ok": bool(check.get("ok")) and schema_ok and listener_ok,
            "database": check,
            "schema_version": check.get("schema_version"),
            "expected_schema_version": SCHEMA_VERSION,
            "database_bytes": database_bytes,
            "observations": database.count_observations(),
            "scan_runs": database.count_scan_runs(),
            "listener": {
                "bind_host": settings.get("bind_host"),
                "bind_port": settings.get("bind_port"),
                "requires_auth": listener_requires_auth(settings),
                "token_configured": bool(str(settings.get("access_token") or "").strip()),
            },
            "runtime": {"pid": runtime_pid, "alive": runtime_alive},
            "pending_deliveries": len(pending),
            "recent_scan_runs": runs,
            "stale_running_runs": stale_running,
            "abandoned_runs_recovered": abandoned,
            "scanning_flag_repaired": scanning_repaired,
        }
        return result
    finally:
        if owns_db:
            database.close()


def _default_db_path() -> Path:
    from apple_refurb_watch.paths import db_path

    return db_path()


def _read_runtime(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _pid_alive(value: Any) -> bool:
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    return runtime_is_alive({"pid": pid})


def _rotate_backup_dirs(root: Path, *, keep: int) -> None:
    if not root.exists():
        return
    dirs = sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name, reverse=True)
    for old in dirs[keep:]:
        shutil.rmtree(old, ignore_errors=False)


__all__ = [
    "EXPORT_VERSION",
    "backup_database",
    "compact_database",
    "doctor",
    "export_config",
    "import_config",
    "integrity_check",
    "restore_database",
]
