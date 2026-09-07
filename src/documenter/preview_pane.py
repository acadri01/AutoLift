"""
preview_pane.py
---------------
A reusable scrollable preview: pages stacked vertically on a grey backing,
scaled to fit the pane width, with Back / Refresh and a page count.

The host decides where it lives (the app's right panel or the sheet editor
window) and what it renders: `pages_fn` is any zero-argument callable that
returns a list of PIL Images (see preview.py). Rendering happens off the
first paint via `after`, so the "Rendering preview..." notice shows while
the PDF pipeline runs.

Mouse wheel: the pane takes over the app-wide <MouseWheel> binding while it
is visible (activate/deactivate); the host restores its own binding in the
on_back callback.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List

from PIL import Image, ImageTk

PAD = 6
BACKING = "#8a8a8a"


class PreviewPane(ttk.Frame):
    def __init__(self, master, title: str, pages_fn: Callable[[], List[Image.Image]],
                 on_back: Callable[[], None]):
        super().__init__(master)
        self.pages_fn = pages_fn
        self.on_back = on_back
        self._imgs: List[ImageTk.PhotoImage] = []

        bar = ttk.Frame(self, padding=(0, 0, 0, PAD)); bar.pack(fill="x")
        ttk.Button(bar, text="< Back", command=self._back).pack(side="left")
        ttk.Label(bar, text=title, font=("Segoe UI", 10, "bold")).pack(side="left", padx=8)
        self.count = ttk.Label(bar, text="", foreground="#666")
        self.count.pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.render).pack(side="right")

        self.cv = tk.Canvas(self, bg=BACKING, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.cv.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.cv.xview)
        self.cv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right", fill="y")
        self.cv.pack(side="left", fill="both", expand=True)

        self.activate()
        self.after(30, self.render)

    # ------------------------------------------------------------------
    def _back(self):
        self.deactivate()
        self.on_back()

    def activate(self):
        self.bind_all("<MouseWheel>", self._wheel)

    def deactivate(self):
        try:
            self.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    def _wheel(self, e):
        try:
            self.cv.yview_scroll(int(-e.delta / 120), "units")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    def render(self):
        try:
            self.cv.delete("all")
            self.cv.create_text(20, 20, anchor="nw", fill="white",
                                font=("Segoe UI", 10),
                                text="Rendering preview...")
            self.update_idletasks()
        except tk.TclError:
            return
        self.after(10, self._do_render)

    def _do_render(self):
        try:
            pages = self.pages_fn()
        except Exception as ex:                     # keep the app alive
            try:
                self.cv.delete("all")
                self.cv.create_text(20, 20, anchor="nw", fill="white",
                                    text=f"Preview failed:\n{ex}")
            except tk.TclError:
                pass
            return

        try:
            self.cv.delete("all")
            if not pages:
                self.cv.create_text(20, 20, anchor="nw", fill="white",
                                    text="(nothing to preview)")
                self.count.config(text="0 pages")
                return

            self._imgs.clear()
            avail = max(600, self.cv.winfo_width() - 34)
            x, y, maxw = 16, 14, 0
            n = len(pages)
            for i, img in enumerate(pages, start=1):
                if img.width > avail:
                    s = avail / img.width
                    img = img.resize((avail, max(1, int(img.height * s))),
                                     Image.LANCZOS)
                ph = ImageTk.PhotoImage(img)
                self._imgs.append(ph)
                self.cv.create_rectangle(x - 1, y - 1, x + img.width + 1,
                                         y + img.height + 1, outline="#555")
                self.cv.create_image(x, y, anchor="nw", image=ph)
                self.cv.create_text(x, y + img.height + 5, anchor="nw",
                                    fill="white", font=("Segoe UI", 8),
                                    text=f"Page {i} of {n}")
                y += img.height + 30
                maxw = max(maxw, img.width + 32)
            self.count.config(text=f"{n} page(s)")
            self.cv.configure(scrollregion=(0, 0, maxw, y))
            self.cv.yview_moveto(0.0)
        except tk.TclError:
            pass
