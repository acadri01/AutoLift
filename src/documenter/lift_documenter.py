"""
lift_documenter.py
------------------
Entry point. One window (app_ui.DocumenterApp) with a navigation tree on
the left and a swapping content panel on the right. The right-clicked
folder decides the STARTING FOCUS:

  Right-click a WORK ORDER folder -> the tree seeds that WO with its lines
  (immediate children) and the WO panel opens.

  Right-click a LINE folder (or 00_CII / 01_REFS / ... below it) -> the
  tree seeds ONLY the route to the top (Work orders -> WO -> line) and the
  line panel opens; it offers to upload an iso if the line has none.

Clicking / expanding tree nodes loads children lazily; moving between line
and work order swaps the right panel - no new windows. Only the sheet
editor opens as a separate (maximized) window.

Registry (folder background):
    lift_documenter.exe "%V"
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

import doc_config
import lift_meta as meta
import line_layout as LL
from app_ui import DocumenterApp
from lift_db import LiftDb

DB_NAME = "lift_markup.db"


def _read_cfg() -> str | None:
    return doc_config.get("db") or None


def _write_cfg(db_path: str) -> None:
    # merge-write: preserves markup_* weights and any other future keys
    doc_config.set("db", db_path)


def _ask_db(root: tk.Tk) -> str | None:
    messagebox.showinfo("Lift Mark-up Database",
        "First run: choose where the database should live.\n\n"
        "Pick a location OUTSIDE the job folders - one database serves every "
        "work order.", parent=root)
    d = filedialog.askdirectory(parent=root, title="Database folder")
    return os.path.join(d, DB_NAME) if d else None


def _ingest_line(db: LiftDb, wo_id: int, line_root: str) -> int:
    """Ingest a line's sidecars (from 00_CII/.liftdoc) and return its line_id."""
    line_no = LL.line_no_of(line_root)
    line_id = db.get_or_create_line(wo_id, line_no, line_root)
    for p in LL.find_sidecars(line_root):
        try:
            db.upsert_case_from_meta(wo_id, meta.read_sidecar(p), line_root)
        except (ValueError, OSError):
            pass
    return line_id


def main() -> int:
    folder = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.getcwd()
    if not os.path.isdir(folder):
        folder = os.path.dirname(folder)

    boot = tk.Tk(); boot.withdraw()
    db_path = _read_cfg()
    if not db_path or not os.path.isdir(os.path.dirname(db_path)):
        db_path = _ask_db(boot)
        if not db_path:
            boot.destroy(); return 1
        _write_cfg(db_path)
    boot.destroy()

    db = LiftDb(db_path)
    mode = LL.classify(folder)

    if mode == "line":
        line_root = LL.resolve_line_root(folder)
        wo_folder = LL.work_order_root(line_root)
        wo_no = LL.work_order_no(line_root)
        wo_id = db.get_or_create_wo(wo_no, wo_folder)
        line_id = _ingest_line(db, wo_id, line_root)
        app = DocumenterApp(db, ("line", wo_id, line_id))

    elif mode == "wo":
        wo_no = os.path.basename(folder.rstrip("\\/"))
        wo_id = db.get_or_create_wo(wo_no, folder)
        for line_root in LL.line_roots_in_wo(folder):
            _ingest_line(db, wo_id, line_root)
        app = DocumenterApp(db, ("wo", wo_id))

    else:
        # not recognisable as either a line or a work order - open at the
        # tree root so the user still gets a window rather than a silent
        # exit, but WITHOUT creating a DB record for this folder. This used
        # to call get_or_create_wo(basename(folder), folder), which meant
        # launching from an unrelated folder (the AutoLift install folder
        # itself, or a container folder that merely holds several real work
        # orders) silently created a phantom "work order" in the tree named
        # after that folder - reported 2026-09-09.
        app = DocumenterApp(db, ("root",))

    app.mainloop()
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
