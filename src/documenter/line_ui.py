"""
line_ui.py
----------
Line mode CONTENT PANEL (right side of the app window).

Navigation now lives in the application tree (app_ui) - this panel only
renders the selected item: the line overview, a lift case's data sheet
(screenshot, forces, functions, note, verdict, sheet editor), or an iso's
note / editor launcher.

Iso note persistence (the "notes textbox does not save on exit" fix):
  * the note is flushed to the DB on FocusOut of the textbox,
  * on any panel re-render / selection change (flush_pending in _clear),
  * on panel swap and app close (on_hidden / app.flush),
  * before opening the iso editor and before any export,
  * and an edit made to the note box INSIDE the sheet editor is written
    back to the DB on editor save, so the two never diverge.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Dict, Optional

from PIL import Image, ImageTk
from pypdf import PdfReader

import case_meta_ui
import catalog
import clipboard_io as clip
import export
import lift_calc as calc
import preview
import sheet_canvas
import sheet_model as SM
from lift_db import LiftDb
from preview_pane import PreviewPane

PAD = 6
THUMB_MAX = (460, 320)


class LinePanel(ttk.Frame):
    def __init__(self, master, app, db: LiftDb, wo_id: int, line_id: int, folder: str):
        super().__init__(master)
        self.app = app                    # DocumenterApp - say(), reload_line(), flush()
        self.db = db
        self.wo_id = wo_id
        self.line_id = line_id
        self.folder = folder
        self.line_no = db.line_no(line_id)
        self.case_id: Optional[int] = None
        self.iso_id: Optional[int] = None
        self._thumb = None
        self._page_imgs: list = []            # inline preview PhotoImage refs
        self._render_gen = 0                  # invalidates stale async renders
        self._fn_vars: Dict[int, tk.StringVar] = {}
        self._force_vars: Dict[int, tk.StringVar] = {}
        self._offered_iso = False

        # pending iso-note state (dirty tracking)
        self._note_iso_id: Optional[int] = None
        self._note_loaded: str = ""

        self._build()

    # ------------------------------------------------------------------
    def _say(self, m):
        self.app.say(m)

    def _top(self):
        return self.winfo_toplevel()

    def _build(self):
        top = ttk.Frame(self, padding=PAD); top.pack(fill="x")
        ttk.Label(top, text=self.line_no, font=("Segoe UI", 13, "bold")).pack(side="left")
        wo = self.db.get_wo(self.wo_id)
        ttk.Label(top, text=f"   work order {wo['wo_no']}", foreground="#666").pack(side="left")
        ttk.Button(top, text="Upload iso...", command=self.upload_iso).pack(side="right")
        ttk.Button(top, text="Add existing case...",
                   command=self.add_existing_case).pack(side="right", padx=PAD)
        ttk.Button(top, text="Sync cases",
                   command=self.sync_cases).pack(side="right", padx=(0, PAD))

        self._cv = tk.Canvas(self, highlightthickness=0)
        self._vsb = ttk.Scrollbar(self, orient="vertical", command=self._cv.yview)
        self.sheet = ttk.Frame(self._cv)
        self.sheet.bind("<Configure>",
                        lambda e: self._cv.configure(scrollregion=self._cv.bbox("all")))
        self._cv_win = self._cv.create_window((0, 0), window=self.sheet, anchor="nw")
        # keep the inner frame the full width of the canvas, so fill='x' / grid
        # weights fill the window and content doesn't collapse after a rebuild
        self._cv.bind("<Configure>",
                      lambda e: self._cv.itemconfigure(self._cv_win, width=e.width))
        self._cv.configure(yscrollcommand=self._vsb.set)
        self._cv.pack(side="left", fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self._vsb.pack(side="right", fill="y")
        self._pv: Optional[PreviewPane] = None
        self._rebind_wheel()

    def _rebind_wheel(self):
        self.bind_all("<MouseWheel>", self._wheel)

    def _wheel(self, e):
        try:
            self._cv.yview_scroll(int(-e.delta / 120), "units")
        except tk.TclError:
            pass

    def on_hidden(self):
        """Called by the app before the panel is destroyed on a swap."""
        self.flush_pending()
        if self._pv is not None:
            self._pv.deactivate()
        try:
            self.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # In-panel preview (replaces the detail area until Back)
    # ------------------------------------------------------------------
    def _show_preview(self, title, pages_fn):
        self.flush_pending()                  # A4: preview reads the DB
        if self._pv is not None:
            self._pv.deactivate(); self._pv.destroy()
        self._cv.pack_forget(); self._vsb.pack_forget()
        self._pv = PreviewPane(self, title, pages_fn, on_back=self._close_preview)
        self._pv.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

    def _close_preview(self):
        if self._pv is not None:
            self._pv.destroy(); self._pv = None
        self._cv.pack(side="left", fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self._vsb.pack(side="right", fill="y")
        self._rebind_wheel()

    def _ensure_detail(self):
        """Tree selection changed while a preview was open - drop back."""
        if self._pv is not None:
            self._pv.deactivate()
            self._close_preview()

    # ------------------------------------------------------------------
    # Inline preview embedding (pages rendered INTO the detail area)
    # ------------------------------------------------------------------
    def _embed_pages(self, parent, pages_fn, note="Rendering preview..."):
        """
        Async-render pages_fn() -> [PIL images] into `parent`, scaled to the
        width of `parent`. A stale render (selection changed meanwhile) is
        dropped via the generation counter. The width is read from the laid-out
        widget with a short retry, so a rebuild (Refresh) still fills the column
        instead of collapsing to a narrow fallback.
        """
        gen = self._render_gen
        lbl = ttk.Label(parent, text=note, foreground="#777")
        lbl.pack(anchor="w", pady=4)

        def done(retries=0):
            if gen != self._render_gen:
                return
            try:
                self.update_idletasks()
                avail = parent.winfo_width()
            except tk.TclError:
                return
            if avail <= 1 and retries < 40:        # geometry not settled yet
                self.after(50, lambda: done(retries + 1))
                return
            avail = max(320, avail - 24)
            try:
                pages = pages_fn()
            except Exception as ex:            # keep the panel alive
                try:
                    lbl.config(text=f"Preview failed: {ex}")
                except tk.TclError:
                    pass
                return
            if gen != self._render_gen:
                return
            try:
                lbl.destroy()
                n = len(pages)
                if not n:
                    ttk.Label(parent, text="(nothing to preview)",
                              foreground="#777").pack(anchor="w")
                    return
                for i, img in enumerate(pages, start=1):
                    if img.width > avail:
                        s = avail / img.width
                        img = img.resize((avail, max(1, int(img.height * s))),
                                         Image.LANCZOS)
                    ph = ImageTk.PhotoImage(img)
                    self._page_imgs.append(ph)
                    tk.Label(parent, image=ph, relief="solid", bd=1
                             ).pack(anchor="w", pady=(4, 0))
                    if n > 1:
                        ttk.Label(parent, text=f"Page {i} of {n}",
                                  foreground="#777", font=("Segoe UI", 8)
                                  ).pack(anchor="w")
            except tk.TclError:
                pass

        self.after(30, done)

    # ------------------------------------------------------------------
    # Iso note persistence
    # ------------------------------------------------------------------
    def flush_pending(self):
        """Write the iso note textbox to the DB if it changed. Safe anywhere."""
        if self._note_iso_id is None:
            return
        try:
            txt = self.iso_note.get("1.0", "end-1c")
        except (tk.TclError, AttributeError):
            self._note_iso_id = None
            return
        if txt != self._note_loaded:
            self.db.set_iso_note(self._note_iso_id, txt)
            self._note_loaded = txt

    def _save_iso_note(self):
        self.flush_pending()
        self._say("Iso note saved.")

    # ------------------------------------------------------------------
    # Public entry points (called by the app on tree selection)
    # ------------------------------------------------------------------
    def show_overview(self):
        self._ensure_detail()
        self._clear()
        self.case_id = self.iso_id = None
        isos = self.db.isos_for_line(self.line_id)
        cases = self.db.cases_for_line(self.line_id)
        lid = self.line_id

        cont = ttk.Frame(self.sheet)
        cont.pack(fill="both", expand=True, padx=(0, PAD))
        cont.columnconfigure(0, weight=0, minsize=300)   # export sequence (left)
        cont.columnconfigure(1, weight=1)                # line preview (grows)
        cont.rowconfigure(0, weight=1)

        # LEFT: export sequence - two stacked reorderable lists (isos, cases)
        left = ttk.LabelFrame(cont, text="Export sequence", padding=PAD)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, PAD))
        left.columnconfigure(0, weight=1)

        iso_box = ttk.LabelFrame(left, text="Isometrics", padding=PAD)
        iso_box.grid(row=0, column=0, sticky="new", pady=(0, PAD))
        iso_box.columnconfigure(0, weight=1)
        self._build_sequence(iso_box, isos)

        case_box = ttk.LabelFrame(left, text="Lift cases", padding=PAD)
        case_box.grid(row=1, column=0, sticky="new")
        case_box.columnconfigure(0, weight=1)
        self._build_case_sequence(case_box, cases)

        # RIGHT: the line preview, all cases, in export order
        right = ttk.LabelFrame(cont, text="Line preview  -  isos + all cases, export order",
                               padding=PAD)
        right.grid(row=0, column=1, sticky="nsew")
        bar = ttk.Frame(right); bar.pack(fill="x")
        ttk.Button(bar, text="Refresh", command=self.show_overview).pack(side="right")
        body = ttk.Frame(right); body.pack(fill="both", expand=True)
        if isos or cases:
            self._embed_pages(body, lambda: preview.line_pages(self.db, lid))
        else:
            ttk.Label(body, text="(nothing to preview yet)",
                      foreground="#777").pack(anchor="w")

    def show_case(self, case_id: int):
        self._ensure_detail()
        self.case_id, self.iso_id = case_id, None
        self._render_case()

    def show_iso(self, iso_id: int):
        self._ensure_detail()
        self.iso_id, self.case_id = iso_id, None
        self._render_iso()

    def _build_sequence(self, parent, isos):
        """Reorderable iso order (the export sequence); persists to seq, which
        the tree, preview and work-order export all follow. Drag rows to
        reorder (preferred), or use Move up/down."""
        parent.columnconfigure(0, weight=1)
        if not isos:
            ttk.Label(parent, text="(no isometrics yet)",
                      foreground="#777").grid(row=0, column=0, sticky="w")
            return
        self.iso_order_lb = tk.Listbox(parent, height=min(14, max(3, len(isos))),
                                       activestyle="dotbox", exportselection=False)
        self._iso_order_ids = []
        for iso in isos:
            self.iso_order_lb.insert(
                "end", f"{os.path.basename(iso['src_pdf'])}  (p{iso['src_page']+1})")
            self._iso_order_ids.append(iso["id"])
        self.iso_order_lb.grid(row=0, column=0, sticky="ew")
        self.iso_order_lb.selection_set(0)
        self._bind_drag_reorder(
            self.iso_order_lb, self._iso_order_ids,
            lambda ids: self.db.reorder_isos(self.line_id, ids))
        bar = ttk.Frame(parent); bar.grid(row=0, column=1, sticky="n", padx=(PAD, 0))
        ttk.Button(bar, text="Move up", width=10,
                   command=lambda: self._move_iso(-1)).pack()
        ttk.Button(bar, text="Move down", width=10,
                   command=lambda: self._move_iso(1)).pack(pady=(4, 0))
        ttk.Label(parent, text="Drag a row to reorder, or use Move up/down. Order "
                               "sets the sequence in the tree, preview and "
                               "work-order export.", foreground="#777",
                  font=("Segoe UI", 8)).grid(row=1, column=0, columnspan=2,
                                             sticky="w", pady=(4, 0))

    def _bind_drag_reorder(self, listbox, order_ids, persist):
        """
        Wires click-drag-release reordering onto a Listbox whose row i
        corresponds to order_ids[i]. Reorders the Listbox and order_ids
        live as the mouse moves - cheap, no DB write, no panel rebuild -
        so dragging a case/iso across a long list is one continuous motion
        instead of many "click, wait for the whole panel to rebuild, click
        again" steps via Move up/down. Only the FINAL position is persisted
        (persist(order_ids), e.g. db.reorder_cases/reorder_isos) and the
        tree/preview refreshed, on mouse release.
        """
        state = {"start": None}

        def on_press(event):
            idx = listbox.nearest(event.y)
            if 0 <= idx < listbox.size():
                state["start"] = idx
                listbox.selection_clear(0, "end")
                listbox.selection_set(idx)

        def on_motion(event):
            if state["start"] is None:
                return
            idx = listbox.nearest(event.y)
            if idx < 0 or idx == state["start"]:
                return
            text = listbox.get(state["start"])
            listbox.delete(state["start"])
            listbox.insert(idx, text)
            order_ids.insert(idx, order_ids.pop(state["start"]))
            listbox.selection_clear(0, "end")
            listbox.selection_set(idx)
            state["start"] = idx

        def on_release(event):
            if state["start"] is None:
                return
            state["start"] = None
            if persist(list(order_ids)):
                self.app.reload_line(self.line_id)   # tree order follows
                self.show_overview()                 # re-render list + preview
                self._say("Order updated.")

        listbox.bind("<Button-1>", on_press)
        listbox.bind("<B1-Motion>", on_motion)
        listbox.bind("<ButtonRelease-1>", on_release)

    def _move_iso(self, delta):
        sel = self.iso_order_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        iso_id = self._iso_order_ids[idx]
        if self.db.move_iso(self.line_id, iso_id, delta):
            self.app.reload_line(self.line_id)     # tree order follows
            self.show_overview()                   # re-render list + preview
            new_idx = idx + delta
            # reselect the moved row in its new position
            self.iso_order_lb.selection_clear(0, "end")
            self.iso_order_lb.selection_set(new_idx)
            self.iso_order_lb.see(new_idx)
            self._say("Iso order updated.")

    def _build_case_sequence(self, parent, cases):
        """Reorderable lift-case order (part of the export sequence); persists to
        lift_cases.seq, which the tree, preview and work-order export all
        follow. Drag rows to reorder (preferred), or use Move up/down."""
        parent.columnconfigure(0, weight=1)
        if not cases:
            ttk.Label(parent, text="(no lift cases yet)",
                      foreground="#777").grid(row=0, column=0, sticky="w")
            return
        self.case_order_lb = tk.Listbox(parent, height=min(14, max(3, len(cases))),
                                        activestyle="dotbox", exportselection=False)
        self._case_order_ids = []
        for c in cases:
            mark = {"OK": "[OK] ", "NOT OK": "[X] ",
                    "PENDING": ""}.get(c["verdict"], "")
            self.case_order_lb.insert("end", f"{mark}{c['case_name']}")
            self._case_order_ids.append(c["id"])
        self.case_order_lb.grid(row=0, column=0, sticky="ew")
        self.case_order_lb.selection_set(0)
        self._bind_drag_reorder(
            self.case_order_lb, self._case_order_ids,
            lambda ids: self.db.reorder_cases(self.line_id, ids))
        bar = ttk.Frame(parent); bar.grid(row=0, column=1, sticky="n", padx=(PAD, 0))
        ttk.Button(bar, text="Move up", width=10,
                   command=lambda: self._move_case(-1)).pack()
        ttk.Button(bar, text="Move down", width=10,
                   command=lambda: self._move_case(1)).pack(pady=(4, 0))
        ttk.Label(parent, text="Drag a row to reorder, or use Move up/down. Order "
                               "sets the case sequence in the tree, preview "
                               "and work-order export.", foreground="#777",
                  font=("Segoe UI", 8)).grid(row=1, column=0, columnspan=2,
                                             sticky="w", pady=(4, 0))

    def _move_case(self, delta):
        sel = self.case_order_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        case_id = self._case_order_ids[idx]
        if self.db.move_case(self.line_id, case_id, delta):
            self.app.reload_line(self.line_id)     # tree order follows
            self.show_overview()                   # re-render list + preview
            new_idx = idx + delta
            # reselect the moved row in its new position
            self.case_order_lb.selection_clear(0, "end")
            self.case_order_lb.selection_set(new_idx)
            self.case_order_lb.see(new_idx)
            self._say("Case order updated.")

    def offer_iso_upload(self):
        if self._offered_iso or self.db.isos_for_line(self.line_id):
            return
        self._offered_iso = True
        if messagebox.askyesno("Isometrics",
                f"Line {self.line_no} has no isometric yet.\n\nUpload one now? "
                "(You can skip and do it later.)", parent=self._top()):
            self.upload_iso()

    # ------------------------------------------------------------------
    # Iso handling
    # ------------------------------------------------------------------
    def upload_iso(self):
        import line_layout as LL
        start = LL.refs_dir(self.folder)
        if not os.path.isdir(start):
            start = self.folder
        p = filedialog.askopenfilename(parent=self._top(), title="Select iso PDF",
                                       initialdir=start,
                                       filetypes=[("PDF", "*.pdf")])
        if not p:
            return
        n = len(PdfReader(p).pages)
        page = 0
        if n > 1:
            page = simpledialog.askinteger("Page",
                f"This PDF has {n} pages.\nWhich page is this line's iso? (1-{n})",
                initialvalue=1, minvalue=1, maxvalue=n, parent=self._top())
            if not page:
                return
            page -= 1
        self.db.ingest_iso(self.line_id, p, page)
        self.app.reload_line(self.line_id)
        self._say("Iso ingested.")

    def _render_iso(self):
        self._clear()
        iso = self.db.get_iso(self.iso_id)
        ttk.Label(self.sheet, text=os.path.basename(iso["src_pdf"]),
                  font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, PAD))

        f = ttk.LabelFrame(self.sheet, text="Isometric page", padding=PAD)
        f.pack(fill="x", padx=(0, PAD))
        ttk.Label(f, text=f"Page {iso['src_page']+1} of the uploaded PDF, overlaid at "
                          "native size on export.").pack(anchor="w")
        # identification view: the uploaded page as-is (no overlay)
        pdf_path, pg = self.db.abs(iso["src_pdf"]), iso["src_page"]
        body = ttk.Frame(f); body.pack(fill="x")
        if pdf_path:
            self._embed_pages(body,
                              lambda: preview.source_pdf_page(pdf_path, pg),
                              note="Rendering isometric...")
        else:
            ttk.Label(body, text="(source PDF missing from the database folder)",
                      foreground="#b36b00").pack(anchor="w")

        nb = ttk.LabelFrame(self.sheet, text="Note (bottom-left, this iso)", padding=PAD)
        nb.pack(fill="x", pady=PAD, padx=(0, PAD))
        self.iso_note = tk.Text(nb, height=4, wrap="word", relief="solid", bd=1)
        self.iso_note.insert("1.0", iso["note"] or "Note:\n")
        self.iso_note.pack(fill="x")
        # dirty-tracking baseline + autosave triggers
        self._note_iso_id = iso["id"]
        self._note_loaded = self.iso_note.get("1.0", "end-1c")
        self.iso_note.bind("<FocusOut>", lambda e: self.flush_pending())
        ttk.Button(nb, text="Save note", command=self._save_iso_note).pack(anchor="e", pady=(4, 0))

        bar = ttk.Frame(self.sheet, padding=(0, PAD)); bar.pack(fill="x")
        ttk.Button(bar, text="Edit iso sheet...", command=self.edit_iso).pack(side="left")
        ttk.Button(bar, text="Delete iso", command=self.delete_iso).pack(side="left", padx=PAD)

    def delete_iso(self):
        if messagebox.askyesno("Delete", "Remove this iso from the line?",
                               parent=self._top()):
            self._note_iso_id = None          # don't resurrect the note
            self.db.delete_iso(self.iso_id)
            self.iso_id = None
            self.app.reload_line(self.line_id)
            self.show_overview()

    def edit_iso(self):
        self.flush_pending()                  # textbox -> DB before the editor reads it
        iso_id = self.iso_id
        iso = self.db.get_iso(iso_id)
        pdf = self.db.abs(iso["src_pdf"])
        import layout_builder as LB
        from pypdf import PdfReader
        mb = PdfReader(pdf).pages[iso["src_page"]].mediabox
        pw, ph = float(mb.width), float(mb.height)
        if iso["layout_json"]:
            lay = SM.SheetLayout.from_json(iso["layout_json"])
        else:
            lay = SM.SheetLayout(kind="iso", line_no=self.line_no, page_w=pw, page_h=ph)
        lay.iso_pdf, lay.iso_page = pdf, iso["src_page"]
        # title / note / sheet furniture, always present on the sheet
        LB.ensure_iso_furniture(lay, pw, ph, iso["note"] or "", None, None)

        def save():
            self.db.set_iso_layout(iso_id, lay.to_json())
            # A3: an in-canvas edit of the note box is written back to the DB
            nb = lay.box("isonote")
            if nb is not None:
                self.db.set_iso_note(iso_id, nb.text)
                self._sync_note_widget(iso_id, nb.text)

        names = [c["case_name"] for c in self.db.cases_for_line(self.line_id)]
        specs = catalog.build_iso(self.line_no, names, iso["note"] or "")
        self._open_editor(lay, specs, is_iso=True, save=save,
                          backdrop=pdf, backdrop_page=iso["src_page"])

    def _sync_note_widget(self, iso_id: int, text: str):
        """Reflect an editor-side note edit in the panel textbox, if visible."""
        if self._note_iso_id != iso_id:
            return
        try:
            self.iso_note.config(state="normal")
            self.iso_note.delete("1.0", "end")
            self.iso_note.insert("1.0", text)
            self._note_loaded = text
        except (tk.TclError, AttributeError):
            pass

    # ------------------------------------------------------------------
    # Case handling
    # ------------------------------------------------------------------
    def _clear(self):
        self.flush_pending()                  # A2: never lose the note on re-render
        self._note_iso_id = None
        self._render_gen += 1                 # cancel any in-flight inline render
        self._page_imgs.clear()
        for w in self.sheet.winfo_children():
            w.destroy()
        self._fn_vars.clear(); self._force_vars.clear()

    # ------------------------------------------------------------------
    # Legacy case adoption + case data editing (sidecar-backed)
    # ------------------------------------------------------------------
    def sync_cases(self):
        """Ingest any newly generated cases for this line from their
        *_liftmeta.json sidecars, without reopening the app. This is the same
        ingest that runs when the app is opened from the line folder."""
        res = self.db.ingest_sidecars(self.wo_id, self.folder)
        added, updated, failed = res["added"], res["updated"], res["failed"]
        if added or updated or failed:
            self.app.reload_line(self.line_id)     # refresh the tree leaves
            self.show_overview()                   # refresh the in-panel preview
            parts = []
            if added:
                parts.append(f"{added} added")
            if updated:
                parts.append(f"{updated} updated")
            if failed:
                parts.append(f"{failed} failed")
            self._say("Cases synced: " + ", ".join(parts) + ".")
        else:
            self._say("No case sidecars found for this line.")

    def add_existing_case(self):
        """Detect unregistered .C2 files, complete their data, write sidecar."""
        known = [c["case_name"] for c in self.db.cases_for_line(self.line_id)]
        stem = case_meta_ui.pick_case_file(self._top(), self.folder, known)
        if not stem:
            return
        initial = {
            "line": self.line_no,
            "case_name": stem,
            "disp_mm": None,
            "supports": [{"node": n}
                         for n in case_meta_ui.parse_support_nodes(stem)],
            "lift_points": [{}, {}],          # the outer pair, blank
        }
        dlg = case_meta_ui.CaseMetaDialog(self._top(),
                                          f"Add existing case  -  {stem}", initial)
        if dlg.result is None:
            return
        cid = case_meta_ui.write_and_ingest(self.db, self.wo_id,
                                            self.folder, dlg.result)
        self.app.reload_line(self.line_id)
        self.app.focus_case(cid)              # tree + detail view in sync
        self._say(f"Case {stem} added (sidecar written).")

    def edit_case_data(self):
        """Edit the sidecar-level data of ANY case; rewrites and re-ingests.
        Forces and support functions of unchanged nodes are preserved."""
        case = self.db.get_case(self.case_id)
        initial = {
            "line": self.line_no,
            "case_name": case["case_name"],
            "disp_mm": case["disp_mm"],
            "supports": [dict(s) for s in self.db.supports_for(self.case_id)],
            "lift_points": [dict(lp) for lp in self.db.lifts_for(self.case_id)],
        }
        dlg = case_meta_ui.CaseMetaDialog(
            self._top(), f"Edit case data  -  {case['case_name']}", initial)
        if dlg.result is None:
            return
        cid = case_meta_ui.write_and_ingest(self.db, self.wo_id,
                                            self.folder, dlg.result)
        self.app.reload_line(self.line_id)
        self.app.focus_case(cid)              # tree + detail view in sync
        self._say("Case data updated (sidecar rewritten).")

    def archive_case(self):
        case = self.db.get_case(self.case_id)
        if not messagebox.askyesno(
                "Archive case",
                f"Archive lift case {case['case_name']}?\n\n"
                "It will be hidden from this line and excluded from exports. "
                "You can restore it later from View archive.",
                parent=self._top()):
            return
        self.db.archive_case(self.case_id)
        self.app.reload_line(self.line_id)
        self.show_overview()
        self._say(f"Case {case['case_name']} archived.")

    def _render_case(self):
        self._clear()
        case = self.db.get_case(self.case_id)
        sups = self.db.supports_for(self.case_id)
        lifts = self.db.lifts_for(self.case_id)
        hdr = ttk.Frame(self.sheet); hdr.pack(fill="x", pady=(0, PAD), padx=(0, PAD))
        ttk.Label(hdr, text=case["case_name"], font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(hdr, text="Archive case",
                   command=self.archive_case).pack(side="right")
        ttk.Button(hdr, text="Edit case data...",
                   command=self.edit_case_data).pack(side="right", padx=(0, PAD))
        self._sec_image(case); self._sec_supports(sups); self._sec_lifts(case, lifts)
        self._sec_note(case, sups, lifts); self._sec_verdict(case); self._sec_sheet(case)

    def _sec_image(self, case):
        f = ttk.LabelFrame(self.sheet, text="CAESAR model screenshot", padding=PAD)
        f.pack(fill="x", pady=(0, PAD), padx=(0, PAD))
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, PAD))
        ttk.Button(bar, text="Paste from clipboard", command=self.paste_image).pack(side="left")
        ttk.Button(bar, text="Load file...", command=self.load_image).pack(side="left", padx=PAD)
        ttk.Button(bar, text="Copy image", command=self.copy_image).pack(side="left")
        path = self.db.abs_image(case["screenshot"])
        if path:
            img = Image.open(path); img.thumbnail(THUMB_MAX, Image.LANCZOS)
            self._thumb = ImageTk.PhotoImage(img)
            tk.Label(f, image=self._thumb, relief="solid", bd=1).pack(anchor="w")
        else:
            tk.Label(f, text="(no screenshot)", width=56, height=9, relief="solid",
                     bd=1, bg="#f4f4f4", fg="#999").pack(anchor="w")

    def paste_image(self):
        img = clip.grab_image()
        if img is None:
            messagebox.showwarning("Paste", "The clipboard holds no image.",
                                   parent=self._top()); return
        self._store_image(img)

    def load_image(self):
        p = filedialog.askopenfilename(parent=self._top(),
                                       filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
        if p:
            self._store_image(Image.open(p).convert("RGB"))

    def _store_image(self, img):
        case = self.db.get_case(self.case_id)
        dest = self.db.image_path(self.line_no, case["case_name"])
        clip.save_png(img, dest); self.db.set_screenshot(self.case_id, self.db.rel(dest))
        self._render_case(); self._say(f"Screenshot stored ({img.width}x{img.height}).")

    def copy_image(self):
        case = self.db.get_case(self.case_id)
        if clip.copy_image_file(self.db.abs_image(case["screenshot"])):
            self._say("Image on clipboard.")
        else:
            messagebox.showwarning("Copy", "No screenshot stored.", parent=self._top())

    def _sec_supports(self, sups):
        f = ttk.LabelFrame(self.sheet, text="Lifted supports  -  enter r / hd / g / l", padding=PAD)
        f.pack(fill="x", pady=(0, PAD), padx=(0, PAD)); f.columnconfigure(2, weight=1)
        for r, s in enumerate(sups):
            ttk.Label(f, text=str(s["node"]), width=8).grid(row=r, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=s["fn_codes"] or ""); self._fn_vars[s["id"]] = var
            e = ttk.Entry(f, textvariable=var, width=16); e.grid(row=r, column=1, sticky="w", padx=2)
            e.bind("<FocusOut>", lambda ev, sid=s["id"]: self._save_fn(sid))
            e.bind("<Return>", lambda ev, sid=s["id"]: self._save_fn(sid))
            prev = tk.Text(f, height=2, width=34, wrap="none", bg="#fbfbfb", relief="solid", bd=1)
            prev.insert("1.0", calc.function_text(s["node"], s["fn_codes"] or "")); prev.config(state="disabled")
            prev.grid(row=r, column=2, sticky="ew", padx=2)
            ttk.Button(f, text="Copy", width=7,
                       command=lambda n=s["node"], sid=s["id"]: self._copy_fn(n, sid)).grid(row=r, column=3)
        ttk.Label(f, text="r=Rest  hd=Hold Down  g=Guide  l=Limit Stop",
                  foreground="#777", font=("Segoe UI", 8)).grid(row=len(sups), column=0, columnspan=4, sticky="w", pady=(PAD, 0))

    def _save_fn(self, sid):
        raw = self._fn_vars[sid].get(); bad = calc.validate_functions(raw)
        if bad:
            messagebox.showwarning("Functions", f"Unrecognised: {', '.join(bad)}",
                                   parent=self._top()); return
        self.db.set_support_fn(sid, " ".join(calc.parse_functions(raw))); self._render_case()

    def _copy_fn(self, node, sid):
        self._save_fn(sid)
        row = next(s for s in self.db.supports_for(self.case_id) if s["id"] == sid)
        clip.copy_text(self, calc.function_text(node, row["fn_codes"] or "")); self._say(f"Copied node {node}.")

    def _sec_lifts(self, case, lifts):
        f = ttk.LabelFrame(self.sheet, text="Lift points", padding=PAD)
        f.pack(fill="x", pady=(0, PAD), padx=(0, PAD)); f.columnconfigure(5, weight=1)

        individual = bool(case["individual_forces"])
        self.ind_var = tk.BooleanVar(value=individual)
        ttk.Checkbutton(
            f, text="Individual lift forces (document each point separately)",
            variable=self.ind_var, command=self._save_individual
        ).grid(row=0, column=0, columnspan=7, sticky="w", pady=(0, 4))

        hdr = 1
        for c, t in enumerate(("Node", "Lift mm", "To sup", "Dist mm", "Force N", "Mark-up")):
            ttk.Label(f, text=t, font=("Segoe UI", 8, "bold")).grid(row=hdr, column=c, sticky="w", padx=2)
        forces = [lp["force_n"] for lp in lifts]
        for r, lp in enumerate(lifts, start=hdr + 1):
            ttk.Label(f, text=str(lp["node"]), width=7).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Label(f, text=f"{(lp['disp_mm'] or 0):g}", width=8).grid(row=r, column=1, sticky="w")
            ttk.Label(f, text=str(lp["support_node"] or "-"), width=7).grid(row=r, column=2, sticky="w")
            ttk.Label(f, text=f"{(lp['distance_mm'] or 0):g}", width=8).grid(row=r, column=3, sticky="w")
            var = tk.StringVar(value="" if lp["force_n"] is None else f"{lp['force_n']:g}")
            self._force_vars[lp["id"]] = var
            e = ttk.Entry(f, textvariable=var, width=11); e.grid(row=r, column=4, sticky="w", padx=2)
            e.bind("<FocusOut>", lambda ev, lid=lp["id"]: self._save_force(lid))
            e.bind("<Return>", lambda ev, lid=lp["id"]: self._save_force(lid))
            pk = calc.point_doc_kg(lp["force_n"], forces, individual)
            txt = calc.lift_label(lp["node"], lp["disp_mm"] or 0, pk)
            prev = tk.Text(f, height=3, width=22, wrap="none", bg="#fbfbfb", relief="solid", bd=1)
            prev.insert("1.0", txt); prev.config(state="disabled"); prev.grid(row=r, column=5, sticky="ew", padx=2)
            ttk.Button(f, text="Copy", width=7, command=lambda t=txt: (clip.copy_text(self, t), self._say("Copied."))).grid(row=r, column=6)
        deriv = calc.force_derivation([dict(lp) for lp in lifts], individual)
        d = ttk.LabelFrame(f, text="Force processing", padding=PAD)
        d.grid(row=len(lifts) + hdr + 1, column=0, columnspan=7, sticky="ew", pady=(PAD, 0)); d.columnconfigure(0, weight=1)
        box = tk.Text(d, height=max(6, deriv.count("\n") + 1), wrap="none", bg="#fbfbfb",
                      relief="solid", bd=1, font=("Consolas", 9))
        box.insert("1.0", deriv); box.config(state="disabled"); box.grid(row=0, column=0, sticky="ew")
        ttk.Button(d, text="Copy calc", command=lambda: (clip.copy_text(self, deriv), self._say("Copied."))).grid(row=0, column=1, padx=(PAD, 0))
        if individual:
            docs = [(lp["node"], calc.documented_kg_one(lp["force_n"]))
                    for lp in lifts if lp["force_n"] is not None]
            if docs:
                summary = "   ".join(f"N{n}: {kg} kg" for n, kg in docs)
                ttk.Label(d, text=f"Documented (per point):  {summary}",
                          font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=(PAD, 0))
                ttk.Button(d, text="Copy all kg",
                           command=lambda s=summary: (clip.copy_text(self, s), self._say("Copied."))
                           ).grid(row=1, column=1, padx=(PAD, 0))
        else:
            doc_kg = calc.documented_kg(forces)
            if doc_kg is not None:
                ttk.Label(d, text=f"Documented lift force:  {doc_kg} kg", font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=(PAD, 0))
                ttk.Button(d, text="Copy kg", command=lambda: (clip.copy_text(self, f"{doc_kg} kg"), self._say("Copied."))).grid(row=1, column=1, padx=(PAD, 0))

    def _save_individual(self):
        self.db.set_individual_forces(self.case_id, self.ind_var.get())
        self._render_case()
        self._say("Individual lift forces on." if self.ind_var.get()
                  else "Governing (single) lift force.")

    def _save_force(self, lid):
        raw = self._force_vars[lid].get().strip().replace(" ", "").replace(",", "")
        if raw == "":
            self.db.set_lift_force(lid, None)
        else:
            try:
                self.db.set_lift_force(lid, abs(float(raw)))
            except ValueError:
                messagebox.showwarning("Force", f"'{raw}' is not a number.",
                                       parent=self._top()); return
        self._render_case()

    def _sec_note(self, case, sups, lifts):
        f = ttk.LabelFrame(self.sheet, text="Note block", padding=PAD)
        f.pack(fill="x", pady=(0, PAD), padx=(0, PAD)); f.columnconfigure(0, weight=1)
        gen = calc.note_text([lp["node"] for lp in lifts], [s["node"] for s in sups], case["disp_mm"] or 0)
        cur = case["note_override"] if case["note_override"] is not None else gen
        self.note_box = tk.Text(f, height=4, wrap="word", relief="solid", bd=1)
        self.note_box.insert("1.0", cur); self.note_box.grid(row=0, column=0, sticky="ew")
        bar = ttk.Frame(f); bar.grid(row=0, column=1, sticky="n", padx=(PAD, 0))
        ttk.Button(bar, text="Copy note", command=lambda: (clip.copy_text(self, self.note_box.get("1.0", "end-1c")), self._say("Copied."))).pack(fill="x")
        ttk.Button(bar, text="Save edit", command=lambda: (self.db.set_note_override(self.case_id, self.note_box.get("1.0", "end-1c")), self._render_case())).pack(fill="x", pady=(4, 0))
        ttk.Button(bar, text="Regenerate", command=lambda: (self.db.set_note_override(self.case_id, None), self._render_case())).pack(fill="x")

    def _sec_verdict(self, case):
        f = ttk.LabelFrame(self.sheet, text="Verdict", padding=PAD)
        f.pack(fill="x", pady=(0, PAD), padx=(0, PAD)); f.columnconfigure(1, weight=1)
        self.v_var = tk.StringVar(value=case["verdict"] or "PENDING")
        cb = ttk.Combobox(f, textvariable=self.v_var, values=["PENDING", "OK", "NOT OK"],
                          state="readonly", width=10)
        cb.grid(row=0, column=0, sticky="w")
        self.v_reason = ttk.Entry(f); self.v_reason.insert(0, case["verdict_reason"] or "")
        self.v_reason.grid(row=0, column=1, sticky="ew", padx=PAD)
        ttk.Button(f, text="Save", command=self._save_verdict).grid(row=0, column=2)

        # NOT OK override: excluded from the work order unless forced in
        try:
            forced = bool(case["force_include"])
        except (IndexError, KeyError):
            forced = False
        self.inc_var = tk.BooleanVar(value=forced)
        self.inc_chk = ttk.Checkbutton(
            f, text="Include in work order despite NOT OK",
            variable=self.inc_var, command=self._save_force_include)
        self.inc_chk.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: (self._sync_inc_state(),
                                                   self._update_verdict_note()))
        self._sync_inc_state()
        self.v_note = ttk.Label(f, text="", foreground="#777", font=("Segoe UI", 8))
        self.v_note.grid(row=2, column=0, columnspan=3, sticky="w")
        self._update_verdict_note()

    def _sync_inc_state(self):
        """The override only applies to NOT OK; disable it otherwise."""
        self.inc_chk.configure(
            state="normal" if self.v_var.get() == "NOT OK" else "disabled")

    def _update_verdict_note(self):
        self.v_note.config(text={
            "NOT OK": "NOT OK cases are left out of the work order by default.",
            "PENDING": "PENDING cases follow the 'Include PENDING' option on export.",
            "OK": "OK cases are always issued.",
        }.get(self.v_var.get(), ""))

    def _save_force_include(self):
        self.db.set_force_include(self.case_id, self.inc_var.get())
        self.app.reload_line(self.line_id)
        self._say("Include-override updated." if self.inc_var.get()
                  else "Override cleared - case excluded from work order.")

    def _save_verdict(self):
        v = self.v_var.get()
        self.db.set_verdict(self.case_id, v, self.v_reason.get())
        # leaving NOT OK clears the override so it can't linger on an OK case
        self.db.set_force_include(self.case_id,
                                  self.inc_var.get() if v == "NOT OK" else False)
        self.app.reload_line(self.line_id)
        self._render_case()
        self._say("Verdict saved.")

    def _sec_sheet(self, case):
        f = ttk.LabelFrame(self.sheet, text="Mark-up sheet", padding=PAD)
        f.pack(fill="x", pady=(0, PAD), padx=(0, PAD))
        state = "normal" if self.db.abs_image(case["screenshot"]) else "disabled"
        ttk.Button(f, text="Edit sheet...", command=self.edit_case_sheet, state=state).grid(row=0, column=0)
        cid = self.case_id
        ttk.Button(f, text="Preview sheet...", state=state,
                   command=lambda: self._show_preview(
                       f"Lift sheet  -  {case['case_name']}",
                       lambda: preview.case_pages(self.db, cid))
                   ).grid(row=0, column=1, padx=PAD)
        ttk.Button(f, text="Export this sheet...", command=self.export_case, state=state).grid(row=0, column=2, padx=(0, PAD))
        ttk.Label(f, text="layout saved" if case["layout_json"] else "not laid out yet",
                  foreground="#2a7" if case["layout_json"] else "#999").grid(row=0, column=3)
        if state == "disabled":
            ttk.Label(f, text="Paste a screenshot first.", foreground="#b36b00", font=("Segoe UI", 8)).grid(row=1, column=0, columnspan=4, sticky="w")

    def edit_case_sheet(self):
        case = self.db.get_case(self.case_id)
        lay = export.load_or_build(self.db, self.case_id, case["sheet_no"], None)
        specs = export.specs_for(self.db, self.case_id, case["sheet_no"], None)
        cid = self.case_id
        self._open_editor(lay, specs, is_iso=False,
                          save=lambda: self.db.set_layout(cid, lay.to_json()))

    def export_case(self):
        import pdf_render
        import line_layout as LL
        self.flush_pending()                  # A4
        case = self.db.get_case(self.case_id)
        start = LL.final_dir(self.folder)
        if not os.path.isdir(start):
            start = self.folder
        out = filedialog.asksaveasfilename(parent=self._top(), defaultextension=".pdf",
                initialdir=start,
                initialfile=f"{case['case_name']}.pdf", filetypes=[("PDF", "*.pdf")])
        if not out:
            return
        lay = export.load_or_build(self.db, self.case_id, case["sheet_no"], None)
        pdf_render.render(lay, out); self._open_file(out)

    # ------------------------------------------------------------------
    def _open_editor(self, lay, specs, is_iso, save, backdrop=None, backdrop_page=0):
        # Provisional sheet numbers so REFER-SHEET callouts size to their final
        # 'REFER SHEET n' string in the editor, matching export - not the long
        # case name. Cleared when the editor closes (close_win).
        try:
            import work_order
            soc = work_order.plan(self.db, self.wo_id,
                                  include_pending=True)["sheet_of_case"]
        except Exception:
            soc = {}
        SM.set_ref_resolver(lambda name: soc.get(name))
        win = tk.Toplevel(self._top())
        win.title("Iso sheet editor" if is_iso else "Lift sheet editor")
        win.geometry("1320x860")
        win.transient(self._top())
        win.resizable(True, True)
        win.minsize(900, 600)
        # start maximized (Windows); harmless elsewhere
        try:
            win.state("zoomed")
        except tk.TclError:
            try:
                win.attributes("-zoomed", True)
            except tk.TclError:
                pass
        ed = sheet_canvas.SheetCanvas(win, lay, specs, backdrop=backdrop, backdrop_page=backdrop_page)
        ed.pack(fill="both", expand=True)
        bar = ttk.Frame(win, padding=PAD); bar.pack(fill="x")

        def do_save():
            save(); self._say("Layout saved.")
            if not is_iso:
                self._render_case()

        # ---- live preview toggle (renders the layout AS IT IS NOW,
        #      unsaved edits included) -------------------------------------
        pv_state = {"pv": None}

        def back_to_editor():
            if pv_state["pv"] is not None:
                pv_state["pv"].deactivate()
                pv_state["pv"].destroy()
                pv_state["pv"] = None
            ed.pack(fill="both", expand=True, before=bar)
            pv_btn.config(text="Preview")

        def toggle_preview():
            if pv_state["pv"] is None:
                ed.pack_forget()
                pv_state["pv"] = PreviewPane(
                    win, "Live preview  -  current editor state (unsaved edits included)",
                    lambda: preview.layout_pages(lay), on_back=back_to_editor)
                pv_state["pv"].pack(fill="both", expand=True, before=bar)
                pv_btn.config(text="Editor")
            else:
                back_to_editor()

        def close_win(save_first: bool):
            if pv_state["pv"] is not None:
                pv_state["pv"].deactivate()
            if save_first:
                do_save()
            SM.set_ref_resolver(None)         # editor-only preview resolver off
            win.destroy()
            self._rebind_wheel()              # hand the wheel back to the panel

        ttk.Button(bar, text="Close", command=lambda: close_win(False)).pack(side="right")
        ttk.Button(bar, text="Save & close", command=lambda: close_win(True)).pack(side="right", padx=PAD)
        ttk.Button(bar, text="Save", command=do_save).pack(side="right")
        pv_btn = ttk.Button(bar, text="Preview", command=toggle_preview)
        pv_btn.pack(side="right", padx=(0, PAD))
        ttk.Label(bar, foreground="#777", font=("Segoe UI", 8),
                  text="  wheel = zoom · middle/right-drag = pan · drag corner = resize box · "
                       "Draw cloud then click vertices · dbl-click text to edit · Del removes · Ctrl+Z").pack(side="left")
        win.protocol("WM_DELETE_WINDOW", lambda: close_win(True))

    def _open_file(self, p):
        try:
            os.startfile(p)
        except (AttributeError, OSError):
            pass
