from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from sobornost._keycodes import KEY_CHOICES, KEY_NAMES, MOD_LABELS, describe_hotkey
from sobornost.config import Config


class SettingsWindow:
    def __init__(self, root: tk.Tk, config: Config, on_save=None):
        self.config = config
        self.on_save = on_save

        self.win = tk.Toplevel(root)
        self.win.title("sobornost - Settings")
        self.win.geometry("500x420")
        self.win.resizable(False, False)

        self.notebook = ttk.Notebook(self.win)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_general_tab()
        self._build_display_tab()

        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))

        ttk.Button(btn_frame, text="Save", command=self._save).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frame, text="Cancel", command=self.win.destroy).pack(side="right")

    def _update_hotkey_label(self):
        mods = [name for name, _ in MOD_LABELS if self.mod_vars[name].get()]
        key = self.key_var.get()
        desc = describe_hotkey(mods, key)
        self.hotkey_label.config(text=f"Switch Client:  {desc}")

    def _build_general_tab(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text="General")

        row = 0
        ttk.Label(frame, text="Thumbnail Width:").grid(row=row, column=0, sticky="w", pady=2)
        self.width_var = tk.IntVar(value=self.config.thumbnail_width)
        ttk.Spinbox(frame, from_=100, to=640, increment=10, textvariable=self.width_var, width=8
                     ).grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        ttk.Label(frame, text="Thumbnail Height:").grid(row=row, column=0, sticky="w", pady=2)
        self.height_var = tk.IntVar(value=self.config.thumbnail_height)
        ttk.Spinbox(frame, from_=80, to=400, increment=10, textvariable=self.height_var, width=8
                     ).grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        ttk.Label(frame, text="Opacity:").grid(row=row, column=0, sticky="w", pady=2)
        self.opacity_var = tk.DoubleVar(value=self.config.thumbnail_opacity)
        ttk.Scale(frame, from_=0.2, to=1.0, variable=self.opacity_var, orient="horizontal", length=150
                     ).grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        ttk.Label(frame, text="Refresh Rate (ms):").grid(row=row, column=0, sticky="w", pady=2)
        self.refresh_var = tk.IntVar(value=self.config.preview_refresh_ms)
        ttk.Spinbox(frame, from_=50, to=1000, increment=50, textvariable=self.refresh_var, width=8
                     ).grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        self.track_var = tk.BooleanVar(value=self.config.track_client_locations)
        ttk.Checkbutton(frame, text="Track Client Locations", variable=self.track_var
                         ).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        row += 1

        # --- Hotkey section ---
        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=6
        )
        row += 1

        self.hotkey_label = ttk.Label(frame, font=("", 11, "bold"))
        self.hotkey_label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        row += 1

        # Modifier checkboxes
        mod_frame = ttk.Frame(frame)
        mod_frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        self.mod_vars: dict[str, tk.BooleanVar] = {}
        for name, label in MOD_LABELS:
            var = tk.BooleanVar(value=name in (self.config.hotkey_modifiers or []))
            self.mod_vars[name] = var
            cb = ttk.Checkbutton(mod_frame, text=label, variable=var,
                                 command=self._update_hotkey_label)
            cb.pack(side="left", padx=(0, 8))
        row += 1

        # Key dropdown
        ttk.Label(frame, text="Key:").grid(row=row, column=0, sticky="w", pady=2)
        key_list = sorted(KEY_CHOICES, key=lambda k: KEY_CHOICES.index(k))
        display_keys = [f"{KEY_NAMES.get(k, k)} ({k})" for k in key_list]
        self.key_var = tk.StringVar(
            value=next(
                (f"{KEY_NAMES.get(k, k)} ({k})" for k in key_list if k == self.config.hotkey_key),
                display_keys[0],
            )
        )
        key_menu = ttk.Combobox(
            frame, textvariable=self.key_var, values=display_keys,
            state="readonly", width=16,
        )
        key_menu.grid(row=row, column=1, sticky="w", pady=2)
        key_menu.bind("<<ComboboxSelected>>", lambda e: self._update_hotkey_label())
        row += 1

        self._update_hotkey_label()

    def _build_display_tab(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text="Display")

        row = 0
        ttk.Label(frame, text="Highlight Color:").grid(row=row, column=0, sticky="w", pady=2)
        self.highlight_var = tk.StringVar(value=self.config.active_client_highlight_color)
        ttk.Entry(frame, textvariable=self.highlight_var, width=12).grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        self.label_var = tk.BooleanVar(value=self.config.label_overlay)
        ttk.Checkbutton(frame, text="Show Label Overlay", variable=self.label_var
                         ).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        row += 1

        ttk.Label(frame, text="Label Font Size:").grid(row=row, column=0, sticky="w", pady=2)
        self.font_size_var = tk.IntVar(value=self.config.label_font_size)
        ttk.Spinbox(frame, from_=6, to=48, increment=1, textvariable=self.font_size_var, width=8
                     ).grid(row=row, column=1, sticky="w", pady=2)

    def _save(self):
        self.config.thumbnail_width = self.width_var.get()
        self.config.thumbnail_height = self.height_var.get()
        self.config.thumbnail_opacity = self.opacity_var.get()
        self.config.preview_refresh_ms = self.refresh_var.get()
        self.config.track_client_locations = self.track_var.get()
        self.config.active_client_highlight_color = self.highlight_var.get()
        self.config.label_overlay = self.label_var.get()
        self.config.label_font_size = self.font_size_var.get()

        # Hotkey from UI
        self.config.hotkey_modifiers = [
            name for name, _ in MOD_LABELS if self.mod_vars[name].get()
        ]
        raw = self.key_var.get()
        # Parse "<display> (<key_name>)" or fallback to key name
        if "(" in raw and raw.endswith(")"):
            key_name = raw[raw.index("(") + 1 : raw.index(")")]
        else:
            key_name = raw
        self.config.hotkey_key = key_name

        self.config.save()
        if self.on_save:
            self.on_save()
        self.win.destroy()
