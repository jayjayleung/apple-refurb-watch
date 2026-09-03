from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from apple_refurb_watch.categories import BASE, LISTING_MODELS, host_ok

__all__ = [
    "ParseError",
    "Product",
    "color_from_title",
    "extract_bootstrap",
    "host_ok",
    "normalize_sku",
    "parse_detail_specs",
    "parse_listing_html",
    "parse_size_gb",
    "product_page_url",
    "sku_from_url",
    "first_srcset_url",
]

SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(tb|gb|t|g)\s*$", re.I)
RAM_DETAIL_RE = re.compile(r"(\d+)\s*GB\s*统一内存", re.I)
SSD_TB_RE = re.compile(r"(\d+(?:\.\d+)?)\s*TB\s*固态硬盘", re.I)
SSD_GB_RE = re.compile(r"(\d+)\s*GB\s*固态硬盘", re.I)
SKU_RE = re.compile(r"/shop/product/([a-z0-9]+)(?:/([ab]))?", re.I)


class ParseError(RuntimeError):
    pass


@dataclass
class Product:
    sku: str
    title: str
    url: str
    price: float | None
    listing_key: str
    ram_gb: int | None = None
    storage_gb: int | None = None
    color_key: str | None = None
    color_label: str | None = None
    model_key: str | None = None
    year: str | None = None
    screensize: str | None = None
    image_url: str | None = None
    extra: dict = field(default_factory=dict)


def parse_size_gb(value: str | None) -> int | None:
    if not value:
        return None
    text = str(value).strip().lower().replace(" ", "").replace("\xa0", "")
    text = text.replace("point", ".").replace("_", ".")
    match = SIZE_RE.match(text)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("t"):
        return int(amount * 1024)
    return int(amount)


def normalize_sku(sku: str | None) -> str:
    if not sku:
        return ""
    text = sku.strip().upper().replace(" ", "")
    if re.fullmatch(r"[A-Z0-9]+/[AB]", text):
        return text
    if re.fullmatch(r"[A-Z0-9]+", text):
        return text if text.endswith("A") else f"{text}/A"
    return text


def sku_from_url(url: str) -> str:
    match = SKU_RE.search(url or "")
    if not match:
        return ""
    part = match.group(1)
    suffix = match.group(2)
    return normalize_sku(f"{part}/{suffix}" if suffix else part)


def product_page_url(sku: str | None = None, raw: str | None = None) -> str:
    """Canonical Apple product URL that browsers can open.

    Official grid links carry a short-lived ``fnode`` query. The stable product
    path is the lowercase SKU without that token.
    """

    code = normalize_sku(sku) or sku_from_url(raw or "")
    if code:
        return f"{BASE}/shop/product/{code.lower()}"
    text = str(raw or "").strip()
    if not text:
        return ""
    parsed = urlparse(urljoin(f"{BASE}/", text.split("?", 1)[0]))
    if parsed.scheme in {"http", "https"} and host_ok(parsed.geturl()):
        path = parsed.path or "/"
        return urljoin(f"{BASE}/", path.lstrip("/"))
    return ""


def color_from_title(title: str) -> str | None:
    if not title:
        return None
    if "；" in title:
        return title.split("；")[-1].strip() or None
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip() or None
    if title.endswith("色") or "表带" in title:
        return title.split("；")[-1].strip()
    return None


def extract_bootstrap(html: str) -> dict | None:
    marker = "window.REFURB_GRID_BOOTSTRAP"
    index = html.find(marker)
    if index < 0:
        return None
    brace = html.find("{", index)
    if brace < 0:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(html[brace:])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def parse_listing_html(html: str, listing_key: str, listing_url: str) -> list[Product]:
    bootstrap = extract_bootstrap(html)
    if bootstrap:
        tiles = bootstrap.get("tiles") or []
        products = [_tile_to_product(tile, listing_key, listing_url) for tile in tiles]
        products = [item for item in products if item]
        implied = LISTING_MODELS.get(listing_key)
        if implied:
            products = [item for item in products if item.model_key == implied]
        return products
    products = _parse_listing_dom(html, listing_key, listing_url)
    if products:
        return products
    raise ParseError("页面结构未识别")


def _tile_to_product(tile: dict, listing_key: str, listing_url: str) -> Product | None:
    sku = normalize_sku(tile.get("partNumber") or "")
    title = (tile.get("title") or "").strip()
    rel = tile.get("productDetailsUrl") or ""
    if not sku and rel:
        sku = sku_from_url(rel)
    if not sku or not title:
        return None
    url = product_page_url(sku, rel)
    price_info = (tile.get("price") or {}).get("currentPrice") or {}
    raw_amount = price_info.get("raw_amount")
    price = None
    if raw_amount not in (None, ""):
        try:
            price = float(str(raw_amount).replace(",", ""))
        except ValueError:
            price = None
    dims = ((tile.get("filters") or {}).get("dimensions")) or {}
    image = tile.get("image") or {}
    src = None
    sources = image.get("sources") or []
    if sources:
        src = first_srcset_url(sources[0].get("srcSet"))
    return Product(
        sku=sku,
        title=title,
        url=url,
        price=price,
        listing_key=listing_key,
        ram_gb=parse_size_gb(dims.get("tsMemorySize")),
        storage_gb=parse_size_gb(dims.get("dimensionCapacity")),
        color_key=dims.get("dimensionColor") or dims.get("dimensionCaseMaterial"),
        color_label=color_from_title(title),
        model_key=dims.get("refurbClearModel"),
        year=dims.get("dimensionRelYear"),
        screensize=dims.get("dimensionScreensize") or dims.get("dimensionCaseSize"),
        image_url=src,
        extra={"listing_url": listing_url, "dims": dims},
    )


def _parse_listing_dom(html: str, listing_key: str, listing_url: str) -> list[Product]:
    soup = BeautifulSoup(html, "html.parser")
    products: list[Product] = []
    seen: set[str] = set()
    for tile in soup.select(".as-producttile, li.as-producttile"):
        link = tile.select_one("a[href*='/shop/product/']")
        title_el = tile.select_one(".as-producttile-title, h3, h2")
        price_el = tile.select_one(".as-price-currentprice, .as-producttile-currentprice")
        href = link.get("href") if link else ""
        sku = sku_from_url(str(href))
        title = title_el.get_text(" ", strip=True) if title_el else ""
        if not sku or not title or sku in seen:
            continue
        seen.add(sku)
        price = None
        if price_el:
            digits = re.sub(r"[^\d.]", "", price_el.get_text())
            if digits:
                try:
                    price = float(digits)
                except ValueError:
                    price = None
        products.append(
            Product(
                sku=sku,
                title=title,
                url=product_page_url(sku, str(href)),
                price=price,
                listing_key=listing_key,
                color_label=color_from_title(title),
            )
        )
    return products


def parse_detail_specs(html: str) -> dict[str, int | None]:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    text = text.replace("\xa0", " ")
    ram = None
    storage = None
    ram_match = RAM_DETAIL_RE.search(text)
    if ram_match:
        ram = int(ram_match.group(1))
    tb_match = SSD_TB_RE.search(text)
    gb_match = SSD_GB_RE.search(text)
    if tb_match:
        storage = int(float(tb_match.group(1)) * 1024)
    elif gb_match:
        storage = int(gb_match.group(1))
    return {"ram_gb": ram, "storage_gb": storage}


def first_srcset_url(srcset: str | None) -> str | None:
    if not srcset:
        return None
    first = srcset.split(",")[0].strip()
    if not first:
        return None
    return first.split()[0].strip() or None
