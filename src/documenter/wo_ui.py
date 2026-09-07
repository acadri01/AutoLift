"""
wo_ui.py
--------
Work-order CONTENT PANEL (right side of the app window).

Shows every line with iso / lift-case counts, the resolved sheet plan, and
"Export work order". Navigation lives in the application tree; double-
clicking a line row here jumps the tree (and the panel) to that line -
no new window.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List

import preview
import work_order
from lift_db import LiftDb
from preview_pane import PreviewPane

PAD = 6


class WoPanel(ttk.Frame):
    def __init__(self, master, app, db: LiftDb, wo_id: int, folder: str):
        super().__init__(master)
        self.app = app                  # DocumenterApp - say(), focus_line(), flush()
        self.db = db
        self.wo_id = wo_id
        self.folder = folder
        self._pv = None
        self._build()
        self.refresh()

    def _top(self):
        return self.winfo_toplevel()

    def _say(self, m):
        self.app.say(m)

    def on_hidden(self):
        if self._pv is not None:
            self._pv.deactivate()

    # ------------------------------------------------------------------
    def _build(self):
        wo = self.db.get_wo(self.wo_id)
        self._main = ttk.Frame(self)
        self._main.pack(fill="both", expand=True)
        top = ttk.Frame(self._main, padding=PAD); top.pack(fill="x")
        ttk.Label(top, text=wo["wo_no"], font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Label(top, text="   full stress mark-up", foreground="#666").pack(side="left")

        cols = ("isos", "cases", "ready")
        self.tv = ttk.Treeview(self._main, columns=cols, show="tree headings",
                               selectmode="browse", height=9)
        self.tv.heading("#0", text="Line")
        self.tv.heading("isos", text="Isos"); self.tv.heading("cases", text="Lift cases")
        self.tv.heading("ready", text="Ready")
        self.tv.column("#0", width=260); self.tv.column("isos", width=70, anchor="center")
        self.tv.column("cases", width=90, anchor="center"); self.tv.column("ready", width=90, anchor="center")
        self.tv.pack(fill="both", expand=True, padx=PAD)
        self.tv.bind("<Double-Button-1>", lambda e: self.open_line())
        self.tv.bind("<Button-3>", self._row_menu)

        plan = ttk.LabelFrame(self._main, text="Sheet plan (export order)", padding=PAD)
        plan.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        self.plan = tk.Text(plan, height=10, wrap="none", font=("Consolas", 9),
                            relief="solid", bd=1, state="disabled")
        self.plan.pack(fill="both", expand=True)

        bar = ttk.Frame(self._main, padding=PAD); bar.pack(fill="x")
        ttk.Button(bar, text="Open line", command=self.open_line).pack(side="left")
        self.pending_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Include PENDING cases", variable=self.pending_var,
                        command=self.refresh).pack(side="left", padx=PAD)
        ttk.Button(bar, text="Export work order...", command=self.export).pack(side="right")
        ttk.Button(bar, text="Preview work order...",
                   command=self.preview_wo).pack(side="right", padx=PAD)

    # ------------------------------------------------------------------
    def refresh(self):
        self.tv.delete(*self.tv.get_children())
        for ln in self.db.lines_for_wo(self.wo_id):
            isos = self.db.isos_for_line(ln["id"])
            cases = self.db.cases_for_line(ln["id"])
            ready = sum(1 for c in cases if c["verdict"] != "PENDING")
            self.tv.insert("", "end", iid=str(ln["id"]), text=ln["line_no"],
                           values=(len(isos), len(cases), f"{ready}/{len(cases)}"))
        self._render_plan()

    def _render_plan(self):
        p = work_order.plan(self.db, self.wo_id, include_pending=self.pending_var.get())
        lines = []
        for pg in p["pages"]:
            tag = pg.get("case_name", os.path.basename(self.db.get_iso(pg["iso_id"])["src_pdf"])
                          if pg["kind"] == "iso" else "")
            lines.append(f"Sheet {pg['sheet_no']:02d}   {pg['kind']:4}   {pg['line_no']:16}   {tag}")
        txt = "\n".join(lines) or "(nothing to export yet)"
        self.plan.config(state="normal"); self.plan.delete("1.0", "end")
        self.plan.insert("1.0", txt); self.plan.config(state="disabled")

    def open_line(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo("Open line", "Select a line first.", parent=self._top())
            return
        self.app.focus_line(int(sel[0]))       # tree + panel swap; no new window

    # ------------------------------------------------------------------
    # Right-click a line row -> archive it (soft; restore from View archive)
    # ------------------------------------------------------------------
    def _row_menu(self, event):
        row = self.tv.identify_row(event.y)
        if not row:
            return
        self.tv.selection_set(row)
        m = tk.Menu(self, tearoff=False)
        m.add_command(label="Archive line",
                      command=lambda: self._archive_line(int(row)))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _archive_line(self, line_id: int):
        ln = self.db.get_line(line_id)
        if not ln:
            return
        if not messagebox.askyesno(
                "Archive line",
                f"Archive line {ln['line_no']}?\n\n"
                "It will be hidden from this work order and excluded from "
                "exports. You can restore it later from View archive.",
                parent=self._top()):
            return
        self.app.flush()
        self.db.archive_line(line_id)
        # rebuild the whole navigation + this panel from the database
        self.app.refresh()
        self.app.say(f"Line {ln['line_no']} archived.")

    # ------------------------------------------------------------------
    # In-panel preview of the full assembled document
    # ------------------------------------------------------------------
    def preview_wo(self):
        self.app.flush()                       # pending edits first
        wo = self.db.get_wo(self.wo_id)
        inc = self.pending_var.get()
        if self._pv is not None:
            self._pv.deactivate(); self._pv.destroy()
        self._main.pack_forget()
        self._pv = PreviewPane(
            self,
            f"Work order {wo['wo_no']}  -  full context"
            + ("  (incl. PENDING)" if inc else ""),
            lambda: preview.wo_pages(self.db, self.wo_id, inc),
            on_back=self._close_preview)
        self._pv.pack(fill="both", expand=True, padx=PAD, pady=PAD)

    def _close_preview(self):
        if self._pv is not None:
            self._pv.destroy(); self._pv = None
        self._main.pack(fill="both", expand=True)
        self.refresh()

    # ------------------------------------------------------------------
    def export(self):
        self.app.flush()                       # A4: pending edits first
        p = work_order.plan(self.db, self.wo_id, include_pending=self.pending_var.get())
        if not p["pages"]:
            messagebox.showwarning("Export", "Nothing to export.", parent=self._top())
            return

        unresolved = self._check_unresolved(p)
        if unresolved:
            if not messagebox.askyesno("Unresolved references",
                    "Some REFER SHEET callouts point at lift cases that won't be "
                    f"in this export:\n\n{chr(10).join(unresolved[:8])}\n\n"
                    "Export anyway? (They will render as 'REFER SHEET ??'.)",
                    parent=self._top()):
                return

        wo = self.db.get_wo(self.wo_id)
        out = filedialog.asksaveasfilename(parent=self._top(), defaultextension=".pdf",
                initialfile=f"{wo['wo_no']}_STRESS_MARKUP.pdf", filetypes=[("PDF", "*.pdf")])
        if not out:
            return
        work_order.export_work_order(self.db, self.wo_id, out,
                                     include_pending=self.pending_var.get())
        self.refresh()
        messagebox.showinfo("Export", f"{p['total']} sheet(s) written:\n{out}",
                            parent=self._top())
        try:
            os.startfile(out)
        except (AttributeError, OSError):
            pass

    def _check_unresolved(self, p) -> List[str]:
        """Iso REFER tokens whose case is neither in the export set nor an
        intentional NOT-OK exclusion (those are suppressed cleanly)."""
        import re
        soc = set(p["sheet_of_case"])
        excluded = p.get("excluded", set())
        bad = []
        for pg in p["pages"]:
            if pg["kind"] != "iso":
                continue
            iso = self.db.get_iso(pg["iso_id"])
            if not iso["layout_json"]:
                continue
            for m in re.findall(r"@@REF:(.+?)@@", iso["layout_json"]):
                if m not in soc and m not in excluded:
                    bad.append(f"{pg['line_no']}: {m}")
        return bad
