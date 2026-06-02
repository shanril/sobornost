from __future__ import annotations

# macOS Carbon keycode map (HID usage page 0x07)
KEY_CODES: dict[str, int] = {
    "grave": 50, "1": 18, "2": 19, "3": 20, "4": 21,
    "5": 23, "6": 22, "7": 26, "8": 28, "9": 25,
    "0": 29, "minus": 27, "equal": 24,
    "a": 0, "b": 11, "c": 8, "d": 2, "e": 14,
    "f": 3, "g": 5, "h": 4, "i": 34, "j": 38,
    "k": 40, "l": 37, "m": 46, "n": 45, "o": 31,
    "p": 35, "q": 12, "r": 15, "s": 1, "t": 17,
    "u": 32, "v": 9, "w": 13, "x": 7, "y": 16,
    "z": 6,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "tab": 48, "space": 49, "enter": 36, "escape": 53,
    "delete": 51, "home": 115, "end": 119,
    "pageup": 116, "pagedown": 121,
    "left": 123, "right": 124, "up": 126, "down": 125,
}

# NSEventModifierFlag → name
MOD_BITS: dict[str, int] = {
    "Control": 1 << 18,
    "Shift": 1 << 17,
    "Option": 1 << 19,
    "Command": 1 << 20,
}

# Ordered display labels for modifier checkboxes
MOD_LABELS: list[tuple[str, str]] = [
    ("Control", "Ctrl"),
    ("Shift", "Shift"),
    ("Option", "Opt"),
    ("Command", "Cmd"),
]

KEY_NAMES: dict[str, str] = {
    "grave": "`", "minus": "-", "equal": "=",
    **{k: k.upper() for k in "1234567890"},
    **{k: k.upper() for k in "abcdefghijklmnopqrstuvwxyz"},
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
    "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
    "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
    "tab": "Tab", "space": "Space", "enter": "Enter",
    "escape": "Esc", "delete": "Del",
    "pageup": "PgUp", "pagedown": "PgDn",
    "left": "←", "right": "→", "up": "↑", "down": "↓",
}

# Ordered list of key names suitable for a dropdown
KEY_CHOICES: list[str] = [
    "grave", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
    "minus", "equal",
    "tab", "space", "enter", "escape", "delete",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "pageup", "pagedown", "home", "end",
    "left", "right", "up", "down",
]


def describe_hotkey(mods: list[str], key: str) -> str:
    return "+".join(mods + [KEY_NAMES.get(key, key)])


def hotkey_to_carbon(mods: list[str], key: str) -> tuple[int, int] | None:
    kc = KEY_CODES.get(key)
    if kc is None:
        return None
    flags = 0
    for m in mods:
        flags |= MOD_BITS.get(m, 0)
    return kc, flags
