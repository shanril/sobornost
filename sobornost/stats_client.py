from __future__ import annotations

import json
import logging
import time

from PySide6.QtCore import QObject, QTimer, QUrl, QUrlQuery
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

logger = logging.getLogger(__name__)

# A snapshot older than this is dropped so dead stats don't linger on overlays
# (e.g. when the log endpoint goes away while polling continues).
STALE_AFTER_SECS = 90.0

_TRANSFER_TIMEOUT_MS = 5000

# Fields read from the short-window (DPS) and long-window (mining) responses.
DPS_FIELDS = ("damage_dealt_per_second", "damage_received_per_second")
MINING_FIELDS = ("mining_m3", "mining_m3_per_second")

_FIELDS = {"dps": DPS_FIELDS, "mining": MINING_FIELDS}

# Per-line colors for the stats overlay.
COLOR_DPS_OUT = "#40e0d0"  # turquoise
COLOR_DPS_IN = "#ff6b6b"  # red
COLOR_ORE = "#ffd54f"  # yellow


def endpoint_url(endpoint: str, window_secs: int) -> QUrl:
    """Return the endpoint URL with its ``last`` query param set to the window.

    Any ``last`` param already present in the configured URL is replaced, so
    configs written before per-window settings existed keep working.
    """
    url = QUrl(endpoint)
    query = QUrlQuery(url.query())
    query.removeQueryItem("last")
    query.addQueryItem("last", str(window_secs))
    url.setQuery(query)
    return url


def parse_summary(payload: bytes | bytearray | memoryview) -> dict[str, dict]:
    """Parse a /api/logs/summary JSON payload into {character_name: stats}."""
    try:
        data = json.loads(bytes(payload))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    characters = data.get("characters")
    if not isinstance(characters, dict):
        return {}
    return {name: stats for name, stats in characters.items() if isinstance(stats, dict)}


def _num(data: dict, key: str) -> float:
    value = data.get(key, 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def format_stats(data: dict) -> list[dict[str, str]]:
    """Build the overlay lines for one character from its merged summary stats.

    Returns a list of {"text", "color"} dicts consumed as a Repeater model by
    Thumbnail.qml.
    """
    return [
        {"text": f"Out: {_num(data, 'damage_dealt_per_second'):.1f} d/s", "color": COLOR_DPS_OUT},
        {"text": f"In : {_num(data, 'damage_received_per_second'):.1f} d/s", "color": COLOR_DPS_IN},
        {"text": f"Ore: {_num(data, 'mining_m3_per_second'):.1f} m³/s", "color": COLOR_ORE},
    ]


class StatsClient(QObject):
    """Polls a game-log summary endpoint for per-character combat/mining stats.

    Each poll issues two requests: one with a short ``last`` window for DPS
    and one with a long window for mining. Both go through
    QNetworkAccessManager on the Qt event loop (no threads, no UI blocking).
    Callers read the merged snapshot via :meth:`snapshot`; polling is
    (re)configured with :meth:`configure`.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._fetch)
        self._endpoint = ""
        self._dps_window_secs = 15
        self._mining_window_secs = 300
        self._data: dict[str, dict[str, dict]] = {"dps": {}, "mining": {}}
        self._replies: dict[str, QNetworkReply | None] = {"dps": None, "mining": None}
        self._updated_at = 0.0
        self._consecutive_failures = 0

    def configure(
        self,
        endpoint: str,
        interval_ms: int,
        dps_window_secs: int,
        mining_window_secs: int,
        enabled: bool,
    ) -> None:
        self._endpoint = endpoint
        self._dps_window_secs = dps_window_secs
        self._mining_window_secs = mining_window_secs
        self._timer.stop()
        if enabled and endpoint:
            self._timer.setInterval(max(1000, interval_ms))
            self._timer.start()
            self._fetch()
        else:
            self._data = {"dps": {}, "mining": {}}

    def snapshot(self) -> dict[str, dict]:
        if (self._data["dps"] or self._data["mining"]) and (time.monotonic() - self._updated_at > STALE_AFTER_SECS):
            self._data = {"dps": {}, "mining": {}}
        merged: dict[str, dict] = {}
        for kind in ("mining", "dps"):
            for name, stats in self._data[kind].items():
                merged.setdefault(name, {}).update(stats)
        return merged

    def stop(self) -> None:
        self._timer.stop()
        for reply in self._replies.values():
            if reply is not None:
                reply.abort()

    def _fetch(self) -> None:
        if not self._endpoint:
            return
        for kind, window in (("dps", self._dps_window_secs), ("mining", self._mining_window_secs)):
            if self._replies[kind] is not None:
                continue  # previous request still in flight
            request = QNetworkRequest(endpoint_url(self._endpoint, window))
            request.setTransferTimeout(_TRANSFER_TIMEOUT_MS)
            reply = self._nam.get(request)
            self._replies[kind] = reply
            reply.finished.connect(lambda k=kind, r=reply: self._on_finished(k, r))

    def _on_finished(self, kind: str, reply: QNetworkReply) -> None:
        if self._replies.get(kind) is reply:
            self._replies[kind] = None
        try:
            error = reply.error()
            if error != QNetworkReply.NetworkError.NoError:
                if error != QNetworkReply.NetworkError.OperationCanceledError:
                    self._consecutive_failures += 1
                    if self._consecutive_failures == 1:
                        logger.warning("stats fetch failed: %s", reply.errorString())
                return
            self._consecutive_failures = 0
            fields = _FIELDS[kind]
            self._data[kind] = {
                name: {f: stats[f] for f in fields if f in stats}
                for name, stats in parse_summary(reply.readAll().data()).items()
            }
            self._updated_at = time.monotonic()
        finally:
            reply.deleteLater()
