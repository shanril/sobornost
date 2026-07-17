import os
import sys

from sobornost import _native as _native
from sobornost import switcher as switcher
from sobornost.capturer import capture_thumbnail as capture_thumbnail
from sobornost.config import Config as Config
from sobornost.detector import Client as Client
from sobornost.detector import detect_clients as detect_clients

__version__ = "0.1.0"


def resource_path(relative: str) -> str:
    """Resolve a path relative to the sobornost package directory.

    In dev mode ``__file__`` is a real filesystem path and the lookup is
    straightforward. In a py2app bundle the ``.pyc`` files live inside a zip
    archive while ``package_data`` files (QML, PNG) are extracted to
    ``lib/pythonX.Y/sobornost/`` on disk; ``__file__`` then points inside the
    zip and ``os.path.dirname(__file__)`` is not a real directory. We fall
    back to ``sys.prefix``-based resolution for that case.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(here, relative)
    if os.path.exists(candidate):
        return candidate
    py_dir = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return os.path.join(sys.prefix, "lib", py_dir, "sobornost", relative)
