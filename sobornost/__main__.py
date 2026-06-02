import os
import sys

# Must be set before tkinter is imported on macOS
if sys.platform == "darwin":
    base = sys.base_prefix
    tcl = f"{base}/lib/tcl8.6"
    if os.path.isdir(tcl):
        os.environ.setdefault("TCL_LIBRARY", tcl)
    tk = f"{base}/lib/tk8.6"
    if os.path.isdir(tk):
        os.environ.setdefault("TK_LIBRARY", tk)

from sobornost import _native

# Set process name before tkinter initialises (controls app menu title)
if sys.platform == "darwin":
    _native.set_process_name("sobornost")

from sobornost.app import SobornostApp


def main():
    app = SobornostApp()
    app.run()


if __name__ == "__main__":
    main()
