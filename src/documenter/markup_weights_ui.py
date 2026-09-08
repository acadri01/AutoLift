"""
markup_weights_ui.py
--------------------
Advanced dialog for tuning per-type markup line weights.

Opened from the app's Advanced menu:

    import markup_weights_ui
    markup_weights_ui.open_markup_weights(self, on_applied=<refresh callback>)

`on_applied` (optional) is called after Set as default / Reset so a currently
open editor can repaint - e.g. pass `editor.redraw`. Weights are resolved at
draw time by sheet_model.stroke_pt(), so the change is retrospective across
every document with no migration; the callback is only about refreshing what
is already on screen.

Set as default   -> writes markup_<kind> keys into lift_doc_tool.cfg
Reset to baked-in -> removes those keys, restoring the compiled defaults
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional

import doc_config
import sheet_model as M

RED = "#CC0000"
STEP = 0.25


def open_markup_weights(parent, on_applied: Optional[Callable[[], None]] = None):
    return _MarkupWeightsDialog(parent, on_applied)


class _MarkupWeightsDialog(tk.Toplevel):
    ROW_H = 30
    PV_W = 210

    def __init__(self, parent, on_applied: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.title("Markup line weights")
        self.transient(parent)
        self.resizable(False, False)
        self._on_applied = on_applied
        self._vars: Dict[str, tk.DoubleVar] = {}

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Line weight (points) per markup type.\n"
                            "Applies to every document, past and future.",
                  foreground="#555", justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        eff = M.effective_weights()
        for i, k in enumerate(M.MARKUP_KINDS, start=1):
            ttk.Label(frm, text=k.capitalize()).grid(
                row=i, column=0, sticky="w", padx=(0, 10), pady=3)
            v = tk.DoubleVar(value=round(eff[k], 2))
            self._vars[k] = v
            sp = ttk.Spinbox(frm, from_=M.STROKE_MIN, to=M.STROKE_MAX,
                             increment=STEP, textvariable=v, width=6,
                             command=self._draw_preview)
            sp.grid(row=i, column=1, sticky="w")
            sp.bind("<KeyRelease>", lambda e: self._draw_preview())
            sp.bind("<<Increment>>", lambda e: self.after(1, self._draw_preview))
            sp.bind("<<Decrement>>", lambda e: self.after(1, self._draw_preview))

        n = len(M.MARKUP_KINDS)
        self.pv = tk.Canvas(frm, width=self.PV_W, height=n * self.ROW_H + 10,
                            bg="white", highlightthickness=1,
                            highlightbackground="#cccccc")
        self.pv.grid(row=1, column=2, rowspan=n, padx=(16, 0), sticky="n")

        bar = ttk.Frame(frm)
        bar.grid(row=n + 1, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Button(bar, text="Reset to baked-in",
                   command=self._reset).pack(side="left")
        self._toast = ttk.Label(bar, text="", foreground="#2a7")
        self._toast.pack(side="left", padx=10)
        ttk.Button(bar, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="Set as default",
                   command=self._apply).pack(side="right", padx=6)

        self._draw_preview()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())

    # -- helpers ----------------------------------------------------------
    def _val(self, k: str) -> float:
        try:
            return M.clamp_stroke(float(self._vars[k].get()))
        except (tk.TclError, ValueError):
            return M.stroke_pt(k)

    def _draw_preview(self) -> None:
        c = self.pv
        c.delete("all")
        x0, x1 = 16, self.PV_W - 16
        for i, k in enumerate(M.MARKUP_KINDS):
            y = 10 + i * self.ROW_H + self.ROW_H / 2
            w = max(1.0, self._val(k))          # honest: points ~= px at 100%
            if k == "cloud":
                pts = []
                seg = (x1 - x0) / 6.0
                for j in range(7):
                    pts += [x0 + j * seg, y + (6 if j % 2 else -6)]
                c.create_line(*pts, fill=RED, width=w, smooth=True, splinesteps=6)
            elif k == "dimension":
                c.create_line(x0, y, x1, y, fill=RED, width=w)
                for tx, dx in ((x0, 1), (x1, -1)):
                    c.create_polygon(tx, y, tx + dx * 8, y - 3, tx + dx * 8, y + 3,
                                     fill=RED, outline=RED)
            elif k == "arrow":
                c.create_line(x0, y, x1 - 8, y, fill=RED, width=w)
                c.create_polygon(x1, y, x1 - 9, y - 3, x1 - 9, y + 3,
                                 fill=RED, outline=RED)
            elif k == "callout":
                c.create_rectangle(x0, y - 8, x0 + 46, y + 8, outline=RED,
                                   width=w)
                c.create_line(x0 + 46, y, x1, y, fill=RED, width=w)
            else:  # line
                c.create_line(x0, y, x1, y, fill=RED, width=w)

    def _refresh_screen(self) -> None:
        if self._on_applied:
            try:
                self._on_applied()
            except Exception:
                pass

    def _flash(self, msg: str) -> None:
        self._toast.config(text=msg)
        self.after(2500, lambda: self._toast.config(text=""))

    # -- actions ----------------------------------------------------------
    def _apply(self) -> None:
        pairs = {f"markup_{k}": round(self._val(k), 2) for k in M.MARKUP_KINDS}
        doc_config.set_many(pairs)
        M.load_stroke_overrides()
        # snap the spinboxes to the clamped, stored values
        for k in M.MARKUP_KINDS:
            self._vars[k].set(round(M.stroke_pt(k), 2))
        self._draw_preview()
        self._refresh_screen()
        self._flash("Saved - applies to all documents.")

    def _reset(self) -> None:
        doc_config.unset(*(f"markup_{k}" for k in M.MARKUP_KINDS))
        M.load_stroke_overrides()
        for k, v in M.baked_weights().items():
            if k in self._vars:
                self._vars[k].set(round(v, 2))
        self._draw_preview()
        self._refresh_screen()
        self._flash("Reset to baked-in defaults.")
