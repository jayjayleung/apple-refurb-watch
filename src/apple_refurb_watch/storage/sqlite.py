from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from apple_refurb_watch.paths import db_path
from apple_refurb_watch.storage.schema import DEFAULT_SETTINGS, SCHEMA, SCHEMA_VERSION, utcnow

log = logging.getLogger(__name__)


class SQLiteStore:
    """Own the SQLite connection, locking and schema lifecycle."""

    def __init__(self, path: Path | None = None, *, auto_migrate: bool = True) -> None:
        self.path = Path(path) if path else db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._transaction_depth = 0
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        if auto_migrate:
            try:
                self.migrate()
            except Exception:
                try:
                    self.conn.close()
                except Exception:  # noqa: BLE001
                    log.debug("关闭失败升级的数据库连接时出错", exc_info=True)
                raise

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        """Run a unit of work with nesting-safe commit/rollback semantics.

        Repository methods intentionally keep their small transaction wrappers,
        while application services can wrap a whole use case in one outer
        transaction. Only the outermost context starts/commits the SQLite
        transaction, so a scan cannot leave half of its state persisted.
        """

        with self.lock:
            outer = self._transaction_depth == 0
            if outer:
                self.conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            self._transaction_depth += 1
            try:
                yield self.conn
            except BaseException:
                if outer:
                    self._transaction_depth = 0
                    self.conn.rollback()
                else:
                    self._transaction_depth -= 1
                raise
            else:
                self._transaction_depth -= 1
                if outer:
                    self.conn.commit()

    @property
    def in_transaction(self) -> bool:
        return self._transaction_depth > 0

    def migrate(self, *, apply_schema: Callable[[], None] | None = None) -> None:
        with self.lock:
            current = self._schema_version()
            backup_path: Path | None = None
            if 0 < current < SCHEMA_VERSION:
                backup_path = self._backup_db(current)
            try:
                (apply_schema or self._apply_schema)()
            except Exception as exc:
                restored = False
                restore_err: BaseException | None = None
                if backup_path is not None:
                    try:
                        self._restore_db(backup_path)
                        restored = True
                    except Exception as rex:  # noqa: BLE001
                        restore_err = rex
                if restored:
                    raise RuntimeError(
                        f"数据库升级失败，已从备份还原。备份仍在 {backup_path}；"
                        f"若仍异常可将该文件复制回 {self.path} 后重试。"
                    ) from exc
                extra = f" 还原也失败（{restore_err}）。" if restore_err else ""
                hint = f" 备份：{backup_path}，可复制回 {self.path}。" if backup_path else ""
                raise RuntimeError(f"数据库升级失败。{extra}{hint}".strip()) from exc

    def _apply_schema(self) -> None:
        self.conn.executescript(SCHEMA)
        cols = [row[1] for row in self.conn.execute("PRAGMA table_info(watches)").fetchall()]
        if "dim_filters" not in cols:
            self.conn.execute("ALTER TABLE watches ADD COLUMN dim_filters TEXT NOT NULL DEFAULT '{}'")
        self._ensure_column("events", "fingerprint", "TEXT")
        for name, definition in (
            ("lease_token", "TEXT"),
            ("leased_until", "TEXT"),
            ("last_attempt_at", "TEXT"),
            ("sent_at", "TEXT"),
            ("created_at", "TEXT"),
        ):
            self._ensure_column("notification_deliveries", name, definition)
        self.conn.commit()
        # Keep the new outbox table populated for databases upgraded from the
        # legacy notification_deliveries table. Hot-path writes no longer touch
        # that table; this copy runs once during schema apply.
        self.conn.execute(
            """
            INSERT OR IGNORE INTO notification_outbox(
                event_id, channel, status, attempts, next_retry_at, last_error,
                lease_token, leased_until, last_attempt_at, sent_at, created_at
            )
            SELECT event_id, channel,
                   CASE WHEN status='ok' THEN 'sent' ELSE status END,
                   attempts, next_retry_at, last_error,
                   lease_token, leased_until, last_attempt_at, sent_at,
                   COALESCE(created_at, ?)
            FROM notification_deliveries
            """,
            (utcnow(),),
        )
        # A partially upgraded database may already contain rows copied before
        # the status translation above.  Normalize those rows in place.
        self.conn.execute(
            "UPDATE notification_outbox SET status='sent' WHERE status='ok'"
        )
        # Existing installations may contain duplicate fingerprints from an
        # interrupted migration. Preserve the earliest event and make later
        # rows non-fingerprinted before creating the uniqueness constraint.
        self.conn.execute(
            """
            UPDATE events
            SET fingerprint = NULL
            WHERE fingerprint IS NOT NULL
              AND id NOT IN (
                  SELECT MIN(id) FROM events
                  WHERE fingerprint IS NOT NULL GROUP BY fingerprint
              )
            """
        )
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_fingerprint "
            "ON events(fingerprint) WHERE fingerprint IS NOT NULL"
        )
        for key, value in DEFAULT_SETTINGS.items():
            existing = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if existing is None:
                self.conn.execute(
                    "INSERT INTO meta(key, value) VALUES(?, ?)",
                    (key, json.dumps(value, ensure_ascii=False)),
                )
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("schema_version", json.dumps(SCHEMA_VERSION)),
        )
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _schema_version(self) -> int:
        try:
            row = self.conn.execute("SELECT value FROM meta WHERE key=?", ("schema_version",)).fetchone()
        except sqlite3.OperationalError:
            return 0
        if row is not None:
            raw = row["value"]
            try:
                return int(json.loads(raw))
            except (TypeError, ValueError, json.JSONDecodeError):
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return 1
        try:
            has_meta = self.conn.execute("SELECT 1 FROM meta LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            return 0
        return 1 if has_meta else 0

    def _backup_db(self, from_version: int) -> Path:
        dest = self.path.with_name(f"{self.path.name}.bak-v{from_version}")
        try:
            dest.unlink(missing_ok=True)
        except TypeError:
            if dest.exists():
                dest.unlink()
        backup = sqlite3.connect(str(dest))
        try:
            self.conn.backup(backup)
            backup.commit()
        finally:
            backup.close()
        return dest

    def _restore_db(self, backup_path: Path) -> None:
        src = sqlite3.connect(str(backup_path))
        try:
            src.backup(self.conn)
            self.conn.commit()
        finally:
            src.close()

    def close(self) -> None:
        with self.lock:
            if self._transaction_depth:
                self.conn.rollback()
                self._transaction_depth = 0
            self.conn.close()
