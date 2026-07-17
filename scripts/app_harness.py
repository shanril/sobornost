#!/usr/bin/env python3
"""Phase 3 integration test harness: drives the REAL SobornostApp with stand-in
windows in place of EVE clients.

Not shipped as part of the sobornost package. Run manually to verify the full
Qt-based app path: tray icon, multi-client thumbnail lifecycle, poll loop,
hotkey cycling, settings dialog, auto add/remove, and clean Ctrl+C shutdown.

Usage:
    QT_QPA_PLATFORM=xcb python scripts/app_harness.py           # Linux
    python scripts/app_harness.py                                # macOS
    python scripts/app_harness.py --wid 1234 --wid 5678 \\
        --title "EVE - Alice" --title "EVE - Bob"               # specific windows
    python scripts/app_harness.py --list                         # list windows only
    python scripts/app_harness.py --count 3                      # auto-pick 3 windows
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

from sobornost import _native  # noqa: E402
from sobornost.detector import Client  # noqa: E402


def list_all_windows() -> list[dict]:
    return _native.list_windows(None, False)


def _synthesize_title(index: int) -> str:
    names = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"]
    name = names[index % len(names)]
    return f"EVE - {name}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 SobornostApp integration harness")
    parser.add_argument(
        "--wid", type=int, action="append", default=[],
        help="Target window id (repeat for multiple clients)",
    )
    parser.add_argument(
        "--title", type=str, action="append", default=[],
        help="Title for the corresponding --wid (repeat; defaults synthesized)",
    )
    parser.add_argument(
        "--count", type=int, default=2,
        help="Number of windows to auto-pick when no --wid given (default 2)",
    )
    parser.add_argument(
        "--list", action="store_true", help="List all visible windows and exit",
    )
    parser.add_argument(
        "--log-level", default="DEBUG", help="Log level (default DEBUG)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.DEBUG),
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if not _native.connect():
        logger.error("Failed to connect to native backend")
        return 1
    logger.debug("Native backend connected")

    # Resolve the stand-in client windows.
    if args.wid:
        if len(args.title) < len(args.wid):
            args.title.extend(
                _synthesize_title(i) for i in range(len(args.title), len(args.wid))
            )
        targets = list(zip(args.wid, args.title))
    else:
        windows = list_all_windows()
        if not windows:
            logger.error("No windows visible from this process")
            _native.disconnect()
            return 1

        if args.list:
            print("\nVisible windows:")
            for w in windows:
                print(f"  wid={w['id']:>8}  pid={w.get('pid', '?'):>6}  title={w.get('title', '')!r}")
            _native.disconnect()
            return 0

        non_sobornost = [w for w in windows if "sobornost" not in w.get("title", "")]
        if len(non_sobornost) < args.count:
            logger.warning(
                "Only %d non-sobornost window(s) available; using all of them",
                len(non_sobornost),
            )
        chosen = non_sobornost[: args.count]
        targets = [
            (w["id"], _synthesize_title(i)) for i, w in enumerate(chosen)
        ]

    if not targets:
        logger.error("No target windows selected")
        _native.disconnect()
        return 1

    logger.info("Stand-in clients:")
    for i, (wid, title) in enumerate(targets):
        logger.info("  [%d] wid=%s title=%r", i, wid, title)

    fake_clients = [
        Client(wid=wid, title=title, pid=0, wm_class="")
        for wid, title in targets
    ]

    # Patch detect_clients in the app module BEFORE importing SobornostApp, so
    # the real _refresh_clients sees our stand-in windows.
    import sobornost.app as app_module  # noqa: E402

    app_module.detect_clients = lambda: fake_clients  # type: ignore[attr-defined]
    logger.debug("Patched sobornost.app.detect_clients -> %d fake clients", len(fake_clients))

    from sobornost.app import SobornostApp  # noqa: E402

    logger.info("Constructing real SobornostApp...")
    try:
        sobornost = SobornostApp()
    except Exception:
        logger.exception("SobornostApp construction failed")
        _native.disconnect()
        return 1

    logger.info("SobornostApp running. Test checklist:")
    logger.info("  - Tray icon visible with Cycle Clients / Settings / Quit")
    logger.info("  - %d thumbnail window(s) should appear", len(targets))
    logger.info("  - Click thumbnail -> focus + active highlight")
    logger.info("  - Ctrl-click thumbnail -> minimize")
    logger.info("  - Press hotkey (default Ctrl+`) -> cycle active client")
    logger.info("  - Tray -> Settings -> change opacity/refresh -> Save")
    logger.info("  - Close a stand-in window -> thumbnail auto-removed (~2s)")
    logger.info("  - Ctrl+C or tray -> Quit -> clean exit")

    # SobornostApp.run() installs its own SIGINT handler; we also keep a fallback
    # so the harness process never hangs if something goes wrong.
    def _fallback_sigint(sig, frame):
        logger.warning("Fallback SIGINT handler triggered")
        _native.disconnect()
        sys.exit(1)

    signal.signal(signal.SIGINT, _fallback_sigint)

    ret = sobornost.run()
    logger.info("Event loop exited (%d)", ret)
    return ret


if __name__ == "__main__":
    sys.exit(main())
