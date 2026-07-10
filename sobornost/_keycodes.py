from __future__ import annotations

# macOS Carbon virtual keycodes (kVK_* constants, e.g. kVK_ANSI_A == 0)
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


# X11 keysyms for key names (for Linux hotkey registration).
# Letters and digits: keysym == ASCII code. Special keys use XK_* constants.
X11_KEY_SYMS: dict[str, int] = {
    "grave": 0x0060,
    "minus": 0x002d,
    "equal": 0x003d,
    "tab": 0xff09,
    "space": 0x0020,
    "enter": 0xff0d,
    "escape": 0xff1b,
    "delete": 0xffff,
    "home": 0xff50,
    "end": 0xff57,
    "pageup": 0xff55,
    "pagedown": 0xff56,
    "left": 0xff51,
    "right": 0xff53,
    "up": 0xff52,
    "down": 0xff54,
    "f1": 0xffbe, "f2": 0xffbf, "f3": 0xffc0, "f4": 0xffc1,
    "f5": 0xffc2, "f6": 0xffc3, "f7": 0xffc4, "f8": 0xffc5,
    "f9": 0xffc6, "f10": 0xffc7, "f11": 0xffc8, "f12": 0xffc9,
    **{k: ord(k) for k in "abcdefghijklmnopqrstuvwxyz"},
    **{k: ord(k) for k in "0123456789"},
}

# X11 modifier masks (for Linux hotkey registration).
X11_MOD_MASKS: dict[str, int] = {
    "Control": 4,    # XCB_MOD_MASK_CONTROL (1 << 2)
    "Shift": 1,      # XCB_MOD_MASK_SHIFT (1 << 0)
    "Option": 8,     # XCB_MOD_MASK_1 / Alt (1 << 3)
    "Command": 64,   # XCB_MOD_MASK_4 / Super (1 << 6)
}


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


def hotkey_to_x11(mods: list[str], key: str) -> tuple[int, int] | None:
    ks = X11_KEY_SYMS.get(key)
    if ks is None:
        return None
    mask = 0
    for m in mods:
        mask |= X11_MOD_MASKS.get(m, 0)
    return ks, mask
