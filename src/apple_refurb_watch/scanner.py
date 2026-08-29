from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Any, Callable

from apple_refurb_watch.categories import compact_listings, listing_url
from apple_refurb_watch.db import Database
from apple_refurb_watch.fetch import HtmlFetcher
from apple_refurb_watch.match import matches_watch, needs_ram, needs_storage
from apple_refurb_watch.notify import NotifyError, send_all
from apple_refurb_watch.parse import Product, extract_bootstrap, parse_detail_specs, parse_listing_html

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
    fetcher: HtmlFetcher | None = None
    if fetch_listing is None or fetch_detail is None:
        fetcher = HtmlFetcher()
        fetch_listing = fetch_listing or fetcher
        fetch_detail = fetch_detail or fetcher
    notifier = notifier or send_all
    sleep_fn = sleep_fn or time.sleep
    try:
        return _run_scan_locked(db, fetch_listing, fetch_detail, notifier, sleep_fn)
    finally:
        db.set_setting("scanning", False)
        _scan_lock.release()
        if fetcher is not None:
            fetcher.close()
        if own_db:
            db.close()


def _run_scan_locked(
    db: Database,
    fetch_listing: Callable[[str], str],
    fetch_detail: Callable[[str], str],
    notifier: Callable[[dict, str, str, str | None], list[str]],
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
        url = listing_url(key)
        try:
            html = fetch_listing(url)
            batch = parse_listing_html(html, key, url)
            products.extend(batch)
            fetched_keys.append(key)
            try:
                from apple_refurb_watch.filters import ingest_bootstrap_catalog

                ingest_bootstrap_catalog(extract_bootstrap(html), key)
            except Exception:  # noqa: BLE001
                pass
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
            specs = parse_detail_specs(fetch_detail(product.url))
            product.ram_gb = product.ram_gb or specs.get("ram_gb")
            product.storage_gb = product.storage_gb or specs.get("storage_gb")
            db.set_spec(product.sku, product.ram_gb, product.storage_gb)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{product.sku}: {exc}")

    rows = [product_to_row(p) for p in products]
    db.upsert_products(rows)
    if fetched_keys:
        db.mark_listing_stock(fetched_keys, {p.sku for p in products if p.listing_key in fetched_keys})

    baseline_done = bool(settings.get("baseline_done"))
    scan_usable = bool(fetched_keys)
    notified = 0
    matched = 0
    for watch in watches:
        present: set[str] = set()
        for product in products:
            if not matches_watch(product, watch):
                continue
            matched += 1
            present.add(product.sku)
            state = db.watch_sku_state(watch["id"], product.sku)
            was_in_stock = bool(state and state.get("in_stock"))
            already_notified = bool(state and state.get("notified"))
            if not baseline_done:
                db.set_watch_sku(watch["id"], product.sku, in_stock=True, notified=False)
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
            try:
                notify_errors = notifier(settings, title, body, product.url)
            except NotifyError as exc:
                notify_errors = [str(exc)]
            except Exception as exc:  # noqa: BLE001
                notify_errors = [str(exc)]
            notify_ok = not notify_errors
            db.set_watch_sku(watch["id"], product.sku, in_stock=True, notified=notify_ok)
            if notify_ok or not was_in_stock:
                db.add_event(
                    type="appeared",
                    sku=product.sku,
                    watch_id=watch["id"],
                    title=product.title,
                    price=product.price,
                    url=product.url,
                    message=body if notify_ok else f"{body}\n通知失败: {'; '.join(notify_errors)}",
                )
            if notify_ok:
                notified += 1
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
