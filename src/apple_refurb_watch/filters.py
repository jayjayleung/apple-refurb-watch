from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

from apple_refurb_watch.categories import LISTING_MODELS as LISTING_IMPLIED_MODEL
from apple_refurb_watch.match import listing_matches, norm_text
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
CHIP_KEY = "chip"
CHIP_LISTING_KEYS = frozenset({"mac", "macbook-pro", "macbook-air", "ipad"})
CHIP_VALUES = {
    "m5_max": "M5 Max",
    "m5_pro": "M5 Pro",
    "m5": "M5",
    "m4_max": "M4 Max",
    "m4_pro": "M4 Pro",
    "m4": "M4",
    "m3_max": "M3 Max",
    "m3_pro": "M3 Pro",
    "m3": "M3",
    "m2_ultra": "M2 Ultra",
    "m2_max": "M2 Max",
    "m2_pro": "M2 Pro",
    "m2": "M2",
    "m1_ultra": "M1 Ultra",
    "m1_max": "M1 Max",
    "m1_pro": "M1 Pro",
    "m1": "M1",
    "a18_pro": "A18 Pro",
    "a17_pro": "A17 Pro",
    "a16": "A16",
    "a15": "A15",
}
CHIP_ORDER = list(CHIP_VALUES)
CHIP_VALUE_LISTINGS = {
    "m5_max": ["mac", "macbook-pro"],
    "m5_pro": ["mac", "macbook-pro"],
    "m5": ["mac", "macbook-pro", "macbook-air", "ipad"],
    "m4_max": ["mac", "macbook-pro"],
    "m4_pro": ["mac", "macbook-pro"],
    "m4": ["mac", "macbook-pro", "macbook-air", "ipad"],
    "m3_max": ["mac", "macbook-pro"],
    "m3_pro": ["mac", "macbook-pro"],
    "m3": ["mac", "macbook-air", "ipad"],
    "m2_ultra": ["mac"],
    "m2_max": ["mac"],
    "m2_pro": ["mac"],
    "m2": ["mac", "ipad"],
    "m1_ultra": ["mac"],
    "m1_max": ["mac"],
    "m1_pro": ["mac"],
    "m1": ["mac"],
    "a18_pro": ["mac"],
    "a17_pro": ["ipad"],
    "a16": ["ipad"],
    "a15": ["ipad"],
}
CHIP_SPEC = {
    "legend": "芯片",
    "listings": ["mac", "macbook-pro", "macbook-air", "ipad"],
    "order": CHIP_ORDER,
    "values": CHIP_VALUES,
    "value_listings": CHIP_VALUE_LISTINGS,
}
CHIP_FINDER = re.compile(r"(M\d+(?:\s+(?:Pro|Max|Ultra))?|A\d+(?:\s+Pro)?)", re.I)
CHIP_TOKEN_RE = re.compile(r"^(m\d+(?:_(?:pro|max|ultra))?|a\d+(?:_pro)?)$", re.I)
CASCADE_OOS_KEYS = frozenset({"tsMemorySize", "dimensionCapacity"})
CPU_CORE_KEY = "cpu_cores"
GPU_CORE_KEY = "gpu_cores"
CORE_LISTING_KEYS = frozenset({"mac", "macbook-pro", "macbook-air"})
CPU_CORE_RE = re.compile(r"(\d+)\s*核中央处理器")
GPU_CORE_RE = re.compile(r"(\d+)\s*核图形处理器")
DERIVED_KEYS = frozenset({CHIP_KEY, CPU_CORE_KEY, GPU_CORE_KEY})


CPU_CORE_SPEC = {
    "legend": "中央处理器",
    "listings": ["mac", "macbook-pro", "macbook-air"],
    "order": [],
    "values": {},
}
GPU_CORE_SPEC = {
    "legend": "图形处理器",
    "listings": ["mac", "macbook-pro", "macbook-air"],
    "order": [],
    "values": {},
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
        keys = list(listing_dims[listing_key])
    else:
        seen: list[str] = []
        for listing_keys in listing_dims.values():
            for key in listing_keys:
                if key not in seen:
                    seen.append(key)
        keys = seen or list((catalog.get("dimensions") or {}).keys())
    return _inject_derived_keys(keys, listing_key)


def _listing_has_chip(listing_key: str | None) -> bool:
    return listing_key is None or listing_key in CHIP_LISTING_KEYS


def _listing_has_cores(listing_key: str | None) -> bool:
    return listing_key is None or listing_key in CORE_LISTING_KEYS


def _inject_derived_keys(keys: list[str], listing_key: str | None) -> list[str]:
    out = list(keys)
    if _listing_has_chip(listing_key) and CHIP_KEY not in out:
        if "refurbClearModel" in out:
            out.insert(out.index("refurbClearModel") + 1, CHIP_KEY)
        else:
            out.insert(0, CHIP_KEY)
    if _listing_has_cores(listing_key):
        anchor = CHIP_KEY if CHIP_KEY in out else "refurbClearModel"
        pos = out.index(anchor) + 1 if anchor in out else 0
        for key in (CPU_CORE_KEY, GPU_CORE_KEY):
            if key not in out:
                out.insert(pos, key)
                pos += 1
    return out


def dim_spec(key: str) -> dict[str, Any]:
    if key == CHIP_KEY:
        return CHIP_SPEC
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
    return format_dim_value(value)


def chip_from_title(title: str | None) -> str | None:
    text = _fold_title(title)
    if not text:
        return None
    candidates: list[tuple[int, str]] = []
    for match in CHIP_FINDER.finditer(text):
        token = _chip_token(match.group(1))
        if not token:
            continue
        candidates.append((len(match.group(1).strip()), token))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def cores_from_title(title: str | None) -> tuple[str | None, str | None]:
    text = _fold_title(title)
    cpu = CPU_CORE_RE.search(text)
    gpu = GPU_CORE_RE.search(text)
    return (
        f"{int(cpu.group(1))}core" if cpu else None,
        f"{int(gpu.group(1))}core" if gpu else None,
    )


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
    core = re.fullmatch(r"(\d+)core", lower)
    if core:
        return f"{core.group(1)} 核"
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


MODEL_DIMS: dict[str, dict[str, list[str]]] = {
    "macbookpro": {
        "dimensionScreensize": ["14inch", "16inch"],
        "tsMemorySize": ["16gb", "18gb", "24gb", "32gb", "36gb", "48gb", "64gb", "96gb", "128gb", "192gb"],
        "dimensionCapacity": ["256gb", "512gb", "1tb", "2tb", "4tb", "8tb"],
        "dimensionColor": ["silver", "spaceblack", "space_gray"],
        "dimensionRelYear": ["2022", "2023", "2024", "2025", "2026"],
        "chip": ["m3_pro", "m3_max", "m4", "m4_pro", "m4_max", "m5", "m5_pro", "m5_max"],
    },
    "macbookair": {
        "dimensionScreensize": ["13inch", "15inch"],
        "tsMemorySize": ["16gb", "24gb", "32gb"],
        "dimensionCapacity": ["256gb", "512gb", "1tb", "2tb"],
        "dimensionColor": ["silver", "starlight", "midnight", "skyblue", "space_gray"],
        "dimensionRelYear": ["2024", "2025", "2026"],
        "chip": ["m2", "m3", "m4", "m5"],
    },
    "macbookneo": {
        "dimensionScreensize": ["13inch"],
        "tsMemorySize": ["16gb", "24gb"],
        "dimensionCapacity": ["256gb", "512gb", "1tb"],
        "dimensionColor": ["silver", "blush", "citrus", "indigo"],
        "dimensionRelYear": ["2026"],
        "chip": ["a18_pro"],
    },
    "imac": {
        "dimensionScreensize": ["24inch"],
        "tsMemorySize": ["8gb", "16gb", "24gb", "32gb"],
        "dimensionCapacity": ["256gb", "512gb", "1tb", "2tb"],
        "dimensionColor": ["silver", "blue", "green", "pink", "yellow", "orange", "purple"],
        "dimensionRelYear": ["2023", "2024", "2025"],
        "chip": ["m3", "m4"],
    },
    "macmini": {
        "tsMemorySize": ["8gb", "16gb", "24gb", "32gb"],
        "dimensionCapacity": ["256gb", "512gb", "1tb", "2tb", "4tb"],
        "dimensionColor": ["silver"],
        "dimensionRelYear": ["2023", "2024", "2025", "2026"],
        "chip": ["m2", "m2_pro", "m4", "m4_pro"],
    },
    "macstudio": {
        "tsMemorySize": ["32gb", "36gb", "48gb", "64gb", "96gb", "128gb", "192gb"],
        "dimensionCapacity": ["512gb", "1tb", "2tb", "4tb", "8tb"],
        "dimensionRelYear": ["2023", "2025"],
        "chip": ["m2_max", "m2_ultra", "m4_max"],
    },
    "macpro": {
        "tsMemorySize": ["96gb", "192gb", "768gb", "1_5tb"],
        "dimensionCapacity": ["1tb", "2tb", "4tb", "8tb"],
        "dimensionColor": ["silver"],
        "dimensionRelYear": ["2019", "2023"],
        "chip": ["m2_ultra"],
    },
    "display": {
        "dimensionScreensize": ["27inch"],
        "dimensionRelYear": ["2022", "2024", "2026"],
    },
    "ipad2017": {
        "dimensionScreensize": ["10_9inch"],
        "dimensionCapacity": ["64gb", "128gb", "256gb", "512gb"],
        "dimensionColor": ["blue", "pink", "silver", "yellow"],
        "dimensionconnectivity": ["wifi", "wificell"],
        "dimensionRelYear": ["2022", "2025"],
        "chip": ["a16"],
    },
    "ipadair_10_9": {
        "dimensionScreensize": ["10_9inch"],
        "dimensionCapacity": ["64gb", "128gb", "256gb"],
        "dimensionconnectivity": ["wifi", "wificell"],
        "chip": ["m1", "m2"],
    },
    "ipadair_11": {
        "dimensionScreensize": ["11inch"],
        "dimensionCapacity": ["128gb", "256gb", "512gb", "1tb"],
        "dimensionColor": ["blue", "purple", "space_gray", "starlight"],
        "dimensionconnectivity": ["wifi", "wificell"],
        "dimensionRelYear": ["2025"],
        "chip": ["m2", "m3"],
    },
    "ipadair_13": {
        "dimensionScreensize": ["13inch"],
        "dimensionCapacity": ["128gb", "256gb", "512gb", "1tb"],
        "dimensionColor": ["blue", "purple", "space_gray", "starlight"],
        "dimensionconnectivity": ["wifi", "wificell"],
        "dimensionRelYear": ["2024", "2025"],
        "chip": ["m2", "m3"],
    },
    "ipadpro_11": {
        "dimensionScreensize": ["11inch"],
        "dimensionCapacity": ["128gb", "256gb", "512gb", "1tb", "2tb"],
        "dimensionColor": ["silver", "space_gray"],
        "dimensionconnectivity": ["wifi", "wificell"],
        "dimensionRelYear": ["2022", "2024"],
        "chip": ["m2", "m4"],
    },
    "ipadpro_12_9": {
        "dimensionScreensize": ["12_9inch"],
        "dimensionCapacity": ["128gb", "256gb", "512gb", "1tb", "2tb"],
        "dimensionColor": ["silver", "space_gray"],
        "dimensionconnectivity": ["wifi", "wificell"],
        "dimensionRelYear": ["2022"],
        "chip": ["m2"],
    },
    "ipadpro_13": {
        "dimensionScreensize": ["13inch"],
        "dimensionCapacity": ["256gb", "512gb", "1tb", "2tb"],
        "dimensionColor": ["silver", "space_gray"],
        "dimensionconnectivity": ["wifi", "wificell"],
        "dimensionRelYear": ["2024"],
        "chip": ["m4"],
    },
    "ipadmini6": {
        "dimensionScreensize": ["8_3inch"],
        "dimensionCapacity": ["64gb", "256gb"],
        "dimensionColor": ["purple", "space_gray", "starlight", "pink"],
        "dimensionconnectivity": ["wifi", "wificell"],
        "dimensionRelYear": ["2021"],
        "chip": ["a15"],
    },
    "watchseries9": {
        "dimensionCaseSize": ["41mm", "45mm"],
        "dimensionCaseMaterial": ["aluminum", "stainless"],
        "dimensionConnection": ["gps", "gpscell"],
    },
    "watchseries10": {
        "dimensionCaseSize": ["42mm", "46mm"],
        "dimensionCaseMaterial": ["aluminum", "titanium"],
        "dimensionConnection": ["gps", "gpscell"],
    },
    "watchseries11": {
        "dimensionCaseSize": ["42mm", "46mm"],
        "dimensionCaseMaterial": ["aluminum", "titanium"],
        "dimensionConnection": ["gps", "gpscell"],
    },
    "watchse2": {
        "dimensionCaseSize": ["40mm", "44mm"],
        "dimensionCaseMaterial": ["aluminum"],
        "dimensionConnection": ["gps", "gpscell"],
    },
    "watchse3": {
        "dimensionCaseSize": ["40mm", "44mm"],
        "dimensionCaseMaterial": ["aluminum"],
        "dimensionConnection": ["gps", "gpscell"],
    },
    "watchultra2": {
        "dimensionCaseSize": ["49mm"],
        "dimensionCaseMaterial": ["titanium"],
        "dimensionConnection": ["gpscell"],
    },
    "watchultra3": {
        "dimensionCaseSize": ["49mm"],
        "dimensionCaseMaterial": ["titanium"],
        "dimensionConnection": ["gpscell"],
    },
}


def cascade_models(listing_key: str | None, selected: Mapping[str, Any] | None) -> list[str]:
    selected_map = normalize_dim_filters(selected)
    models = list(selected_map.get("refurbClearModel") or [])
    if models:
        return models
    implied = LISTING_IMPLIED_MODEL.get(listing_key or "")
    return [implied] if implied else []


def cascade_allowed_values(
    key: str,
    models: list[str],
    chips: list[str],
    products: list[Mapping[str, Any]] | None,
) -> set[str] | None:
    if key == "refurbClearModel":
        return None
    if not models and not chips:
        return None
    if key == CHIP_KEY:
        if not models:
            return None
        allowed: set[str] = set()
        for model in models:
            allowed.update(MODEL_DIMS.get(model, {}).get(CHIP_KEY) or [])
        for item in products or []:
            dims = product_dims(item)
            if dims.get("refurbClearModel") in models and dims.get(CHIP_KEY):
                allowed.add(dims[CHIP_KEY])
        return allowed
    allowed = set()
    for item in products or []:
        dims = product_dims(item)
        if models and dims.get("refurbClearModel") not in models:
            continue
        if chips and dims.get(CHIP_KEY) not in chips:
            continue
        if dims.get(key):
            allowed.add(dims[key])
    if models:
        for model in models:
            extras = MODEL_DIMS.get(model, {}).get(key) or []
            if chips and key not in CASCADE_OOS_KEYS:
                continue
            allowed.update(extras)
    return allowed


def model_allowed_values(
    key: str,
    models: list[str],
    products: list[Mapping[str, Any]] | None,
) -> set[str] | None:
    return cascade_allowed_values(key, models, [], products)


def prune_cascade_dims(
    listing_key: str | None,
    selected: Mapping[str, Any] | None,
    products: list[Mapping[str, Any]] | None = None,
) -> dict[str, list[str]]:
    clean = restrict_dims(selected, listing_key)
    models = cascade_models(listing_key, clean)
    chips = list(clean.get(CHIP_KEY) or [])
    if not models and not chips:
        return clean
    pruned: dict[str, list[str]] = {}
    for key, values in clean.items():
        allow = cascade_allowed_values(key, models, chips, products)
        if allow is None:
            pruned[key] = values
            continue
        kept = [value for value in values if value in allow]
        if kept:
            pruned[key] = kept
    return pruned


def facet_groups(
    products: list[Mapping[str, Any]] | None,
    listing_key: str | None,
    selected: Mapping[str, Any] | None = None,
    *,
    include_catalog: bool = False,
    show_counts: bool = True,
    cascade: bool = False,
    refine: bool = False,
) -> list[dict[str, Any]]:
    catalog = load_catalog()
    listing_dims = catalog.get("listing_dimensions") or {}
    listing_legends = (catalog.get("listing_legends") or {}).get(listing_key or "") or {}
    keys = dimension_keys_for(listing_key)
    selected_map = normalize_dim_filters(selected)
    scoped = list(products or [])
    if listing_key:
        scoped = [item for item in scoped if listing_matches({"listing_key": listing_key}, item)]
    models = cascade_models(listing_key, selected_map) if cascade else []
    chips = list(selected_map.get(CHIP_KEY) or []) if cascade else []
    implied_model = LISTING_IMPLIED_MODEL.get(listing_key or "") if cascade else None
    auto_model = bool(implied_model and not (selected_map.get("refurbClearModel") or []))
    model_items = scoped
    if models:
        model_items = [item for item in scoped if product_dims(item).get("refurbClearModel") in models]
    count_items = model_items
    if chips:
        count_items = [item for item in model_items if product_dims(item).get(CHIP_KEY) in chips]
    listing_counts: dict[str, dict[str, int]] = {}
    for item in scoped:
        for key, value in product_dims(item).items():
            listing_counts.setdefault(key, {})
            listing_counts[key][value] = listing_counts[key].get(value, 0) + 1
    model_counts: dict[str, dict[str, int]] = {}
    for item in model_items:
        for key, value in product_dims(item).items():
            model_counts.setdefault(key, {})
            model_counts[key][value] = model_counts[key].get(value, 0) + 1
    live_counts: dict[str, dict[str, int]] = {}
    for item in count_items:
        for key, value in product_dims(item).items():
            live_counts.setdefault(key, {})
            live_counts[key][value] = live_counts[key].get(value, 0) + 1

    refine_counts: dict[str, dict[str, int]] = {}
    if refine:
        for key in keys:
            others = {name: values for name, values in selected_map.items() if name != key}
            bucket: dict[str, int] = {}
            for item in scoped:
                if not dims_match(item, others):
                    continue
                value = product_dims(item).get(key)
                if value:
                    bucket[value] = bucket.get(value, 0) + 1
            refine_counts[key] = bucket

    def counts_for(key: str) -> dict[str, int]:
        if refine:
            return refine_counts.get(key) or {}
        if key == "refurbClearModel":
            return listing_counts.get(key) or {}
        if key == CHIP_KEY:
            return (model_counts if models else listing_counts).get(key) or {}
        return live_counts.get(key) or {}

    groups: list[dict[str, Any]] = []
    for key in keys:
        spec = dim_spec(key)
        allow = None
        if cascade and (models or chips):
            allow = cascade_allowed_values(key, models, chips, scoped)
        dim_counts = counts_for(key)
        values: list[str] = []
        if include_catalog:
            values.extend(list(spec.get("order") or spec.get("values", {}).keys()))
            for extra in (spec.get("values") or {}).keys():
                if extra not in values:
                    values.append(extra)
        for live in dim_counts.keys():
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
                if dim_counts.get(value) or value in (selected_map.get(key) or [])
            ]
        if not values:
            continue
        options = []
        for value in values:
            listings = _value_listings(key, value, spec)
            count = dim_counts.get(value, 0)
            if listing_key and listing_key not in listings:
                live_here = key in DERIVED_KEYS and bool(dim_counts.get(value))
                if value not in (selected_map.get(key) or []) and not live_here:
                    continue
            if allow is not None and value not in allow and value not in (selected_map.get(key) or []):
                continue
            options.append(
                {
                    "value": value,
                    "label": label_for(key, value),
                    "count": count if show_counts else None,
                    "checked": value in (selected_map.get(key) or [])
                    or (key == "refurbClearModel" and auto_model and value == implied_model),
                    "listings": listings,
                }
            )
        if not options:
            continue
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


def summarize_dims(dim_filters: Mapping[str, Any] | None) -> list[str]:
    parts: list[str] = []
    for key, values in normalize_dim_filters(dim_filters).items():
        legend = dim_spec(key).get("legend") or key
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
        if spec.get("value_listings"):
            merged_values = current.setdefault("value_listings", {})
            for val, lists in spec["value_listings"].items():
                merged_values[val] = list(dict.fromkeys([*(merged_values.get(val) or []), *(lists or [])]))
    return out


SCREEN_VALUE_LISTINGS = {
    "8_3inch": ["ipad"],
    "10_2inch": ["ipad"],
    "10_9inch": ["ipad"],
    "11inch": ["ipad"],
    "12_9inch": ["ipad"],
    "13inch": ["mac", "macbook-pro", "macbook-air", "ipad"],
    "14inch": ["mac", "macbook-pro"],
    "15inch": ["mac", "macbook-air"],
    "16inch": ["mac", "macbook-pro"],
    "24inch": ["mac"],
    "27inch": ["mac"],
}


def _listings_for_key(key: str, listing_dims: Mapping[str, Any]) -> list[str]:
    return [listing for listing, keys in listing_dims.items() if key in (keys or [])]


def _screen_token(value: str) -> str:
    return str(value).lower().replace("-", "_").replace(" ", "")


def _value_listings(key: str, value: str, spec: Mapping[str, Any]) -> list[str]:
    custom = (spec.get("value_listings") or {}).get(value)
    if custom:
        return list(custom)
    if key == "dimensionScreensize":
        mapped = SCREEN_VALUE_LISTINGS.get(_screen_token(value))
        if mapped:
            return list(mapped)
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
    return ["mac"]


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
    if key == CHIP_KEY:
        mapped = _chip_token(token)
        if mapped:
            return mapped
    if key in {CPU_CORE_KEY, GPU_CORE_KEY}:
        mapped = _core_token(token)
        if mapped:
            return mapped
    table = VALUE_NORMALIZE.get(key) or {}
    return table.get(token) or table.get(token.lower()) or token


def _fold_title(title: str | None) -> str:
    return (
        str(title or "")
        .replace("\u200d", "")
        .replace("\u200b", "")
        .replace("\xa0", " ")
    )


def _core_token(raw: str) -> str | None:
    text = str(raw).strip().lower().replace(" ", "").replace("核", "")
    if text.endswith("core"):
        text = text[:-4]
    if text.isdigit():
        return f"{int(text)}core"
    return None


def _chip_token(raw: str) -> str | None:
    text = str(raw).strip()
    if not text:
        return None
    if text in CHIP_VALUES:
        return text
    low = text.lower().replace(" ", "_").replace("-", "_")
    if low in CHIP_VALUES:
        return low
    for token, label in CHIP_VALUES.items():
        if text == label or text.lower() == label.lower():
            return token
    if CHIP_TOKEN_RE.match(low):
        return low
    label = _normalize_chip_label(text)
    if not label:
        return None
    token = label.lower().replace(" ", "_")
    if CHIP_TOKEN_RE.match(token):
        return token
    return None


def _normalize_chip_label(raw: str) -> str:
    text = re.sub(r"\s+", " ", str(raw).strip())
    if not text:
        return ""
    parts = text.split()
    head = parts[0].upper()
    rest = [part[:1].upper() + part[1:].lower() for part in parts[1:] if part]
    return " ".join([head, *rest]).strip()


def _chip_label_from_token(token: str) -> str:
    parts = str(token).replace("-", "_").split("_")
    if not parts:
        return str(token)
    head = parts[0]
    if head:
        head = head[0].upper() + head[1:]
    rest = [part.capitalize() for part in parts[1:] if part]
    return " ".join([head, *rest])


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
