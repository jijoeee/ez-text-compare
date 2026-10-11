"""Paths, settings, logging and OS helpers."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler

from . import APP_NAME, BRAND

log = logging.getLogger("ezcompare")

def resource_path(*parts: str) -> str:
    """Locate bundled files both from source and inside the PyInstaller build."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)


def app_data_dir() -> str:
    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(root, BRAND, APP_NAME)
    else:
        path = os.path.join(os.path.expanduser("~"), ".config", "ezkerja", "ez-text-compare")
    os.makedirs(path, exist_ok=True)
    return path


def log_dir() -> str:
    path = os.path.join(app_data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def setup_logging() -> str:
    """Log to a rotating file. A windowed .exe has no console, so this is the only record."""
    path = os.path.join(log_dir(), "ez-text-compare.log")
    handler = RotatingFileHandler(path, maxBytes=512_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:  # None inside a windowed PyInstaller build
        root.addHandler(logging.StreamHandler())
    return path


class Settings:
    """Tiny JSON settings store in %APPDATA%\\EZKerja\\EZ Text Compare."""

    def __init__(self):
        self._path = os.path.join(app_data_dir(), "settings.json")
        self._data: dict = {}
        try:
            with open(self._path, encoding="utf-8") as f:
                self._data = json.load(f)
        except (OSError, ValueError):
            self._data = {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value) -> None:
        self._data[key] = value
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError:
            log.warning("Could not write settings to %s", self._path)


def open_path(path: str) -> None:
    """Open a file or folder with the default program."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError:
        log.exception("Could not open %s", path)


def reveal_in_folder(path: str) -> None:
    """Open the containing folder with the file highlighted (Explorer /select)."""
    if sys.platform == "win32" and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        open_path(path if os.path.isdir(path) else os.path.dirname(path))


def set_window_icon(window, ico_path: str) -> bool:
    """Set a window's icon crisply on Windows.

    Tk's iconbitmap() hands the whole .ico to Tk, which picks one entry and rescales
    it itself - that is what makes the taskbar icon look soft. Instead we ask Windows
    for the exact sizes it wants (small for the title bar, big for the taskbar and
    Alt+Tab) and let it choose the matching entry from the .ico. Returns True on
    success so callers can fall back.
    """
    if sys.platform != "win32" or not os.path.exists(ico_path):
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
        SM_CXICON, SM_CYICON, SM_CXSMICON, SM_CYSMICON = 11, 12, 49, 50

        window.update_idletasks()  # the frame window must exist before we can address it
        hwnd = int(window.wm_frame(), 16)
        sizes = {
            ICON_SMALL: (user32.GetSystemMetrics(SM_CXSMICON), user32.GetSystemMetrics(SM_CYSMICON)),
            ICON_BIG: (user32.GetSystemMetrics(SM_CXICON), user32.GetSystemMetrics(SM_CYICON)),
        }
        handles = []
        for which, (cx, cy) in sizes.items():
            handle = user32.LoadImageW(None, ico_path, IMAGE_ICON, cx, cy, LR_LOADFROMFILE)
            if not handle:
                return False
            user32.SendMessageW(hwnd, WM_SETICON, which, handle)
            handles.append(handle)
        # Keep the handles alive for the window's lifetime.
        window._icon_handles = handles
        return True
    except Exception:
        log.warning("Could not set the window icon through Windows; using Tk instead")
        return False


def set_windows_app_id(app_id: str) -> None:
    """Make Windows group the taskbar button under our own icon, not python.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass
