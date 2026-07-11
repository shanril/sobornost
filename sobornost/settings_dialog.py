from __future__ import annotations

import os
from typing import Callable, Optional

from PySide6.QtCore import QEventLoop, QUrl
from PySide6.QtGui import QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from sobornost.config import Config


def _qml_dir() -> str:
    from sobornost import resource_path
    return resource_path("qml")


def open_settings_dialog(
    config: Config,
    on_save: Optional[Callable[[], None]] = None,
) -> int:
    """Open the QML settings dialog modally and block until it closes.

    Lazily constructs a ``QApplication`` if none exists yet, so repeated calls
    keep working whether or not the caller already owns a Qt event loop. The
    dialog reads from ``config`` via a :class:`~sobornost.config_bridge.ConfigBridge`;
    on Save the bridge writes the edited working values back to ``config`` and
    calls ``config.save()``, then runs ``on_save`` so the caller can refresh
    thumbnails / re-register the hotkey.

    A local :class:`QEventLoop` runs the dialog in isolation so closing it never
    tears down a caller-owned main ``QApplication`` (e.g. sobornost's own event
    loop). The nested loop still processes the caller's timers, so thumbnails keep
    refreshing while the dialog is open.
    """
    QApplication.instance() or QApplication([])

    engine = QQmlApplicationEngine()
    from sobornost.config_bridge import ConfigBridge

    bridge = ConfigBridge(config, on_save=on_save)
    engine.rootContext().setContextProperty("bridge", bridge)

    qml_file = os.path.join(_qml_dir(), "Settings.qml")
    engine.load(QUrl.fromLocalFile(qml_file))

    if not engine.rootObjects():
        raise RuntimeError(f"Failed to load QML settings dialog from {qml_file}")

    root = engine.rootObjects()[0]
    if not isinstance(root, QWindow):
        raise RuntimeError(
            f"Settings.qml root is not a QWindow (got {type(root).__name__})"
        )

    loop = QEventLoop()

    # QML Save/Cancel buttons both call win.close() (which flips visible -> False)
    # before emitting their signal; the OS title-bar close button only closes the
    # window. Quitting on `visibleChanged` covers all three close paths uniformly
    # without modifying Settings.qml.
    root.visibleChanged.connect(lambda visible: loop.quit() if not visible else None)
    for sig in ("saved", "canceled"):
        getattr(root, sig).connect(loop.quit)

    return loop.exec()
