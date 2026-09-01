from pathlib import Path

import pytest

from apple_refurb_watch.db import Database
from apple_refurb_watch.scanner import run_scan


def _scan(db, html, notifier=None, fetch_listing=None):
    notes: list[str] = []

    def notify(settings, title, body, url):
        notes.append(title)
        return []

    result = run_scan(
        db,
        fetch_listing=fetch_listing or (lambda url: html),
        fetch_detail=lambda url: "",
        notifier=notifier or notify,
        sleep_fn=lambda _s: None,
    )
    return result, notes


def test_baseline_then_notify(tmp_path: Path, listing_html: str) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["mac"])
    db.create_watch(
        {
            "name": "14 MBP",
            "mode": "condition",
            "all_of": ["MacBook Pro", "M5 Pro"],
            "min_ram_gb": 24,
        }
    )
    notes: list[str] = []

    def notify(settings, title, body, url):
        notes.append(title)
        return []

    gone = listing_html.replace("FGDN4CH/A", "ZZZZ4CH/A").replace("MacBook Pro Apple M5 Pro", "Mac mini Apple M4")

    first = run_scan(
        db,
        fetch_listing=lambda url: listing_html,
        fetch_detail=lambda url: "",
        notifier=notify,
        sleep_fn=lambda _s: None,
    )
    assert first["ok"]
    assert first["notified"] == 0
    assert notes == []
    assert db.get_setting("baseline_done") is True

    run_scan(
        db,
        fetch_listing=lambda url: gone,
        fetch_detail=lambda url: "",
        notifier=notify,
        sleep_fn=lambda _s: None,
    )

    second = run_scan(
        db,
        fetch_listing=lambda url: listing_html,
        fetch_detail=lambda url: "",
        notifier=notify,
        sleep_fn=lambda _s: None,
    )
    assert second["notified"] == 1
    assert notes
    appeared = [item for item in db.list_events() if item.get("type") == "appeared"]
    assert appeared
    assert "命中：" in (appeared[0].get("message") or "")

    third = run_scan(
        db,
        fetch_listing=lambda url: listing_html,
        fetch_detail=lambda url: "",
        notifier=notify,
        sleep_fn=lambda _s: None,
    )
    assert third["notified"] == 0
    db.close()


def test_staying_in_stock_after_baseline_does_not_notify(tmp_path: Path, listing_html: str) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["mac"])
    db.create_watch({"name": "14 MBP", "all_of": ["MacBook Pro", "M5 Pro"], "min_ram_gb": 24})
    first, notes = _scan(db, listing_html)
    assert first["notified"] == 0
    assert notes == []
    second, notes = _scan(db, listing_html)
    assert second["ok"]
    assert second["notified"] == 0
    assert notes == []
    db.close()


def test_new_watch_does_not_notify_existing_stock(tmp_path: Path, listing_html: str) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["mac"])
    first, _ = _scan(db, listing_html)
    assert first["ok"]
    assert db.get_setting("baseline_done") is True

    db.create_watch(
        {
            "name": "14 MBP",
            "mode": "condition",
            "all_of": ["MacBook Pro", "M5 Pro"],
            "min_ram_gb": 24,
        }
    )
    seeded, notes = _scan(db, listing_html)
    assert seeded["notified"] == 0
    assert notes == []

    gone = listing_html.replace("FGDN4CH/A", "ZZZZ4CH/A").replace("MacBook Pro Apple M5 Pro", "Mac mini Apple M4")
    _scan(db, gone)
    back, notes = _scan(db, listing_html)
    assert back["notified"] == 1
    assert notes
    db.close()


def test_failed_listing_does_not_clear_stock(tmp_path: Path, listing_html: str) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["mac"])
    first, _ = _scan(db, listing_html)
    assert first["ok"]
    assert any(p["sku"] == "FGDN4CH/A" for p in db.list_products(in_stock=True))

    def boom(url: str) -> str:
        raise RuntimeError("mac down")

    failed, _ = _scan(db, listing_html, fetch_listing=boom)
    assert failed["ok"] is False
    stock = db.list_products(in_stock=True)
    assert any(p["sku"] == "FGDN4CH/A" for p in stock)
    db.close()


def test_partial_scan_preserves_watch_state_and_success_timestamp(tmp_path: Path, listing_html: str) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["mac", "ipad"])
    watch = db.create_watch({"name": "14 MBP", "all_of": ["MacBook Pro"]})

    def initial(url: str) -> str:
        return listing_html

    first = run_scan(
        db,
        fetch_listing=initial,
        fetch_detail=lambda _url: "",
        notifier=lambda *args: [],
        sleep_fn=lambda _seconds: None,
    )
    assert first["ok"]
    db.set_watch_sku(watch["id"], "FGDN4CH/A", in_stock=True, notified=True)
    previous_success = db.get_setting("last_success_at")
    assert previous_success

    def partial(url: str) -> str:
        if "/ipad" in url:
            raise RuntimeError("ipad temporarily unavailable")
        return "<html><body>empty but valid response</body></html>"

    result = run_scan(
        db,
        fetch_listing=partial,
        fetch_detail=lambda _url: "",
        notifier=lambda *args: [],
        sleep_fn=lambda _seconds: None,
    )
    assert result["ok"] is True
    assert result["partial"] is True
    state = db.watch_sku_state(watch["id"], "FGDN4CH/A")
    assert state and state["in_stock"] == 1
    assert db.get_setting("last_success_at") == previous_success
    assert db.get_setting("last_error")
    db.close()


def test_scan_run_and_observations_are_persisted_together(tmp_path: Path, listing_html: str) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["mac"])
    result = run_scan(
        db,
        fetch_listing=lambda _url: listing_html,
        fetch_detail=lambda _url: "",
        notifier=lambda *args: [],
        sleep_fn=lambda _seconds: None,
    )
    run = db.get_scan_run(result["scan_run_id"])
    assert run
    assert run["status"] == "succeeded"
    assert run["requested_listings"] == ["mac"]
    assert run["successful_listings"] == ["mac"]
    observations = db.list_observations(result["scan_run_id"])
    assert observations
    assert all(item["scan_run_id"] == result["scan_run_id"] for item in observations)
    assert run["product_count"] == len(observations)
    db.close()


def test_scan_persistence_failure_rolls_back_inventory_and_events(tmp_path: Path, listing_html: str, monkeypatch) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["mac"])
    original = db.add_event

    def fail_scan_event(**kwargs):
        if kwargs.get("type") == "scan_ok":
            raise RuntimeError("simulated commit failure")
        return original(**kwargs)

    monkeypatch.setattr(db, "add_event", fail_scan_event)
    with pytest.raises(RuntimeError, match="simulated commit failure"):
        run_scan(
            db,
            fetch_listing=lambda _url: listing_html,
            fetch_detail=lambda _url: "",
            notifier=lambda *args: [],
            sleep_fn=lambda _seconds: None,
        )
    assert db.list_products(in_stock=None) == []
    assert db.list_events() == []
    runs = db.list_scan_runs()
    assert runs and runs[0]["status"] == "failed"
    assert db.list_observations(runs[0]["id"]) == []
    db.close()


def test_failed_first_scan_skips_baseline(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["mac"])

    def boom(url: str) -> str:
        raise RuntimeError("network")

    result, _ = _scan(db, "", fetch_listing=boom)
    assert result["ok"] is False
    assert db.get_setting("baseline_done") is False
    db.close()


def test_notify_failure_retries(tmp_path: Path, listing_html: str) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["mac"])
    watch = db.create_watch({"name": "14 MBP", "all_of": ["MacBook Pro", "M5 Pro"], "min_ram_gb": 24})
    gone = listing_html.replace("FGDN4CH/A", "ZZZZ4CH/A").replace("MacBook Pro Apple M5 Pro", "Mac mini Apple M4")

    def ok_notify(settings, title, body, url):
        return []

    def bad_notify(settings, title, body, url):
        return ["bark: timeout"]

    run_scan(db, fetch_listing=lambda u: listing_html, fetch_detail=lambda u: "", notifier=ok_notify, sleep_fn=lambda s: None)
    run_scan(db, fetch_listing=lambda u: gone, fetch_detail=lambda u: "", notifier=ok_notify, sleep_fn=lambda s: None)

    failed = run_scan(
        db,
        fetch_listing=lambda u: listing_html,
        fetch_detail=lambda u: "",
        notifier=bad_notify,
        sleep_fn=lambda s: None,
    )
    assert failed["notified"] == 0
    state = db.watch_sku_state(watch["id"], "FGDN4CH/A")
    assert state and state["in_stock"] == 1
    assert state["notified"] == 1
    pending = db.list_pending_deliveries()
    assert pending
    events = [item for item in db.list_events() if item.get("type") == "appeared"]
    assert len(events) == 1

    retried = run_scan(
        db,
        fetch_listing=lambda u: listing_html,
        fetch_detail=lambda u: "",
        notifier=ok_notify,
        sleep_fn=lambda s: None,
    )
    assert retried["notified"] == 1
    state = db.watch_sku_state(watch["id"], "FGDN4CH/A")
    assert state["notified"] == 1
    assert not db.list_pending_deliveries()
    assert len([item for item in db.list_events() if item.get("type") == "appeared"]) == 1
    db.close()


def test_detail_fetch_only_for_matching_watch(tmp_path: Path, listing_html: str, detail_html: str) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["mac"])
    db.create_watch({"name": "Neo", "all_of": ["MacBook Neo"], "min_ram_gb": 8})
    fetched: list[str] = []

    def fetch_detail(url: str) -> str:
        fetched.append(url)
        return detail_html

    run_scan(
        db,
        fetch_listing=lambda u: listing_html,
        fetch_detail=fetch_detail,
        notifier=lambda *a: [],
        sleep_fn=lambda s: None,
    )
    assert len(fetched) == 1
    assert "fhfa4ch" in fetched[0].lower()
    db.close()


def test_scan_skips_mac_child_listings(tmp_path: Path, listing_html: str) -> None:
    db = Database(tmp_path / "app.db")
    db.set_setting("listings", ["mac", "macbook-pro", "macbook-air", "ipad"])
    seen: list[str] = []

    def fetch_listing(url: str) -> str:
        seen.append(url)
        return listing_html

    result = run_scan(
        db,
        fetch_listing=fetch_listing,
        fetch_detail=lambda url: "",
        notifier=lambda *a: [],
        sleep_fn=lambda s: None,
    )
    assert result["ok"]
    assert seen == [
        "https://www.apple.com.cn/shop/refurbished/mac",
        "https://www.apple.com.cn/shop/refurbished/ipad",
    ]
    db.close()


def _stale_row(sku: str, title: str, listing_key: str) -> dict:
    return {
        "sku": sku,
        "title": title,
        "url": f"https://www.apple.com.cn/shop/product/{sku}",
        "price": 3000,
        "listing_key": listing_key,
    }


def test_scan_marks_unselected_listings_out(tmp_path: Path, listing_html: str) -> None:
    db = Database(tmp_path / "app.db")
    db.upsert_products(
        [
            _stale_row("IPAD1CH/A", "翻新 iPad", "ipad"),
            _stale_row("WATCH1CH/A", "翻新 Apple Watch", "watch"),
            _stale_row("OLDPROCH/A", "翻新旧 MacBook Pro", "macbook-pro"),
        ]
    )
    db.set_setting("listings", ["mac"])
    result, _ = _scan(db, listing_html)
    assert result["ok"]
    stock = {p["sku"] for p in db.list_products(in_stock=True)}
    assert "FGDN4CH/A" in stock
    assert "IPAD1CH/A" not in stock
    assert "WATCH1CH/A" not in stock
    assert "OLDPROCH/A" not in stock
    rows = {p["sku"]: p for p in db.list_products(in_stock=None)}
    assert rows["IPAD1CH/A"]["in_stock"] == 0
    assert rows["OLDPROCH/A"]["in_stock"] == 0
    db.close()


def test_scan_keeps_failed_selected_listing(tmp_path: Path, listing_html: str) -> None:
    db = Database(tmp_path / "app.db")
    db.upsert_products(
        [
            _stale_row("IPAD1CH/A", "翻新 iPad", "ipad"),
            _stale_row("WATCH1CH/A", "翻新 Apple Watch", "watch"),
        ]
    )
    db.set_setting("listings", ["mac", "ipad"])

    def fetch_listing(url: str) -> str:
        if "/ipad" in url:
            raise RuntimeError("ipad down")
        return listing_html

    result, _ = _scan(db, listing_html, fetch_listing=fetch_listing)
    assert result["ok"]
    stock = {p["sku"] for p in db.list_products(in_stock=True)}
    assert "FGDN4CH/A" in stock
    assert "IPAD1CH/A" in stock
    assert "WATCH1CH/A" not in stock
    db.close()
