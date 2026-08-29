from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from apple_refurb_watch.textutil import norm_text

from .catalog import dimension_keys_for, dim_spec, label_for
from .tokens import (
    CHIP_KEY,
    CPU_CORE_KEY,
    GPU_CORE_KEY,
    MATERIAL_KEYS,
    chip_from_title,
    cores_from_title,
    _as_dim_token,
    _canonical_dim,
    _gb_token,
    _looks_like,
)

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
    title = item.get("title") or ""
    if CHIP_KEY not in out:
        chip = chip_from_title(title)
        if chip:
            out[CHIP_KEY] = chip
    cpu, gpu = cores_from_title(title)
    if CPU_CORE_KEY not in out and cpu:
        out[CPU_CORE_KEY] = cpu
    if GPU_CORE_KEY not in out and gpu:
        out[GPU_CORE_KEY] = gpu
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

def summarize_dims(dim_filters: Mapping[str, Any] | None) -> list[str]:
    parts: list[str] = []
    for key, values in normalize_dim_filters(dim_filters).items():
        legend = dim_spec(key).get("legend") or key
        labels = [label_for(key, value) for value in values]
        parts.append(f"{legend}：{' / '.join(labels)}")
    return parts
