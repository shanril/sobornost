from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QPainter
from PySide6.QtQuick import QQuickPaintedItem

_registered = False


def register_qml_types() -> None:
    global _registered
    if _registered:
        return
    from PySide6.QtQml import qmlRegisterType

    qmlRegisterType(ThumbnailPaintItem, "Sobornost", 1, 0, "ThumbnailPaintItem")  # type: ignore[call-overload]
    _registered = True


class ThumbnailPaintItem(QQuickPaintedItem):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._image: QImage | None = None

    def set_image(self, image: QImage) -> None:
        self._image = image
        self.update()

    def sizeHint(self) -> QSize:
        if self._image is not None:
            return self._image.size()
        return QSize(0, 0)

    def paint(self, painter: QPainter) -> None:
        if self._image is not None:
            painter.drawImage(0, 0, self._image)
