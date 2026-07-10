from __future__ import annotations

import logging

from PIL import Image

from sobornost import _native

logger = logging.getLogger(__name__)

_warned_wids: set[int] = set()


def capture_thumbnail(wid: int, max_size: tuple[int, int] | None = None) -> Image.Image | None:
    # Pass the target size to the native layer so it downscales during capture
    # (on the GPU for ScreenCaptureKit) instead of shipping full-resolution
    # frames. 0,0 means "no scaling". The PIL resize below stays as a safety net.
    mw, mh = max_size if max_size else (0, 0)

    # Try ScreenCaptureKit first (handles Metal/GPU-accelerated windows)
    result = _native.capture_sc(wid, mw, mh) if hasattr(_native, "capture_sc") else None
    if result is None:
        result = _native.capture(wid, 5, mw, mh)
    if result is None:
        result = _native.capture_pixmap(wid, mw, mh)
    if result is None:
        result = _native.capture_window_direct(wid, mw, mh)
    if result is None:
        if wid not in _warned_wids:
            logger.warning("capture failed for wid=%s (GPU-accelerated or invalid window)", wid)
            _warned_wids.add(wid)
        else:
            logger.debug("capture failed for wid=%s", wid)
        return None

    _warned_wids.discard(wid)

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



