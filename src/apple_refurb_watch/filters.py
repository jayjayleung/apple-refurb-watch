from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

from apple_refurb_watch.match import norm_text
from apple_refurb_watch.paths import data_dir

PACKAGED_CATALOG = Path(__file__).resolve().parent / "data" / "filter_catalog.json"
VALUE_ALIASES = {
    "wifi": "无线局域网",
    "wificell": "无线局域网 + 蜂窝网络",
    "gps": "GPS",
    "gpscell": "GPS + 蜂窝网络",
    "aluminum": "铝金属",
    "stainless": "不锈钢",
    "titanium": "钛金属",
}
MATERIAL_KEYS = {"aluminum", "stainless", "titanium"}
VALUE_NORMALIZE = {
    "dimensionColor": {
        "spacegray": "space_gray",
        "spacegrey": "space_gray",
    },
}

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
    if listing_key and listing_key in listing_dims:
        return list(listing_dims[listing_key])
    seen: list[str] = []
    for keys in listing_dims.values():
        for key in keys:
            if key not in seen:
                seen.append(key)
    if seen:
        return seen
    return list((catalog.get("dimensions") or {}).keys())


def label_for(key: str, value: str | None) -> str:
    if not value:
        return ""
    catalog = load_catalog()
    spec = (catalog.get("dimensions") or {}).get(key) or {}
    labels = spec.get("values") or {}
    if value in labels:
        return str(labels[value])
    return format_dim_value(value)


def format_dim_value(value: str) -> str:
    raw = str(value).strip()
    lower = raw.lower().replace(" ", "")
    if lower in VALUE_ALIASES:
        return VALUE_ALIASES[lower]
    inch = re.fullmatch(r"(\d+)(?:_(\d+))?inch", lower)
    if inch:
        if inch.group(2):
            return f"{inch.group(1)}.{inch.group(2)} 英寸"
        return f"{inch.group(1)} 英寸"
    mm = re.fullmatch(r"(\d+(?:\.\d+)?)mm", lower)
    if mm:
        return f"{mm.group(1)} 毫米"
    size = re.fullmatch(r"(\d+(?:\.\d+)?)(gb|tb)", lower.replace("point", ".").replace("_", "."))
    if size:
        return f"{size.group(1)}{size.group(2).upper()}"
    if re.fullmatch(r"\d{4}", raw):
        return f"{raw} 年"
    return raw


def product_dims(item: Mapping[str, Any]) -> dict[str, str]:
    extra = item.get("extra") or {}
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            extra = {}
    raw = dict((extra or {}).get("dims") or {})
    fallbacks = {
        "refurbClearModel": item.get("model_key"),
        "dimensionScreensize": item.get("screensize") if _looks_like("inch", item.get("screensize")) else None,
        "dimensionCaseSize": item.get("screensize") if _looks_like("mm", item.get("screensize")) else None,
        "dimensionRelYear": item.get("year"),
        "dimensionColor": None if str(item.get("color_key") or "").lower() in MATERIAL_KEYS else item.get("color_key"),
        "tsMemorySize": _gb_token(item.get("ram_gb")),
        "dimensionCapacity": _gb_token(item.get("storage_gb")),
    }
    out: dict[str, str] = {}
    for key, value in raw.items():
        token = _canonical_dim(str(key), _as_dim_token(value))
        if token:
            out[str(key)] = token
    for key, value in fallbacks.items():
        if key in out:
            continue
        token = _canonical_dim(key, _as_dim_token(value))
        if token:
            out[key] = token
    return out


def dims_match(item: Mapping[str, Any], dim_filters: Mapping[str, Any] | None) -> bool:
    wanted_map = normalize_dim_filters(dim_filters)
    if not wanted_map:
        return True
    have = product_dims(item)
    for key, wanted in wanted_map.items():
        got = have.get(key)
        if got is None:
            return False
        got_n = norm_text(got)
        if not any(norm_text(value) == got_n for value in wanted):
            return False
    return True


def normalize_dim_filters(dim_filters: Mapping[str, Any] | None) -> dict[str, list[str]]:
    if not dim_filters:
        return {}
    if isinstance(dim_filters, str):
        try:
            dim_filters = json.loads(dim_filters)
        except json.JSONDecodeError:
            return {}
    out: dict[str, list[str]] = {}
    for key, values in dict(dim_filters).items():
        if isinstance(values, str):
            tokens = [values]
        elif isinstance(values, Iterable):
            tokens = [str(v) for v in values]
        else:
            tokens = [str(values)]
        clean = [_canonical_dim(str(key), _as_dim_token(v)) for v in tokens]
        clean = [v for v in clean if v]
        if clean:
            out[str(key)] = list(dict.fromkeys(clean))
    return out


def selected_dims(params: Any) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if params is None:
        return out
    if hasattr(params, "multi_items"):
        items = params.multi_items()
    elif hasattr(params, "items"):
        items = params.items()
    else:
        return out
    for key, value in items:
        name = str(key)
        token = _as_dim_token(value)
        if not name.startswith("d_") or not token:
            continue
        out.setdefault(name[2:], []).append(token)
    return normalize_dim_filters(out)


def restrict_dims(dim_filters: Mapping[str, Any] | None, listing_key: str | None) -> dict[str, list[str]]:
    clean = normalize_dim_filters(dim_filters)
    if not listing_key:
        return clean
    allowed = set(dimension_keys_for(listing_key))
    return {key: values for key, values in clean.items() if key in allowed}


def facet_groups(
    products: list[Mapping[str, Any]] | None,
    listing_key: str | None,
    selected: Mapping[str, Any] | None = None,
    *,
    include_catalog: bool = False,
    show_counts: bool = True,
) -> list[dict[str, Any]]:
    catalog = load_catalog()
    specs = catalog.get("dimensions") or {}
    listing_dims = catalog.get("listing_dimensions") or {}
    listing_legends = (catalog.get("listing_legends") or {}).get(listing_key or "") or {}
    keys = dimension_keys_for(listing_key)
    selected_map = normalize_dim_filters(selected)
    live_counts: dict[str, dict[str, int]] = {}
    for item in products or []:
        for key, value in product_dims(item).items():
            live_counts.setdefault(key, {})
            live_counts[key][value] = live_counts[key].get(value, 0) + 1
    groups: list[dict[str, Any]] = []
    for key in keys:
        spec = specs.get(key) or {}
        values: list[str] = []
        if include_catalog:
            values.extend(list(spec.get("order") or spec.get("values", {}).keys()))
            for extra in (spec.get("values") or {}).keys():
                if extra not in values:
                    values.append(extra)
        for live in (live_counts.get(key) or {}).keys():
            if live not in values:
                values.append(live)
        for picked in selected_map.get(key) or []:
            if picked not in values:
                values.append(picked)
        values = _sort_values(values, spec)
        if not include_catalog:
            values = [
                value
                for value in values
                if (live_counts.get(key) or {}).get(value) or value in (selected_map.get(key) or [])
            ]
        if not values:
            continue
        options = []
        for value in values:
            count = (live_counts.get(key) or {}).get(value, 0)
            options.append(
                {
                    "value": value,
                    "label": label_for(key, value),
                    "count": count if show_counts else None,
                    "checked": value in (selected_map.get(key) or []),
                    "listings": _value_listings(key, value, spec),
                }
            )
        groups.append(
            {
                "key": key,
                "legend": listing_legends.get(key) or spec.get("legend") or key,
                "listings": spec.get("listings") or _listings_for_key(key, listing_dims),
                "options": options,
            }
        )
    return groups


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


def summarize_dims(dim_filters: Mapping[str, Any] | None) -> list[str]:
    catalog = load_catalog()
    specs = catalog.get("dimensions") or {}
    parts: list[str] = []
    for key, values in normalize_dim_filters(dim_filters).items():
        legend = (specs.get(key) or {}).get("legend") or key
        labels = [label_for(key, value) for value in values]
        parts.append(f"{legend}：{' / '.join(labels)}")
    return parts


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
    return out


def _listings_for_key(key: str, listing_dims: Mapping[str, Any]) -> list[str]:
    return [listing for listing, keys in listing_dims.items() if key in (keys or [])]


def _value_listings(key: str, value: str, spec: Mapping[str, Any]) -> list[str]:
    custom = (spec.get("value_listings") or {}).get(value)
    if custom:
        return list(custom)
    default = list(spec.get("listings") or [])
    if key != "refurbClearModel":
        return default
    low = value.lower()
    if low.startswith("ipad"):
        return ["ipad"]
    if "watch" in low:
        return ["watch"]
    if "airpod" in low:
        return ["airpods"]
    if low == "macbookpro":
        return ["mac", "macbook-pro"]
    if low == "macbookair":
        return ["mac", "macbook-air"]
    if low == "macpro":
        return ["mac"]
    return ["mac", "macbook-pro", "macbook-air"]


def _sort_values(values: list[str], spec: Mapping[str, Any]) -> list[str]:
    order = list(spec.get("order") or (spec.get("values") or {}).keys())
    rank = {value: index for index, value in enumerate(order)}
    return sorted(values, key=lambda value: (rank.get(value, 1000), _natural_key(value)))


def _natural_key(value: str) -> tuple:
    parts = re.split(r"(\d+)", str(value).lower())
    out: list[Any] = []
    for part in parts:
        out.append(int(part) if part.isdigit() else part)
    return tuple(out)


def _as_dim_token(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, list):
        return _as_dim_token(value[0] if value else None)
    text = str(value).strip()
    return text or None


def _canonical_dim(key: str, token: str | None) -> str | None:
    if not token:
        return None
    table = VALUE_NORMALIZE.get(key) or {}
    return table.get(token) or table.get(token.lower()) or token


def _looks_like(kind: str, value: Any) -> bool:
    text = str(value or "").lower()
    return kind in text


def _gb_token(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return None
    if amount >= 1024 and amount % 1024 == 0:
        return f"{amount // 1024}tb"
    return f"{amount}gb"
