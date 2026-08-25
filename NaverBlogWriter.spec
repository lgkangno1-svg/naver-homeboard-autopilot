# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files

playwright_datas, playwright_binaries, playwright_hidden = collect_all("playwright")
tz_datas = collect_data_files("tzdata")


a = Analysis(
    ["app_gui.py"],
    pathex=[],
    binaries=playwright_binaries,
    datas=playwright_datas + tz_datas + [("config.json", ".")],
    hiddenimports=playwright_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NaverBlogWriter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NaverBlogWriter",
)
