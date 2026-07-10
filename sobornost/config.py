from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

from sobornost._keycodes import KEY_CODES, MOD_BITS

# Reverse maps for migration
_KEY_BY_CODE: dict[int, str] = {v: k for k, v in KEY_CODES.items()}
_MOD_NAMES_BY_BIT: dict[int, str] = {v: k for k, v in MOD_BITS.items()}

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "sobornost")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


@dataclass
class Config:
    thumbnail_width: int = 320
    thumbnail_height: int = 200
    preview_refresh_ms: int = 200
    thumbnail_opacity: float = 1.0
    active_client_highlight_color: str = "#00ff00"
    active_client_highlight_thickness: int = 3
    label_overlay: bool = True
    label_font_size: int = 13
    track_client_locations: bool = True
    per_client_position: dict[str, dict] = field(default_factory=dict)
    hotkey_modifiers: list[str] = field(default_factory=lambda: ["Control"])
    hotkey_key: str = "grave"

    @classmethod
    def load(cls) -> Config:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    data = json.load(f)
                # Migrate old (int-based) hotkey format to new (name-based) format
                mods = data.get("hotkey_modifiers")
                kc = data.get("hotkey_keycode")
                if isinstance(mods, int) or kc is not None:
                    if isinstance(mods, int):
                        data["hotkey_modifiers"] = [
                            n for b, n in _MOD_NAMES_BY_BIT.items() if mods & b
                        ]
                    if kc is not None:
                        data["hotkey_key"] = _KEY_BY_CODE.get(kc, "grave")
                        del data["hotkey_keycode"]
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(asdict(self), f, indent=2)
