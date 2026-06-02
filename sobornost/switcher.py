from sobornost import _native


def focus_client(wid: int) -> bool:
    return bool(_native.focus_window(wid))


def minimize_client(wid: int) -> bool:
    return bool(_native.minimize_window(wid))
