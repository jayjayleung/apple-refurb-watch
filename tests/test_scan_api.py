from __future__ import annotations

import time

from fastapi.testclient import TestClient

from apple_refurb_watch.api import create_app
from apple_refurb_watch.db import Database
from apple_refurb_watch.scanner import ScanService


class EmptySource:
    def fetch_listing(self, _listing: str):
        return []

    def fetch_detail(self, _url: str):
        return {}

    def close(self) -> None:
        return None


def test_scan_resource_can_be_submitted_and_polled(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    service = ScanService(db, source=EmptySource(), sleep_fn=lambda _seconds: None)
    app = create_app(db, with_scheduler=False, scan_service=service)
    with TestClient(app) as client:
        response = client.post("/api/scans")
        assert response.status_code == 202
        payload = response.json()
        run_id = payload["scan_run_id"]
        assert payload["accepted"] is True
        assert response.headers["location"] == f"/api/scans/{run_id}"
        assert client.get(f"/api/scans/{run_id}").status_code == 200
        deadline = time.time() + 3
        while time.time() < deadline:
            run = client.get(f"/api/scans/{run_id}").json()
            if run["status"] != "running":
                break
            time.sleep(0.01)
        assert run["status"] == "succeeded"
        listed = client.get("/api/scans").json()
        assert listed[0]["id"] == run_id
    service.close()
    db.close()


def test_legacy_scan_endpoint_falls_back_to_synchronous_service(tmp_path) -> None:
    db = Database(tmp_path / "app.db")

    class LegacyService:
        def run_once(self):
            return {"ok": True, "scan_run_id": 7, "scan_status": "succeeded"}

    app = create_app(db, with_scheduler=False, scan_service=LegacyService())
    with TestClient(app) as client:
        response = client.post("/api/scans")
        assert response.status_code == 200
        assert response.json()["scan_run_id"] == 7
        legacy = client.post("/api/scan")
        assert legacy.status_code == 200
        assert legacy.json()["ok"] is True
    db.close()


def test_settings_scan_queues_and_redirects_to_run_status(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    service = ScanService(db, source=EmptySource(), sleep_fn=lambda _seconds: None)
    app = create_app(db, with_scheduler=False, scan_service=service)
    with TestClient(app) as client:
        response = client.post("/settings/scan", follow_redirects=False)
        assert response.status_code == 303
        location = response.headers["location"]
        assert "flash=scan-queued" in location
        assert "scan_run_id=" in location
        page = client.get(location)
        assert page.status_code == 200
        assert "scan-run-status" in page.text
        run_id = int(location.split("scan_run_id=", 1)[1].split("&", 1)[0])
        deadline = time.time() + 3
        while time.time() < deadline:
            run = client.get(f"/api/scans/{run_id}").json()
            if run["status"] != "running":
                break
            time.sleep(0.01)
        assert run["status"] == "succeeded"
    service.close()
    db.close()
