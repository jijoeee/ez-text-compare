"""Check a tool's colour tokens meet WCAG AA contrast, in light and dark mode.

    python check_palette.py ezcompare/theme.py

Reads the (light, dark) tokens straight from theme.py, so it always checks what
actually ships - never a copy that has drifted. Every line must print OK.
Exit code is 0 when everything passes, 1 otherwise.
"""
from __future__ import annotations

import re
import sys

# (foreground, background) pairs that carry readable text in the UI, including text
# on the tinted panels (result messages, selected items). Missing tokens are skipped.
PAIRS = [
    ("TEXT", "BG"), ("TEXT", "SURFACE"), ("TEXT_2", "SURFACE"),
    ("PRIMARY_TEXT", "SURFACE"), ("ON_PRIMARY", "PRIMARY"),
    ("DANGER", "SURFACE"), ("SUCCESS", "SURFACE"),
    ("PRIMARY_TEXT", "PRIMARY_SOFT"), ("TEXT_2", "PRIMARY_SOFT"),
    ("DANGER", "DANGER_SOFT"), ("SUCCESS", "SUCCESS_SOFT"),
    # EZ Text Compare: the comparison panes, line numbers and the Stop button
    ("TEXT", "PRIMARY_SOFT"), ("ON_PRIMARY", "DANGER_FILL"), ("TEXT_2", "SURFACE_2"),
    ("TEXT", "REMOVED_LINE"), ("TEXT", "REMOVED_CHAR"), ("TEXT", "ADDED_LINE"),
    ("TEXT", "ADDED_CHAR"), ("TEXT", "CHANGED_LINE"), ("TEXT", "MOVED_LINE"), ("TEXT_2", "FILLER"),
]
TOKEN = re.compile(r'^([A-Z_0-9]+)\s*=\s*\("(#[0-9A-Fa-f]{6})",\s*"(#[0-9A-Fa-f]{6})"\)', re.M)


def load(path: str) -> dict[str, tuple[str, str]]:
    with open(path, encoding="utf-8") as f:
        return {k: (a, b) for k, a, b in TOKEN.findall(f.read())}


def _lum(h: str) -> float:
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    tokens = load(sys.argv[1])
    if not tokens:
        print(f"No colour tokens found in {sys.argv[1]}")
        return 2
    failed = checked = 0
    for fg, bg in PAIRS:
        if fg not in tokens or bg not in tokens:
            continue
        for i, mode in enumerate(("light", "dark")):
            r = contrast(tokens[fg][i], tokens[bg][i])
            ok = r >= 4.5
            checked += 1
            failed += not ok
            label = f"{fg} on {bg}"
            print(f"{label:<30}{mode:<7}{r:5.2f}  {'OK' if ok else 'FAIL - adjust the colour'}")
    print(f"\n{checked - failed}/{checked} pass" + ("" if not failed else " - fix before release"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
