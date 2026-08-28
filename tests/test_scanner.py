from pathlib import Path

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

    third = run_scan(
        db,
        fetch_listing=lambda url: listing_html,
        fetch_detail=lambda url: "",
        notifier=notify,
        sleep_fn=lambda _s: None,
    )
    assert third["notified"] == 0
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
    assert state["notified"] == 0

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
