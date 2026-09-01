from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Any, Callable

from apple_refurb_watch.categories import compact_listings
from apple_refurb_watch.db import Database
from apple_refurb_watch.deliveries import enabled_channels, retry_pending_deliveries
from apple_refurb_watch.listing_source import ListingSource
from apple_refurb_watch.match import matches_watch, needs_ram, needs_storage
from apple_refurb_watch.parse import Product
from apple_refurb_watch.storage.events import event_fingerprint

_scan_lock = threading.Lock()


def product_to_row(product: Product) -> dict[str, Any]:
    data = asdict(product)
    extra = data.pop("extra", {}) or {}
    data["extra"] = extra
    return data


class ScanService:
    """Own the dependencies for repeated scans.

    The scheduler and the manual API both call this service.  Keeping the
    ``ListingSource`` alive for the service lifetime lets its HTTP client reuse
    connections while ``run_scan`` remains a backwards-compatible one-shot
    helper for CLI callers and tests.
    """

    def __init__(
        self,
        db: Database,
        *,
        fetch_listing: Callable[[str], str] | None = None,
        fetch_detail: Callable[[str], str] | None = None,
        notifier: Callable[[dict, str, str, str | None], list[str]] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        source: ListingSource | None = None,
    ) -> None:
        self.db = db
        self.source = source if source is not None else ListingSource(fetch_listing=fetch_listing, fetch_detail=fetch_detail)
        self._owns_source = source is None
        self.notifier = notifier
        self.sleep_fn = sleep_fn or time.sleep
        self._closed = False
        self._thread_lock = threading.Lock()
        self._active_thread: threading.Thread | None = None

    def run_once(self) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("扫描服务已关闭")
        if not _scan_lock.acquire(blocking=False):
            return {"ok": False, "message": "已有扫描在进行"}
        try:
            return _run_scan_locked(self.db, self.source, self.notifier, self.sleep_fn)
        finally:
            # A failed fetch must never leave the UI in a permanent "scanning"
            # state, including exceptions raised before the normal result path.
            try:
                self.db.set_setting("scanning", False)
            finally:
                _scan_lock.release()

    def submit(self) -> dict[str, Any]:
        """Queue one scan and return its durable run id immediately.

        The same process-wide lock used by ``run_once`` prevents a scheduler,
        legacy API call, and a submitted scan from overlapping.  Reserving the
        ``scan_runs`` row before starting the thread means clients can poll a
        stable id even while network work is still in progress.
        """

        if self._closed:
            raise RuntimeError("扫描服务已关闭")
        if not _scan_lock.acquire(blocking=False):
            return {"accepted": False, "ok": False, "status": "busy", "message": "已有扫描在进行"}
        try:
            settings = self.db.settings()
            listings = compact_listings(list(settings.get("listings") or ["mac"]))
            run_id = self.db.start_scan_run(listings, metadata={"trigger": "api"})
            self.db.set_setting("scanning", True)
            thread = threading.Thread(
                target=self._run_submitted,
                args=(run_id,),
                name="arw-scan-submit",
                daemon=True,
            )
            with self._thread_lock:
                self._active_thread = thread
            thread.start()
            return {
                "accepted": True,
                "ok": True,
                "status": "queued",
                "scan_run_id": run_id,
                "id": run_id,
            }
        except Exception as exc:
            # If reservation or thread startup fails, do not leave an
            # apparently running row for doctor to discover much later.
            try:
                if "run_id" in locals():
                    self.db.finish_scan_run(
                        int(run_id),
                        status="failed",
                        errors=[str(exc)],
                    )
            except Exception:  # noqa: BLE001
                pass
            _scan_lock.release()
            raise

    def _run_submitted(self, run_id: int) -> None:
        try:
            _run_scan_locked(
                self.db,
                self.source,
                self.notifier,
                self.sleep_fn,
                reserved_run_id=run_id,
            )
        except Exception:
            # The scan service records a failed run where possible.  There is
            # no request thread to propagate the exception to; callers inspect
            # the run resource instead.
            pass
        finally:
            try:
                self.db.set_setting("scanning", False)
            finally:
                with self._thread_lock:
                    self._active_thread = None
                _scan_lock.release()

    # Short aliases make the service convenient for scheduler adapters and
    # callers that naturally describe the operation as ``scan`` or ``run``.
    scan = run_once
    run = run_once

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._thread_lock:
            thread = self._active_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=30.0)
        if self._owns_source:
            self.source.close()

    def __enter__(self) -> "ScanService":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def run_scan(
    db: Database | None = None,
    *,
    fetch_listing: Callable[[str], str] | None = None,
    fetch_detail: Callable[[str], str] | None = None,
    notifier: Callable[[dict, str, str, str | None], list[str]] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    own_db = db is None
    database = db if db is not None else Database()
    service: ScanService | None = None
    try:
        service = ScanService(
            database,
            fetch_listing=fetch_listing,
            fetch_detail=fetch_detail,
            notifier=notifier,
            sleep_fn=sleep_fn,
        )
        return service.run_once()
    finally:
        try:
            if service is not None:
                service.close()
        finally:
            if own_db:
                database.close()


def _run_scan_locked(
    db: Database,
    source: ListingSource,
    hook: Callable[[dict, str, str, str | None], list[str]] | None,
    sleep_fn: Callable[[float], None],
    *,
    reserved_run_id: int | None = None,
) -> dict[str, Any]:
    from apple_refurb_watch.storage.schema import utcnow

    settings = db.settings()
    listings = compact_listings(list(settings.get("listings") or ["mac"]))
    watches = db.enabled_watches()
    started_run = reserved_run_id is not None
    run_id: int | None = reserved_run_id
    products: list[Product] = []
    errors: list[str] = []
    fetched_keys: list[str] = []
    detail_updates: list[tuple[str, int | None, int | None]] = []

    db.set_setting("scanning", True)
    try:
        if run_id is None:
            run_id = db.start_scan_run(listings)
            started_run = True

        # Network and parsing happen before the write transaction. A source
        # failure is recorded in memory first, so it cannot commit a half
        # inventory snapshot or an orphan event.
        for key in listings:
            try:
                batch = source.fetch_listing(key)
                products.extend(batch)
                fetched_keys.append(key)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{key}: {exc}")

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
                detail_updates.append((product.sku, product.ram_gb, product.storage_gb))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{product.sku}: {exc}")

        baseline_done = bool(settings.get("baseline_done"))
        last_ok = str(settings.get("last_success_at") or "")
        scan_complete = bool(fetched_keys) and set(fetched_keys) == set(listings)
        observed_at = utcnow()
        matched = 0

        # Everything derived from the fetched snapshot is committed together.
        # BEGIN IMMEDIATE also prevents a concurrent settings/scan writer from
        # interleaving state transitions.
        with db.transaction(immediate=True):
            rows = [product_to_row(p) for p in products]
            if rows:
                db.upsert_products(rows)
            for sku, ram_gb, storage_gb in detail_updates:
                db.set_spec(sku, ram_gb, storage_gb)
            if fetched_keys:
                db.mark_listing_stock(fetched_keys, {p.sku for p in products if p.listing_key in fetched_keys})
                db.mark_listings_out_except(listings)
            db.add_observations(run_id, products, observed_at=observed_at)

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
                    # Include the previous state marker so a later restock can
                    # produce a new event while retries of this transition are
                    # idempotent.
                    marker = str((state or {}).get("updated_at") or "initial")
                    event_id = db.add_event(
                        type="appeared",
                        sku=product.sku,
                        watch_id=watch["id"],
                        title=product.title,
                        price=product.price,
                        url=product.url,
                        message=body,
                        fingerprint=event_fingerprint(
                            "appeared",
                            sku=product.sku,
                            watch_id=int(watch["id"]),
                            state=marker,
                        ),
                    )
                    db.set_watch_sku(watch["id"], product.sku, in_stock=True, notified=True)
                    for channel, _conf in enabled_channels(settings, hook):
                        db.enqueue_delivery(event_id, channel)
                # A missing SKU is meaningful only after every selected source
                # was observed successfully.
                if scan_complete:
                    db.mark_watch_skus_out(watch["id"], present)

            db.set_setting("last_scan_at", observed_at)
            db.set_setting("last_product_count", len(products))
            if not fetched_keys:
                message = "; ".join(errors) if errors else "没有成功抓取任何分类"
                db.set_setting("last_error", message)
                db.add_event(
                    type="scan_error",
                    message=message,
                    fingerprint=event_fingerprint("scan_error", state=f"{run_id}:failed"),
                )
                if not baseline_done:
                    db.add_event(
                        type="scan_error",
                        message="首次扫描失败，未建立基线",
                        fingerprint=event_fingerprint("scan_error", state=f"{run_id}:baseline"),
                    )
                run_status = "failed"
            elif not scan_complete:
                message = "; ".join(errors) if errors else "部分分类抓取成功"
                db.set_setting("last_error", message)
                db.add_event(
                    type="scan_partial",
                    message=f"部分扫描完成：{message}",
                    fingerprint=event_fingerprint("scan_partial", state=str(run_id)),
                )
                run_status = "partial"
            else:
                if not baseline_done:
                    db.set_setting("baseline_done", True)
                    db.add_event(
                        type="baseline",
                        message=f"已建立基线，当前在售 {len(products)} 件，之后才通知上新",
                        fingerprint=event_fingerprint("baseline", state=str(run_id)),
                    )
                db.set_setting("last_success_at", observed_at)
                db.set_setting("last_error", None)
                db.add_event(
                    type="scan_ok",
                    message=f"扫描完成：{len(products)} 件在售，命中 {matched}",
                    fingerprint=event_fingerprint("scan_ok", state=str(run_id)),
                )
                run_status = "succeeded"
            db.finish_scan_run(
                run_id,
                status=run_status,
                successful_listings=fetched_keys,
                product_count=len(products),
                matched_count=matched,
                errors=errors,
                finished_at=utcnow(),
            )

        # Delivery is deliberately post-commit. If the process dies while a
        # provider is unavailable, the outbox row remains for the worker/retry
        # path and the inventory transaction is still durable.
        notified = retry_pending_deliveries(db, settings, hook)
        baseline_final = bool(db.get_setting("baseline_done"))
        return {
            "ok": bool(fetched_keys),
            "partial": bool(fetched_keys) and not scan_complete,
            "count": len(products),
            "matched": matched,
            "notified": notified,
            "errors": errors,
            "baseline": baseline_final,
            "scan_run_id": run_id,
            "scan_status": run_status,
        }
    except Exception as exc:
        # A persistence failure must not leave a run stuck in `running` or the
        # UI stuck in `scanning=true`. Keep this recovery write separate from
        # the rolled-back snapshot transaction.
        if started_run and run_id is not None:
            try:
                with db.transaction(immediate=True):
                    db.finish_scan_run(
                        run_id,
                        status="failed",
                        successful_listings=fetched_keys,
                        product_count=0,
                        matched_count=0,
                        errors=[*errors, str(exc)],
                    )
                    db.set_setting("last_error", str(exc))
            except Exception:  # noqa: BLE001
                pass
        raise


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
