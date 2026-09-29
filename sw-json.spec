# -*- mode: python ; coding: utf-8 -*-
"""免安装目录：python -m PyInstaller sw-json.spec"""

a = Analysis(
    ["launch_web.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("web/static", "web/static"),
        (".cache", ".cache"),
    ],
    hiddenimports=["web.server", "sw_runes", "sw_units", "constants"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sw-json",
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="sw-json",
)
