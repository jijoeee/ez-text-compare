"""Design tokens for EZ Text Compare.

Raspberry (hue 320) is the working colour; the logo's orange swoosh is reserved
for one place only. Every colour is a (light, dark) pair, so dark mode works
everywhere. Run  python check_palette.py ezcompare/theme.py  after any change.
"""

from __future__ import annotations

import sys
import tkinter.font as tkfont
from functools import lru_cache

import customtkinter as ctk
from PIL import Image

from .system import resource_path

# ---------------------------------------------------------------- colours
BG = ("#F7EEF4", "#1C1219")
SURFACE = ("#FFFFFF", "#281A23")
SURFACE_2 = ("#FBF6F9", "#301F2A")
BORDER = ("#ECDCE7", "#3F2A38")
TEXT = ("#301B29", "#F1E6ED")
TEXT_2 = ("#77586D", "#BCA3B4")
TEXT_3 = ("#A3879A", "#8A6F81")

PRIMARY = ("#993F7B", "#A3477F")
PRIMARY_HOVER = ("#843469", "#B2558E")
PRIMARY_TEXT = ("#993F7B", "#DA8DC0")   # links, active labels, selected borders
PRIMARY_SOFT = ("#F7E6F1", "#3A1E31")
PRIMARY_DISABLED = ("#D9B8CE", "#462A3D")
ON_PRIMARY = ("#FFFFFF", "#FFFFFF")

ACCENT = ("#F05A28", "#F26B3A")         # logo swoosh; used once, on purpose

DANGER = ("#C33737", "#E26E6E")
DANGER_HOVER = ("#B03535", "#EB7B7B")
DANGER_SOFT = ("#FBEAEA", "#3A2326")
DANGER_FILL = ("#C33737", "#B03535")    # the Stop button: white text needs a darker red in dark mode
DANGER_FILL_HOVER = ("#B03535", "#C33737")
SUCCESS = ("#297B4D", "#56B784")
SUCCESS_SOFT = ("#E8F5EE", "#1B3326")

HOVER = ("#F8F0F5", "#372431")

# The comparison itself. These are the one place red, green and amber mean something:
# a whole line gets the soft colour, the exact characters that differ get the strong one.
# Red = only in the left file, green = only in the right file, amber = changed, blue = moved.
REMOVED_LINE = ("#FBE8E8", "#3D2226")
REMOVED_CHAR = ("#F2B8B8", "#6E2F36")
ADDED_LINE = ("#E3F4E8", "#1C3526")
ADDED_CHAR = ("#AEDFBC", "#2C5C3D")
CHANGED_LINE = ("#FCF2D6", "#3A311C")
MOVED_LINE = ("#E3EDF9", "#1D2A3C")
FILLER = ("#F3EFF2", "#211720")         # the empty side of an added or removed line
GUTTER = SURFACE_2                      # line numbers
# A diff block you jumped to gets a coloured bar beside its line numbers.
CURRENT_MARK = PRIMARY

# ---------------------------------------------------------------- type
IS_WINDOWS = sys.platform == "win32"
_FAMILY = "Segoe UI" if IS_WINDOWS else "DejaVu Sans"
_FAMILY_SEMIBOLD = "Segoe UI Semibold" if IS_WINDOWS else "DejaVu Sans"
_FAMILY_MONO = "Consolas" if IS_WINDOWS else "DejaVu Sans Mono"

# Type scale (px): 22 display, 16 title, 13 body, 12 small, 11 caption
_font_cache: dict = {}


def font(size: int = 13, semibold: bool = False) -> ctk.CTkFont:
    key = (size, semibold)
    if key not in _font_cache:
        if semibold and IS_WINDOWS:
            _font_cache[key] = ctk.CTkFont(family=_FAMILY_SEMIBOLD, size=size)
        else:
            _font_cache[key] = ctk.CTkFont(family=_FAMILY, size=size,
                                           weight="bold" if semibold else "normal")
    return _font_cache[key]


_tk_font_cache: dict = {}


def tk_font(size: int, scale: float, semibold: bool = False, mono: bool = False) -> tkfont.Font:
    """A plain Tk font for widgets CustomTkinter doesn't scale (the two text panes).

    Negative sizes are pixels, so ``size`` matches the px type scale above.
    """
    px = max(8, round(size * scale))
    key = (px, semibold, mono)
    if key not in _tk_font_cache:
        if mono:
            family, weight = _FAMILY_MONO, "normal"
        elif semibold and IS_WINDOWS:
            family, weight = _FAMILY_SEMIBOLD, "normal"
        else:
            family, weight = _FAMILY, "bold" if semibold else "normal"
        _tk_font_cache[key] = tkfont.Font(family=family, size=-px, weight=weight)
    return _tk_font_cache[key]


def pick(token: tuple[str, str]) -> str:
    """The colour of a token for the current appearance mode (for plain Tk widgets)."""
    return token[1] if ctk.get_appearance_mode() == "Dark" else token[0]


# ---------------------------------------------------------------- spacing
SPACE_1, SPACE_2, SPACE_3, SPACE_4 = 4, 8, 16, 24
RADIUS_S, RADIUS_M, RADIUS_L = 6, 10, 16
SIDEBAR_W = 300
CONTENT_W = SIDEBAR_W - 2 * SPACE_4 - 16  # usable width inside the sidebar scroll area


# ---------------------------------------------------------------- icons
@lru_cache(maxsize=None)
def _mask(name: str) -> Image.Image:
    return Image.open(resource_path("assets", "icons", f"{name}.png")).convert("RGBA")


def _tint(name: str, hex_color: str) -> Image.Image:
    m = _mask(name)
    solid = Image.new("RGBA", m.size, hex_color)
    solid.putalpha(m.getchannel("A"))
    return solid


@lru_cache(maxsize=None)
def icon(name: str, size: int = 18, color: tuple[str, str] = TEXT_2) -> ctk.CTkImage:
    """A Lucide icon tinted for light and dark mode."""
    return ctk.CTkImage(light_image=_tint(name, color[0]), dark_image=_tint(name, color[1]),
                        size=(size, size))


@lru_cache(maxsize=None)
def blank(size: int = 16) -> ctk.CTkImage:
    """Transparent placeholder: CTkLabel can't reliably remove an image once set."""
    img = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    return ctk.CTkImage(img, img, size=(size, size))


@lru_cache(maxsize=None)
def asset_image(file: str, size: int) -> ctk.CTkImage:
    img = Image.open(resource_path("assets", file)).convert("RGBA")
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
