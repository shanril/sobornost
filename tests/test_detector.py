from __future__ import annotations

import pytest

from sobornost.detector import (
    EVE_TITLE_FILTER,
    LAUNCHER_EXCLUDE,
    Client,
    detect_clients,
)


@pytest.fixture
def windows(monkeypatch, fake_native):
    """Set the window list returned by the (faked) native layer."""

    def _set(win_list):
        monkeypatch.setattr(fake_native, "list_windows", lambda *a, **k: win_list)

    return _set


def test_client_repr():
    c = Client(wid=7, title="EVE - Pilot", pid=42)
    assert repr(c) == "Client(wid=7, title='EVE - Pilot')"
    assert c.wm_class == ""  # defaults to empty string, never None


def test_no_windows_returns_empty(windows):
    windows([])
    assert detect_clients() == []


def test_maps_window_fields(windows):
    windows([{"id": 1, "title": "EVE - Alpha", "pid": 100, "wm_class": "eve"}])
    [client] = detect_clients()
    assert client.wid == 1
    assert client.title == "EVE - Alpha"
    assert client.pid == 100
    assert client.wm_class == "eve"


def test_missing_optional_fields_get_defaults(windows):
    windows([{"id": 2, "title": "EVE"}])
    [client] = detect_clients()
    assert client.title == "EVE"
    assert client.pid == 0
    assert client.wm_class == ""


@pytest.mark.parametrize("title", ["EVE", "EVE - Alpha"])
def test_accepts_exact_eve_client_titles(windows, title):
    windows([{"id": 1, "title": title}])
    assert [client.title for client in detect_clients()] == [title]


@pytest.mark.parametrize(
    "title",
    ["EVE Online", "EVELand", "I love eve", "eve", "EVE- Alpha", ""],
)
def test_rejects_non_client_eve_titles(windows, title):
    windows([{"id": 1, "title": title}])
    assert detect_clients() == []


def test_excludes_launcher_window(windows):
    windows([
        {"id": 1, "title": "EVE - Alpha"},
        {"id": 2, "title": "EVE Launcher"},
    ])
    titles = [c.title for c in detect_clients()]
    assert titles == ["EVE - Alpha"]


def test_exclude_filter_is_case_insensitive(windows):
    windows([{"id": 1, "title": "eve launcher"}])
    assert detect_clients(exclude_filter="EVE Launcher") == []


def test_deduplicates_by_window_id(windows):
    windows([
        {"id": 5, "title": "EVE - Alpha"},
        {"id": 5, "title": "EVE - Alpha (dupe)"},
    ])
    clients = detect_clients()
    assert len(clients) == 1
    assert clients[0].title == "EVE - Alpha"  # first occurrence wins


def test_empty_exclude_filter_keeps_everything(windows):
    windows([{"id": 1, "title": "EVE - Alpha"}])
    assert len(detect_clients(exclude_filter="")) == 1


def test_default_filters_are_eve_and_launcher(monkeypatch, fake_native):
    # The title filter and launcher exclusion are fixed constants (not config):
    # detect_clients() must query the native layer with the EVE filter and
    # drop the launcher by default.
    captured = {}

    def spy(pattern=None, only_eve=False):
        captured["pattern"] = pattern
        return [{"id": 1, "title": "EVE Launcher"}, {"id": 2, "title": "EVE - Pilot"}]

    monkeypatch.setattr(fake_native, "list_windows", spy)
    clients = detect_clients()

    assert captured["pattern"] == EVE_TITLE_FILTER
    assert LAUNCHER_EXCLUDE == "EVE Launcher"
    assert [c.title for c in clients] == ["EVE - Pilot"]
