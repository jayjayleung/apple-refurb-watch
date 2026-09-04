from __future__ import annotations

import re
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi.testclient import TestClient

from apple_refurb_watch.api import create_app
from apple_refurb_watch.db import Database
from apple_refurb_watch.paths import package_root
from apple_refurb_watch.scanner import ScanService


class EmptySource:
    def fetch_listing(self, _listing: str):
        return []

    def fetch_detail(self, _url: str):
        return {}

    def close(self) -> None:
        return None


class GateSource:
    def __init__(self, gate: threading.Event) -> None:
        self.gate = gate

    def fetch_listing(self, _listing: str):
        self.gate.wait(timeout=5)
        return []

    def fetch_detail(self, _url: str):
        return {}

    def close(self) -> None:
        return None


def _wait_run(client: TestClient, run_id: int, timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    run = {"status": "running"}
    while time.time() < deadline:
        run = client.get(f"/api/scans/{run_id}").json()
        if run["status"] != "running":
            break
        time.sleep(0.01)
    return run


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
        run = _wait_run(client, run_id)
        assert run["status"] == "succeeded"
        listed = client.get("/api/scans").json()
        assert listed[0]["id"] == run_id
        status = client.get("/api/status").json()
        assert status["scanning"] is False
        assert status["view"]["label"] != "正在扫描"
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
        run = _wait_run(client, run_id)
        assert run["status"] == "succeeded"
        idle = client.get("/events")
        assert "立即扫描" in idle.text
        assert 'aria-busy="true"' not in idle.text
        assert 'data-state="busy"' not in idle.text
    service.close()
    db.close()


def test_events_page_shows_scanning_while_run_is_active(tmp_path) -> None:
    gate = threading.Event()
    db = Database(tmp_path / "app.db")
    service = ScanService(db, source=GateSource(gate), sleep_fn=lambda _seconds: None)
    app = create_app(db, with_scheduler=False, scan_service=service)
    try:
        with TestClient(app) as client:
            response = client.post("/settings/scan", follow_redirects=False)
            assert response.status_code == 303
            location = response.headers["location"]
            page = client.get(location)
            assert "正在扫描" in page.text
            assert 'aria-busy="true"' in page.text
            assert 'data-state="busy"' in page.text
            status = client.get("/api/status").json()
            assert status["scanning"] is True
            assert status["view"]["label"] == "正在扫描"
            gate.set()
            run_id = int(location.split("scan_run_id=", 1)[1].split("&", 1)[0])
            run = _wait_run(client, run_id)
            assert run["status"] == "succeeded"
            idle_status = client.get("/api/status").json()
            assert idle_status["scanning"] is False
            assert idle_status["view"]["label"] != "正在扫描"
            idle = client.get("/events")
            assert "立即扫描" in idle.text
            assert 'data-state="busy"' not in idle.text
    finally:
        gate.set()
        service.close()
        db.close()


def test_events_scan_done_flash_includes_dismiss_hooks(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    app = create_app(db, with_scheduler=False)
    with TestClient(app) as client:
        page = client.get("/events?flash=scan-done")
        assert page.status_code == 200
        assert "扫描已完成" in page.text
        assert 'id="scan-run-status"' in page.text
        assert "__arwScheduleScanFlashDismiss" in page.text
        js = client.get("/static/app.js").text
        assert "SCAN_FLASH_DISMISS_MS = 4000" in js
        assert "__arwScheduleScanFlashDismiss" in js
        assert "__arwHideScanRunStatus" in js
        assert "__arwScanFlashIsDone" in js
    db.close()


def test_scan_complete_does_not_leave_scanning_chrome(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    service = ScanService(db, source=EmptySource(), sleep_fn=lambda _seconds: None)
    app = create_app(db, with_scheduler=False, scan_service=service)
    with TestClient(app) as client:
        response = client.post("/settings/scan", follow_redirects=False)
        location = response.headers["location"]
        run_id = int(location.split("scan_run_id=", 1)[1].split("&", 1)[0])
        run = _wait_run(client, run_id)
        assert run["status"] == "succeeded"
        status = client.get("/api/status").json()
        assert status["scanning"] is False
        assert status["view"]["scanning"] is False
        assert status["view"]["label"] != "正在扫描"
        assert status["view"]["label"] != "扫描完成"
        idle = client.get("/events")
        assert "立即扫描" in idle.text
        assert 'aria-busy="true"' not in idle.text
        assert 'data-state="busy"' not in idle.text
    service.close()
    db.close()


def test_scan_flash_dismiss_timer_hides_node_and_strips_query() -> None:
    src = (package_root() / "web" / "static" / "app.js").read_text(encoding="utf-8")
    start = src.find("/* scan-flash-dismiss */")
    end = src.find("/* /scan-flash-dismiss */")
    assert start >= 0 and end > start
    block = src[start : end + len("/* /scan-flash-dismiss */")]
    ms_match = re.search(r"SCAN_FLASH_DISMISS_MS = (\d+)", block)
    done_match = re.search(r"/([^/]+)/\.test\(String\(text", block)
    assert ms_match is not None
    assert int(ms_match.group(1)) == 4000
    assert done_match is not None
    done_re = re.compile(done_match.group(1))
    assert done_re.search("扫描完成。")
    assert done_re.search("扫描已完成。")
    assert done_re.search("扫描已提交，正在运行…") is None
    assert done_re.search("正在扫描") is None

    class StatusNode:
        def __init__(self) -> None:
            self.hidden = False
            self.textContent = "扫描已完成。"
            self.attrs: dict[str, str] = {}

        def getAttribute(self, key: str) -> str | None:
            return self.attrs.get(key)

        def setAttribute(self, key: str, value: str) -> None:
            self.attrs[key] = str(value)

    node = StatusNode()
    timeouts: list[tuple[object, int]] = []
    href = "http://127.0.0.1:9/events?flash=scan-done&page=2"

    def strip_scan_flash_query() -> None:
        nonlocal href
        parts = urlsplit(href)
        params = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)]
        flash = next((value for key, value in params if key == "flash"), "")
        if flash not in {"scan-done", "scan-queued"}:
            return
        query = urlencode([(key, value) for key, value in params if key != "flash"])
        href = "http://127.0.0.1:9" + parts.path + (("?" + query) if query else "")

    def hide_scan_run_status() -> None:
        node.hidden = True
        node.textContent = ""
        node.setAttribute("aria-hidden", "true")
        strip_scan_flash_query()

    def schedule(delay_ms: int | None = None) -> int:
        if node.getAttribute("data-dismiss-scheduled") == "1":
            return 0
        node.setAttribute("data-dismiss-scheduled", "1")
        ms = 4000 if delay_ms is None else delay_ms
        strip_scan_flash_query()
        timeouts.append((hide_scan_run_status, ms))
        return len(timeouts)

    timer = schedule()
    assert timer == 1
    assert timeouts == [(hide_scan_run_status, 4000)]
    assert node.hidden is False
    assert node.textContent == "扫描已完成。"
    assert "flash=scan-done" not in href
    assert schedule() == 0
    assert len(timeouts) == 1
    hide_fn, ms = timeouts[0]
    assert ms == 4000
    hide_fn()
    assert node.hidden is True
    assert node.textContent == ""
    assert "flash=" not in href


def test_scanning_flag_clears_before_next_submit(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    service = ScanService(db, source=EmptySource(), sleep_fn=lambda _seconds: None)
    app = create_app(db, with_scheduler=False, scan_service=service)
    try:
        with TestClient(app) as client:
            response = client.post("/api/scans")
            run_id = response.json()["scan_run_id"]
            run = _wait_run(client, run_id)
            assert run["status"] == "succeeded"
            status = client.get("/api/status").json()
            assert status["scanning"] is False
            assert status["view"]["label"] != "正在扫描"
            second = client.post("/api/scans")
            assert second.status_code == 202
            assert second.json()["accepted"] is True
    finally:
        service.close()
        db.close()
