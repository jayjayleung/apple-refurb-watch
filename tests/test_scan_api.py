from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time

import pytest
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
    if not shutil.which("node"):
        pytest.skip("需要 node 来执行扫描完成提示的定时器")
    app_js = package_root() / "web" / "static" / "app.js"
    harness = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
const start = src.indexOf("/* scan-flash-dismiss */");
const end = src.indexOf("/* /scan-flash-dismiss */");
if (start < 0 || end < 0) {
  console.error("missing scan-flash-dismiss markers");
  process.exit(2);
}
const block = src.slice(start, end + "/* /scan-flash-dismiss */".length);
const timeouts = [];
const node = {
  hidden: false,
  textContent: "扫描已完成。",
  attrs: {},
  getAttribute(key) { return this.attrs[key] || null; },
  setAttribute(key, value) { this.attrs[key] = String(value); },
};
let href = "http://127.0.0.1:9/events?flash=scan-done&page=2";
const win = {
  setTimeout(fn, ms) { timeouts.push({fn, ms}); return timeouts.length; },
  history: { replaceState(_state, _title, url) { href = "http://127.0.0.1:9" + url; } },
  location: { get href() { return href; } },
  document: { getElementById(id) { return id === "scan-run-status" ? node : null; } },
};
global.window = win;
eval(block);
if (win.__arwScanFlashDismissMs !== 4000) {
  console.error("dismiss ms", win.__arwScanFlashDismissMs);
  process.exit(1);
}
if (!win.__arwScanFlashIsDone("扫描完成。") || !win.__arwScanFlashIsDone("扫描已完成。")) {
  console.error("done matcher missed");
  process.exit(1);
}
if (win.__arwScanFlashIsDone("扫描已提交，正在运行…") || win.__arwScanFlashIsDone("正在扫描")) {
  console.error("done matcher too broad");
  process.exit(1);
}
const timer = win.__arwScheduleScanFlashDismiss(node, undefined, win);
if (!timer || timeouts.length !== 1 || timeouts[0].ms !== 4000) {
  console.error("timer", JSON.stringify({timer, timeouts: timeouts.map((t) => t.ms)}));
  process.exit(1);
}
if (node.hidden || node.textContent !== "扫描已完成。") {
  console.error("hidden before timeout");
  process.exit(1);
}
if (href.includes("flash=scan-done")) {
  console.error("flash query not stripped", href);
  process.exit(1);
}
if (win.__arwScheduleScanFlashDismiss(node, undefined, win) !== 0 || timeouts.length !== 1) {
  console.error("double schedule");
  process.exit(1);
}
timeouts[0].fn();
if (!node.hidden || node.textContent !== "") {
  console.error("still visible", node.hidden, node.textContent);
  process.exit(1);
}
console.log(JSON.stringify({ok: true, href: href, ms: timeouts[0].ms}));
"""
    result = subprocess.run(
        ["node", "-e", harness, str(app_js)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        pytest.fail(result.stderr or result.stdout or f"node exit {result.returncode}")
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["ms"] == 4000
    assert "flash=" not in payload["href"]


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
