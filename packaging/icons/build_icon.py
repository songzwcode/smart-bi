#!/usr/bin/env python3
"""Generate Smart BI app icon at all required sizes.

Design:
- Rounded-square background with indigo→cyan diagonal gradient.
- Three ascending white bars (representing BI / data).
- A 4-point concave sparkle on top of the tallest bar (representing AI).

Outputs:
    packaging/icons/icon_16.png … icon_1024.png
    packaging/icons/icon.iconset/   (for iconutil → icon.icns)
    packaging/icons/icon.ico        (multi-resolution ICO for Windows)
    packaging/icons/icon.svg        (vector source for documentation)
    frontend/public/favicon.svg     (32×32 simplified for the web)
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent

# ---- Palette -----------------------------------------------------------------

# Indigo-600 → Cyan-500. Both are pulled from the existing design system
# (primary / accent tokens used in the Sidebar logo and theme previews).
C_BG_TOP = (79, 70, 229)   # #4F46E5 indigo-600
C_BG_BOT = (6, 182, 212)   # #06B6D4 cyan-500
C_WHITE = (255, 255, 255)

# Design grid uses a 512×512 viewBox; we scale at render time.
VB = 512
CONTAINER_RADIUS = 116            # 116/512 ≈ 22.6% — modern macOS squircle feel
BAR_RADIUS = 22                   # 22/76 ≈ 29% — generous rounded caps

# Three ascending bars (x, y, w, h). Bottom-aligned so the sparkle has
# room to sit on top of the tallest one without colliding with bar 2.
BARS = [
    (120, 320, 76, 104),  # short
    (218, 256, 76, 168),  # medium
    (320, 176, 76, 248),  # tallest — top at y=176
]

# Sparkle: centered horizontally on bar 3 (x=358), resting on its top with
# a slight overlap so the bar "grows into" the sparkle.
SPARKLE_CX = 358
SPARKLE_CY = 122  # bar 3 top y=176; sparkle bottom y=170 → 6px overlap
SPARKLE_R = 56    # smaller + more delicate than the original draft


# ---- Drawing primitives ------------------------------------------------------

def make_gradient_bg(size: int) -> Image.Image:
    """Diagonal (top-left → bottom-right) RGB gradient."""
    x = np.arange(size, dtype=np.float32).reshape(1, -1)
    y = np.arange(size, dtype=np.float32).reshape(-1, 1)
    t = (x + y) / (2.0 * (size - 1))
    t = t[..., np.newaxis]
    top = np.array(C_BG_TOP, dtype=np.float32)
    bot = np.array(C_BG_BOT, dtype=np.float32)
    arr = (top * (1.0 - t) + bot * t).clip(0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


def rounded_mask(size: int, radius: int) -> Image.Image:
    """Solid-white rounded-rectangle mask, same size as the icon."""
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return m


def sparkle_path(cx: float, cy: float, r: float, samples: int = 48, pull: float = 0.62):
    """Return points for a 4-point concave sparkle.

    `pull` ∈ (0, 1): how strongly the bezier control points are pulled toward
    the center. 0 = straight-sided octagon, 1 = fully pinched to a cross.
    """
    T = (cx, cy - r)
    R = (cx + r, cy)
    B = (cx, cy + r)
    L = (cx - r, cy)

    def toward(anchor, t):
        return (anchor[0] * (1 - t) + cx * t, anchor[1] * (1 - t) + cy * t)

    def bezier(p0, p1, p2, p3, n):
        out = []
        for i in range(n):
            ti = i / (n - 1)
            u = 1 - ti
            x = u**3 * p0[0] + 3 * u**2 * ti * p1[0] + 3 * u * ti**2 * p2[0] + ti**3 * p3[0]
            y = u**3 * p0[1] + 3 * u**2 * ti * p1[1] + 3 * u * ti**2 * p2[1] + ti**3 * p3[1]
            out.append((x, y))
        return out

    pts: list[tuple[float, float]] = []
    for a, b in [(T, R), (R, B), (B, L), (L, T)]:
        pts.extend(bezier(a, toward(a, pull), toward(b, pull), b, samples))
    return pts


def render(size: int) -> Image.Image:
    """Render the icon at the given pixel size."""
    scale = size / VB

    bg = make_gradient_bg(size)
    mask = rounded_mask(size, max(1, int(round(CONTAINER_RADIUS * scale))))

    # Round the background, then composite onto transparent canvas so the
    # rounded corners don't anti-alias against whatever the icon sits on.
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(bg, (0, 0), mask)

    draw = ImageDraw.Draw(out)
    fill = C_WHITE + (250,)  # 250/255 alpha — almost-solid white

    for (x, y, w, h) in BARS:
        x0 = int(round(x * scale))
        y0 = int(round(y * scale))
        x1 = int(round((x + w) * scale))
        y1 = int(round((y + h) * scale))
        rx = max(1, int(round(BAR_RADIUS * scale)))
        draw.rounded_rectangle((x0, y0, x1, y1), radius=rx, fill=fill)

    cx = SPARKLE_CX * scale
    cy = SPARKLE_CY * scale
    r = SPARKLE_R * scale
    if size >= 32:
        pts = sparkle_path(cx, cy, r)
        draw.polygon(pts, fill=fill)
    else:
        # At very small sizes the sparkle becomes sub-pixel noise. Render it
        # as a single bold dot so the silhouette still reads as a "data point
        # with a sparkle".
        rr = max(1, int(round(r * 0.35)))
        draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=fill)

    return out


# ---- SVG export --------------------------------------------------------------

SVG_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb} {vb}" width="{w}" height="{h}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#4F46E5"/>
      <stop offset="100%" stop-color="#06B6D4"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="{vb}" height="{vb}" rx="{r}" fill="url(#bg)"/>
  <g fill="#FFFFFF">
    <rect x="120" y="320" width="76" height="104" rx="22"/>
    <rect x="218" y="256" width="76" height="168" rx="22"/>
    <rect x="320" y="176" width="76" height="248" rx="22"/>
    <path d="{sparkle_d}"/>
  </g>
</svg>
"""

SPARKLE_PATH_D = (
    "M 358,66 "                              # top point (cy=122, r=56 → 122-56=66)
    "C 358,90 374,106 414,122 "              # → right (414=358+56)
    "C 374,138 358,154 358,178 "             # → bottom (178=122+56)
    "C 358,154 342,138 302,122 "             # → left (302=358-56)
    "C 342,106 358,90 358,66 Z"              # back to top
)
# Sparkle path with pull=0.62 — control points pulled toward center so the
# sides curve inward (concave), giving the 4-point "spark" silhouette.


def write_svg(path: Path, w: int = 512, h: int = 512) -> None:
    svg = SVG_TEMPLATE.format(
        vb=VB,
        w=w,
        h=h,
        r=CONTAINER_RADIUS,
        sparkle_d=SPARKLE_PATH_D,
    )
    path.write_text(svg, encoding="utf-8")


# ---- Build -------------------------------------------------------------------

SIZES_PNG = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
SIZES_ICNSET = [16, 32, 64, 128, 256, 512]   # standard Apple iconset sizes
SIZES_ICO = [16, 24, 32, 48, 64, 128, 256]    # standard Windows ICO sizes


def main() -> None:
    iconset = HERE / "icon.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()

    # 1) Render the master 1024 image and downscale.
    master = render(1024)
    master.save(HERE / "icon_1024.png")

    rendered: dict[int, Image.Image] = {1024: master}
    for s in SIZES_PNG:
        if s == 1024:
            continue
        rendered[s] = master.resize((s, s), Image.LANCZOS)

    # 2) Write individual PNGs for inspection.
    for s, img in rendered.items():
        img.save(HERE / f"icon_{s}.png")

    # 3) Build the .iconset directory (Apple naming convention).
    #    Apple expects files named like icon_16x16.png, icon_32x32@2x.png, etc.
    #    We populate standard sizes; @2x variants come from the next size up.
    iconset_map = {
        16: "icon_16x16.png",
        32: "icon_16x16@2x.png",   # 32 used as @2x of 16
        64: "icon_32x32.png",
        128: "icon_32x32@2x.png",  # 128 used as @2x of 32
        256: "icon_128x128.png",
        512: "icon_128x128@2x.png",  # 512 used as @2x of 128
        1024: "icon_256x256@2x.png",
    }
    # Re-map to Apple's actual canonical filenames:
    canonical = {
        "icon_16x16.png": 16,
        "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32,
        "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128,
        "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256,
        "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512,
        "icon_512x512@2x.png": 1024,
    }
    for fname, sz in canonical.items():
        rendered[sz].save(iconset / fname)

    # 4) Build the multi-resolution .ico for Windows.
    ico_frames = [rendered[s].convert("RGBA") for s in SIZES_ICO]
    ico_frames[0].save(
        HERE / "icon.ico",
        format="ICO",
        sizes=[(s, s) for s in SIZES_ICO],
        append_images=ico_frames[1:],
    )

    # 5) Write vector source for documentation + favicon.
    write_svg(HERE / "icon.svg", 512, 512)
    write_svg(HERE / "../../frontend/public/favicon.svg", 32, 32)

    print("✓ Generated:")
    for s in SIZES_PNG:
        print(f"    icon_{s}.png   ({rendered[s].size[0]}×{rendered[s].size[1]})")
    print(f"    icon.iconset/   ({len(canonical)} sizes)")
    print(f"    icon.ico        ({SIZES_ICO})")
    print(f"    icon.svg        (512×512)")
    print(f"    frontend/public/favicon.svg  (32×32)")


if __name__ == "__main__":
    main()