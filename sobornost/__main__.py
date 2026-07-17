import logging
import os
import sys

# On Linux, force the XCB Qt platform plugin so QWindow.winId() returns real X11
# window ids that _native.set_always_on_top() can act on. Must be set before any
# PySide6 import.
if sys.platform.startswith("linux"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from sobornost import _native

# Set process name before the application initialises (controls app menu title).
if sys.platform == "darwin":
    _native.set_process_name("sobornost")

from sobornost.app import SobornostApp


def main():
    logging.basicConfig(
        level=os.environ.get("SOBORNOST_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    app = SobornostApp()
    app.run()


if __name__ == "__main__":
    main()
