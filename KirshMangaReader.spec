# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


# Spec-файл фиксирует параметры PyInstaller, чтобы EXE собирался одинаково без длинной команды из README.
hiddenimports = (
    collect_submodules("selenium")
    + collect_submodules("webdriver_manager")
    + ["themes"]
)

a = Analysis(
    ["mr.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("UnRAR.exe", "."),
        ("icon.ico", "."),
        ("theme_backgrounds", "theme_backgrounds"),
    ],
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
    name="KirshMangaReader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",
)
