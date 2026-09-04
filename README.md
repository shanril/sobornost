# sobornost

EVE Online client preview and switcher — primary target macOS, Linux not yet implemented.

Inspired by [eve-o-preview](https://github.com/Proopai/eve-o-preview). Detects running EVE Online clients, displays live thumbnail previews, and lets you switch between them with a single click.

Licensed under MIT.

## Features

- **Live thumbnails** — real-time previews via CoreGraphics (macOS) or X Composite (Linux)
- **Click to switch** — click a thumbnail to focus and raise that client (AX API on macOS, EWMH on Linux)
- **Draggable previews** — reposition thumbnails by dragging; positions persist per client
- **Zoom on hover** — hover a thumbnail for a larger preview
- **Always on top** — thumbnails stay above game windows
- **Settings UI** — thumbnail size, opacity, refresh rate, highlight color, switch hotkey
- **JSON config** — settings saved to `~/.config/sobornost/config.json`
- **Undecorated windows** — borderless preview windows
- **Ctrl+Click minimize** — minimize an EVE client from its thumbnail
- **Stats overlay** — optional per-character mining (m³) and incoming/outgoing DPS from a game-log summary endpoint
- **Automatic client detection** — windows titled exactly `EVE` or `EVE - <character>` are detected; the `EVE Launcher` is always excluded

## Requirements

| Platform | Requirements |
|---|---|
| **macOS** | Python 3.9+, Xcode CLI tools, Screen Recording permission (System Settings → Privacy & Security) |
| **Linux** | Python 3.9+, X11 (Xorg/XWayland), compositor recommended (`picom` etc.), EWMH-compatible WM |

### macOS

Grant **Screen Recording** permission when prompted on first run. Accessibility permission is optional (enables focus switching).

### Linux

```bash
# Arch
sudo pacman -S python python-xcb-proto libxcb xcb-util xcb-util-image \
               xcb-util-keysyms xcb-util-wm
```

> **Note**: Linux support is not yet implemented. The `_linux_utils.c` extension compiles but raises `NotImplementedError` on import.

## Installation

### Manual

```bash
git clone https://github.com/shanril/sobornost.git
cd sobornost

# Use the Makefile (recommended)
make dev       # run directly
make build     # build dist/sobornost.app
make run       # build + open

# Or run with uv directly
uv run python -m sobornost
```

## Usage

1. Launch your EVE Online clients
2. Start sobornost:
   ```bash
   make dev
   ```
3. Thumbnails appear automatically for each detected EVE client
4. **Click** a thumbnail to switch to that client
5. **Drag** a thumbnail to reposition it
6. **Ctrl+Click** a thumbnail to minimize that client
7. Use the tray icon → **Settings** to adjust thumbnail size, opacity, refresh rate, and more
8. Use the tray icon → **Cycle Clients** (or the global hotkey, default `Ctrl+``) to switch between clients. The client list refreshes automatically every ~2s, so newly launched clients are picked up without manual action.

### Qtile Configuration (Linux only)

```python
@hook.subscribe.client_new
def float_sobornost(client):
    if client.name and "sobornost" in client.name.lower():
        client.floating = True
```

## Configuration

Settings are stored in `~/.config/sobornost/config.json`.

| Key | Default | Description |
|-|-|-|
| `thumbnail_width` | `320` | Preview width in pixels |
| `thumbnail_height` | `200` | Preview height in pixels |
| `thumbnail_opacity` | `0.85` | Preview opacity (0.2–1.0) |
| `preview_refresh_ms` | `200` | Thumbnail update interval |
| `active_client_highlight_color` | `"#00ff00"` | Border color for active client |
| `label_overlay` | `true` | Show character name on thumbnail |
| `label_font_size` | `13` | Font size for thumbnail label overlay (6–48) |
| `track_client_locations` | `true` | Remember thumbnail positions |
| `stats_enabled` | `false` | Show mining/DPS stats overlay on thumbnails |
| `stats_endpoint` | `"http://localhost:8080/api/logs/summary"` | Game-log summary endpoint base URL |
| `stats_refresh_ms` | `5000` | Stats poll interval (1000–60000) |
| `stats_dps_window_secs` | `15` | `last` window (seconds) used for DPS stats |
| `stats_mining_window_secs` | `300` | `last` window (seconds) used for mining stats |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│            Python / PySide6  (sobornost)                    │
│  ┌──────┐ ┌──────┐ ┌──────────┐ ┌────────────┐ ┌────────┐  │
│  │ app  │ │config│ │  tray    │ │ QML windows │ │settings│  │
│  │(loop)│ │(JSON)│ │(QSystem- │ │(QQuickWindow│ │(QML dlg)│  │
│  │      │ │      │ │TrayIcon) │ │  +QSG paint)│ │        │  │
│  └──┬───┘ └──────┘ └──────────┘ └─────┬──────┘ └────────┘  │
│     │     detector/capturer/switcher │                     │
│     └──────────────┬─────────────────┘                     │
└────────────────────┼────────────────────────────────────────┘
                     │ C Python API
          ┌──────────┴──────────┐
┌─────────┴─────────┐ ┌─────────┴─────────┐
│  _macos_utils.m   │ │  _linux_utils.c   │
│ (ObjC, macOS)     │ │(XCB, Linux — stub)│
│ CoreGraphics + AX │ │                   │
└─────────┬─────────┘ └─────────┬─────────┘
          │                      │
┌─────────┴─────────┐ ┌─────────┴─────────┐
│  macOS WindowSvr  │ │  X11 Server (Xorg)│
│ (CG + AX APIs)    │ │  (not implemented)│
└───────────────────┘ └───────────────────┘
```

## Development

```bash
# Common tasks (see Makefile)
make build        # build dist/sobornost.app
make run          # build + open
make dev          # run directly (no .app)
make lint         # ruff check
make typecheck    # mypy
make test         # pytest (native ext is stubbed — see tests/conftest.py)
make clean        # remove build artifacts

# Or run with uv directly
uv run python -m sobornost
uv run pytest

# Logging verbosity (default INFO)
SOBORNOST_LOG_LEVEL=DEBUG uv run python -m sobornost

# Code structure
sobornost/
├── __init__.py          # Package init
├── __main__.py          # Entry: python -m sobornost
├── _macos_utils.m       # C extension (ObjC, CoreGraphics + AX)
├── _linux_utils.c       # C extension (XCB, Linux — stub, not impl.)
├── _native.pyi          # Type stubs (shared interface for both)
├── app.py               # Main controller (QTimer poll loop, tray menu)
├── capturer.py          # Thumbnail capture (calls C ext)
├── config.py            # JSON config
├── config_bridge.py     # Q_PROPERTY bridge exposing Config to Settings.qml
├── detector.py          # Window detection
├── switcher.py          # Window focus/minimize
├── thumbnail_window.py  # QQuickWindow + QML host per thumbnail
├── thumbnail_item.py    # QQuickPaintedItem ( QPainter draws the live frame )
├── settings_dialog.py   # Loads Settings.qml, runs modal QEventLoop
├── stats_client.py      # Polls game-log summary endpoint (QNetworkAccessManager)
├── qml/
│   ├── Thumbnail.qml    # Per-thumbnail view (border, paint item, drag area)
│   └── Settings.qml     # Settings dialog (size/opacity/refresh/hotkey/stats)
└── resources/           # Tray icon PNG

tests/                   # pytest suite (config, keycodes, detector, stats)
└── conftest.py          # stubs the native _native ext so tests need no build
```

## License

MIT — see [LICENSE](LICENSE).
