from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Any, Callable

from apple_refurb_watch.categories import compact_listings
from apple_refurb_watch.db import Database
from apple_refurb_watch.deliveries import deliver_event, retry_pending_deliveries
from apple_refurb_watch.listing_source import ListingSource
from apple_refurb_watch.match import matches_watch, needs_ram, needs_storage
from apple_refurb_watch.parse import Product

_scan_lock = threading.Lock()


def product_to_row(product: Product) -> dict[str, Any]:
    data = asdict(product)
    extra = data.pop("extra", {}) or {}
    data["extra"] = extra
    return data


def run_scan(
    db: Database | None = None,
    *,
    fetch_listing: Callable[[str], str] | None = None,
    fetch_detail: Callable[[str], str] | None = None,
    notifier: Callable[[dict, str, str, str | None], list[str]] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    if not _scan_lock.acquire(blocking=False):
        return {"ok": False, "message": "已有扫描在进行"}
    own_db = db is None
    db = db or Database()
    source = ListingSource(fetch_listing=fetch_listing, fetch_detail=fetch_detail)
    sleep_fn = sleep_fn or time.sleep
    try:
        return _run_scan_locked(db, source, notifier, sleep_fn)
    finally:
        db.set_setting("scanning", False)
        _scan_lock.release()
        source.close()
        if own_db:
            db.close()


def _run_scan_locked(
    db: Database,
    source: ListingSource,
    hook: Callable[[dict, str, str, str | None], list[str]] | None,
    sleep_fn: Callable[[float], None],
) -> dict[str, Any]:
    settings = db.settings()
    db.set_setting("scanning", True)
    listings = compact_listings(list(settings.get("listings") or ["mac"]))
    watches = db.enabled_watches()
    products: list[Product] = []
    errors: list[str] = []
    fetched_keys: list[str] = []
    for key in listings:
        try:
            batch = source.fetch_listing(key)
            products.extend(batch)
            fetched_keys.append(key)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}: {exc}")
            db.add_event(type="scan_error", message=f"抓取 {key} 失败: {exc}")

    delay = float(settings.get("detail_delay_seconds") or 1.4)
    for product in products:
        if not _needs_detail(product, watches):
            continue
        cached = db.get_spec(product.sku)
        if cached:
            product.ram_gb = product.ram_gb or cached.get("ram_gb")
            product.storage_gb = product.storage_gb or cached.get("storage_gb")
            if not _needs_detail(product, watches):
                continue
        try:
            sleep_fn(delay)
            specs = source.fetch_detail(product.url)
            product.ram_gb = product.ram_gb or specs.get("ram_gb")
            product.storage_gb = product.storage_gb or specs.get("storage_gb")
            db.set_spec(product.sku, product.ram_gb, product.storage_gb)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{product.sku}: {exc}")

    rows = [product_to_row(p) for p in products]
    db.upsert_products(rows)
    if fetched_keys:
        db.mark_listing_stock(fetched_keys, {p.sku for p in products if p.listing_key in fetched_keys})
        db.mark_listings_out_except(listings)

    baseline_done = bool(settings.get("baseline_done"))
    last_ok = str(settings.get("last_success_at") or "")
    scan_usable = bool(fetched_keys)
    notified = retry_pending_deliveries(db, settings, hook)
    matched = 0
    for watch in watches:
        present: set[str] = set()
        seed_watch = _should_seed_watch(watch, baseline_done, last_ok)
        for product in products:
            if not matches_watch(product, watch):
                continue
            matched += 1
            present.add(product.sku)
            state = db.watch_sku_state(watch["id"], product.sku)
            was_in_stock = bool(state and state.get("in_stock"))
            already_notified = bool(state and state.get("notified"))
            if seed_watch:
                db.set_watch_sku(watch["id"], product.sku, in_stock=True, notified=True)
                continue
            if was_in_stock and already_notified:
                db.set_watch_sku(watch["id"], product.sku, in_stock=True, notified=True)
                continue
            title = f"官翻上线：{watch['name']}"
            specs = []
            if product.ram_gb:
                specs.append(f"{product.ram_gb}GB 内存")
            if product.storage_gb:
                specs.append(_storage_label(product.storage_gb))
            if product.price is not None:
                specs.append(f"RMB {product.price:,.0f}")
            body = f"{product.title}\n" + " · ".join(specs) + f"\n{product.sku}"
            event_id = db.add_event(
                type="appeared",
                sku=product.sku,
                watch_id=watch["id"],
                title=product.title,
                price=product.price,
                url=product.url,
                message=body,
            )
            db.set_watch_sku(watch["id"], product.sku, in_stock=True, notified=True)
            notified += deliver_event(db, event_id, settings, title, body, product.url, hook)
        db.mark_watch_skus_out(watch["id"], present)

    from apple_refurb_watch.db import utcnow

    db.set_setting("last_scan_at", utcnow())
    db.set_setting("last_product_count", len(products))
    if not scan_usable:
        if not baseline_done:
            db.add_event(type="scan_error", message="首次扫描失败，未建立基线")
        db.set_setting("last_error", "; ".join(errors) if errors else "没有成功抓取任何分类")
        db.add_event(type="scan_error", message="; ".join(errors) if errors else "没有成功抓取任何分类")
        return {"ok": False, "count": 0, "matched": matched, "notified": notified, "errors": errors, "baseline": baseline_done}

    if not baseline_done:
        db.set_setting("baseline_done", True)
        db.add_event(type="baseline", message=f"已建立基线，当前在售 {len(products)} 件，之后才通知上新")
    db.set_setting("last_success_at", utcnow())
    db.set_setting("last_error", None)
    db.add_event(
        type="scan_ok",
        message=f"扫描完成：{len(products)} 件在售，命中 {matched}，新通知 {notified}",
    )
    return {
        "ok": True,
        "count": len(products),
        "matched": matched,
        "notified": notified,
        "errors": errors,
        "baseline": baseline_done,
    }


def _should_seed_watch(watch: dict, baseline_done: bool, last_ok: str) -> bool:
    if not baseline_done or not last_ok:
        return True
    created = str(watch.get("created_at") or "")
    return bool(created) and created >= last_ok


def _needs_detail(product: Product, watches: list[dict]) -> bool:
    for watch in watches:
        skip_ram = needs_ram(watch) and product.ram_gb is None
        skip_storage = needs_storage(watch) and product.storage_gb is None
        if not skip_ram and not skip_storage:
            continue
        if matches_watch(product, watch, ignore_ram=skip_ram, ignore_storage=skip_storage):
            return True
    return False


def _storage_label(storage_gb: int) -> str:
    if storage_gb >= 1024 and storage_gb % 1024 == 0:
        return f"{storage_gb // 1024}TB 硬盘"
    return f"{storage_gb}GB 硬盘"
