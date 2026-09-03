from __future__ import annotations

from typing import Any, Iterable
from pathlib import Path

from apple_refurb_watch.categories import DEFAULT_LISTINGS
from apple_refurb_watch.storage.schema import (
    DEFAULT_NOTIFY,
    DEFAULT_SETTINGS,
    EVENT_KEEP,
    SCHEMA,
    SCHEMA_VERSION,
    utcnow,
)
from apple_refurb_watch.storage.events import EventRepository
from apple_refurb_watch.storage.products import ProductRepository
from apple_refurb_watch.storage.scans import ScanRunRepository
from apple_refurb_watch.storage.settings import SettingsRepository
from apple_refurb_watch.storage.sqlite import SQLiteStore
from apple_refurb_watch.storage.watches import WatchRepository, _as_dim_filters, _as_float, _as_int


class Database:
    # Private helpers remain available for older integrations that imported
    # them from ``db`` while the actual implementations live in repositories.
    _watch_row = staticmethod(WatchRepository._row)
    _watch_payload = staticmethod(WatchRepository._payload)

    def __init__(self, path: Path | None = None) -> None:
        # Keep migration overridable for callers that validate/repair old databases.
        self._store = SQLiteStore(path, auto_migrate=False)
        # Keep these attributes public for existing migrations and callers.
        self.path = self._store.path
        self.conn = self._store.conn
        self._lock = self._store.lock
        self.settings_repo = SettingsRepository(self._store)
        self.watches_repo = WatchRepository(self._store)
        self.products_repo = ProductRepository(self._store)
        self.events_repo = EventRepository(self._store)
        self.scans_repo = ScanRunRepository(self._store)
        try:
            self.migrate()
        except Exception:
            try:
                self._store.close()
            except Exception:  # noqa: BLE001
                pass
            raise

    @property
    def settings_version(self) -> int:
        return self.settings_repo.version

    def migrate(self) -> None:
        self._store.migrate(apply_schema=self._apply_schema)

    def _apply_schema(self) -> None:
        self._store._apply_schema()

    def _schema_version(self) -> int:
        return self._store._schema_version()

    def _backup_db(self, from_version: int) -> Path:
        return self._store._backup_db(from_version)

    def _restore_db(self, backup_path: Path) -> None:
        self._store._restore_db(backup_path)

    def close(self) -> None:
        self._store.close()

    def transaction(self, *, immediate: bool = False):
        """Expose the store transaction for application-level atomic use cases."""

        return self._store.transaction(immediate=immediate)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.settings_repo.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self.settings_repo.set(key, value)

    def settings(self) -> dict[str, Any]:
        return self.settings_repo.all()

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        return self.settings_repo.update(patch)

    def list_watches(self) -> list[dict]:
        return self.watches_repo.list()

    def count_watches(self, *, enabled: bool | None = None) -> int:
        return self.watches_repo.count(enabled=enabled)

    def get_watch(self, watch_id: int) -> dict | None:
        return self.watches_repo.get(watch_id)

    def create_watch(self, data: dict) -> dict:
        return self.watches_repo.create(data)

    def update_watch(self, watch_id: int, data: dict) -> dict | None:
        return self.watches_repo.update(watch_id, data)

    def delete_watch(self, watch_id: int) -> bool:
        return self.watches_repo.delete(watch_id)

    def enabled_watches(self) -> list[dict]:
        return self.watches_repo.enabled()

    def upsert_products(self, products: Iterable[dict]) -> None:
        self.products_repo.upsert(products)

    def mark_listing_stock(self, listing_keys: list[str], seen_skus: set[str]) -> None:
        self.products_repo.mark_listing_stock(listing_keys, seen_skus)

    def mark_listings_out_except(self, keep_keys: list[str]) -> None:
        self.products_repo.mark_listings_out_except(keep_keys)

    def list_products(
        self,
        in_stock: bool | None = True,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        return self.products_repo.list(in_stock, limit=limit, offset=offset)

    def get_spec(self, sku: str) -> dict | None:
        return self.products_repo.get_spec(sku)

    def set_spec(self, sku: str, ram_gb: int | None, storage_gb: int | None) -> None:
        self.products_repo.set_spec(sku, ram_gb, storage_gb)

    def watch_sku_state(self, watch_id: int, sku: str) -> dict | None:
        return self.watches_repo.sku_state(watch_id, sku)

    def watch_sku_states(self, watch_id: int) -> dict[str, dict]:
        return self.watches_repo.sku_states(watch_id)

    def set_watch_sku(self, watch_id: int, sku: str, in_stock: bool, notified: bool) -> None:
        self.watches_repo.set_sku(watch_id, sku, in_stock, notified)

    def mark_watch_skus_out(self, watch_id: int, present: set[str], *, listing_keys: list[str] | None = None) -> None:
        self.watches_repo.mark_skus_out(watch_id, present, listing_keys=listing_keys)

    def list_watch_skus(self, watch_id: int) -> list[dict]:
        return self.watches_repo.list_skus(watch_id)

    def delete_watch_sku(self, watch_id: int, sku: str) -> bool:
        return self.watches_repo.delete_sku(watch_id, sku)

    def add_event(self, **kwargs: Any) -> int:
        return self.events_repo.add(**kwargs)

    def get_event(self, event_id: int) -> dict | None:
        return self.events_repo.get(event_id)

    def list_events(
        self,
        limit: int = 100,
        *,
        after_id: int | None = None,
        type: str | None = None,
    ) -> list[dict]:
        return self.events_repo.list(limit, after_id=after_id, type=type)

    def clear_events(self) -> int:
        return self.events_repo.clear()

    def enqueue_delivery(self, event_id: int, channel: str) -> None:
        self.events_repo.enqueue_delivery(event_id, channel)

    def list_pending_deliveries(self) -> list[dict]:
        return self.events_repo.list_pending_deliveries()

    def mark_delivery(
        self,
        event_id: int,
        channel: str,
        *,
        ok: bool,
        last_error: str | None = None,
        lease_token: str | None = None,
    ) -> bool:
        return self.events_repo.mark_delivery(
            event_id,
            channel,
            ok=ok,
            last_error=last_error,
            lease_token=lease_token,
        )

    def claim_pending_deliveries(self, **kwargs: Any) -> list[dict]:
        return self.events_repo.claim_pending_deliveries(**kwargs)

    def complete_delivery(self, event_id: int, channel: str, **kwargs: Any) -> bool:
        return self.events_repo.complete_delivery(event_id, channel, **kwargs)

    def release_delivery(self, event_id: int, channel: str, **kwargs: Any) -> bool:
        return self.events_repo.release_delivery(event_id, channel, **kwargs)

    def cancel_delivery(self, event_id: int, channel: str, *, reason: str = "通道未启用") -> bool:
        return self.events_repo.cancel_delivery(event_id, channel, reason=reason)

    def release_expired_leases(self) -> int:
        return self.events_repo.release_expired_leases()

    def count_products(
        self,
        *,
        in_stock: bool | None = True,
        listing_key: str | None = None,
        listing_keys: list[str] | None = None,
    ) -> int:
        return self.products_repo.count(in_stock=in_stock, listing_key=listing_key, listing_keys=listing_keys)

    def scan_status(self) -> dict[str, Any]:
        return self.settings_repo.scan_status()

    def start_scan_run(self, requested_listings: Iterable[str], *, metadata: dict | None = None) -> int:
        return self.scans_repo.start(requested_listings, metadata=metadata)

    def finish_scan_run(self, run_id: int, **kwargs: Any) -> None:
        self.scans_repo.finish(run_id, **kwargs)

    def prune_scan_history(self, **kwargs: Any) -> int:
        return self.scans_repo.prune(**kwargs)

    def count_observations(self) -> int:
        return self.scans_repo.count_observations()

    def count_scan_runs(self) -> int:
        return self.scans_repo.count_runs()

    def get_scan_run(self, run_id: int) -> dict | None:
        return self.scans_repo.get(run_id)

    def list_scan_runs(self, limit: int = 50) -> list[dict]:
        return self.scans_repo.list(limit)

    def mark_abandoned_scan_runs(self, *, older_than: str) -> int:
        return self.scans_repo.mark_abandoned(older_than=older_than)

    def add_observations(self, run_id: int, products: Iterable[Any], *, observed_at: str | None = None) -> int:
        return self.scans_repo.add_observations(run_id, products, observed_at=observed_at)

    def list_observations(self, run_id: int, *, limit: int = 1000) -> list[dict]:
        return self.scans_repo.list_observations(run_id, limit=limit)
