from __future__ import annotations

import logging
import os
import platform
import tkinter as tk

from PIL import ImageDraw, ImageFont, ImageTk

from sobornost import switcher
from sobornost.capturer import capture_thumbnail

logger = logging.getLogger(__name__)


class ThumbnailWindow:
    def __init__(self, root: tk.Tk, app, wid: int, title: str, config):
        self.root = root
        self.app = app
        self.wid = wid
        self.title = title
        self.config = config
        self.photo: ImageTk.PhotoImage | None = None
        self._destroyed = False
        self._active = False
        self._drag_data = {"x": 0, "y": 0, "started": False}

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.title(f"sobornost_{self.wid}")
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black")
        self.win.attributes("-alpha", self.config.thumbnail_opacity)
        self.win.configure(
            highlightbackground=self.config.active_client_highlight_color,
            highlightcolor=self.config.active_client_highlight_color,
            highlightthickness=0,
        )

        self.label_frame = tk.Frame(self.win, bg="black", highlightthickness=0)
        self.label_frame.pack(fill="both", expand=True)

        self.label = tk.Label(self.label_frame, bg="black", cursor="hand2")
        self.label.pack(fill="both", expand=True)

        self._setup_bindings()
        self._apply_geometry()

    _LINUX_FONT_PATHS = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
    )

    @staticmethod
    def _load_label_font(size: int) -> ImageFont.FreeTypeFont:
        if platform.system() == "Darwin":
            return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
        for p in ThumbnailWindow._LINUX_FONT_PATHS:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
        return ImageFont.truetype("DejaVuSans.ttf", size)

    def _setup_bindings(self):
        for w in (self.win, self.label):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)
            w.bind("<Control-Button-1>", self._on_ctrl_click)

    def _drag_start(self, event):
        self._drag_data["x"] = event.x_root
        self._drag_data["y"] = event.y_root
        self._drag_data["started"] = False
        self.app._drag_paused += 1

    def _drag_move(self, event):
        dx = event.x_root - self._drag_data["x"]
        dy = event.y_root - self._drag_data["y"]
        if abs(dx) > 3 or abs(dy) > 3:
            x = self.win.winfo_x() + dx
            y = self.win.winfo_y() + dy
            self.win.geometry(f"+{x}+{y}")
            self._drag_data["x"] = event.x_root
            self._drag_data["y"] = event.y_root
            self._drag_data["started"] = True

    def _drag_end(self, event):
        self.app._drag_paused = max(0, self.app._drag_paused - 1)
        if not self._drag_data["started"]:
            switcher.focus_client(self.wid)
            self.app._set_active_client(self.wid)
            self.win.after(50, self._restore_topmost)
        self._drag_data["started"] = False
        self._save_position()

    def _on_ctrl_click(self, event):
        switcher.minimize_client(self.wid)

    @property
    def character_name(self) -> str:
        parts = self.title.split(" - ", 1)
        return parts[-1].strip() if len(parts) > 1 else ""

    def _pos_key(self) -> str:
        cn = self.character_name
        return cn if cn else str(self.wid)

    def _save_position(self):
        x = self.win.winfo_x()
        y = self.win.winfo_y()
        if self.config.per_client_position is not None:
            self.config.per_client_position[self._pos_key()] = {"x": x, "y": y}
            self.config.save()

    def _restore_topmost(self):
        try:
            if not self._destroyed:
                self.win.attributes("-topmost", True)
                self.win.lift()
        except tk.TclError:
            pass

    def _apply_geometry(self):
        tw = self.config.thumbnail_width
        th = self.config.thumbnail_height
        t = self.config.active_client_highlight_thickness if self._active else 0
        outer_w = tw + 2 * t
        outer_h = th + 2 * t
        pos = (self.config.per_client_position or {}).get(self._pos_key())
        base_x = pos["x"] if pos else 100
        base_y = pos["y"] if pos else 100
        self.win.geometry(f"{outer_w}x{outer_h}+{base_x - t}+{base_y - t}")
        self.win.configure(
            highlightbackground=self.config.active_client_highlight_color,
            highlightcolor=self.config.active_client_highlight_color,
            highlightthickness=t,
        )

    def set_active(self, active: bool):
        self._active = active
        self._apply_geometry()
        self._refresh_thumbnail()

    def update_title(self, title: str):
        """Update the cached window title and reposition if the per-client key
        changed. Driven by the ~2s client-refresh (which already has fresh
        titles from list_windows), so we no longer query the title per frame."""
        if title and title != self.title:
            old_key = self._pos_key()
            self.title = title
            if self._pos_key() != old_key:
                self._apply_geometry()

    def refresh(self):
        if self._destroyed:
            return
        self._refresh_thumbnail()

    def _refresh_thumbnail(self):
        tw, th = (self.config.thumbnail_width, self.config.thumbnail_height)
        img = capture_thumbnail(self.wid, max_size=(tw, th))
        if img is None:
            return

        if self.config.label_overlay:
            tw, th = img.size
            draw = ImageDraw.Draw(img)
            parts = self.title.split(" - ", 1)
            name = parts[-1].strip() if len(parts) > 1 else self.title
            if not name:
                name = str(self.wid)
            try:
                font = self._load_label_font(13)
            except Exception:
                font = ImageFont.load_default()
            _, _, tw_text, th_text = draw.textbbox((0, 0), name, font=font)
            tx = (tw - tw_text) // 2
            ty = 2
            draw.text((tx - 1, ty - 1), name, font=font, fill=(0, 0, 0, 160))
            draw.text((tx + 1, ty - 1), name, font=font, fill=(0, 0, 0, 160))
            draw.text((tx - 1, ty + 1), name, font=font, fill=(0, 0, 0, 160))
            draw.text((tx + 1, ty + 1), name, font=font, fill=(0, 0, 0, 160))
            draw.text((tx, ty), name, font=font, fill=(255, 255, 255, 230))

        self.photo = ImageTk.PhotoImage(img)
        self.label.configure(image=self.photo)

    def is_visible(self) -> bool:
        if self._destroyed:
            return False
        try:
            state = self.win.state()
            return state not in ("withdrawn", "iconic")
        except tk.TclError:
            return False

    def destroy(self):
        self._destroyed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass
