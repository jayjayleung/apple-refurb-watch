"""Lazy adapters for optional desktop-only dependencies.

The server and CLI can be imported on headless machines.  This module keeps
``pywebview``/``pystray`` imports behind an explicit load boundary so a missing
GUI runtime is reported by the desktop command instead of breaking unrelated
commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any


@dataclass(frozen=True)
class DesktopModules:
    webview: Any | None = None
    pystray: Any | None = None
    image: Any | None = None
    errors: dict[str, str] | None = None

    @property
    def status(self) -> dict[str, str]:
        errors = self.errors or {}
        return {
            "webview": "ok" if self.webview is not None else errors.get("webview", "不可用"),
            "tray": "ok" if self.pystray is not None and self.image is not None else errors.get("tray", "不可用"),
        }


class DesktopAdapter:
    """Load and expose optional GUI modules only when desktop mode is used."""

    def __init__(self) -> None:
        self._modules: DesktopModules | None = None

    def load(self) -> DesktopModules:
        if self._modules is not None:
            return self._modules
        errors: dict[str, str] = {}
        webview = None
        pystray = None
        image = None
        try:
            webview = import_module("webview")
        except Exception as exc:  # noqa: BLE001
            errors["webview"] = str(exc)
        try:
            pystray = import_module("pystray")
            image_module = import_module("PIL.Image")
            image = image_module
        except Exception as exc:  # noqa: BLE001
            errors["tray"] = str(exc)
        self._modules = DesktopModules(webview, pystray, image, errors)
        return self._modules

    def status(self) -> dict[str, str]:
        return self.load().status

    def require_webview(self) -> Any:
        modules = self.load()
        if modules.webview is None:
            raise RuntimeError(f"请先安装桌面依赖：{modules.status['webview']}")
        return modules.webview

    def require_tray(self) -> tuple[Any, Any]:
        modules = self.load()
        if modules.pystray is None or modules.image is None:
            raise RuntimeError(f"托盘依赖缺失：{modules.status['tray']}")
        return modules.pystray, modules.image


__all__ = ["DesktopAdapter", "DesktopModules"]
