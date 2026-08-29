from __future__ import annotations

import json
from typing import Any

from .catalog import _cache, _merge_catalog, live_catalog_path, load_catalog
from .tokens import _as_dim_token, _canonical_dim

def ingest_bootstrap_catalog(bootstrap: dict | None, listing_key: str) -> None:
    fragment = catalog_from_bootstrap(bootstrap, listing_key)
    if not fragment:
        return
    path = live_catalog_path()
    existing: dict[str, Any] = {"version": 2, "listing_dimensions": {}, "listing_legends": {}, "dimensions": {}}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            existing = _merge_catalog(existing, loaded)
    merged = _merge_catalog(existing, fragment)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _cache["sig"] = None


def catalog_from_bootstrap(bootstrap: dict | None, listing_key: str) -> dict[str, Any]:
    if not bootstrap:
        return {}
    dims = bootstrap.get("dimensions") or []
    dictionaries = ((bootstrap.get("dictionaries") or {}).get("dimensions")) or {}
    if not dims and not dictionaries:
        return {}
    if not dictionaries:
        return {}
    ordered_keys = [str(item.get("key")) for item in dims if item.get("key")]
    legends = {str(item.get("key")): str(item.get("legend") or item.get("key")) for item in dims if item.get("key")}
    dimensions: dict[str, Any] = {}
    for key in ordered_keys or dictionaries.keys():
        meta = dictionaries.get(key) or {}
        values: dict[str, str] = {}
        order: list[str] = []
        ranked = sorted(
            meta.items(),
            key=lambda item: item[1].get("sortOrder", 1000) if isinstance(item[1], dict) else 1000,
        )
        for value, info in ranked:
            token = _canonical_dim(str(key), _as_dim_token(value))
            if not token:
                continue
            label = str((info or {}).get("text") or token).replace("\xa0", " ").strip()
            if token not in values:
                values[token] = label
                order.append(token)
        dimensions[str(key)] = {
            "legend": legends.get(key) or key,
            "listings": [listing_key],
            "order": order,
            "values": values,
            "value_listings": {token: [listing_key] for token in order},
        }
    listing_legends = {listing_key: legends} if legends else {}
    return {
        "listing_dimensions": {listing_key: ordered_keys} if ordered_keys else {},
        "listing_legends": listing_legends,
        "dimensions": dimensions,
    }


def sync_filter_catalog(fetch_listing) -> dict[str, Any]:
    from apple_refurb_watch.categories import CATEGORIES
    from apple_refurb_watch.parse import extract_bootstrap

    for key, item in CATEGORIES.items():
        html = fetch_listing(item["url"])
        ingest_bootstrap_catalog(extract_bootstrap(html), key)
    return load_catalog()
