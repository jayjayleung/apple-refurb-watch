from __future__ import annotations

import json
from pathlib import Path

import pytest

from apple_refurb_watch.db import Database
from apple_refurb_watch.maintenance import (
    backup_database,
    doctor,
    export_config,
    import_config,
    restore_database,
)


def test_backup_and_restore_are_verified_and_keep_prior_copy(tmp_path: Path) -> None:
    source = tmp_path / "app.db"
    db = Database(source)
    db.set_setting("interval_seconds", 123)
    db.close()
    # A runtime file is common beside the live database.  Backing up to the
    # same directory must not attempt to copy this file onto itself.
    (tmp_path / "daemon.json").write_text(json.dumps({"pid": 1}), encoding="utf-8")

    backup = backup_database(source, destination=tmp_path / "snapshot", keep=None)
    snapshot = Path(backup["backup"])
    assert snapshot.exists()
    assert backup["ok"] is True

    target = tmp_path / "restored.db"
    old = Database(target)
    old.set_setting("interval_seconds", 999)
    old.close()
    restored = restore_database(snapshot, target)
    assert restored["ok"] is True
    assert restored["prior"] is not None
    check = Database(target)
    assert check.get_setting("interval_seconds") == 123
    check.close()


def test_config_export_redacts_secrets_and_import_preserves_local_secrets(tmp_path: Path) -> None:
    source = Database(tmp_path / "source.db")
    source.update_settings(
        {
            "interval_seconds": 180,
            "access_token": "source-token",
            "notify": {"bark": {"enabled": True, "url": "https://api.day.app/source"}},
        }
    )
    source.create_watch({"name": "Mac", "listing_key": "mac"})
    config_path = tmp_path / "config.json"
    payload = export_config(config_path, db=source)
    assert payload["includes_secrets"] is False
    encoded = config_path.read_text(encoding="utf-8")
    assert "source-token" not in encoded
    assert "api.day.app/source" not in encoded

    target = Database(tmp_path / "target.db")
    target.update_settings(
        {
            "access_token": "local-token",
            "notify": {"bark": {"url": "https://api.day.app/local"}},
        }
    )
    imported = import_config(config_path, db=target)
    assert imported["watches_imported"] == 1
    assert target.get_setting("interval_seconds") == 180
    assert target.get_setting("access_token") == "local-token"
    assert target.settings()["notify"]["bark"]["url"] == "https://api.day.app/local"
    source.close()
    target.close()


def test_config_import_rolls_back_settings_and_watches_on_bad_rule(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("interval_seconds", 300)
    db.create_watch({"name": "existing", "listing_key": "mac"})
    payload = {
        "format": "apple-refurb-watch.config",
        "version": 1,
        "settings": {"interval_seconds": 60},
        "watches": [
            {"name": "new", "listing_key": "mac"},
            {"name": "bad", "min_ram_gb": "not-a-number"},
        ],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        import_config(path, db=db, replace_watches=True)
    assert db.get_setting("interval_seconds") == 300
    assert [item["name"] for item in db.list_watches()] == ["existing"]
    db.close()


def test_doctor_does_not_recover_stale_run_while_daemon_is_alive(tmp_path: Path, monkeypatch) -> None:
    db = Database(tmp_path / "app.db")
    run_id = db.start_scan_run(["mac"])
    db.conn.execute(
        "UPDATE scan_runs SET started_at=? WHERE id=?",
        ("2000-01-01T00:00:00+00:00", run_id),
    )
    db.conn.commit()
    (tmp_path / "daemon.json").write_text(json.dumps({"pid": 4242}), encoding="utf-8")
    monkeypatch.setattr("apple_refurb_watch.maintenance._pid_alive", lambda _pid: True)
    live = doctor(db=db, stale_after_minutes=1)
    assert live["abandoned_runs_recovered"] == 0
    assert live["stale_running_runs"]
    assert db.get_scan_run(run_id)["status"] == "running"

    monkeypatch.setattr("apple_refurb_watch.maintenance._pid_alive", lambda _pid: False)
    dead = doctor(db=db, stale_after_minutes=1)
    assert dead["abandoned_runs_recovered"] == 1
    assert db.get_scan_run(run_id)["status"] == "failed"
    db.close()
