# -*- mode: python ; coding: utf-8 -*-
# 请在 Windows / macOS / Linux 上分别执行:
#   pyinstaller packaging/apple-refurb-watch.spec

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("apple_refurb_watch")

a = Analysis(
    ["src/apple_refurb_watch/__main__.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["uvicorn.logging", "uvicorn.protocols.http.auto"],
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
    upx=True,
    console=True,
)
