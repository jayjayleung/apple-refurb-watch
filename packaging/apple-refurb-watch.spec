# -*- mode: python ; coding: utf-8 -*-
# 请在仓库根目录执行:
#   python -m PyInstaller packaging/apple-refurb-watch.spec

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

spec_dir = Path(SPEC).resolve().parent
repo_root = spec_dir.parent
pkg = repo_root / "src" / "apple_refurb_watch"
datas, binaries, hiddenimports = collect_all("apple_refurb_watch")

datas += [
    (str(pkg / "web" / "templates"), "apple_refurb_watch/web/templates"),
    (str(pkg / "web" / "static"), "apple_refurb_watch/web/static"),
    (str(pkg / "data"), "apple_refurb_watch/data"),
]

try:
    tz_datas, tz_bins, tz_hidden = collect_all("tzdata")
    datas += tz_datas
    binaries += tz_bins
    hiddenimports += tz_hidden
except Exception:
    pass
try:
    import tzdata

    tz_dir = Path(tzdata.__file__).resolve().parent
    zoneinfo = tz_dir / "zoneinfo"
    if zoneinfo.is_dir():
        datas.append((str(zoneinfo), "tzdata/zoneinfo"))
except Exception:
    pass

try:
    w_datas, w_bins, w_hidden = collect_all("webview")
    datas += w_datas
    binaries += w_bins
    hiddenimports += w_hidden
except Exception:
    pass

hiddenimports += [
    "tzdata",
    "uvicorn.logging",
    "uvicorn.lifespan.on",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "apscheduler.schedulers.background",
    "bottle",
    "proxy_tools",
]
if sys.platform == "win32":
    hiddenimports += [
        "clr",
        "clr_loader",
        "pythonnet",
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
    ]
elif sys.platform == "darwin":
    hiddenimports += [
        "webview.platforms.cocoa",
    ]

a = Analysis(
    [str(repo_root / "src" / "apple_refurb_watch" / "__main__.py")],
    pathex=[str(repo_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="apple-refurb-watch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
