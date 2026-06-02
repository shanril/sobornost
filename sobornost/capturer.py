from __future__ import annotations

import sys

from PIL import Image

from sobornost import _native


def capture_thumbnail(wid: int, max_size: tuple[int, int] | None = None) -> Image.Image | None:
    # Try ScreenCaptureKit first (handles Metal/GPU-accelerated windows)
    result = _native.capture_sc(wid) if hasattr(_native, "capture_sc") else None
    if result is None:
        result = _native.capture(wid, 5)
    if result is None:
        result = _native.capture_pixmap(wid)
    if result is None:
        result = _native.capture_window_direct(wid)
    if result is None:
        print(f"[sobornost] capture failed for wid={wid} (GPU-accelerated or invalid window)", file=sys.stderr)
        return None

    data, w, h, fmt = result
    pil_mode = fmt

    if w == 0 or h == 0:
        return None

    img = Image.frombuffer(pil_mode, (w, h), data, "raw", pil_mode, 0, 1)

    if max_size:
        tw, th = max_size
        if w > tw or h > th:
            ratio = min(tw / w, th / h)
            new_w = int(w * ratio)
            new_h = int(h * ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    return img



