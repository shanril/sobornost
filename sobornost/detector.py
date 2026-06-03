from __future__ import annotations

from sobornost import _native

# EVE Online client windows always have titles beginning with "EVE".
EVE_TITLE_FILTER = "EVE"
# The launcher matches the title filter above but is not a game client,
# so it is always excluded.
LAUNCHER_EXCLUDE = "EVE Launcher"


class Client:
    def __init__(self, wid: int, title: str, pid: int, wm_class: str | None = None):
        self.wid = wid
        self.title = title
        self.pid = pid
        self.wm_class = wm_class or ""

    def __repr__(self) -> str:
        return f"Client(wid={self.wid}, title={self.title!r})"


def detect_clients(
    title_filter: str = EVE_TITLE_FILTER,
    exclude_filter: str = LAUNCHER_EXCLUDE,
) -> list[Client]:
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
