from __future__ import annotations

import re
from typing import Any, Mapping

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
