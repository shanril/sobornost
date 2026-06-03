from __future__ import annotations

import logging
import platform
import subprocess
import tkinter as tk

from sobornost import _native
from sobornost._keycodes import describe_hotkey, hotkey_to_carbon
from sobornost.config import Config
from sobornost.detector import EVE_TITLE_FILTER, detect_clients
from sobornost.switcher import focus_client
from sobornost.thumbnails import ThumbnailWindow
from sobornost.ui import SettingsWindow

logger = logging.getLogger(__name__)


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
            logger.info("macOS: dock icon visible (click to open settings)")
            self.root.createcommand("::tk::mac::OnReopen", self._open_settings)
            if hasattr(_native, "is_accessibility_trusted"):
                logger.info("Accessibility trusted: %s", _native.is_accessibility_trusted())
        self._macos_topmost_count = 0

        self.thumbnails: dict[int, ThumbnailWindow] = {}
        self.active_client_wid: int | None = None
        self.client_damage: dict[int, int] = {}
        self.dirty_wids: set[int] = set()
        self._refresh_count = 0
        self._drag_paused = 0
        self._client_pids: set[int] = set()
        self._idle_skip_count = 0
        self._logged_no_windows = False

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
        clients = detect_clients()
        logger.debug("Found %d matching client(s)", len(clients))

        # The capture path caches the (expensive) system window enumeration;
        # drop it on each client refresh so it re-enumerates at most every ~2s
        # rather than per frame.
        if hasattr(_native, "invalidate_capture_cache"):
            _native.invalidate_capture_cache()

        if not clients:
            if platform.system() == "Darwin":
                self._diagnose_no_windows()
        else:
            # Reset so the diagnostic is emitted again if clients later vanish.
            self._logged_no_windows = False

        current_wids = set()
        for c in clients:
            current_wids.add(c.wid)
            if c.wid not in self.thumbnails:
                logger.info("Adding client: wid=%s title=%r", c.wid, c.title)
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
            else:
                # Refresh the title here (titles come from list_windows) instead
                # of querying get_window_title per frame.
                self.thumbnails[c.wid].update_title(c.title)

        wids_to_remove = set(self.thumbnails.keys()) - current_wids
        for wid in wids_to_remove:
            logger.info("Removing client: wid=%s", wid)
            self.thumbnails[wid].destroy()
            del self.thumbnails[wid]
            damage_id = self.client_damage.pop(wid, -1)
            if damage_id >= 0:
                _native.destroy_damage(damage_id)
            self.dirty_wids.discard(wid)

        self._client_pids = {c.pid for c in clients}

    def _diagnose_no_windows(self):
        """Explain (once) why no client windows were found on macOS.

        Runs on every refresh while no clients are visible, but the guidance is
        static, so we emit it only once per "dry spell" to avoid log spam.
        """
        if self._logged_no_windows:
            return
        self._logged_no_windows = True
        try:
            r = subprocess.run(
                ["pgrep", "-if", EVE_TITLE_FILTER],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            logger.warning("pgrep failed while checking for EVE process", exc_info=True)
            return

        if r.returncode == 0:
            pids = ", ".join(r.stdout.strip().splitlines())
            logger.warning(
                "EVE process IS running (pids: %s) but no windows are visible from "
                "this context. Grant Screen Recording permission to your terminal "
                "(Settings → Privacy & Security), then relaunch — or package as a "
                ".app with entitlements.",
                pids,
            )
        else:
            logger.warning("No EVE process found running.")

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
                logger.warning("set_always_on_top failed for %r", tw.win.title())
            else:
                logger.debug("Thumbnail window level: %s", level)
        except tk.TclError:
            logger.debug("set_thumbnail_level: window gone for wid=%s", wid, exc_info=True)

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
                logger.warning("Unknown hotkey key: %s", self.config.hotkey_key)
                return
            kc, flags = result
            desc = describe_hotkey(self.config.hotkey_modifiers, self.config.hotkey_key)
            logger.info("Registering hotkey: %s", desc)
            _native.register_hotkey(kc, flags)
        except Exception:
            logger.exception("Hotkey registration error")

    def _cycle_clients(self):
        logger.debug("_cycle_clients called")
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
            # Battery: skip captures when no EVE window is frontmost. One query
            # for the frontmost pid beats calling is_app_frontmost per client.
            eve_is_frontmost = False
            if self._client_pids:
                front_pid = _native.frontmost_pid()
                eve_is_frontmost = front_pid in self._client_pids

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
                        logger.debug("failed to re-assert topmost for wid=%s", tw.wid, exc_info=True)

        # Register global hotkey on first poll
        if not self._hotkey_registered:
            self._register_hotkey()
            self._hotkey_registered = True

        # Check global hotkey
        try:
            if _native.hotkey_triggered():
                self._cycle_clients()
        except Exception:
            logger.debug("hotkey poll failed", exc_info=True)

        self.root.after(self.config.preview_refresh_ms, self._poll_loop)

    def _update_thumbnails(self):
        if self.dirty_wids:
            for wid in list(self.dirty_wids):
                tw = self.thumbnails.get(wid)
                if tw and tw.is_visible():
                    try:
                        tw.refresh()
                    except Exception:
                        logger.debug("thumbnail refresh failed for wid=%s", wid, exc_info=True)
            self.dirty_wids.clear()
        else:
            for tw in list(self.thumbnails.values()):
                try:
                    if tw.is_visible():
                        tw.refresh()
                except Exception:
                    logger.debug("thumbnail refresh failed for wid=%s", tw.wid, exc_info=True)

    def _quit(self):
        _native.disconnect()
        self.root.quit()
        self.root.destroy()

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._quit()
