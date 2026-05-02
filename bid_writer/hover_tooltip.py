"""Shared hover tooltip helper."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .gui import apply_window_surface


class HoverTooltip:
    def __init__(self, widget: tk.Misc, text: str, *, delay_ms: int = 450):
        self.widget = widget
        self.text = text.strip()
        self.delay_ms = delay_ms
        self.tip_window: tk.Toplevel | None = None
        self._after_id: str | None = None

        if not self.text:
            return

        widget.bind("<Enter>", self._schedule_show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule_show(self, _event=None):
        self._cancel_pending()
        if not self.text:
            return
        try:
            self._after_id = self.widget.after(self.delay_ms, self._show)
        except tk.TclError:
            self._after_id = None

    def _cancel_pending(self):
        if self._after_id is None:
            return
        try:
            self.widget.after_cancel(self._after_id)
        except tk.TclError:
            pass
        self._after_id = None

    def _show(self):
        self._after_id = None
        if self.tip_window is not None or not self.widget.winfo_exists():
            return

        try:
            x = self.widget.winfo_rootx() + 16
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10
        except tk.TclError:
            return

        tip = tk.Toplevel(self.widget)
        apply_window_surface(tip)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")

        container = ttk.Frame(tip, padding=(10, 8))
        container.pack(fill=tk.BOTH, expand=True)
        label = ttk.Label(
            container,
            text=self.text,
            justify=tk.LEFT,
            wraplength=360,
        )
        label.pack(fill=tk.BOTH, expand=True)
        self.tip_window = tip

    def _hide(self, _event=None):
        self._cancel_pending()
        if self.tip_window is not None:
            try:
                self.tip_window.destroy()
            except tk.TclError:
                pass
            self.tip_window = None


__all__ = ["HoverTooltip"]
