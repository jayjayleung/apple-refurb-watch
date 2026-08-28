# -*- mode: python ; coding: utf-8 -*-
# 请在仓库根目录执行:
#   python -m PyInstaller packaging/apple-refurb-watch.spec

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

spec_dir = Path(SPEC).resolve().parent
repo_root = spec_dir.parent
datas, binaries, hiddenimports = collect_all("apple_refurb_watch")

a = Analysis(
    [str(repo_root / "src" / "apple_refurb_watch" / "__main__.py")],
    pathex=[str(repo_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports
    + [
        "uvicorn.logging",
        "uvicorn.lifespan.on",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "apscheduler.schedulers.background",
    ],
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
