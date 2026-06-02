from __future__ import annotations

import platform
import subprocess
import sys
import tkinter as tk

from sobornost import _native
from sobornost._keycodes import describe_hotkey, hotkey_to_carbon
from sobornost.config import Config
from sobornost.detector import detect_clients
from sobornost.switcher import focus_client
from sobornost.thumbnails import ThumbnailWindow
from sobornost.ui import SettingsWindow


class SobornostApp:
    @staticmethod
    def _ensure_supported_platform():
        system = platform.system()
        if system == "Linux":
            raise NotImplementedError(
                "sobornost: Linux support is not yet implemented"
            )
        elif system != "Darwin":
            raise RuntimeError(f"Unsupported platform: {system}")

    def __init__(self):
        self.config = Config.load()
        self._ensure_supported_platform()
        self.root = tk.Tk()
        self.root.title("sobornost")
        self.root.withdraw()
        if platform.system() == "Darwin":
            print("[sobornost] macOS: dock icon visible (click to open settings)", file=sys.stderr)
            self.root.createcommand("::tk::mac::OnReopen", self._open_settings)
            if hasattr(_native, "is_accessibility_trusted"):
                trusted = _native.is_accessibility_trusted()
                print(f"[sobornost] Accessibility trusted: {trusted}", file=sys.stderr)
        self._macos_topmost_count = 0

        self.thumbnails: dict[int, ThumbnailWindow] = {}
        self.active_client_wid: int | None = None
        self.client_damage: dict[int, int] = {}
        self.dirty_wids: set[int] = set()
        self._refresh_count = 0
        self._drag_paused = 0
        self._client_pids: set[int] = set()
        self._idle_skip_count = 0

        self._setup_menu()
        self._refresh_clients()
        self._hotkey_registered = False
        self._poll_loop()

    def _setup_menu(self):
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)

        file_menu = tk.Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="Cycle Clients", command=self._cycle_clients)
        file_menu.add_command(label="Settings", command=self._open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._quit)
        self.menubar.add_cascade(label="File", menu=file_menu)

    def _refresh_clients(self):
        title_filter = "EVE"
        clients = detect_clients(title_filter, "EVE Launcher")
        print(f"[sobornost] Found {len(clients)} matching client(s)", file=sys.stderr)

        if not clients:
            if platform.system() == "Darwin":
                # check if EVE process is running at all
                try:
                    r = subprocess.run(
                        ["pgrep", "-if", "EVE"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if r.returncode == 0:
                        pids = r.stdout.strip().splitlines()
                        print(f"[sobornost]   EVE process IS running (pids: {', '.join(pids)})", file=sys.stderr)
                        print("[sobornost]   but no windows visible from CLI context.", file=sys.stderr)
                        print("[sobornost]   Grant Screen Recording permission to", file=sys.stderr)
                        print("[sobornost]     Terminal/iTerm2 in: Settings → Privacy & Security", file=sys.stderr)
                        print("[sobornost]   Then relaunch or package as .app with entitlements.", file=sys.stderr)
                    else:
                        print("[sobornost]   No EVE process found running.", file=sys.stderr)
                except Exception as exc:
                    print(f"[sobornost]   pgrep failed: {exc}", file=sys.stderr)

        current_wids = set()
        for c in clients:
            current_wids.add(c.wid)
            if c.wid not in self.thumbnails:
                print(f"[sobornost]   Adding client: wid={c.wid}, title=\"{c.title}\"", file=sys.stderr)
                tw = ThumbnailWindow(
                    root=self.root,
                    app=self,
                    wid=c.wid,
                    title=c.title,
                    config=self.config,
                )
                self.thumbnails[c.wid] = tw
                self._setup_thumbnail_x11(tw, c.wid)
                damage_id = _native.create_damage(c.wid)
                if damage_id >= 0:
                    self.client_damage[c.wid] = damage_id

        wids_to_remove = set(self.thumbnails.keys()) - current_wids
        for wid in wids_to_remove:
            print(f"[sobornost]   Removing client: wid={wid}", file=sys.stderr)
            self.thumbnails[wid].destroy()
            del self.thumbnails[wid]
            damage_id = self.client_damage.pop(wid, -1)
            if damage_id >= 0:
                _native.destroy_damage(damage_id)
            self.dirty_wids.discard(wid)

        self._client_pids = {c.pid for c in clients}

    def _setup_thumbnail_x11(self, tw: ThumbnailWindow, wid: int):
        # On macOS, winfo_id() returns a MacDrawable pointer, not a
        # CGWindowID. We identify the thumbnail by its unique title
        # ("sobornost_{wid}") and look it up via NSApp.windows /
        # CGWindowListCopyWindowInfo.  Wait a tick so the Tk window is
        # registered with the window server before we search.
        self.root.after(50, self._set_thumbnail_level, tw, wid)
    def _set_thumbnail_level(self, tw: ThumbnailWindow, wid: int):
        try:
            level = _native.set_always_on_top(tw.win.title(), True)
            if level is False:
                print(f"[sobornost]   WARN: _native.set_always_on_top failed for \"{tw.win.title()}\"", file=sys.stderr)
            else:
                print(f"[sobornost]   Thumbnail window level: {level}", file=sys.stderr)
        except tk.TclError:
            pass

    def _set_active_client(self, wid: int | None):
        self.active_client_wid = wid
        for tw in self.thumbnails.values():
            tw.set_active(tw.wid == wid)

    def _register_hotkey(self):
        try:
            result = hotkey_to_carbon(
                self.config.hotkey_modifiers,
                self.config.hotkey_key,
            )
            if result is None:
                print(
                    f"[sobornost] Unknown hotkey key: {self.config.hotkey_key}",
                    file=sys.stderr,
                )
                return
            kc, flags = result
            desc = describe_hotkey(self.config.hotkey_modifiers, self.config.hotkey_key)
            print(f"[sobornost] Registering hotkey: {desc}", file=sys.stderr)
            _native.register_hotkey(kc, flags)
        except Exception as e:
            print(f"[sobornost] Hotkey registration error: {e}", file=sys.stderr)

    def _cycle_clients(self):
        print("[sobornost] _cycle_clients called", file=sys.stderr)
        wids = sorted(self.thumbnails.keys())
        if not wids:
            return
        if self.active_client_wid in self.thumbnails:
            idx = wids.index(self.active_client_wid)
            next_wid = wids[(idx + 1) % len(wids)]
        else:
            next_wid = wids[0]
        focus_client(next_wid)
        self._set_active_client(next_wid)

    def _open_settings(self):
        SettingsWindow(self.root, self.config, on_save=self._on_settings_save)

    def _on_settings_save(self):
        for tw in self.thumbnails.values():
            tw.win.attributes("-alpha", self.config.thumbnail_opacity)
            has_pos = self.config.per_client_position.get(tw._pos_key())
            if not has_pos:
                tw._update_geometry()
        self._refresh_clients()
        if self.active_client_wid is not None and self.active_client_wid in self.thumbnails:
            self.thumbnails[self.active_client_wid].set_active(True)
        self._register_hotkey()  # re-register in case hotkey changed

    def _poll_loop(self):
        if not self._drag_paused:
            # Battery: skip captures when no EVE window is frontmost
            eve_is_frontmost = False
            if self._client_pids:
                for pid in self._client_pids:
                    if _native.is_app_frontmost(pid):
                        eve_is_frontmost = True
                        break

            if eve_is_frontmost:
                self._idle_skip_count = 0
                self._update_thumbnails()
            else:
                self._idle_skip_count += 1
                if self._idle_skip_count >= 150:
                    self._idle_skip_count = 0
                    self._update_thumbnails()

            # Auto-refresh client list every ~2s
            self._refresh_count += 1
            interval = max(1, 2000 // self.config.preview_refresh_ms)
            if self._refresh_count >= interval:
                self._refresh_count = 0
                self._refresh_clients()

            # Periodically re-assert topmost (can be lost when other apps activate)
            self._macos_topmost_count += 1
            if self._macos_topmost_count >= 10:
                self._macos_topmost_count = 0
                for tw in self.thumbnails.values():
                    try:
                        tw._restore_topmost()
                        _native.set_always_on_top(tw.win.title(), True)
                    except Exception:
                        pass

        # Register global hotkey on first poll
        if not self._hotkey_registered:
            self._register_hotkey()
            self._hotkey_registered = True

        # Check global hotkey
        try:
            if _native.hotkey_triggered():
                self._cycle_clients()
        except Exception:
            pass

        self.root.after(self.config.preview_refresh_ms, self._poll_loop)

    def _update_thumbnails(self):
        if self.dirty_wids:
            for wid in list(self.dirty_wids):
                tw = self.thumbnails.get(wid)
                if tw and tw.is_visible():
                    try:
                        tw.refresh()
                    except Exception:
                        pass
            self.dirty_wids.clear()
        else:
            for tw in list(self.thumbnails.values()):
                try:
                    if tw.is_visible():
                        tw.refresh()
                except Exception:
                    pass

    def _quit(self):
        _native.disconnect()
        self.root.quit()
        self.root.destroy()

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._quit()
