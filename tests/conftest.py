"""Shared test fixtures.

The ``sobornost`` package imports the compiled ``_native`` C extension at
import time (via ``sobornost/__init__.py``).  Building that extension requires
a working ObjC toolchain and the right macOS SDK, which we don't want tests to
depend on.  We therefore register a pure-Python fake ``sobornost._native`` in
``sys.modules`` *before* the package is first imported.  Every function the
package touches during import lives on the fake; tests that exercise behaviour
monkeypatch the specific calls they care about.
"""

from __future__ import annotations

import sys
import types

import pytest


def _make_fake_native() -> types.ModuleType:
    mod = types.ModuleType("sobornost._native")

    # All 26 functions from _native.pyi with type-appropriate defaults.
    # Tests override specific calls via monkeypatch.
    mod.__dict__.update(
        connect=lambda display=None: False,
        disconnect=lambda: None,
        list_windows=lambda pattern=None, only_eve=False: [],
        capture=lambda wid, timeout_secs=5, max_w=0, max_h=0: None,
        capture_pixmap=lambda wid, max_w=0, max_h=0: None,
        capture_window_direct=lambda wid, max_w=0, max_h=0: None,
        capture_sc=lambda wid, max_w=0, max_h=0: None,
        invalidate_capture_cache=lambda: None,
        focus_window=lambda wid: False,
        minimize_window=lambda wid: False,
        move_resize=lambda wid, x, y, w, h: False,
        set_always_on_top=lambda wid, flag: False,
        hide_caption=lambda wid: False,
        get_geometry=lambda wid: None,
        get_window_level=lambda wid: -1,
        create_damage=lambda wid: -1,
        destroy_damage=lambda damage_id: None,
        poll_event=lambda: None,
        register_hotkey=lambda keycode, modifiers: False,
        hotkey_triggered=lambda: False,
        is_app_frontmost=lambda pid: False,
        frontmost_pid=lambda: None,
        get_window_title=lambda wid: None,
        get_active_window=lambda: None,
        set_process_name=lambda name: True,
        is_accessibility_trusted=lambda: True,
    )
    return mod


# Install the fake before anything imports the real package.
sys.modules.setdefault("sobornost._native", _make_fake_native())


@pytest.fixture
def fake_native():
    """The installed fake ``sobornost._native`` module."""
    return sys.modules["sobornost._native"]
