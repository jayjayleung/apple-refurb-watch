from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from apple_refurb_watch.paths import data_dir

from .tokens import (
    CHIP_KEY,
    CHIP_LISTING_KEYS,
    CHIP_SPEC,
    CORE_LISTING_KEYS,
    CORES_KEY,
    CORES_SPEC,
    CPU_CORE_KEY,
    CPU_CORE_SPEC,
    GPU_CORE_KEY,
    GPU_CORE_SPEC,
    core_label_from_token,
    cores_label_from_token,
    format_dim_value,
    _chip_label_from_token,
)

PACKAGED_CATALOG = Path(__file__).resolve().parent.parent / "data" / "filter_catalog.json"
_cache: dict[str, Any] = {"sig": None, "data": None}


def packaged_catalog_path() -> Path:
    return PACKAGED_CATALOG


def user_catalog_path() -> Path:
    return data_dir() / "filter_catalog.json"


def live_catalog_path() -> Path:
    return data_dir() / "filter_catalog.live.json"


def load_catalog() -> dict[str, Any]:
    packaged = PACKAGED_CATALOG
    live = live_catalog_path()
    overlay = user_catalog_path()
    sig = (
        (str(packaged), packaged.stat().st_mtime if packaged.exists() else 0),
        (str(live), live.stat().st_mtime if live.exists() else 0),
        (str(overlay), overlay.stat().st_mtime if overlay.exists() else 0),
    )
    if _cache["sig"] == sig and _cache["data"] is not None:
        return _cache["data"]
    data = json.loads(packaged.read_text(encoding="utf-8"))
    for path in (live, overlay):
        if not path.exists():
            continue
        try:
            extra = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            extra = {}
        if isinstance(extra, dict):
            data = _merge_catalog(data, extra)
    _cache["sig"] = sig
    _cache["data"] = data
    return data


def dimension_keys_for(listing_key: str | None) -> list[str]:
    catalog = load_catalog()
    listing_dims = catalog.get("listing_dimensions") or {}
    if not listing_key:
        return []
    keys = list(listing_dims.get(listing_key) or [])
    return _inject_derived_keys(keys, listing_key)


def _listing_has_chip(listing_key: str | None) -> bool:
    return bool(listing_key) and listing_key in CHIP_LISTING_KEYS


def _listing_has_cores(listing_key: str | None) -> bool:
    return bool(listing_key) and listing_key in CORE_LISTING_KEYS


def _inject_derived_keys(keys: list[str], listing_key: str | None) -> list[str]:
    out = list(keys)
    if _listing_has_chip(listing_key) and CHIP_KEY not in out:
        if "refurbClearModel" in out:
            out.insert(out.index("refurbClearModel") + 1, CHIP_KEY)
        else:
            out.insert(0, CHIP_KEY)
    if _listing_has_cores(listing_key) and CORES_KEY not in out:
        anchor = CHIP_KEY if CHIP_KEY in out else "refurbClearModel"
        pos = out.index(anchor) + 1 if anchor in out else 0
        out.insert(pos, CORES_KEY)
    return out


def dim_spec(key: str) -> dict[str, Any]:
    if key == CHIP_KEY:
        return CHIP_SPEC
    if key == CORES_KEY:
        return CORES_SPEC
    if key == CPU_CORE_KEY:
        return CPU_CORE_SPEC
    if key == GPU_CORE_KEY:
        return GPU_CORE_SPEC
    catalog = load_catalog()
    return (catalog.get("dimensions") or {}).get(key) or {}


def label_for(key: str, value: str | None) -> str:
    if not value:
        return ""
    labels = dim_spec(key).get("values") or {}
    if value in labels:
        return str(labels[value])
    if key == CHIP_KEY:
        return _chip_label_from_token(value)
    if key == CORES_KEY:
        return cores_label_from_token(value)
    if key in {CPU_CORE_KEY, GPU_CORE_KEY}:
        return core_label_from_token(key, value)
    return format_dim_value(value)


def _merge_catalog(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    if overlay.get("notes"):
        out["notes"] = overlay["notes"]
    if overlay.get("listing_dimensions"):
        out.setdefault("listing_dimensions", {}).update(overlay["listing_dimensions"])
    if overlay.get("listing_legends"):
        target_legends = out.setdefault("listing_legends", {})
        for listing, legends in overlay["listing_legends"].items():
            target_legends.setdefault(listing, {}).update(legends or {})
    extra_dims = overlay.get("dimensions") or {}
    target = out.setdefault("dimensions", {})
    for key, spec in extra_dims.items():
        if key not in target:
            target[key] = deepcopy(spec)
            continue
        current = target[key]
        if spec.get("legend"):
            current["legend"] = spec["legend"]
        if spec.get("listings"):
            current["listings"] = list(dict.fromkeys([*(current.get("listings") or []), *spec["listings"]]))
        if spec.get("order"):
            current["order"] = list(dict.fromkeys([*(current.get("order") or []), *spec["order"]]))
        current.setdefault("values", {}).update(spec.get("values") or {})
        if spec.get("value_listings"):
            merged_values = current.setdefault("value_listings", {})
            for val, lists in spec["value_listings"].items():
                merged_values[val] = list(dict.fromkeys([*(merged_values.get(val) or []), *(lists or [])]))
    return out
