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
        "深空灰色": "space_gray",
        "深空灰": "space_gray",
        "银色": "silver",
        "深空黑色": "spaceblack",
        "深空黑": "spaceblack",
        "星光色": "starlight",
        "午夜色": "midnight",
        "天蓝色": "skyblue",
        "蓝色": "blue",
        "靛蓝色": "indigo",
        "紫色": "purple",
        "粉色": "pink",
        "桃粉色": "pink",
        "黄色": "yellow",
        "柑橘黄色": "orange",
        "橙色": "orange",
        "黑色": "black",
        "金色": "gold",
        "原色": "natural",
        "绿色": "green",
        "白色": "white",
        "腮红色": "blush",
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
CORES_KEY = "cores"
CORE_LISTING_KEYS = frozenset({"mac", "macbook-pro", "macbook-air"})
CPU_CORE_RE = re.compile(r"(\d+)\s*核中央处理器")
GPU_CORE_RE = re.compile(r"(\d+)\s*核图形处理器")
CORES_PAIR_RE = re.compile(r"^(\d+)core_(\d+)core$", re.I)
DERIVED_KEYS = frozenset({CHIP_KEY, CORES_KEY, CPU_CORE_KEY, GPU_CORE_KEY})


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
CORES_SPEC = {
    "legend": "中央处理器 / 图形处理器",
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


def cores_token(cpu: str | None, gpu: str | None) -> str | None:
    cpu_token = _core_token(cpu) if cpu else None
    gpu_token = _core_token(gpu) if gpu else None
    if cpu_token and gpu_token:
        return f"{cpu_token}_{gpu_token}"
    return cpu_token or gpu_token


def split_cores_token(token: str | None) -> tuple[str | None, str | None]:
    mapped = _cores_token(token) if token else None
    if not mapped:
        return None, None
    pair = CORES_PAIR_RE.fullmatch(mapped)
    if pair:
        return f"{int(pair.group(1))}core", f"{int(pair.group(2))}core"
    return _core_token(mapped), None


def cores_label_from_token(token: str | None) -> str:
    cpu, gpu = split_cores_token(token)
    parts: list[str] = []
    if cpu:
        parts.append(f"{int(cpu[:-4])} 核")
    if gpu:
        parts.append(f"{int(gpu[:-4])} 核")
    if not parts:
        return str(token or "")
    return " / ".join(parts)


def core_label_from_token(key: str, token: str | None) -> str:
    mapped = _core_token(token) if token else None
    if not mapped:
        return format_dim_value(str(token or ""))
    count = int(mapped[:-4])
    if key == GPU_CORE_KEY:
        return f"{count} 核图形处理器"
    return f"{count} 核中央处理器"


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

_MAC = ["mac", "macbook-pro", "macbook-air"]
_MAC_IPAD = ["mac", "macbook-pro", "macbook-air", "ipad"]
SCREEN_VALUE_LISTINGS = {
    "8_3inch": ["ipad"],
    "10_2inch": ["ipad"],
    "10_9inch": ["ipad"],
    "11inch": ["ipad"],
    "12_9inch": ["ipad"],
    "13inch": list(_MAC_IPAD),
    "14inch": ["mac", "macbook-pro"],
    "15inch": ["mac", "macbook-air"],
    "16inch": ["mac", "macbook-pro"],
    "24inch": ["mac"],
    "27inch": ["mac"],
}
COLOR_VALUE_LISTINGS = {
    "silver": list(_MAC_IPAD),
    "space_gray": list(_MAC_IPAD),
    "starlight": list(_MAC_IPAD),
    "skyblue": list(_MAC_IPAD),
    "pink": list(_MAC_IPAD),
    "green": list(_MAC_IPAD),
    "blue": list(_MAC_IPAD),
    "purple": list(_MAC_IPAD),
    "gold": list(_MAC_IPAD),
    "spaceblack": list(_MAC),
    "midnight": list(_MAC) + ["homepod"],
    "white": ["homepod"],
    "yellow": list(_MAC),
    "orange": list(_MAC),
    "blush": list(_MAC),
    "citrus": list(_MAC),
    "indigo": list(_MAC),
    "rosegold": ["ipad"],
}
YEAR_VALUE_LISTINGS = {
    "2019": list(_MAC),
    "2020": list(_MAC_IPAD),
    "2021": list(_MAC_IPAD),
    "2022": list(_MAC_IPAD),
    "2023": list(_MAC_IPAD),
    "2024": list(_MAC_IPAD),
    "2025": list(_MAC_IPAD),
    "2026": list(_MAC),
}
CAPACITY_VALUE_LISTINGS = {
    "32gb": ["ipad"],
    "64gb": ["ipad"],
    "128gb": list(_MAC_IPAD),
    "256gb": list(_MAC_IPAD),
    "512gb": list(_MAC_IPAD),
    "1tb": list(_MAC_IPAD),
    "2tb": list(_MAC_IPAD),
    "1point5tb": list(_MAC),
    "1_5tb": list(_MAC),
    "3tb": list(_MAC),
    "4tb": list(_MAC),
    "8tb": list(_MAC),
}
BUILTIN_VALUE_LISTINGS = {
    "dimensionScreensize": SCREEN_VALUE_LISTINGS,
    "dimensionColor": COLOR_VALUE_LISTINGS,
    "dimensionRelYear": YEAR_VALUE_LISTINGS,
    "dimensionCapacity": CAPACITY_VALUE_LISTINGS,
    CHIP_KEY: CHIP_VALUE_LISTINGS,
}


def _listings_for_key(key: str, listing_dims: Mapping[str, Any]) -> list[str]:
    return [listing for listing, keys in listing_dims.items() if key in (keys or [])]


def _screen_token(value: str) -> str:
    return str(value).lower().replace("-", "_").replace(" ", "")


def _with_mac_parent(listings: list[str]) -> list[str]:
    out = list(dict.fromkeys(listings))
    if any(key in {"macbook-pro", "macbook-air"} for key in out) and "mac" not in out:
        out.append("mac")
    return out


def _model_listings(value: str) -> list[str]:
    low = value.lower()
    if low == "ipadaccessories":
        return ["ipad", "accessories"]
    if low.startswith("ipad"):
        return ["ipad"]
    if "watch" in low:
        return ["watch"]
    if low == "airpods":
        return ["airpods", "accessories"]
    if "airpod" in low:
        return ["airpods"]
    if low == "homepod":
        return ["homepod", "accessories"]
    if low == "display":
        return ["mac", "accessories"]
    if low == "macbookpro":
        return ["mac", "macbook-pro"]
    if low == "macbookair":
        return ["mac", "macbook-air"]
    return ["mac"]


def _lookup_value_listings(key: str, value: str) -> list[str] | None:
    table = BUILTIN_VALUE_LISTINGS.get(key)
    if not table:
        return None
    token = _screen_token(value) if key == "dimensionScreensize" else str(value).lower()
    mapped = table.get(token) or table.get(value)
    return list(mapped) if mapped else None


def _value_listings(key: str, value: str, spec: Mapping[str, Any]) -> list[str]:
    if key == "refurbClearModel":
        return _model_listings(value)
    if key == "heroAirPods":
        return ["airpods"]
    if key == "tsMemorySize":
        return list(_MAC)
    if key in {"dimensionCaseSize", "dimensionCaseMaterial", "dimensionConnection"}:
        return ["watch"]
    if key == "dimensionconnectivity":
        return ["ipad"]
    builtin = _lookup_value_listings(key, value)
    if builtin:
        return builtin
    custom = (spec.get("value_listings") or {}).get(value)
    if custom:
        return _with_mac_parent(list(custom))
    return _with_mac_parent(list(spec.get("listings") or []))


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
    if key == CORES_KEY:
        mapped = _cores_token(token)
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


def _cores_token(raw: str) -> str | None:
    text = str(raw).strip()
    if not text:
        return None
    folded = _fold_title(text)
    cpu = CPU_CORE_RE.search(folded)
    gpu = GPU_CORE_RE.search(folded)
    if cpu or gpu:
        return cores_token(
            f"{int(cpu.group(1))}core" if cpu else None,
            f"{int(gpu.group(1))}core" if gpu else None,
        )
    compact = folded.lower().replace(" ", "").replace("核", "")
    pair = re.fullmatch(r"(\d+)(?:core)?_(\d+)(?:core)?", compact)
    if pair:
        return f"{int(pair.group(1))}core_{int(pair.group(2))}core"
    return _core_token(text)


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
