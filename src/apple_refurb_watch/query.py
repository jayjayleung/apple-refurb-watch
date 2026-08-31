from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from apple_refurb_watch.categories import listing_item_matches
from apple_refurb_watch.filters import dims_match, normalize_dim_filters
from apple_refurb_watch.parse import Product, normalize_sku
from apple_refurb_watch.textutil import norm_text


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace("\n", ",").split(",")]
        return [part for part in parts if part]
    return [str(item).strip() for item in value if str(item).strip()]


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _product_item(product: Product | dict) -> dict:
    if is_dataclass(product):
        return asdict(product)
    return dict(product)


@dataclass
class ProductQuery:
    """在售筛选与条件规则共用的查询形状。只增字段，不改名。"""

    listing_key: str | None = None
    dims: dict[str, list[str]] = field(default_factory=dict)
    q: str | None = None
    all_of: list[str] = field(default_factory=list)
    none_of: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    max_price: float | None = None
    min_price: float | None = None
    min_ram_gb: int | None = None
    min_storage_gb: int | None = None
    mode: str = "condition"
    sku: str | None = None

    @classmethod
    def from_watch(cls, watch: dict[str, Any] | None) -> ProductQuery:
        data = dict(watch or {})
        nested = data.get("query")
        if isinstance(nested, dict) and nested:
            base = cls.from_mapping(nested).to_dict()
            explicit = {key: value for key, value in data.items() if key != "query" and value is not None}
            if "dim_filters" in explicit and "dims" not in explicit:
                explicit["dims"] = explicit["dim_filters"]
            return cls.from_mapping({**base, **explicit})
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> ProductQuery:
        payload = dict(data or {})
        all_of = _as_list(payload.get("all_of"))
        q = str(payload.get("q") or "").strip() or None
        if q and q not in all_of:
            all_of = [*all_of, q]
        colors = _as_list(payload.get("colors"))
        color = str(payload.get("color") or "").strip()
        if color and color not in colors:
            colors = [*colors, color]
        dims = payload.get("dims") if payload.get("dims") not in (None, {}) else payload.get("dim_filters")
        return cls(
            listing_key=str(payload.get("listing_key") or "").strip() or None,
            dims=normalize_dim_filters(dims or {}),
            q=q,
            all_of=all_of,
            none_of=_as_list(payload.get("none_of")),
            colors=colors,
            max_price=_as_float(payload.get("max_price")),
            min_price=_as_float(payload.get("min_price")),
            min_ram_gb=_as_int(payload.get("min_ram_gb")),
            min_storage_gb=_as_int(payload.get("min_storage_gb")),
            mode=str(payload.get("mode") or "condition"),
            sku=(str(payload.get("sku") or "").strip().upper() or None),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_key": self.listing_key,
            "dims": dict(self.dims),
            "q": self.q,
            "all_of": list(self.all_of),
            "none_of": list(self.none_of),
            "colors": list(self.colors),
            "max_price": self.max_price,
            "min_price": self.min_price,
            "min_ram_gb": self.min_ram_gb,
            "min_storage_gb": self.min_storage_gb,
            "mode": self.mode,
            "sku": self.sku,
        }

    def to_watch_fields(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "sku": self.sku,
            "listing_key": self.listing_key,
            "all_of": list(self.all_of),
            "none_of": list(self.none_of),
            "colors": list(self.colors),
            "min_ram_gb": self.min_ram_gb,
            "min_storage_gb": self.min_storage_gb,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "dim_filters": dict(self.dims),
        }

    def matches(
        self,
        product: Product | dict,
        *,
        ignore_ram: bool = False,
        ignore_storage: bool = False,
    ) -> bool:
        from apple_refurb_watch.match import color_matches

        item = _product_item(product)
        if not listing_item_matches(self.listing_key, item):
            return False
        if (self.mode or "condition") == "sku":
            want = normalize_sku(self.sku or "")
            return bool(want) and normalize_sku(item.get("sku") or "") == want

        title_n = norm_text(item.get("title"))
        for token in self.all_of:
            if norm_text(token) not in title_n:
                return False
        for token in self.none_of:
            if norm_text(token) and norm_text(token) in title_n:
                return False
        if self.min_price is not None:
            if item.get("price") is None or float(item["price"]) < float(self.min_price):
                return False
        if self.max_price is not None:
            if item.get("price") is None or float(item["price"]) > float(self.max_price):
                return False
        if not ignore_ram and self.min_ram_gb is not None:
            ram = item.get("ram_gb")
            if ram is None or int(ram) < int(self.min_ram_gb):
                return False
        if not ignore_storage and self.min_storage_gb is not None:
            storage = item.get("storage_gb")
            if storage is None or int(storage) < int(self.min_storage_gb):
                return False
        if not color_matches(self.colors, item):
            return False
        if not dims_match(item, self.dims):
            return False
        return True
