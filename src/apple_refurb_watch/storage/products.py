from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from apple_refurb_watch.storage.schema import MAX_PRODUCT_PAGE, utcnow
from apple_refurb_watch.storage.sqlite import SQLiteStore

SPEC_CACHE_TTL = timedelta(hours=6)


def spec_cache_is_fresh(row: dict | None, *, now: datetime | None = None) -> bool:
    if not row:
        return False
    raw = str(row.get("fetched_at") or "").strip()
    if not raw:
        return False
    try:
        fetched = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current - fetched <= SPEC_CACHE_TTL


class ProductRepository:
    """Persistence for the current product inventory and specification cache."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def upsert(self, products: Iterable[dict]) -> None:
        now = utcnow()
        with self.store.transaction() as conn:
            for item in products:
                extra = item.get("extra") or {}
                extra_text = json.dumps(extra, ensure_ascii=False) if isinstance(extra, dict) else str(extra)
                conn.execute(
                    """
                    INSERT INTO products(sku, title, url, price, listing_key, ram_gb, storage_gb, color_key,
                        color_label, model_key, year, screensize, image_url, in_stock, first_seen_at, last_seen_at, extra)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)
                    ON CONFLICT(sku) DO UPDATE SET
                        title=excluded.title,
                        url=excluded.url,
                        price=excluded.price,
                        listing_key=excluded.listing_key,
                        ram_gb=COALESCE(excluded.ram_gb, products.ram_gb),
                        storage_gb=COALESCE(excluded.storage_gb, products.storage_gb),
                        color_key=excluded.color_key,
                        color_label=excluded.color_label,
                        model_key=excluded.model_key,
                        year=excluded.year,
                        screensize=excluded.screensize,
                        image_url=excluded.image_url,
                        in_stock=1,
                        last_seen_at=excluded.last_seen_at,
                        extra=excluded.extra
                    """,
                    (
                        item["sku"],
                        item["title"],
                        item["url"],
                        item.get("price"),
                        item.get("listing_key"),
                        item.get("ram_gb"),
                        item.get("storage_gb"),
                        item.get("color_key"),
                        item.get("color_label"),
                        item.get("model_key"),
                        item.get("year"),
                        item.get("screensize"),
                        item.get("image_url"),
                        now,
                        now,
                        extra_text,
                    ),
                )

    def mark_listing_stock(self, listing_keys: list[str], seen_skus: set[str]) -> None:
        if not listing_keys:
            return
        keys_ph = ",".join("?" for _ in listing_keys)
        with self.store.transaction() as conn:
            if seen_skus:
                sku_ph = ",".join("?" for _ in seen_skus)
                conn.execute(
                    f"UPDATE products SET in_stock=0 WHERE listing_key IN ({keys_ph}) AND sku NOT IN ({sku_ph})",
                    (*listing_keys, *seen_skus),
                )
            else:
                conn.execute(
                    f"UPDATE products SET in_stock=0 WHERE listing_key IN ({keys_ph})",
                    tuple(listing_keys),
                )

    def mark_listings_out_except(self, keep_keys: list[str]) -> None:
        # An empty successful-list set means the scan fetched nothing; preserve the
        # previous inventory instead of marking every product as unavailable.
        if not keep_keys:
            return
        keys_ph = ",".join("?" for _ in keep_keys)
        with self.store.transaction() as conn:
            conn.execute(
                f"UPDATE products SET in_stock=0 WHERE listing_key NOT IN ({keys_ph})",
                tuple(keep_keys),
            )

    def list(
        self,
        in_stock: bool | None = True,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        sql = "SELECT * FROM products"
        if in_stock is True:
            sql += " WHERE in_stock=1"
        elif in_stock is False:
            sql += " WHERE in_stock=0"
        sql += " ORDER BY price IS NULL, price ASC, title"
        args: list[Any] = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            args.extend((min(MAX_PRODUCT_PAGE, max(0, int(limit))), max(0, int(offset))))
        with self.store.lock:
            rows = self.store.conn.execute(sql, args).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            extra = item.get("extra")
            if isinstance(extra, str):
                try:
                    item["extra"] = json.loads(extra)
                except json.JSONDecodeError:
                    item["extra"] = {}
        return items

    def count(self, *, in_stock: bool | None = True, listing_key: str | None = None, listing_keys: list[str] | None = None) -> int:
        clauses: list[str] = []
        args: list[Any] = []
        if in_stock is True:
            clauses.append("in_stock=1")
        elif in_stock is False:
            clauses.append("in_stock=0")
        if listing_key:
            clauses.append("listing_key=?")
            args.append(listing_key)
        elif listing_keys is not None:
            keys = [str(key) for key in listing_keys if key]
            if not keys:
                return 0
            clauses.append(f"listing_key IN ({','.join('?' for _ in keys)})")
            args.extend(keys)
        sql = "SELECT COUNT(*) AS n FROM products"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        with self.store.lock:
            return int(self.store.conn.execute(sql, args).fetchone()["n"])

    def get_spec(self, sku: str) -> dict | None:
        with self.store.lock:
            row = self.store.conn.execute("SELECT * FROM spec_cache WHERE sku=?", (sku,)).fetchone()
        return dict(row) if row else None

    def set_spec(self, sku: str, ram_gb: int | None, storage_gb: int | None) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO spec_cache(sku, ram_gb, storage_gb, fetched_at) VALUES(?,?,?,?)
                ON CONFLICT(sku) DO UPDATE SET
                    ram_gb=excluded.ram_gb,
                    storage_gb=excluded.storage_gb,
                    fetched_at=excluded.fetched_at
                """,
                (sku, ram_gb, storage_gb, utcnow()),
            )
            if ram_gb is not None or storage_gb is not None:
                conn.execute(
                    "UPDATE products SET ram_gb=COALESCE(?, ram_gb), storage_gb=COALESCE(?, storage_gb) WHERE sku=?",
                    (ram_gb, storage_gb, sku),
                )


ProductsRepository = ProductRepository

__all__ = ["ProductRepository", "ProductsRepository"]
