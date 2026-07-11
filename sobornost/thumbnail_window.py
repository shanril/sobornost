from __future__ import annotations

import logging
import os
import platform

from PySide6.QtCore import Property, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow

from sobornost import switcher
from sobornost.capturer import capture_thumbnail
from sobornost.config import Config
from sobornost.thumbnail_item import ThumbnailPaintItem, register_qml_types

logger = logging.getLogger(__name__)


def _qml_dir() -> str:
    from sobornost import resource_path
    return resource_path("qml")


class ThumbnailBridge(QObject):
    _activeChanged = Signal(bool)
    _characterNameChanged = Signal(str)

    def __init__(self, tw: ThumbnailWindow, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tw = tw
        cfg = tw.config
        self._highlight_color: str = cfg.active_client_highlight_color
        self._highlight_thickness: int = cfg.active_client_highlight_thickness
        self._label_overlay: bool = cfg.label_overlay
        self._label_font_size: int = cfg.label_font_size
        self._thumbnail_width: int = cfg.thumbnail_width
        self._thumbnail_height: int = cfg.thumbnail_height
        self._opacity: float = cfg.thumbnail_opacity
        self._active: bool = False
        self._character_name: str = tw.character_name
        self._drag_start_gx: float = 0.0
        self._drag_start_gy: float = 0.0
        self._drag_start_wx: int = 0
        self._drag_start_wy: int = 0

    @Property(str, constant=True)
    def highlightColor(self) -> str:
        return self._highlight_color

    @Property(int, constant=True)
    def highlightThickness(self) -> int:
        return self._highlight_thickness

    @Property(bool, constant=True)
    def labelOverlay(self) -> bool:
        return self._label_overlay

    @Property(int, constant=True)
    def labelFontSize(self) -> int:
        return self._label_font_size

    @Property(int, constant=True)
    def thumbnailWidth(self) -> int:
        return self._thumbnail_width

    @Property(int, constant=True)
    def thumbnailHeight(self) -> int:
        return self._thumbnail_height

    @Property(float, constant=True)
    def opacity(self) -> float:
        return self._opacity

    @Property(bool, notify=_activeChanged)
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        if self._active != value:
            self._active = value
            self._activeChanged.emit(value)

    @Property(str, notify=_characterNameChanged)
    def characterName(self) -> str:
        return self._character_name

    @characterName.setter
    def characterName(self, value: str) -> None:
        if self._character_name != value:
            self._character_name = value
            self._characterNameChanged.emit(value)

    @Slot(float, float)
    def dragStarted(self, gx: float, gy: float) -> None:
        self._drag_start_gx = gx
        self._drag_start_gy = gy
        win = self._tw.win
        self._drag_start_wx = win.x()
        self._drag_start_wy = win.y()
        self._tw.app._drag_paused += 1

    @Slot(float, float)
    def dragMoved(self, gx: float, gy: float) -> None:
        dx = int(gx - self._drag_start_gx)
        dy = int(gy - self._drag_start_gy)
        self._tw.win.setPosition(self._drag_start_wx + dx, self._drag_start_wy + dy)

    @Slot()
    def dragEnded(self) -> None:
        app = self._tw.app
        app._drag_paused = max(0, app._drag_paused - 1)
        self._tw._save_position()

    @Slot()
    def clicked(self) -> None:
        tw = self._tw
        switcher.focus_client(tw.wid)
        tw.app._set_active_client(tw.wid)
        QTimer.singleShot(50, tw._restore_topmost)

    @Slot()
    def ctrlClicked(self) -> None:
        switcher.minimize_client(self._tw.wid)


class ThumbnailWindow:
    def __init__(self, app, wid: int, title: str, config: Config) -> None:
        self.app = app
        self.wid = wid
        self.title = title
        self.config = config
        self._destroyed = False
        self._active = False

        QGuiApplication.instance() or QGuiApplication([])
        register_qml_types()

        self.win = QQuickWindow()
        self.win.setTitle(f"sobornost_{self.wid}")
        self.win.setFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.win.setOpacity(self.config.thumbnail_opacity)
        self.win.setColor("black")
        self.win.setObjectName("thumbnailRoot")

        self.bridge = ThumbnailBridge(self)
        self.engine = QQmlEngine(self.win)
        self.engine.rootContext().setContextProperty("bridge", self.bridge)

        qml_file = os.path.join(_qml_dir(), "Thumbnail.qml")
        component = QQmlComponent(self.engine, QGuiApplication.instance())
        component.loadUrl(qml_file)
        if component.isError():
            for err in component.errors():
                logger.error("QML error: %s", err.toString())
            raise RuntimeError(f"Failed to load Thumbnail.qml: {component.errors()}")

        item = component.create()
        if item is None:
            raise RuntimeError("Failed to create Thumbnail.qml item")
        item.setParentItem(self.win.contentItem())  # type: ignore[attr-defined]
        self._root_item = item

        self._paint_item = self._find_paint_item(item)
        if self._paint_item is None:
            raise RuntimeError("ThumbnailPaintItem 'paintItem' not found in QML")

        self._apply_geometry()
        self.win.show()

        QTimer.singleShot(50, self._apply_topmost)

    @staticmethod
    def _find_paint_item(root: object) -> ThumbnailPaintItem | None:
        stack: list[object] = [root]
        while stack:
            current = stack.pop()
            if isinstance(current, ThumbnailPaintItem) and current.objectName() == "paintItem":
                return current
            child_items = getattr(current, "childItems", None)
            if child_items is not None:
                stack.extend(child_items())
        return None

    def _apply_topmost(self) -> None:
        from sobornost import _native

        if self._destroyed:
            return
        try:
            result = _native.set_always_on_top(self._topmost_target(), True)
            if result is False:
                logger.warning("set_always_on_top failed for wid=%s", self.wid)
            else:
                logger.debug("Thumbnail window level set for wid=%s", self.wid)
        except Exception:
            logger.debug("set_always_on_top error for wid=%s", self.wid, exc_info=True)

    def _topmost_target(self) -> int | str:
        if platform.system() == "Darwin":
            return self.win.title()
        return self.win.winId()

    @property
    def character_name(self) -> str:
        parts = self.title.split(" - ", 1)
        return parts[-1].strip() if len(parts) > 1 else ""

    def _pos_key(self) -> str:
        cn = self.character_name
        return cn if cn else str(self.wid)

    def _save_position(self) -> None:
        if self._destroyed:
            return
        x = self.win.x()
        y = self.win.y()
        if self.config.per_client_position is not None:
            self.config.per_client_position[self._pos_key()] = {"x": x, "y": y}
            self.config.save()

    def _restore_topmost(self) -> None:
        if self._destroyed:
            return
        try:
            if platform.system() != "Darwin":
                self.win.raise_()
            self.win.setOpacity(self.config.thumbnail_opacity)
        except Exception:
            logger.debug("restore_topmost failed for wid=%s", self.wid, exc_info=True)

    def _apply_geometry(self) -> None:
        tw = self.config.thumbnail_width
        th = self.config.thumbnail_height
        t = self.config.active_client_highlight_thickness if self._active else 0
        outer_w = tw + 2 * t
        outer_h = th + 2 * t
        pos = (self.config.per_client_position or {}).get(self._pos_key())
        base_x = pos["x"] if pos else 100
        base_y = pos["y"] if pos else 100
        self.win.setGeometry(base_x - t, base_y - t, outer_w, outer_h)
        self.bridge.active = self._active

    def set_active(self, active: bool) -> None:
        self._active = active
        self._apply_geometry()
        self.refresh()

    def update_title(self, title: str) -> None:
        if title and title != self.title:
            old_key = self._pos_key()
            self.title = title
            self.bridge.characterName = self.character_name
            if self._pos_key() != old_key:
                self._apply_geometry()

    def refresh(self) -> None:
        if self._destroyed or self._paint_item is None:
            return
        tw, th = self.config.thumbnail_width, self.config.thumbnail_height
        img = capture_thumbnail(self.wid, max_size=(tw, th))
        if img is None:
            return
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        data = img.tobytes()
        qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888).copy()  # type: ignore[attr-defined]
        self._paint_item.set_image(qimg)

    def is_visible(self) -> bool:
        if self._destroyed:
            return False
        try:
            return self.win.isVisible()
        except Exception:
            return False

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        try:
            self.win.hide()
            self.win.destroy()
            import shiboken6
            if shiboken6.isValid(self.win):
                shiboken6.delete(self.win)
        except Exception:
            logger.debug("destroy error for wid=%s", self.wid, exc_info=True)
