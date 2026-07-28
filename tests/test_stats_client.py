from __future__ import annotations

import json

from sobornost.stats_client import COLOR_DPS_IN, COLOR_DPS_OUT, COLOR_ORE, endpoint_url, format_stats, parse_summary

# Captured from a live GET /api/logs/summary?last=60.
SAMPLE_PAYLOAD = {
    "window_start": "2026-07-28T19:30:36.927029Z",
    "window_end": "2026-07-28T19:31:36.927029Z",
    "characters": {
        "Malaykha Shanril": {
            "damage_dealt": 5121.0,
            "damage_received": 988.0,
            "damage_dealt_per_second": 85.35,
            "damage_received_per_second": 16.47,
            "mining_units": 1234,
            "mining_m3": 738.5,
            "mining_m3_per_second": 12.308,
            "mining_by_type": {},
            "mining_m3_by_type": {},
        }
    },
    "unknown_ore_types": [],
}

SAMPLE_STATS = SAMPLE_PAYLOAD["characters"]["Malaykha Shanril"]


def _payload_bytes(obj) -> bytes:
    return json.dumps(obj).encode()


def test_endpoint_url_adds_last_param():
    url = endpoint_url("http://localhost:8080/api/logs/summary", 15)
    assert url.toString() == "http://localhost:8080/api/logs/summary?last=15"


def test_endpoint_url_replaces_existing_last_param():
    url = endpoint_url("http://localhost:8080/api/logs/summary?last=60", 300)
    assert url.toString() == "http://localhost:8080/api/logs/summary?last=300"


def test_endpoint_url_preserves_other_params():
    url = endpoint_url("http://localhost:8080/api?foo=1&last=60", 15)
    s = url.toString()
    assert "foo=1" in s
    assert "last=15" in s
    assert "last=60" not in s


def test_parse_summary_extracts_characters():
    result = parse_summary(_payload_bytes(SAMPLE_PAYLOAD))
    assert result == SAMPLE_PAYLOAD["characters"]


def test_parse_summary_empty_characters():
    assert parse_summary(_payload_bytes({"characters": {}})) == {}


def test_parse_summary_missing_characters_key():
    assert parse_summary(_payload_bytes({"window_start": "x"})) == {}


def test_parse_summary_invalid_json():
    assert parse_summary(b"{ not json") == {}


def test_parse_summary_non_dict_root():
    assert parse_summary(b"[1, 2, 3]") == {}


def test_parse_summary_skips_non_dict_entries():
    payload = {"characters": {"Alice": {"mining_m3": 1.0}, "Bob": "broken"}}
    assert parse_summary(_payload_bytes(payload)) == {"Alice": {"mining_m3": 1.0}}


def test_format_stats_full_data():
    assert format_stats(SAMPLE_STATS) == [
        {"text": "DPS out: 85.3", "color": COLOR_DPS_OUT},
        {"text": "DPS in: 16.5", "color": COLOR_DPS_IN},
        {"text": "Ore: 738 m³ (12.3 m³/s)", "color": COLOR_ORE},
    ]


def test_format_stats_line_colors_are_distinct():
    colors = [line["color"] for line in format_stats({})]
    assert len(set(colors)) == 3


def test_format_stats_missing_keys_default_to_zero():
    texts = [line["text"] for line in format_stats({})]
    assert texts == ["DPS out: 0.0", "DPS in: 0.0", "Ore: 0 m³ (0.0 m³/s)"]


def test_format_stats_partial_data():
    # Character present in only one of the two window responses.
    texts = [line["text"] for line in format_stats({"mining_m3": 738.5, "mining_m3_per_second": 12.308})]
    assert texts == ["DPS out: 0.0", "DPS in: 0.0", "Ore: 738 m³ (12.3 m³/s)"]


def test_format_stats_thousands_separator():
    stats = {"mining_m3": 12345.6, "mining_m3_per_second": 205.76}
    texts = [line["text"] for line in format_stats(stats)]
    assert texts == ["DPS out: 0.0", "DPS in: 0.0", "Ore: 12,346 m³ (205.8 m³/s)"]
