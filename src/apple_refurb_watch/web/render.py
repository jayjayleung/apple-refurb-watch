from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from apple_refurb_watch import __version__
from apple_refurb_watch.argv import is_frozen
from apple_refurb_watch.categories import CATEGORIES, LISTING_GROUPS, SHOP_FAMILIES, shop_family_key
from apple_refurb_watch.db import Database
from apple_refurb_watch.filters import label_for, live_catalog_path, summarize_dims, user_catalog_path
from apple_refurb_watch.listing import format_cny, format_gb, thumb_url
from apple_refurb_watch.paths import package_root
from apple_refurb_watch.settings import (
    listing_family_checked,
    notify_channel_ready,
    notify_channel_status,
    public_settings,
    NOTIFY_CHANNEL_UI,
)
from apple_refurb_watch.status_view import format_localtime, load_status
from apple_refurb_watch.update_check import GITHUB_URL


def web_dir() -> Path:
    return package_root() / "web"


def asset_version() -> str:
    digest = hashlib.sha256()
    static = web_dir() / "static"
    for name in ("app.js", "style.css"):
        path = static / name
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def templates() -> Environment:
    folder = web_dir() / "templates"
    if not folder.is_dir():
        raise RuntimeError(f"安装包缺少网页模板: {folder}")
    env = Environment(
        loader=FileSystemLoader(str(folder)),
        autoescape=select_autoescape(["html"]),
        auto_reload=not is_frozen(),
    )
    env.globals["categories"] = CATEGORIES
    env.globals["listing_groups"] = LISTING_GROUPS
    env.globals["shop_families"] = SHOP_FAMILIES
    env.globals["shop_family_key"] = shop_family_key
    env.globals["listing_family_checked"] = listing_family_checked
    env.globals["notify_channel_ui"] = NOTIFY_CHANNEL_UI
    env.globals["notify_channel_status"] = notify_channel_status
    env.globals["notify_channel_ready"] = notify_channel_ready
    env.globals["dim_summary"] = summarize_dims
    env.globals["label_for"] = label_for
    env.filters["cny"] = format_cny
    env.filters["gb"] = format_gb
    env.filters["thumb"] = thumb_url
    env.filters["localtime"] = format_localtime
    env.globals["github_url"] = GITHUB_URL
    env.globals["app_version"] = __version__
    env.globals["asset_v"] = asset_version()
    return env


class PageRenderer:
    def __init__(self, db: Database, jinja: Environment) -> None:
        self.db = db
        self.jinja = jinja

    def __call__(self, name: str, request: Request, **ctx) -> HTMLResponse:
        settings = public_settings(self.db.settings())
        hx = bool(request.headers.get("HX-Request"))
        if hx:
            html_body = self.jinja.get_template(name).render(
                request=request,
                settings=settings,
                status={},
                status_view={},
                watch_count=0,
                user_catalog_path=str(user_catalog_path()),
                live_catalog_path=str(live_catalog_path()),
                **ctx,
            )
            return HTMLResponse(html_body)
        payload = load_status(self.db)
        html_body = self.jinja.get_template(name).render(
            request=request,
            settings=settings,
            status=payload,
            status_view=payload["view"],
            watch_count=payload["watch_count"],
            user_catalog_path=str(user_catalog_path()),
            live_catalog_path=str(live_catalog_path()),
            **ctx,
        )
        return HTMLResponse(html_body)
