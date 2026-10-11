# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build spec for EZ Text Compare.
# Don't run this directly. Use:  python build.py   (or double-click build.bat)

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files

sys.path.insert(0, SPECPATH)
from ezcompare import APP_NAME  # noqa: E402

datas = [
    ("assets", "assets"),
    ("THIRD_PARTY_NOTICES.md", "."),
    ("LICENSE", "."),
]
binaries = []
# Pillow's Tk bridge is imported dynamically; without it every image crashes the frozen app.
hiddenimports = ["PIL._tkinter_finder", "PIL.ImageTk"]

# CustomTkinter ships theme JSON files PyInstaller doesn't find on its own.
datas += collect_data_files("customtkinter")

# tkinterdnd2 ships the native tkdnd library: collect all of it so nothing is missed.
# openpyxl is pure Python; PyInstaller's own hook finds it.
for pkg in ("tkinterdnd2",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h


def _keep(entry):
    """Drop other operating systems' binaries from the build.

    tkinterdnd2 ships tkdnd for 12 platforms (Windows, macOS, Linux, x86/x64/arm).
    Shipping Linux .so and macOS .dylib files inside a Windows app is pointless
    weight AND a real antivirus false-positive trigger: scanners flag a Windows
    executable that carries foreign binaries as suspicious. Keep only this
    platform's folder.
    """
    dest = entry[0].replace("\\", "/").split("/")
    if "tkdnd" not in dest:
        return True
    i = dest.index("tkdnd")
    if i + 1 >= len(dest):
        return True
    plat = dest[i + 1]
    if sys.platform == "win32":
        return plat in ("win-x64", "win-x64-tcl9")   # 64-bit Windows, Tcl 8 and 9
    if sys.platform == "darwin":
        return plat.startswith("osx-")
    return plat.startswith("linux-")


datas = [d for d in datas if _keep(d)]
binaries = [b for b in binaries if _keep(b)]

# Import libraries (.lib) are only needed when compiling, never at runtime.
datas = [d for d in datas if not d[0].lower().endswith(".lib")]

a = Analysis(
    ["main.py"],
    pathex=[SPECPATH],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=[
        # Not used at runtime; keeping them out makes the app smaller and faster to start.
        "numpy", "cv2", "matplotlib", "scipy", "pandas", "IPython", "pytest", "cairosvg",
        "PyQt5", "PyQt6", "PySide2", "PySide6", "unittest", "pydoc_data",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

version_file = os.path.join(SPECPATH, "build", "version_info.txt")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # onedir: fast start-up, fewer antivirus false positives
    name=APP_NAME,
    console=False,                  # no black console window
    icon=os.path.join(SPECPATH, "assets", "app.ico"),
    version=version_file if sys.platform == "win32" and os.path.exists(version_file) else None,
    upx=False,                      # UPX-packed files are flagged by antivirus far more often
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    upx=False,
    name=APP_NAME,
)
