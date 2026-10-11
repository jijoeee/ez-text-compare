"""Generate an EZKerja tool's brand assets from the master logo.

    python make_assets.py --mark ORG --hue 211
    python make_assets.py --mark EDT --hue 148
    python make_assets.py --mark FLS --hue 268 --glyph folder_search

Outputs into assets/:
    app.ico        12-size Windows icon, logo + 3-character mark
    logo.png       256 px clean logo for the in-app header and About box
    drop_orb.png   200 px glossy empty-state orb in the product's hue
    icon_preview.png   check this before committing

Requires: Pillow. Run make_logo_master.py and make_icons.py first: this needs
brand/ezkerja_logo_master.png and the orb glyph in assets/icons/. The mark font is
downloaded automatically on first run.
"""
from __future__ import annotations

import argparse
import colorsys
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(ROOT, "brand", "ezkerja_logo_master.png")
ICON_DIR = os.path.join(ROOT, "assets", "icons")
OUT = os.path.join(ROOT, "assets")

# Every size Windows asks for at 100/125/150/175/200% scaling, plus Explorer views.
ICO_SIZES = [256, 128, 96, 64, 56, 48, 40, 32, 28, 24, 20, 16]

# The mark's typeface. Every EZKerja product must use the SAME font so the marks match.
# DejaVu Sans Bold 2.37, free to redistribute (Bitstream Vera licence). If it is not in
# brand/ yet, it is downloaded once from the official release; the icons it produces are
# pixel-identical to the shipped EZ PDF Organizer icon.
FONT = os.path.join(ROOT, "brand", "DejaVuSans-Bold.ttf")
FONT_URL = ("https://github.com/dejavu-fonts/dejavu-fonts/releases/download/"
            "version_2_37/dejavu-fonts-ttf-2.37.zip")


def mark_font_path() -> str:
    """Return the mark font, downloading it into brand/ on first use."""
    if os.path.exists(FONT):
        return FONT
    import io
    import urllib.request
    import zipfile
    print("Downloading the mark font (DejaVu Sans Bold 2.37) into brand/ ...")
    try:
        data = urllib.request.urlopen(FONT_URL, timeout=60).read()
    except OSError as exc:
        sys.exit(f"Could not download the font ({exc}). Download {FONT_URL} and copy "
                 "ttf/DejaVuSans-Bold.ttf into brand/. Do not substitute another font.")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        ttf = next(n for n in names if n.endswith("ttf/DejaVuSans-Bold.ttf"))
        lic = next(n for n in names if n.endswith("/LICENSE"))
        os.makedirs(os.path.dirname(FONT), exist_ok=True)
        with open(FONT, "wb") as f:
            f.write(z.read(ttf))
        with open(os.path.join(os.path.dirname(FONT), "LICENSE-dejavu.txt"), "wb") as f:
            f.write(z.read(lic))
    return FONT


def with_mark(logo: Image.Image, size: int, mark: str, font_path: str) -> Image.Image:
    """Logo with a white mark, supersampled 8x then reduced for clean edges.

    Small icons get proportionally larger text so the mark survives the downscale.
    The text is fitted to a share of the width, so it can never overflow the circle.
    """
    S = size * 8
    width_share = 0.72 if size >= 48 else (0.78 if size >= 32 else 0.86)
    centre_y = 0.70 if size >= 48 else (0.68 if size >= 32 else 0.66)
    shadow_alpha = 195 if size >= 48 else 220

    img = logo.resize((S, S), Image.LANCZOS)
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    pt = int(S * 0.42)
    while pt > 4:
        font = ImageFont.truetype(font_path, pt)
        bb = draw.textbbox((0, 0), mark, font=font)
        if bb[2] - bb[0] <= S * width_share:
            break
        pt -= 1
    bb = draw.textbbox((0, 0), mark, font=font)
    x = S * 0.5 - (bb[2] + bb[0]) / 2
    y = S * centre_y - (bb[3] + bb[1]) / 2

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x, y + S * 0.010), mark, font=font,
                                fill=(8, 22, 42, shadow_alpha),
                                stroke_width=int(S * 0.016),
                                stroke_fill=(8, 22, 42, shadow_alpha))
    layer.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(S * 0.016)))
    draw.text((x, y), mark, font=font, fill=(255, 255, 255, 255))
    img.alpha_composite(layer)

    out = img.resize((size, size), Image.LANCZOS)
    return out.filter(ImageFilter.UnsharpMask(radius=0.5, percent=95, threshold=0))


def glossy_orb(hue_deg: float, glyph_path: str, px: int = 200) -> Image.Image:
    """The empty-state orb: a glass sphere in the product's hue with an upload glyph."""
    S = 512
    hue = hue_deg / 360
    top = [v * 255 for v in colorsys.hls_to_rgb(hue, 0.686, 0.61)]
    bot = [v * 255 for v in colorsys.hls_to_rgb(hue, 0.373, 0.45)]
    glow = [v * 255 for v in colorsys.hls_to_rgb(hue, 0.60, 0.55)]

    cx = cy = S / 2
    r = S * 0.46
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    px_ = img.load()
    for yy in range(S):
        t = min(1.0, max(0.0, (yy - (cy - r)) / (2 * r)))
        for xx in range(S):
            d = ((xx - cx) ** 2 + (yy - cy) ** 2) ** 0.5
            if d > r + 1:
                continue
            rim = min(1.0, max(0.0, (d / r - 0.72) / 0.28))
            gx = (xx - cx) / (r * 0.7)
            gy = (yy - (cy + r * 0.62)) / (r * 0.28)
            g = 2.718 ** -(gx * gx + gy * gy)
            col = [(top[i] * (1 - t) + bot[i] * t) * (1 - 0.28 * rim) + glow[i] * 0.35 * g
                   for i in range(3)]
            a = min(1.0, max(0.0, (r - d) * 1.5 + 0.5))
            px_[xx, yy] = tuple(int(min(255, c)) for c in col) + (int(a * 255),)

    hl = Image.new("L", (S, S), 0)
    ImageDraw.Draw(hl).ellipse((cx - r * 0.78, cy - r * 0.93, cx + r * 0.78, cy - r * 0.05), fill=255)
    hl = hl.filter(ImageFilter.GaussianBlur(6))
    grad = Image.new("L", (S, S), 0)
    gp = grad.load()
    for yy in range(S):
        v = max(0.0, 1 - (yy - (cy - r * 0.93)) / (r * 0.95)) ** 1.3 * 0.62
        for xx in range(S):
            gp[xx, yy] = int(v * 255)
    white = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    white.putalpha(ImageChops.multiply(hl, grad))
    img = Image.alpha_composite(img, white)

    ring = Image.new("L", (S, S), 0)
    ImageDraw.Draw(ring).ellipse((cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2), outline=255, width=3)
    ring = ring.filter(ImageFilter.GaussianBlur(1)).point(lambda v: int(v * 0.35))
    rl = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    rl.putalpha(ring)
    img = Image.alpha_composite(img, rl)

    glyph = Image.open(glyph_path).convert("RGBA").resize((int(r * 0.95),) * 2, Image.LANCZOS)
    shadow = Image.new("RGBA", glyph.size, (20, 40, 70, 0))
    shadow.putalpha(ImageChops.multiply(glyph.getchannel("A"), Image.new("L", glyph.size, 110)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(5))
    pos = (int(cx - glyph.width / 2), int(cy - glyph.height / 2 + 4))
    img.alpha_composite(shadow, (pos[0], pos[1] + 6))
    img.alpha_composite(glyph, pos)

    img = img.crop((int(cx - r - 4), int(cy - r - 4), int(cx + r + 4), int(cy + r + 4)))
    return img.resize((px, px), Image.LANCZOS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark", required=True, help="exactly 3 characters, e.g. ORG")
    ap.add_argument("--hue", type=float, required=True, help="product hue in degrees, e.g. 211 blue, 148 green")
    ap.add_argument("--glyph", default="upload",
                    help="icon from assets/icons/ shown on the empty-state orb (default: upload)")
    args = ap.parse_args()

    mark = args.mark.strip().upper()
    if len(mark) != 3 or not mark.isalnum():
        sys.exit("The mark must be exactly 3 letters or digits (see 08-tool-build-standard.md).")
    glyph = os.path.join(ICON_DIR, f"{args.glyph}.png")
    for p in (MASTER, glyph):
        if not os.path.exists(p):
            sys.exit(f"Missing {p}")

    os.makedirs(OUT, exist_ok=True)
    logo = Image.open(MASTER).convert("RGBA")
    font = mark_font_path()

    frames = [with_mark(logo, s, mark, font) for s in ICO_SIZES]
    frames[0].save(os.path.join(OUT, "app.ico"), format="ICO",
                   sizes=[(s, s) for s in ICO_SIZES], append_images=frames[1:])
    logo.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "logo.png"), optimize=True)
    orb = glossy_orb(args.hue, glyph)
    orb.save(os.path.join(OUT, "drop_orb.png"), optimize=True)

    # Preview sheet: light and dark backgrounds, every size at 1:1.
    prev = Image.new("RGBA", (1160, 330), (238, 242, 247, 255))
    prev.paste(Image.new("RGBA", (580, 330), (18, 22, 28, 255)), (580, 0))
    for ox in (0, 580):
        prev.alpha_composite(frames[0].resize((150, 150), Image.LANCZOS), (ox + 20, 20))
        prev.alpha_composite(orb.resize((110, 110), Image.LANCZOS), (ox + 190, 40))
        x = ox + 20
        for s, f in zip(ICO_SIZES, frames):
            if s > 64:
                continue
            prev.alpha_composite(f, (x, 230))
            x += s + 10
    prev.save(os.path.join(OUT, "icon_preview.png"))

    got = sorted(Image.open(os.path.join(OUT, "app.ico")).info["sizes"])
    print(f"app.ico sizes: {[s[0] for s in got]}")
    print("Wrote assets/app.ico, assets/logo.png, assets/drop_orb.png, assets/icon_preview.png")
    print("Open icon_preview.png and check the mark is readable at 16 and 24 px.")


if __name__ == "__main__":
    main()
