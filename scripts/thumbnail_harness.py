#!/usr/bin/env python3
"""Standalone manual test harness for the Qt ThumbnailWindow (Phase 2).

Not shipped as part of the sobornost package. Run manually to verify a single
ThumbnailWindow through create -> refresh -> drag -> click -> ctrl-click ->
destroy.

Usage:
    QT_QPA_PLATFORM=xcb python scripts/thumbnail_harness.py           # Linux
    python scripts/thumbnail_harness.py                                # macOS
    python scripts/thumbnail_harness.py --wid 1234 --title "Test"     # specific
    python scripts/thumbnail_harness.py --all                          # list windows, pick first
    python scripts/thumbnail_harness.py --list                         # list windows only
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys

logger = logging.getLogger("harness")


def _ensure_xcb_on_linux() -> None:
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")


_ensure_xcb_on_linux()

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from sobornost import _native  # noqa: E402
from sobornost.config import Config  # noqa: E402
from sobornost.detector import detect_clients  # noqa: E402
from sobornost.thumbnail_window import ThumbnailWindow  # noqa: E402


class MockApp:
    def __init__(self) -> None:
        self._drag_paused = 0
        self.active_client_wid: int | None = None

    def _set_active_client(self, wid: int | None) -> None:
        self.active_client_wid = wid
        logger.info("set_active_client(wid=%s)", wid)


def list_all_windows() -> list[dict]:
    return _native.list_windows(None, False)


def find_target(args: argparse.Namespace) -> tuple[int, str] | None:
    if args.wid is not None:
        wid = args.wid
        title = args.title or f"Window {wid}"
        logger.info("Using specified wid=%s title=%r", wid, title)
        return wid, title

    clients = detect_clients()
    if clients:
        c = clients[0]
        logger.info("Found EVE client: wid=%s title=%r", c.wid, c.title)
        return c.wid, c.title

    logger.info("No EVE clients found")

    if args.all or args.list:
        windows = list_all_windows()
        if not windows:
            logger.warning("No windows visible from this process")
            return None
        print("\nVisible windows:")
        for w in windows:
            print(f"  wid={w['id']:>8}  pid={w.get('pid', '?'):>6}  title={w.get('title', '')!r}")
        if args.list:
            return None
        non_sobornost = [w for w in windows if "sobornost" not in w.get("title", "")]
        if non_sobornost:
            w = non_sobornost[0]
            logger.info("Using first non-sobornost window: wid=%s title=%r", w["id"], w.get("title", ""))
            return w["id"], w.get("title", f"Window {w['id']}")
        logger.warning("No non-sobornost windows found")
        return None

    logger.warning("No target window. Use --all to list windows, or --wid/--title to specify one.")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="ThumbnailWindow test harness")
    parser.add_argument("--wid", type=int, help="Target window id")
    parser.add_argument("--title", type=str, help="Target window title")
    parser.add_argument("--all", action="store_true", help="List all windows and pick first non-sobornost")
    parser.add_argument("--list", action="store_true", help="List all windows and exit")
    parser.add_argument("--log-level", default="DEBUG", help="Log level (default DEBUG)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.DEBUG),
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if not _native.connect():
        logger.error("Failed to connect to native backend (needs X display / Screen Recording permission)")
        return 1

    logger.debug("Native backend connected")

    target = find_target(args)
    if target is None:
        _native.disconnect()
        return 1

    wid, title = target

    app = QGuiApplication(sys.argv)
    mock = MockApp()
    config = Config.load()

    logger.info("Creating ThumbnailWindow(wid=%s, title=%r)", wid, title)
    tw = ThumbnailWindow(app=mock, wid=wid, title=title, config=config)
    logger.info("ThumbnailWindow created. win title=%r winId=%s", tw.win.title(), tw.win.winId())

    refresh_count = 0
    topmost_count = 0

    def refresh_loop() -> None:
        nonlocal refresh_count, topmost_count
        if tw._destroyed:
            return

        try:
            tw.refresh()
            refresh_count += 1
            if refresh_count % 25 == 0:
                logger.debug("refresh #%d (wid=%s)", refresh_count, wid)
        except Exception:
            logger.debug("refresh failed", exc_info=True)

        topmost_count += 1
        if topmost_count >= 25:
            topmost_count = 0
            try:
                tw._restore_topmost()
                result = _native.set_always_on_top(tw._topmost_target(), True)
                logger.debug("re-assert topmost: set_always_on_top -> %s", result)
            except Exception:
                logger.debug("re-assert topmost failed", exc_info=True)

    timer = QTimer()
    timer.timeout.connect(refresh_loop)
    timer.start(config.preview_refresh_ms)

    def on_sigint(sig, frame):
        logger.info("Signal received, shutting down")
        timer.stop()
        tw.destroy()
        app.quit()

    signal.signal(signal.SIGINT, on_sigint)

    logger.info("Harness running. Interact with the thumbnail:")
    logger.info("  - Click (no drag) -> focus client + set active")
    logger.info("  - Drag -> move window, position saved on release")
    logger.info("  - Ctrl-click -> minimize client")
    logger.info("  - Ctrl+C or close window -> exit")

    ret = app.exec()
    logger.info("Event loop exited (%d)", ret)
    _native.disconnect()
    return ret


if __name__ == "__main__":
    sys.exit(main())
