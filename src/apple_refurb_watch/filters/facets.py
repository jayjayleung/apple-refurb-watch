from __future__ import annotations

from typing import Any, Mapping

from apple_refurb_watch.categories import LISTING_MODELS as LISTING_IMPLIED_MODEL
from apple_refurb_watch.match import listing_matches

from .catalog import dimension_keys_for, dim_spec, label_for, load_catalog
from .dims import dims_match, normalize_dim_filters, product_dims, restrict_dims
from .model_dims import MODEL_DIMS
from .tokens import (
    CASCADE_OOS_KEYS,
    CHIP_KEY,
    DERIVED_KEYS,
    _listings_for_key,
    _sort_values,
    _value_listings,
)

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
