"""Generate sobornost.icns — Triglavian Collective style icon.

Drop-in replacement for the original script.
Requires: Pillow  (pip install Pillow)
macOS only (uses iconutil).
"""
import math
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(__file__)
ICNS = os.path.join(HERE, "sobornost.app", "Contents", "Resources", "sobornost.icns")

SIZES = [16, 32, 64, 128, 256, 512]

# ── Palette ──────────────────────────────────────────────────────────────────
BG          = (  6,  0,  0, 255)    # near-black background
GLOW_CORE   = (187, 22,  0, 220)    # bright red glow centre
ARM_LIGHT   = (106, 13, 13, 255)    # arm fill bright
ARM_DARK    = ( 26,  2,  2, 255)    # arm fill dark edge
EDGE_BRIGHT = (221, 34,  0, 255)    # arm stroke / hub ring
EDGE_HOT    = (255, 51,  0, 200)    # inner hot ring
SCAN_LINE   = (204, 24,  0, 165)    # horizontal scan-line texture
HUB_BG      = (  6,  0,  0, 255)
TEXT_FULL   = (234, 207, 160, 255)  # warm parchment — "Соборность"
TEXT_HUB    = (255, 221, 170, 255)  # slightly brighter — "СБ" in hub
RULE_LINE   = (204,  34,  0, 170)   # divider lines


# ── Maths helpers ─────────────────────────────────────────────────────────────

def rot(px, py, cx, cy, deg):
    r = math.radians(deg)
    dx, dy = px - cx, py - cy
    return (cx + dx * math.cos(r) - dy * math.sin(r),
            cy + dx * math.sin(r) + dy * math.cos(r))

def rot_poly(pts, cx, cy, deg):
    return [rot(x, y, cx, cy, deg) for x, y in pts]

def lerp_color(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


# ── Radial gradient via concentric ellipses ───────────────────────────────────

def draw_radial(draw, cx, cy, rx, ry, color_centre, color_edge, steps=22):
    for i in range(steps, 0, -1):
        t = i / steps
        c = lerp_color(color_centre, color_edge, t)
        erx, ery = rx * t, ry * t
        draw.ellipse([cx - erx, cy - ery, cx + erx, cy + ery], fill=c)


# ── Chevron arm polygon ───────────────────────────────────────────────────────

def arm_polygon(cx, cy, arm_len, arm_w, angle_deg):
    """
    Chevron arm pointing upward from (cx,cy), rotated by angle_deg.
    Shape: two vertical legs joined at top by a cap,
           tapering to a downward chevron tip at the bottom.
    """
    hw  = arm_w / 2          # half outer width
    ihw = arm_w / 2 * 0.38   # half inner gap
    tip = arm_len * 0.28      # tip extension below cx

    pts = [
        ( ihw,       0),
        ( hw,        0),
        ( hw,       -arm_len),
        (-hw,       -arm_len),
        (-hw,        0),
        (-ihw,       0),
        ( 0,         tip),
    ]
    pts = [(x + cx, y + cy) for x, y in pts]
    return rot_poly(pts, cx, cy, angle_deg)


# ── Scan-line texture ─────────────────────────────────────────────────────────

def draw_scanlines(draw, bbox, step, color):
    x0, y0, x1, y1 = bbox
    y = y0 + step
    while y < y1:
        draw.line([(x0, y), (x1, y)], fill=color, width=1)
        y += step


# ── Main draw ─────────────────────────────────────────────────────────────────

def draw_icon(size: int) -> Image.Image:
    S  = size
    cx = S / 2
    cy = S / 2

    base = Image.new("RGBA", (S, S), BG)

    # 1 — radial glow
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    draw_radial(gd, cx, cy, S * 0.52, S * 0.52,
                GLOW_CORE, (0, 0, 0, 0), steps=26)
    draw_radial(gd, S * 0.74, S * 0.18, S * 0.44, S * 0.38,
                (64, 14, 128, 65), (0, 0, 0, 0), steps=16)
    base = Image.alpha_composite(base, glow)

    # 2 — energy streaks
    sd = ImageDraw.Draw(base)
    streak_c = (160, 18, 0, 36)
    for angle in (210, 330, 90, 150, 270, 30):
        r  = math.radians(angle)
        ex = cx + math.cos(r) * S * 0.56
        ey = cy + math.sin(r) * S * 0.56
        sd.line([(cx, cy), (ex, ey)],
                fill=streak_c, width=max(1, S // 60))

    draw = ImageDraw.Draw(base)

    # 3 — three chevron arms
    arm_len = S * 0.295
    arm_w   = S * 0.188

    for angle in (0, 120, 240):
        pts       = arm_polygon(cx, cy, arm_len, arm_w, angle)
        pts_inner = arm_polygon(cx, cy, arm_len * 0.86, arm_w * 0.70, angle)

        draw.polygon(pts,       fill=ARM_DARK)
        draw.polygon(pts_inner, fill=ARM_LIGHT)

        # scan-line texture
        if S >= 64:
            mask  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            md    = ImageDraw.Draw(mask)
            md.polygon(pts, fill=(255, 255, 255, 255))
            lines = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            ld    = ImageDraw.Draw(lines)
            step  = max(2, S // 68)
            bbox  = (int(min(p[0] for p in pts)),
                     int(min(p[1] for p in pts)),
                     int(max(p[0] for p in pts)),
                     int(max(p[1] for p in pts)))
            draw_scanlines(ld, bbox, step, SCAN_LINE)
            masked = Image.composite(
                lines,
                Image.new("RGBA", (S, S), (0, 0, 0, 0)),
                mask.split()[3],
            )
            base  = Image.alpha_composite(base, masked)
            draw  = ImageDraw.Draw(base)

        # bright edge stroke
        draw.polygon(pts, outline=EDGE_BRIGHT)

    # 4 — central hub
    hub_r     = S * 0.086
    hub_inner = S * 0.064

    draw.ellipse([cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r],
                 fill=HUB_BG)
    draw.ellipse([cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r],
                 outline=EDGE_BRIGHT, width=max(1, round(S * 0.005)))
    draw.ellipse([cx - hub_inner, cy - hub_inner,
                  cx + hub_inner, cy + hub_inner],
                 outline=EDGE_HOT,    width=max(1, round(S * 0.003)))

    # 5 — text
    cyrillic_fonts = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Geneva.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]

    def load_font(px):
        for fp in cyrillic_fonts:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, size=px)
                except Exception:
                    pass
        return ImageFont.load_default()

    def put_text(d, text, x, y, font, color):
        bb = d.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        d.text((x - tw / 2 - bb[0], y - th / 2 - bb[1]),
               text, font=font, fill=color)

    def hline(d, y, margin_frac, alpha_mul=1.0):
        m = S * margin_frac
        c = (*RULE_LINE[:3], int(RULE_LINE[3] * alpha_mul))
        d.line([(m, y), (S - m, y)], fill=c,
               width=max(1, round(S * 0.003)))

    if S >= 256:
        put_text(draw, "СБ", cx, cy,
                 load_font(max(8, int(S * 0.066))), TEXT_HUB)
        hline(draw, cy + S * 0.305, 0.20)
        hline(draw, cy + S * 0.400, 0.20, 0.45)
        put_text(draw, "Соборность",
                 cx, cy + S * 0.352,
                 load_font(max(9, int(S * 0.078))), TEXT_FULL)

    elif S >= 128:
        put_text(draw, "СБ", cx, cy,
                 load_font(max(7, int(S * 0.068))), TEXT_HUB)
        hline(draw, cy + S * 0.308, 0.17)
        put_text(draw, "Соборность",
                 cx, cy + S * 0.357,
                 load_font(max(7, int(S * 0.078))), TEXT_FULL)

    elif S >= 64:
        put_text(draw, "СБ", cx, cy,
                 load_font(max(5, int(S * 0.130))), TEXT_HUB)
        hline(draw, cy + S * 0.310, 0.14)
        put_text(draw, "Соборность",
                 cx, cy + S * 0.365,
                 load_font(max(5, int(S * 0.092))), TEXT_FULL)

    elif S >= 32:
        # hub too small for circle label — place "СБ" just above centre
        put_text(draw, "СБ", cx, cy,
                 load_font(max(4, int(S * 0.22))), TEXT_HUB)

    # S < 32: symbol only

    # 6 — rounded-rect clip mask
    r    = S * 0.195
    mask = Image.new("L", (S, S), 0)
    md   = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, S, S], radius=r, fill=255)
    base.putalpha(mask)

    return base


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    os.makedirs(os.path.dirname(ICNS), exist_ok=True)
    iconset = tempfile.mkdtemp(suffix=".iconset")
    try:
        for s in SIZES:
            draw_icon(s).save(
                os.path.join(iconset, f"icon_{s}x{s}.png"))
            draw_icon(s * 2).save(
                os.path.join(iconset, f"icon_{s}x{s}@2x.png"))
        subprocess.run(
            ["iconutil", "-c", "icns", iconset, "-o", ICNS],
            check=True,
        )
    finally:
        shutil.rmtree(iconset, ignore_errors=True)
    print(f"Created {ICNS}")


if __name__ == "__main__":
    main()