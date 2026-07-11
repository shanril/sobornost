from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from sobornost._keycodes import KEY_CHOICES, KEY_NAMES, MOD_LABELS, describe_hotkey
from sobornost.config import Config


class ConfigBridge(QObject):
    def __init__(self, config: Config, on_save=None, parent: QObject | None = None):
        super().__init__(parent)
        self._config = config
        self._on_save = on_save

        self._thumbnail_width: int = config.thumbnail_width
        self._thumbnail_height: int = config.thumbnail_height
        self._thumbnail_opacity: float = config.thumbnail_opacity
        self._preview_refresh_ms: int = config.preview_refresh_ms
        self._track_client_locations: bool = config.track_client_locations
        self._highlight_color: str = config.active_client_highlight_color
        self._label_overlay: bool = config.label_overlay
        self._label_font_size: int = config.label_font_size

        active_mods = set(config.hotkey_modifiers or [])
        self._ctrl_mod = "Control" in active_mods
        self._shift_mod = "Shift" in active_mods
        self._opt_mod = "Option" in active_mods
        self._cmd_mod = "Command" in active_mods
        self._hotkey_key: str = config.hotkey_key if config.hotkey_key in KEY_CHOICES else KEY_CHOICES[0]

    _thumbnailWidthChanged = Signal(int)

    @Property(int, notify=_thumbnailWidthChanged)
    def thumbnailWidth(self) -> int:
        return self._thumbnail_width

    @thumbnailWidth.setter
    def thumbnailWidth(self, value: int) -> None:
        if self._thumbnail_width != value:
            self._thumbnail_width = value
            self._thumbnailWidthChanged.emit(value)

    _thumbnailHeightChanged = Signal(int)

    @Property(int, notify=_thumbnailHeightChanged)
    def thumbnailHeight(self) -> int:
        return self._thumbnail_height

    @thumbnailHeight.setter
    def thumbnailHeight(self, value: int) -> None:
        if self._thumbnail_height != value:
            self._thumbnail_height = value
            self._thumbnailHeightChanged.emit(value)

    _thumbnailOpacityChanged = Signal(float)

    @Property(float, notify=_thumbnailOpacityChanged)
    def thumbnailOpacity(self) -> float:
        return self._thumbnail_opacity

    @thumbnailOpacity.setter
    def thumbnailOpacity(self, value: float) -> None:
        if self._thumbnail_opacity != value:
            self._thumbnail_opacity = value
            self._thumbnailOpacityChanged.emit(value)

    _previewRefreshMsChanged = Signal(int)

    @Property(int, notify=_previewRefreshMsChanged)
    def previewRefreshMs(self) -> int:
        return self._preview_refresh_ms

    @previewRefreshMs.setter
    def previewRefreshMs(self, value: int) -> None:
        if self._preview_refresh_ms != value:
            self._preview_refresh_ms = value
            self._previewRefreshMsChanged.emit(value)

    _trackClientLocationsChanged = Signal(bool)

    @Property(bool, notify=_trackClientLocationsChanged)
    def trackClientLocations(self) -> bool:
        return self._track_client_locations

    @trackClientLocations.setter
    def trackClientLocations(self, value: bool) -> None:
        if self._track_client_locations != value:
            self._track_client_locations = value
            self._trackClientLocationsChanged.emit(value)

    _highlightColorChanged = Signal(str)

    @Property(str, notify=_highlightColorChanged)
    def highlightColor(self) -> str:
        return self._highlight_color

    @highlightColor.setter
    def highlightColor(self, value: str) -> None:
        if self._highlight_color != value:
            self._highlight_color = value
            self._highlightColorChanged.emit(value)

    _labelOverlayChanged = Signal(bool)

    @Property(bool, notify=_labelOverlayChanged)
    def labelOverlay(self) -> bool:
        return self._label_overlay

    @labelOverlay.setter
    def labelOverlay(self, value: bool) -> None:
        if self._label_overlay != value:
            self._label_overlay = value
            self._labelOverlayChanged.emit(value)

    _labelFontSizeChanged = Signal(int)

    @Property(int, notify=_labelFontSizeChanged)
    def labelFontSize(self) -> int:
        return self._label_font_size

    @labelFontSize.setter
    def labelFontSize(self, value: int) -> None:
        if self._label_font_size != value:
            self._label_font_size = value
            self._labelFontSizeChanged.emit(value)

    _hotkeyDescChanged = Signal()

    @Property(bool, notify=_hotkeyDescChanged)
    def ctrlMod(self) -> bool:
        return self._ctrl_mod

    @ctrlMod.setter
    def ctrlMod(self, value: bool) -> None:
        if self._ctrl_mod != value:
            self._ctrl_mod = value
            self._hotkeyDescChanged.emit()

    @Property(bool, notify=_hotkeyDescChanged)
    def shiftMod(self) -> bool:
        return self._shift_mod

    @shiftMod.setter
    def shiftMod(self, value: bool) -> None:
        if self._shift_mod != value:
            self._shift_mod = value
            self._hotkeyDescChanged.emit()

    @Property(bool, notify=_hotkeyDescChanged)
    def optMod(self) -> bool:
        return self._opt_mod

    @optMod.setter
    def optMod(self, value: bool) -> None:
        if self._opt_mod != value:
            self._opt_mod = value
            self._hotkeyDescChanged.emit()

    @Property(bool, notify=_hotkeyDescChanged)
    def cmdMod(self) -> bool:
        return self._cmd_mod

    @cmdMod.setter
    def cmdMod(self, value: bool) -> None:
        if self._cmd_mod != value:
            self._cmd_mod = value
            self._hotkeyDescChanged.emit()

    _hotkeyKeyChanged = Signal(str)

    @Property(str, notify=_hotkeyKeyChanged)
    def hotkeyKey(self) -> str:
        return self._hotkey_key

    @hotkeyKey.setter
    def hotkeyKey(self, value: str) -> None:
        if value in KEY_CHOICES and self._hotkey_key != value:
            self._hotkey_key = value
            self._hotkeyKeyChanged.emit(value)
            self._hotkeyDescChanged.emit()

    @Property(list, constant=True)
    def keyModel(self) -> list[dict[str, str]]:
        return [{"display": KEY_NAMES.get(k, k), "value": k} for k in KEY_CHOICES]

    @Property(list, constant=True)
    def modLabels(self) -> list[dict[str, str]]:
        return [{"name": name, "label": label} for name, label in MOD_LABELS]

    @Property(str, notify=_hotkeyDescChanged)
    def hotkeyDescription(self) -> str:
        return describe_hotkey(self._active_mods(), self._hotkey_key)

    def _active_mods(self) -> list[str]:
        mods: list[str] = []
        if self._ctrl_mod:
            mods.append("Control")
        if self._shift_mod:
            mods.append("Shift")
        if self._opt_mod:
            mods.append("Option")
        if self._cmd_mod:
            mods.append("Command")
        return mods

    @Slot()
    def save(self) -> None:
        self._config.thumbnail_width = self._thumbnail_width
        self._config.thumbnail_height = self._thumbnail_height
        self._config.thumbnail_opacity = self._thumbnail_opacity
        self._config.preview_refresh_ms = self._preview_refresh_ms
        self._config.track_client_locations = self._track_client_locations
        self._config.active_client_highlight_color = self._highlight_color
        self._config.label_overlay = self._label_overlay
        self._config.label_font_size = self._label_font_size
        self._config.hotkey_modifiers = self._active_mods()
        self._config.hotkey_key = self._hotkey_key
        self._config.save()
        if self._on_save is not None:
            self._on_save()

    @Slot(result=int)
    def keyIndexOf(self, key: str) -> int:
        try:
            return KEY_CHOICES.index(key)
        except ValueError:
            return 0
