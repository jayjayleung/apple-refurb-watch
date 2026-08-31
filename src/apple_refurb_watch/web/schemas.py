from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WatchIn(BaseModel):
    name: str = "未命名规则"
    enabled: bool = True
    mode: str = "condition"
    sku: str | None = None
    listing_key: str | None = None
    all_of: list[str] | str | None = None
    none_of: list[str] | str | None = None
    colors: list[str] | str | None = None
    min_ram_gb: int | None = None
    min_storage_gb: int | None = None
    min_price: float | None = None
    max_price: float | None = None
    dim_filters: dict[str, list[str]] | None = None
    query: dict[str, Any] | None = None


class WatchPatch(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    mode: str | None = None
    sku: str | None = None
    listing_key: str | None = None
    all_of: list[str] | str | None = None
    none_of: list[str] | str | None = None
    colors: list[str] | str | None = None
    min_ram_gb: int | None = Field(default=None)
    min_storage_gb: int | None = Field(default=None)
    min_price: float | None = Field(default=None)
    max_price: float | None = Field(default=None)
    dim_filters: dict[str, list[str]] | None = None
    query: dict[str, Any] | None = None


class AutostartPatch(BaseModel):
    enabled: bool


class NotifyTestIn(BaseModel):
    channel: str | None = None


class SettingsPatch(BaseModel):
    interval_seconds: int | None = None
    bind_host: str | None = None
    bind_port: int | None = None
    lan_enabled: bool | None = None
    access_token: str | None = None
    listings: list[str] | None = None
    detail_delay_seconds: float | None = None
    close_window_keeps_daemon: bool | None = None
    listen_enabled: bool | None = None
    notify: dict[str, Any] | None = None
