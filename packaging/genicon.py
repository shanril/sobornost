"""Generate sobornost.icns — simple blue S icon."""
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(__file__)
ICNS = os.path.join(HERE, "sobornost.app", "Contents", "Resources", "sobornost.icns")

SIZES = [16, 32, 64, 128, 256, 512]


def draw_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = size // 6
    r = size // 5
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=r, fill=(40, 100, 210, 255),
    )
    try:
        font = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc",
                                  size=int(size * 0.55))
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "S", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1]
    draw.text((x, y), "S", font=font, fill=(255, 255, 255, 255))
    return img


def main():
    os.makedirs(os.path.dirname(ICNS), exist_ok=True)
    iconset = tempfile.mkdtemp(suffix=".iconset")
    for s in SIZES:
        img = draw_icon(s)
        img.save(os.path.join(iconset, f"icon_{s}x{s}.png"))
        img2x = draw_icon(s * 2)
        img2x.save(os.path.join(iconset, f"icon_{s}x{s}@2x.png"))
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", ICNS], check=True)
    shutil.rmtree(iconset)
    print(f"Created {ICNS}")


if __name__ == "__main__":
    main()
