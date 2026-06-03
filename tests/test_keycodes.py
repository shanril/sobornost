from __future__ import annotations

from sobornost import _keycodes as kc


def test_describe_hotkey_uses_display_names():
    assert kc.describe_hotkey(["Control"], "grave") == "Control+`"
    assert kc.describe_hotkey(["Command", "Shift"], "a") == "Command+Shift+A"


def test_describe_hotkey_falls_back_to_raw_key_name():
    # An unknown key has no display name, so the raw key is shown verbatim.
    assert kc.describe_hotkey([], "f13") == "f13"


def test_hotkey_to_carbon_known_key():
    keycode, flags = kc.hotkey_to_carbon(["Control"], "grave")
    assert keycode == kc.KEY_CODES["grave"]
    assert flags == kc.MOD_BITS["Control"]


def test_hotkey_to_carbon_combines_modifier_bits():
    _, flags = kc.hotkey_to_carbon(["Control", "Command"], "a")
    assert flags == kc.MOD_BITS["Control"] | kc.MOD_BITS["Command"]


def test_hotkey_to_carbon_ignores_unknown_modifier():
    _, flags = kc.hotkey_to_carbon(["Bogus"], "a")
    assert flags == 0


def test_hotkey_to_carbon_unknown_key_returns_none():
    assert kc.hotkey_to_carbon(["Control"], "definitely-not-a-key") is None


def test_every_key_choice_is_resolvable():
    # A key offered in the settings dropdown must map to a real keycode,
    # otherwise selecting it would silently fail at registration time.
    for key in kc.KEY_CHOICES:
        assert key in kc.KEY_CODES, f"{key!r} in KEY_CHOICES but missing from KEY_CODES"


def test_modifier_bits_are_distinct():
    bits = list(kc.MOD_BITS.values())
    assert len(bits) == len(set(bits))
