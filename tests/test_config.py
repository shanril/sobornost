from __future__ import annotations

import json
import os

import pytest

from sobornost import config as config_mod
from sobornost.config import Config


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect XDG config storage so tests never touch the user's config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg_dir = tmp_path / "sobornost"
    cfg_path = cfg_dir / "config.json"
    return cfg_path


def _write(path, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def test_defaults():
    c = Config()
    assert c.thumbnail_width == 320
    assert c.thumbnail_height == 200
    assert c.hotkey_modifiers == ["Control"]
    assert c.hotkey_key == "grave"
    assert c.per_client_position == {}
    assert c.label_overlay is True
    assert c.label_font_size == 13


def test_load_missing_file_returns_defaults(tmp_config):
    assert not tmp_config.exists()
    assert Config.load() == Config()


def test_save_then_load_round_trips(tmp_config):
    c = Config(thumbnail_width=512, thumbnail_opacity=0.5, hotkey_key="f1",
               label_overlay=False, label_font_size=20)
    c.save()
    assert tmp_config.exists()
    loaded = Config.load()
    assert loaded == c


def test_config_path_honors_xdg_config_home(tmp_path, monkeypatch):
    xdg_config_home = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config_home))

    assert config_mod._config_dir() == str(xdg_config_home / "sobornost")
    assert config_mod._config_path() == str(xdg_config_home / "sobornost" / "config.json")


def test_config_path_falls_back_to_home_dot_config(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert config_mod._config_dir() == str(tmp_path / ".config" / "sobornost")
    assert config_mod._config_path() == str(tmp_path / ".config" / "sobornost" / "config.json")


def test_xdg_save_and_load_persist(tmp_path, monkeypatch):
    xdg_config_home = tmp_path / "flatpak-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config_home))

    expected_path = xdg_config_home / "sobornost" / "config.json"
    config = Config(thumbnail_width=640, stats_enabled=True)
    config.save()

    assert expected_path.exists()
    assert Config.load() == config


def test_load_ignores_unknown_keys(tmp_config):
    _write(tmp_config, {"thumbnail_width": 400, "bogus_key": 123})
    loaded = Config.load()
    assert loaded.thumbnail_width == 400
    assert not hasattr(loaded, "bogus_key")


def test_load_corrupt_json_returns_defaults(tmp_config):
    os.makedirs(os.path.dirname(tmp_config), exist_ok=True)
    with open(tmp_config, "w") as f:
        f.write("{ this is not valid json")
    assert Config.load() == Config()


def test_migrates_legacy_int_modifiers_and_keycode(tmp_config):
    from sobornost._keycodes import KEY_CODES, MOD_BITS

    legacy = {
        "hotkey_modifiers": MOD_BITS["Control"] | MOD_BITS["Shift"],
        "hotkey_keycode": KEY_CODES["f1"],
    }
    _write(tmp_config, legacy)
    loaded = Config.load()

    assert set(loaded.hotkey_modifiers) == {"Control", "Shift"}
    assert loaded.hotkey_key == "f1"
    # The legacy field must not survive into the dataclass.
    assert not hasattr(loaded, "hotkey_keycode")


def test_migrates_unknown_legacy_keycode_to_grave(tmp_config):
    _write(tmp_config, {"hotkey_keycode": 99999})
    loaded = Config.load()
    assert loaded.hotkey_key == "grave"
