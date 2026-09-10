"""
app_ui.py
---------
The single application window.

Left  : navigation tree      Database root -> work orders -> lines
                             -> iso / lift-case leaves.
Right : content panel that SWAPS with the selection - WoPanel for a work
        order, LinePanel for a line / iso / case. No new windows when
        moving around the tree; only the sheet editor opens as a Toplevel.

Lazy loading rules (as agreed):
  * Entering at LINE level, only the route to the top is built:
        Work orders -> <this WO> -> <this line>
    Nothing else is loaded until you click / expand it.
  * Clicking (or expanding) a WORK ORDER loads its immediate children
    (the lines) - not grandchildren.
  * Clicking (or expanding) a LINE loads its leaves - isos and lift cases.
  * Expanding the "Work orders" root lists every WO in the database.

Folder conventions:
  * An "Archive" folder (any case) sitting alongside the lines under a work
    order is skipped when the WO's lines are listed - see _is_archive_line.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Dict, Optional

import markup_weights_ui
import sheet_canvas
from lift_db import LiftDb
from line_ui import LinePanel
from wo_ui import WoPanel

PAD = 6
ROOT_IID = "root"

# Folder names skipped when listing a work order's lines (compared lower-case,
# so "Archive", "archive", "ARCHIVE" all match).
_ARCHIVE_NAMES = {"archive"}


def _is_archive_line(row) -> bool:
    """True when a 'line' row is really the Archive folder (any case).

    Checks the line's own name first, then the basename of its folder path,
    so it catches the case whether the scanner stored 'Archive' as line_no or
    only as the folder.
    """
    if (row["line_no"] or "").strip().lower() in _ARCHIVE_NAMES:
        return True
    try:
        folder = row["folder"] or ""
    except (IndexError, KeyError):
        folder = ""
    base = os.path.basename(folder.rstrip("/\\")).strip().lower()
    return base in _ARCHIVE_NAMES


class DocumenterApp(tk.Tk):
    """
    focus: ("wo", wo_id)  or  ("line", wo_id, line_id)  or  ("root",)
    Decides what the tree starts with and which panel opens first. ("root",)
    is for when the launching folder wasn't recognisable as either a line or
    a work order - opens at the tree root, no DB record created for it.
    """

    def __init__(self, db: LiftDb, focus):
        super().__init__()
        self.db = db
        self.geometry("1360x840")
        self.minsize(1080, 680)

        self._panel: Optional[ttk.Frame] = None
        self._panel_key: Optional[tuple] = None     # ("wo", id) | ("line", id)
        self._populated: set = set()                # tree iids whose children are loaded

        self._build()

        if focus[0] == "line":
            _, wo_id, line_id = focus
            self._seed_line_route(wo_id, line_id)
        elif focus[0] == "wo":
            _, wo_id = focus
            self._seed_wo(wo_id)
        else:
            self._seed_root()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(60, self._raise)

    # ------------------------------------------------------------------
    def _raise(self):
        try:
            self.lift(); self.attributes("-topmost", True); self.focus_force()
            self.after(300, lambda: self._safe(
                lambda: self.attributes("-topmost", False)))
        except tk.TclError:
            pass

    def _safe(self, fn):
        try:
            fn()
        except tk.TclError:
            pass

    def _build(self):
        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        left = ttk.Frame(body); body.add(left, weight=0)

        bar = ttk.Frame(left)
        bar.pack(side="top", fill="x", pady=(0, 4))
        ttk.Button(bar, text="Refresh", width=12,
                   command=self.refresh).pack(side="left")
        ttk.Button(bar, text="View archive",
                   command=self._open_archive).pack(side="left", padx=(4, 0))

        treewrap = ttk.Frame(left)
        treewrap.pack(side="top", fill="both", expand=True)
        self.nav = ttk.Treeview(treewrap, show="tree", selectmode="browse")
        self.nav.column("#0", width=300)
        vsb = ttk.Scrollbar(treewrap, orient="vertical", command=self.nav.yview)
        self.nav.configure(yscrollcommand=vsb.set)
        self.nav.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.nav.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.nav.bind("<<TreeviewOpen>>", lambda e: self._on_open())
        self.nav.bind("<Button-3>", self._nav_menu)
        self.bind("<F5>", lambda e: self.refresh())

        menubar = tk.Menu(self)
        adv = tk.Menu(menubar, tearoff=False)
        adv.add_command(label="Database admin...", command=self._open_db_admin)
        adv.add_command(label="Markup line weights...",
                        command=self._open_markup_weights)
        menubar.add_cascade(label="Advanced", menu=adv)
        self.config(menu=menubar)

        self.content = ttk.Frame(body)
        body.add(self.content, weight=1)

        self.status = ttk.Label(self, text="", anchor="w", padding=(PAD, 2))
        self.status.pack(fill="x")

        self.nav.insert("", "end", iid=ROOT_IID, text="Work orders", open=True)
        self._add_dummy(ROOT_IID)

    def say(self, m: str):
        self.status.config(text=m)
        self.after(4000, lambda: self._safe(
            lambda: self.status.config(text="")))

    # ------------------------------------------------------------------
    # Tree plumbing - lazy children
    # ------------------------------------------------------------------
    def _add_dummy(self, iid: str):
        """Marks a node expandable without loading its children yet."""
        if not self.nav.get_children(iid):
            self.nav.insert(iid, "end", iid=f"{iid}::d", text="...")

    def _drop_dummy(self, iid: str):
        d = f"{iid}::d"
        if self.nav.exists(d):
            self.nav.delete(d)

    def _wo_iid(self, wo_id: int) -> str: return f"wo:{wo_id}"
    def _line_iid(self, line_id: int) -> str: return f"line:{line_id}"

    def _insert_wo(self, wo_row) -> str:
        iid = self._wo_iid(wo_row["id"])
        if not self.nav.exists(iid):
            self.nav.insert(ROOT_IID, "end", iid=iid, text=wo_row["wo_no"])
            self._add_dummy(iid)
        return iid

    def _insert_line(self, wo_iid: str, line_row) -> str:
        iid = self._line_iid(line_row["id"])
        if not self.nav.exists(iid):
            self.nav.insert(wo_iid, "end", iid=iid, text=line_row["line_no"])
            self._add_dummy(iid)
        return iid

    def _populate(self, iid: str):
        """Load a node's immediate children (idempotent)."""
        if iid in self._populated:
            return
        self._drop_dummy(iid)

        if iid == ROOT_IID:
            for wo in self.db.wos():
                self._insert_wo(wo)

        elif iid.startswith("wo:"):
            wo_id = int(iid.split(":")[1])
            for ln in self.db.lines_for_wo(wo_id):
                if _is_archive_line(ln):        # skip the Archive folder + contents
                    continue
                self._insert_line(iid, ln)

        elif iid.startswith("line:"):
            line_id = int(iid.split(":")[1])
            for iso in self.db.isos_for_line(line_id):
                self.nav.insert(iid, "end", iid=f"iso:{iso['id']}",
                                text=f"[iso]  {os.path.basename(iso['src_pdf'])}"
                                     f"  p{iso['src_page'] + 1}")
            for c in self.db.cases_for_line(line_id):
                mark = {"OK": "[OK] ", "NOT OK": "[X] ",
                        "PENDING": ""}.get(c["verdict"], "")
                self.nav.insert(iid, "end", iid=f"case:{c['id']}",
                                text=f"{mark}{c['case_name']}")

        self._populated.add(iid)

    def reload_line(self, line_id: int):
        """Re-list a line's leaves (verdict marks, new isos/cases)."""
        iid = self._line_iid(line_id)
        if not self.nav.exists(iid) or iid not in self._populated:
            return
        sel = self.nav.selection()
        keep = sel[0] if sel else None
        for ch in self.nav.get_children(iid):
            self.nav.delete(ch)
        self._populated.discard(iid)
        self._populate(iid)
        if keep and self.nav.exists(keep):
            self.nav.selection_set(keep)

    # ------------------------------------------------------------------
    # Refresh - full work-order rescan + tree rebuild
    # ------------------------------------------------------------------
    def _expanded_iids(self) -> list:
        """Currently-expanded node iids, root-first, dummies skipped."""
        out = []

        def walk(node):
            for ch in self.nav.get_children(node):
                if ch.endswith("::d"):
                    continue
                if self.tk.getboolean(self.nav.item(ch, "open")):
                    out.append(ch)
                walk(ch)

        walk(ROOT_IID)
        return out

    def _rescan_from_disk(self):
        """
        Ingest any newly generated case sidecars (*_liftmeta.json) for the work
        orders currently loaded in the tree, so Refresh pulls in cases created
        while the app was open. Idempotent; a line with no sidecars is a no-op.
        """
        for iid in list(self._populated):
            if not iid.startswith("wo:"):
                continue
            wo_id = int(iid.split(":")[1])
            wo = self.db.get_wo(wo_id)
            wo_folder = (wo["folder"] if wo else "") or ""
            for ln in self.db.lines_for_wo(wo_id):
                folder = ln["folder"] or (
                    os.path.join(wo_folder, ln["line_no"]) if wo_folder else "")
                if not folder:
                    continue
                try:
                    self.db.ingest_sidecars(wo_id, folder)
                except Exception as exc:              # never let a scan kill refresh
                    self.say(f"Sync skipped for {ln['line_no']} ({exc}).")

    def refresh(self):
        """Full work-order rescan and tree rebuild, preserving expansion and
        selection where still valid. Bound to the Refresh button and F5."""
        self.flush()                                # persist pending iso note first

        open_iids = self._expanded_iids()
        sel = self.nav.selection()
        keep_sel = sel[0] if sel else None

        self._rescan_from_disk()                    # optional filesystem walk

        # tear the tree down to the root
        for ch in self.nav.get_children(ROOT_IID):
            self.nav.delete(ch)
        self._populated.clear()
        self._add_dummy(ROOT_IID)

        # rebuild: work orders, then re-expand what was open (WOs before lines)
        self._populate(ROOT_IID)
        self.nav.item(ROOT_IID, open=True)
        for iid in open_iids:
            if iid.startswith("wo:") and self.nav.exists(iid):
                self._populate(iid)
                self.nav.item(iid, open=True)
        for iid in open_iids:
            if iid.startswith("line:") and self.nav.exists(iid):
                self._populate(iid)
                self.nav.item(iid, open=True)

        # force the content panel to rebuild against fresh data
        self._panel_key = None

        # restore selection, or fall back cleanly if it is gone
        if keep_sel and self.nav.exists(keep_sel):
            self.nav.selection_set(keep_sel)
            self.nav.see(keep_sel)
        else:
            self.nav.selection_set(ROOT_IID)
            self._show_blank("Structure refreshed - previous item no longer present.")
        self.say("Structure refreshed.")

    # ------------------------------------------------------------------
    # Seeding - what exists when the window first opens
    # ------------------------------------------------------------------
    def _seed_wo(self, wo_id: int):
        wo = self.db.get_wo(wo_id)
        iid = self._insert_wo(wo)
        self._populate(iid)                 # immediate children (lines) only
        self.nav.item(iid, open=True)
        self.nav.selection_set(iid)         # -> triggers WoPanel

    def _seed_root(self):
        """No specific line/WO was recognised at launch - show the tree root
        (every real work order already in the database) so the user can
        navigate to one themselves. Creates no DB record."""
        self._populate(ROOT_IID)
        self.nav.item(ROOT_IID, open=True)
        self.nav.selection_set(ROOT_IID)
        self._show_blank("Select a work order.")

    def _seed_line_route(self, wo_id: int, line_id: int):
        """Route to the top ONLY: root -> this WO -> this line."""
        wo = self.db.get_wo(wo_id)
        wo_iid = self._insert_wo(wo)        # NOT populated - route only
        ln = self.db.get_line(line_id)
        line_iid = self._insert_line(wo_iid, ln)
        self.nav.item(wo_iid, open=True)
        self.nav.selection_set(line_iid)    # -> triggers LinePanel
        self.after(250, lambda: self._offer_iso(line_id))

    def _offer_iso(self, line_id: int):
        p = self._panel
        if (isinstance(p, LinePanel) and p.line_id == line_id):
            p.offer_iso_upload()

    # ------------------------------------------------------------------
    # Selection -> panel swap
    # ------------------------------------------------------------------
    def _on_open(self):
        iid = self.nav.focus()
        if iid and not iid.endswith("::d"):
            self._populate(iid)

    def _on_select(self):
        sel = self.nav.selection()
        if not sel:
            return
        iid = sel[0]
        if iid.endswith("::d"):
            return

        if iid == ROOT_IID:
            self._populate(iid)
            self._show_blank("Select a work order.")
            return

        kind, sid = iid.split(":", 1)
        sid = int(sid)

        if kind == "wo":
            self._populate(iid)
            self.nav.item(iid, open=True)
            self._show_wo(sid)

        elif kind == "line":
            self._populate(iid)
            self.nav.item(iid, open=True)
            self._show_line(sid).show_overview()

        elif kind == "iso":
            iso = self.db.get_iso(sid)
            if iso:
                self._show_line(iso["line_id"]).show_iso(sid)

        elif kind == "case":
            case = self.db.get_case(sid)
            if case:
                self._show_line(case["line_id"]).show_case(sid)

    # ------------------------------------------------------------------
    def _swap(self, key: tuple, build) -> ttk.Frame:
        if self._panel_key == key and self._panel is not None:
            return self._panel
        if self._panel is not None:
            if hasattr(self._panel, "on_hidden"):
                self._panel.on_hidden()     # flush edits, release wheel binding
            self._panel.destroy()
        self._panel = build()
        self._panel.pack(fill="both", expand=True)
        self._panel_key = key
        return self._panel

    def _show_blank(self, msg: str):
        def build():
            f = ttk.Frame(self.content, padding=PAD)
            ttk.Label(f, text=msg, foreground="#777").pack(anchor="nw")
            return f
        self._swap(("blank", msg), build)
        self.title("Lift Mark-up Documenter")

    def _show_wo(self, wo_id: int) -> "WoPanel":
        wo = self.db.get_wo(wo_id)
        panel = self._swap(("wo", wo_id),
                           lambda: WoPanel(self.content, self, self.db, wo_id,
                                           wo["folder"] or ""))
        self.title(f"Lift Mark-up  -  work order {wo['wo_no']}")
        return panel

    def _show_line(self, line_id: int) -> "LinePanel":
        ln = self.db.get_line(line_id)
        wo = self.db.get_wo(ln["wo_id"])
        folder = ln["folder"] or os.path.join(wo["folder"] or "", ln["line_no"])
        panel = self._swap(("line", line_id),
                           lambda: LinePanel(self.content, self, self.db,
                                             ln["wo_id"], line_id, folder))
        self.title(f"Lift Mark-up  -  line {ln['line_no']}  ({wo['wo_no']})")
        return panel

    def focus_line(self, line_id: int):
        """Programmatic navigation (e.g. double-click in the WO table)."""
        ln = self.db.get_line(line_id)
        if not ln:
            return
        wo_iid = self._wo_iid(ln["wo_id"])
        if not self.nav.exists(wo_iid):
            self._insert_wo(self.db.get_wo(ln["wo_id"]))
        self._insert_line(wo_iid, ln)
        self.nav.item(wo_iid, open=True)
        self.nav.selection_set(self._line_iid(line_id))
        self.nav.see(self._line_iid(line_id))

    def focus_case(self, case_id: int):
        """Select a case leaf in the tree (renders its detail view)."""
        case = self.db.get_case(case_id)
        if not case:
            return
        ln = self.db.get_line(case["line_id"])
        wo_iid = self._wo_iid(ln["wo_id"])
        if not self.nav.exists(wo_iid):
            self._insert_wo(self.db.get_wo(ln["wo_id"]))
        line_iid = self._insert_line(wo_iid, ln)
        self._populate(line_iid)
        self.nav.item(wo_iid, open=True)
        self.nav.item(line_iid, open=True)
        iid = f"case:{case_id}"
        if self.nav.exists(iid):
            self.nav.selection_set(iid)
            self.nav.see(iid)

    def flush(self):
        """Persist any pending edits (iso note) - call before exports."""
        if isinstance(self._panel, LinePanel):
            self._panel.flush_pending()

    # ------------------------------------------------------------------
    # Archive (soft) - tree right-click, and the archive browser
    # ------------------------------------------------------------------
    def _nav_menu(self, event):
        iid = self.nav.identify_row(event.y)
        if not iid or iid.endswith("::d") or iid == ROOT_IID:
            return
        self.nav.selection_set(iid)
        kind, sid = iid.split(":", 1)
        m = tk.Menu(self, tearoff=False)
        if kind == "wo":
            m.add_command(label="Archive work order",
                          command=lambda: self._archive_wo(int(sid)))
        elif kind == "line":
            m.add_command(label="Archive line",
                          command=lambda: self._archive_line(int(sid)))
        elif kind == "case":
            m.add_command(label="Archive case",
                          command=lambda: self._archive_case(int(sid)))
        else:
            return
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _archive_wo(self, wo_id: int):
        wo = self.db.get_wo(wo_id)
        if not wo:
            return
        if not messagebox.askyesno(
                "Archive work order",
                f"Archive work order {wo['wo_no']}?\n\n"
                "It (and all its lines) will be hidden from the tree and "
                "excluded from exports. You can restore it from View archive.",
                parent=self):
            return
        self.flush()
        self.db.archive_wo(wo_id)
        self.refresh()
        self.say(f"Work order {wo['wo_no']} archived.")

    def _archive_line(self, line_id: int):
        ln = self.db.get_line(line_id)
        if not ln:
            return
        if not messagebox.askyesno(
                "Archive line",
                f"Archive line {ln['line_no']}?\n\n"
                "It will be hidden from its work order and excluded from "
                "exports. You can restore it from View archive.",
                parent=self):
            return
        self.flush()
        self.db.archive_line(line_id)
        self.refresh()
        self.say(f"Line {ln['line_no']} archived.")

    def _archive_case(self, case_id: int):
        case = self.db.get_case(case_id)
        if not case:
            return
        if not messagebox.askyesno(
                "Archive case",
                f"Archive lift case {case['case_name']}?\n\n"
                "It will be hidden from its line and excluded from exports. "
                "You can restore it from View archive.",
                parent=self):
            return
        self.flush()
        self.db.archive_case(case_id)
        self.reload_line(case["line_id"])
        if isinstance(self._panel, LinePanel) and self._panel.case_id == case_id:
            self._panel.show_overview()
        self.say(f"Case {case['case_name']} archived.")

    def _open_archive(self):
        _ArchiveWindow(self, self.db)

    def _open_db_admin(self):
        _DbAdminWindow(self, self.db)

    def _open_markup_weights(self):
        markup_weights_ui.open_markup_weights(
            self, on_applied=self._refresh_after_weights)

    def _refresh_after_weights(self):
        """Repaint what's on screen after Set as default / Reset. Weights are
        resolved at draw time, so this only refreshes the current view - every
        other document already reflects the change on its next render."""
        # 1) any open sheet-editor windows (their master is this app)
        for w in self.winfo_children():
            if isinstance(w, tk.Toplevel):
                self._redraw_canvases_in(w)
        # 2) the live line preview in the current panel
        if isinstance(self._panel, LinePanel):
            try:
                self._panel.show_overview()
            except Exception:
                pass

    def _redraw_canvases_in(self, widget):
        for ch in widget.winfo_children():
            if isinstance(ch, sheet_canvas.SheetCanvas):
                try:
                    ch.redraw()
                except Exception:
                    pass
            else:
                self._redraw_canvases_in(ch)

    # ------------------------------------------------------------------
    def _on_close(self):
        self.flush()
        self.destroy()


# ======================================================================
# Archive browser  (soft-archived work orders and lines; restore only)
# ======================================================================
class _ArchiveWindow(tk.Toplevel):
    def __init__(self, app: "DocumenterApp", db: LiftDb):
        super().__init__(app)
        self.app = app
        self.db = db
        self.title("Archive")
        self.geometry("640x760")
        self.transient(app)
        self._build()
        self._reload()
        self.grab_set()

    def _build(self):
        wof = ttk.LabelFrame(self, text="Archived work orders", padding=PAD)
        wof.pack(fill="both", expand=True, padx=PAD, pady=(PAD, 0))
        self.wo_tv = ttk.Treeview(wof, show="tree", selectmode="browse", height=6)
        self.wo_tv.pack(side="left", fill="both", expand=True)
        wsb = ttk.Scrollbar(wof, orient="vertical", command=self.wo_tv.yview)
        self.wo_tv.configure(yscrollcommand=wsb.set); wsb.pack(side="right", fill="y")
        ttk.Button(self, text="Restore work order",
                   command=self._restore_wo).pack(anchor="w", padx=PAD, pady=(2, PAD))

        lnf = ttk.LabelFrame(self, text="Archived lines", padding=PAD)
        lnf.pack(fill="both", expand=True, padx=PAD, pady=(0, 0))
        self.ln_tv = ttk.Treeview(lnf, columns=("wo",), show="tree headings",
                                  selectmode="browse", height=8)
        self.ln_tv.heading("#0", text="Line"); self.ln_tv.heading("wo", text="Work order")
        self.ln_tv.column("#0", width=320); self.ln_tv.column("wo", width=220)
        self.ln_tv.pack(side="left", fill="both", expand=True)
        lsb = ttk.Scrollbar(lnf, orient="vertical", command=self.ln_tv.yview)
        self.ln_tv.configure(yscrollcommand=lsb.set); lsb.pack(side="right", fill="y")
        ttk.Button(self, text="Restore line",
                   command=self._restore_line).pack(anchor="w", padx=PAD, pady=(2, PAD))

        cf = ttk.LabelFrame(self, text="Archived lift cases", padding=PAD)
        cf.pack(fill="both", expand=True, padx=PAD, pady=(0, 0))
        self.case_tv = ttk.Treeview(cf, columns=("line", "wo"), show="tree headings",
                                    selectmode="browse", height=8)
        self.case_tv.heading("#0", text="Case"); self.case_tv.heading("line", text="Line")
        self.case_tv.heading("wo", text="Work order")
        self.case_tv.column("#0", width=240); self.case_tv.column("line", width=160)
        self.case_tv.column("wo", width=140)
        self.case_tv.pack(side="left", fill="both", expand=True)
        csb = ttk.Scrollbar(cf, orient="vertical", command=self.case_tv.yview)
        self.case_tv.configure(yscrollcommand=csb.set); csb.pack(side="right", fill="y")
        ttk.Button(self, text="Restore case",
                   command=self._restore_case).pack(anchor="w", padx=PAD, pady=(2, PAD))

        ttk.Button(self, text="Close", command=self.destroy).pack(side="right",
                                                                   padx=PAD, pady=(0, PAD))

    def _reload(self):
        self.wo_tv.delete(*self.wo_tv.get_children())
        for wo in self.db.archived_wos():
            self.wo_tv.insert("", "end", iid=str(wo["id"]), text=wo["wo_no"])
        self.ln_tv.delete(*self.ln_tv.get_children())
        for ln in self.db.archived_lines():
            self.ln_tv.insert("", "end", iid=str(ln["id"]), text=ln["line_no"],
                              values=(ln["wo_no"],))
        self.case_tv.delete(*self.case_tv.get_children())
        for c in self.db.archived_cases():
            self.case_tv.insert("", "end", iid=str(c["id"]), text=c["case_name"],
                                values=(c["line_no"], c["wo_no"]))

    def _restore_wo(self):
        sel = self.wo_tv.selection()
        if not sel:
            messagebox.showinfo("Restore", "Select an archived work order.", parent=self)
            return
        self.db.restore_wo(int(sel[0]))
        self._reload()
        self.app.refresh()
        self.app.say("Work order restored.")

    def _restore_line(self):
        sel = self.ln_tv.selection()
        if not sel:
            messagebox.showinfo("Restore", "Select an archived line.", parent=self)
            return
        self.db.restore_line(int(sel[0]))
        self._reload()
        self.app.refresh()
        self.app.say("Line restored.")

    def _restore_case(self):
        sel = self.case_tv.selection()
        if not sel:
            messagebox.showinfo("Restore", "Select an archived case.", parent=self)
            return
        case_id = int(sel[0])
        case = self.db.get_case(case_id)
        self.db.restore_case(case_id)
        self._reload()
        if case:
            self.app.reload_line(case["line_id"])
        self.app.say("Case restored.")


# ======================================================================
# Database admin  (ADVANCED - permanent delete, typed confirm + backup)
# ======================================================================
class _DbAdminWindow(tk.Toplevel):
    def __init__(self, app: "DocumenterApp", db: LiftDb):
        super().__init__(app)
        self.app = app
        self.db = db
        self.title("Database admin  -  permanent delete")
        self.geometry("620x580")
        self.transient(app)
        self._build()
        self._reload()
        self.grab_set()

    def _build(self):
        warn = ("Permanent delete. Removes the work order, line, or lift case and "
                "ALL of its data (isos, lift cases, supports, lift points) plus the "
                "associated files under the database folder. This cannot be "
                "undone. Archived items are shown too.")
        ttk.Label(self, text=warn, wraplength=580, foreground="#a00",
                  padding=PAD).pack(fill="x")

        tf = ttk.Frame(self, padding=(PAD, 0)); tf.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(tf, show="tree", selectmode="browse")
        self.tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y")

        bar = ttk.Frame(self, padding=PAD); bar.pack(fill="x")
        self.backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Back up database before deleting",
                        variable=self.backup_var).pack(side="left")
        ttk.Button(bar, text="Delete selected (permanent)",
                   command=self._delete).pack(side="right")
        ttk.Button(bar, text="Close", command=self.destroy).pack(side="right", padx=PAD)

    def _reload(self):
        self.tv.delete(*self.tv.get_children())
        for wo in self.db.wos(include_archived=True):
            tag = "  [archived]" if wo["archived"] else ""
            wid = self.tv.insert("", "end", iid=f"wo:{wo['id']}",
                                 text=f"{wo['wo_no']}{tag}", open=False)
            for ln in self.db.lines_for_wo(wo["id"], include_archived=True):
                ltag = "  [archived]" if ln["archived"] else ""
                lid = self.tv.insert(wid, "end", iid=f"line:{ln['id']}",
                                     text=f"{ln['line_no']}{ltag}")
                for c in self.db.cases_for_line(ln["id"], include_archived=True):
                    ctag = "  [archived]" if c["archived"] else ""
                    self.tv.insert(lid, "end", iid=f"case:{c['id']}",
                                   text=f"{c['case_name']}{ctag}")

    def _delete(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo("Delete", "Select a work order or line.", parent=self)
            return
        iid = sel[0]
        kind, sid = iid.split(":", 1)
        sid = int(sid)

        if kind == "wo":
            wo = self.db.get_wo(sid)
            if not wo:
                return
            name, label = wo["wo_no"], f"work order {wo['wo_no']}"
        elif kind == "line":
            ln = self.db.get_line(sid)
            if not ln:
                return
            name, label = ln["line_no"], f"line {ln['line_no']}"
        else:
            case = self.db.get_case(sid)
            if not case:
                return
            name, label = case["case_name"], f"lift case {case['case_name']}"

        typed = simpledialog.askstring(
            "Confirm permanent delete",
            f"This permanently deletes {label} and all associated data and "
            f"files.\nThis cannot be undone.\n\nType  {name}  to confirm:",
            parent=self)
        if typed is None:
            return
        if typed.strip() != name:
            messagebox.showinfo("Cancelled", "Name did not match - nothing deleted.",
                                parent=self)
            return

        if self.backup_var.get():
            try:
                dest = self.db.backup()
                self.app.say(f"Backup written: {os.path.basename(dest)}")
            except OSError as exc:
                if not messagebox.askyesno(
                        "Backup failed",
                        f"Backup could not be written ({exc}).\nDelete anyway?",
                        parent=self):
                    return

        if kind == "wo":
            summ = self.db.purge_wo(sid, delete_files=True)
        elif kind == "line":
            summ = self.db.purge_line(sid, delete_files=True)
        else:
            summ = self.db.purge_case(sid, delete_files=True)

        self._reload()
        self.app.refresh()
        messagebox.showinfo(
            "Deleted",
            "Removed: " + ", ".join(f"{v} {k}" for k, v in summ.items() if v),
            parent=self)
