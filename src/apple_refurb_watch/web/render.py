from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from apple_refurb_watch.argv import is_frozen
from apple_refurb_watch.categories import CATEGORIES
from apple_refurb_watch.db import Database
from apple_refurb_watch.filters import label_for, live_catalog_path, summarize_dims, user_catalog_path
from apple_refurb_watch.status_view import format_localtime, present_status
from apple_refurb_watch.web.listing import thumb_url
from apple_refurb_watch.web.settings_public import public_settings

WEB_DIR = Path(__file__).resolve().parent


def templates() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(WEB_DIR / "templates")),
        autoescape=select_autoescape(["html"]),
        auto_reload=not is_frozen(),
    )
    env.globals["categories"] = CATEGORIES
    env.globals["dim_summary"] = summarize_dims
    env.globals["label_for"] = label_for
    env.filters["cny"] = lambda v: "" if v is None else f"{v:,.0f}"
    env.filters["gb"] = lambda v: "" if v is None else (f"{v // 1024}TB" if v >= 1024 and v % 1024 == 0 else f"{v}GB")
    env.filters["thumb"] = thumb_url
    env.filters["localtime"] = format_localtime
    return env


class PageRenderer:
    def __init__(self, db: Database, jinja: Environment) -> None:
        self.db = db
        self.jinja = jinja

    def __call__(self, name: str, request: Request, **ctx) -> HTMLResponse:
        settings = public_settings(self.db.settings())
        status = self.db.scan_status()
        watch_enabled = self.db.count_watches(enabled=True)
        watch_total = self.db.count_watches()
        status_view = present_status(
            status,
            settings,
            in_stock=self.db.count_products(in_stock=True),
            watch_enabled=watch_enabled,
            watch_total=watch_total,
        )
        html_body = self.jinja.get_template(name).render(
            request=request,
            settings=settings,
            status=status,
            status_view=status_view,
            watch_count=watch_enabled,
            user_catalog_path=str(user_catalog_path()),
            live_catalog_path=str(live_catalog_path()),
            **ctx,
        )
        return HTMLResponse(html_body)
