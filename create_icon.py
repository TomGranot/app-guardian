#!/usr/bin/env python3
"""
Generate App Guardian icons.

Menu bar icon: a minimal ghost silhouette (round head, straight body,
three scalloped bumps at the bottom, two oval eyes punched through).

Template image = black on transparent → macOS auto-inverts for dark/light mode.
"""

from PIL import Image, ImageDraw
import os, math

OUT = os.path.join(os.path.dirname(__file__), "icons")
os.makedirs(OUT, exist_ok=True)


# ── Ghost silhouette ──────────────────────────────────────────────────────────

def ghost(size: int) -> Image.Image:
    """
    A clean ghost silhouette, precisely centred in the canvas.

    Design target (all in absolute pixels for a 44-px canvas, then scaled):
        padding         : 4 px top & bottom  →  4 px top, ~4 px bottom
        head_r          : 9 px  (0.2045 × size)
        head centre y   : pad + head_r  =  13 px
        body bottom     : size - pad - bump_space  →  33 px
        body width      : 2 × head_r  =  18 px (centred)
        scallops        : 3 bumps, each radius = body_width / 6 = 3 px
        actual bottom   : body_bottom + bump_r × 1.7 + 2  ≈  40 px
        bottom padding  : 44 − 40 = 4 px  ✓  vertically centred
    """
    s   = float(size)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    BLK = (0, 230, 80, 255)   # bright green
    TRN = (0, 0, 0, 0)

    # 44-px target layout — scaled up ~12% from accepted vertical centre:
    #   head_r      = 11.44 px  (0.26 × 44)
    #   head_top    = 6.8 px  → decent top breathing room
    #   head_cy     = 18.25 px  (0.415 × 44)
    #   body_bottom = 35.2 px  (0.80 × 44)
    #   scallop bottom ≈ 43.7 px  →  0.3 px clear from edge
    head_r  = s * 0.31        # same size as before
    cx      = s * 0.50
    head_cy = s * 0.559       # shifted down again by same delta

    body_top    = head_cy
    body_bottom = s * 0.87    # scallops clip at canvas edge — fine at 22 px
    body_l      = cx - head_r
    body_r      = cx + head_r

    # ── Filled head circle ────────────────────────────────────────────────────
    d.ellipse(
        [cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
        fill=BLK,
    )

    # ── Filled body rectangle ─────────────────────────────────────────────────
    d.rectangle([body_l, body_top, body_r, body_bottom], fill=BLK)

    # ── Scalloped bottom (3 bumps cut out) ────────────────────────────────────
    n      = 3
    bump_r = (body_r - body_l) / (n * 2)
    for i in range(n):
        bx = body_l + bump_r * (2 * i + 1)
        by = body_bottom - bump_r * 0.30
        d.ellipse([bx - bump_r, by, bx + bump_r, by + bump_r * 2 + 2], fill=TRN)

    # ── Eyes (transparent ovals) ──────────────────────────────────────────────
    eye_rx = head_r * 0.22
    eye_ry = head_r * 0.28
    eye_y  = head_cy - head_r * 0.05
    for ex in [cx - head_r * 0.36, cx + head_r * 0.36]:
        d.ellipse(
            [ex - eye_rx, eye_y - eye_ry, ex + eye_rx, eye_y + eye_ry],
            fill=TRN,
        )

    return img


# ── Broom silhouette (alternate) ──────────────────────────────────────────────

def broom(size: int) -> Image.Image:
    """
    A clean broom: angled handle + trapezoidal head.
    Good as a dock/app icon alternative.
    """
    s   = float(size)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    w   = max(2, round(s / 14))       # handle stroke width
    BLK = (0, 0, 0, 255)

    # Handle  — from top-right to mid-left
    hx1, hy1 = s * 0.78, s * 0.06
    hx2, hy2 = s * 0.28, s * 0.60
    d.line([(hx1, hy1), (hx2, hy2)], fill=BLK, width=w * 2)

    # Brush head — trapezoid wider at bottom
    pts = [
        (round(s * 0.06), round(s * 0.60)),   # top-left
        (round(s * 0.52), round(s * 0.60)),   # top-right
        (round(s * 0.62), round(s * 0.88)),   # bottom-right
        (round(s * 0.00), round(s * 0.88)),   # bottom-left
    ]
    d.polygon(pts, fill=BLK)

    # Bristle lines
    n_lines = 5
    for i in range(n_lines):
        t  = i / (n_lines - 1)           # 0..1
        bx = round(s * 0.06 + (s * 0.56) * t)
        by = round(s * 0.88)
        ex = round(bx - s * 0.04 + (s * 0.08) * t)
        ey = round(by + s * 0.10)
        d.line([(bx, by), (ex, ey)], fill=BLK, width=max(1, w))

    return img


# ── Export ────────────────────────────────────────────────────────────────────

def save(img: Image.Image, path: str):
    img.save(path, "PNG")
    print(f"  {path.replace(os.path.expanduser('~'), '~')}  ({img.size[0]}×{img.size[1]})")


if __name__ == "__main__":
    print("Generating App Guardian icons…\n")

    # ── Menu bar icons (template: black on transparent) ───────────────────────
    # macOS loads @2x automatically when the screen is Retina
    print("Menu bar — ghost:")
    save(ghost(22),  os.path.join(OUT, "menubar.png"))
    save(ghost(44),  os.path.join(OUT, "menubar@2x.png"))

    print("\nMenu bar — broom (alternate):")
    save(broom(22),  os.path.join(OUT, "broom.png"))
    save(broom(44),  os.path.join(OUT, "broom@2x.png"))

    # ── App / dock icons ──────────────────────────────────────────────────────
    print("\nApp icon (ghost, various sizes):")
    for sz in [16, 32, 64, 128, 256, 512]:
        save(ghost(sz), os.path.join(OUT, f"icon_{sz}.png"))

    # ── icns bundle (for proper .app packaging later) ─────────────────────────
    # Build an iconset folder that `iconutil` can turn into .icns
    iconset = os.path.join(OUT, "AppGuardian.iconset")
    os.makedirs(iconset, exist_ok=True)
    ICNS_SIZES = {
        "icon_16x16.png":      16,
        "icon_16x16@2x.png":   32,
        "icon_32x32.png":      32,
        "icon_32x32@2x.png":   64,
        "icon_128x128.png":    128,
        "icon_128x128@2x.png": 256,
        "icon_256x256.png":    256,
        "icon_256x256@2x.png": 512,
        "icon_512x512.png":    512,
        "icon_512x512@2x.png": 1024,
    }
    print(f"\n.iconset ({iconset.replace(os.path.expanduser('~'), '~')}):")
    for fname, sz in ICNS_SIZES.items():
        save(ghost(sz), os.path.join(iconset, fname))

    print("\nDone.  Run `iconutil -c icns icons/AppGuardian.iconset` for .icns")
