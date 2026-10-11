"""Render the Lucide UI icons an EZKerja tool needs, as white masks.

    python make_icons.py

Pure Python: downloads Lucide's icon font from the npm registry (no Node.js needed)
and renders each glyph with Pillow (no Cairo needed), so it works on a plain Windows PC.

Edit ICONS below: the key is the name the app uses, the value is the Lucide icon name
(browse them at https://lucide.dev/icons). Output: assets/icons/<key>.png, 96x96, white
on transparent, tinted at runtime by theme.icon(). Also saves Lucide's ISC licence.
"""
import io
import json
import os
import tarfile
import urllib.request

from PIL import Image, ImageDraw, ImageFont

ICONS = {
    # shared by every EZKerja tool - keep these
    "upload": "file-up", "add": "plus", "close": "x", "success": "circle-check",
    "error": "circle-alert", "info": "info", "folder": "folder-open", "file": "file-text",
    "external": "external-link", "sun": "sun", "moon": "moon", "shield": "shield-check",
    "reset": "undo-2", "select_all": "check-check", "remove": "trash-2", "sort": "arrow-down-a-z",
    # EZ Text Compare
    "compare": "file-diff", "stop": "square", "copy": "copy", "export": "download",
    "up": "chevron-up", "down": "chevron-down", "first": "chevrons-up", "last": "chevrons-down",
    "swap": "arrow-left-right", "paste": "clipboard-paste", "refresh": "refresh-cw",
}

SIZE = 96
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icons")


def fetch_lucide() -> tuple[bytes, dict, bytes, str]:
    meta = json.load(urllib.request.urlopen("https://registry.npmjs.org/lucide-static/latest", timeout=30))
    version, url = meta["version"], meta["dist"]["tarball"]
    data = urllib.request.urlopen(url, timeout=60).read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        font = tar.extractfile("package/font/lucide.ttf").read()
        codes = json.load(tar.extractfile("package/font/codepoints.json"))
        licence = tar.extractfile("package/LICENSE").read()
    return font, codes, licence, version


def render(font: ImageFont.FreeTypeFont, codepoint: int) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    ch = chr(codepoint)
    bb = draw.textbbox((0, 0), ch, font=font)
    x = (SIZE - (bb[2] - bb[0])) / 2 - bb[0]
    y = (SIZE - (bb[3] - bb[1])) / 2 - bb[1]
    draw.text((x, y), ch, font=font, fill=(255, 255, 255, 255))
    return img


def main() -> None:
    font_bytes, codes, licence, version = fetch_lucide()
    font = ImageFont.truetype(io.BytesIO(font_bytes), int(SIZE * 0.90))
    os.makedirs(OUT, exist_ok=True)
    missing = [v for v in ICONS.values() if v not in codes]
    if missing:
        raise SystemExit(f"Not in Lucide {version}: {missing}. Check names at https://lucide.dev/icons")
    for key, name in ICONS.items():
        render(font, codes[name]).save(os.path.join(OUT, f"{key}.png"), optimize=True)
    with open(os.path.join(OUT, "LICENSE-lucide.txt"), "wb") as f:
        f.write(licence)
    print(f"Rendered {len(ICONS)} icons from Lucide {version} into assets/icons/")


if __name__ == "__main__":
    main()
