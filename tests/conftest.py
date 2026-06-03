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

    # Functions referenced by the package. Defaults are inert; tests override
    # the ones they care about via monkeypatch. Any other attribute access
    # returns a no-op callable so incidental references during import never
    # blow up (e.g. capturer's ``hasattr(_native, "capture_sc")``).
    mod.__dict__.update(
        list_windows=lambda pattern=None, only_eve=False: [],
        focus_window=lambda wid: False,
        minimize_window=lambda wid: False,
        capture=lambda wid, timeout_secs=5: None,
        capture_pixmap=lambda wid: None,
        capture_window_direct=lambda wid: None,
        get_window_title=lambda wid: None,
        disconnect=lambda: None,
        __getattr__=lambda name: (lambda *a, **k: None),
    )
    return mod


# Install the fake before anything imports the real package.
sys.modules.setdefault("sobornost._native", _make_fake_native())


@pytest.fixture
def fake_native():
    """The installed fake ``sobornost._native`` module."""
    return sys.modules["sobornost._native"]
