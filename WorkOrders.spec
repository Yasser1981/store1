# -*- mode: python ; coding: utf-8 -*-
# ملف بناء البرنامج بأداة PyInstaller:   pyinstaller --noconfirm WorkOrders.spec
# الناتج: مجلد dist/WorkOrders وفيه WorkOrders.exe

import sys

sys.path.insert(0, SPECPATH)
from workorders import __version__  # noqa: E402

version_resource = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo)

    parts = tuple(int(x) for x in __version__.split(".")) + (0,)
    version_resource = VSVersionInfo(
        ffi=FixedFileInfo(filevers=parts, prodvers=parts),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "Karbala Electricity Distribution Branch"),
                StringStruct("FileDescription", "Work Orders Archive - Planning Edition"),
                StringStruct("FileVersion", __version__),
                StringStruct("InternalName", "WorkOrders"),
                StringStruct("OriginalFilename", "WorkOrders.exe"),
                StringStruct("ProductName", "Work Orders Archive"),
                StringStruct("ProductVersion", __version__),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

a = Analysis(
    ["run.py"],
    pathex=[SPECPATH],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc", "pytest", "numpy", "PIL", "lxml"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WorkOrders",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/app.ico",
    version=version_resource,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="WorkOrders",
)
