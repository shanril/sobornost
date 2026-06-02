from __future__ import annotations

from sobornost import _native


class Client:
    def __init__(self, wid: int, title: str, pid: int, wm_class: str | None = None):
        self.wid = wid
        self.title = title
        self.pid = pid
        self.wm_class = wm_class or ""

    def __repr__(self) -> str:
        return f"Client(wid={self.wid}, title={self.title!r})"


def detect_clients(title_filter: str = "EVE", exclude_filter: str = "EVE Launcher") -> list[Client]:
    windows = _native.list_windows(title_filter, False)
    if not windows:
        return []

    clients = []
    seen_wids = set()
    for w in windows:
        wid = w["id"]
        if wid in seen_wids:
            continue
        seen_wids.add(wid)
        title = w.get("title", "")
        if exclude_filter and exclude_filter.lower() in title.lower():
            continue
        clients.append(Client(
            wid=wid,
            title=title,
            pid=w.get("pid", 0),
            wm_class=w.get("wm_class"),
        ))
    return clients
