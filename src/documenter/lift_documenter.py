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

import doc_config
import lift_meta as meta
import line_layout as LL
from app_ui import DocumenterApp
from lift_db import LiftDb

DB_NAME = "lift_markup.db"


def _default_db_path() -> str:
    """AutoLift's fixed per-user AppData location for the database - see
    app_paths.autolift_appdata_dir."""
    import app_paths
    return os.path.join(app_paths.autolift_appdata_dir(), DB_NAME)


def _resolve_db_path() -> str:
    """
    The database path to use: whatever `lift_doc_tool.cfg`'s `db=` line
    already says (an explicit choice, or a legacy pre-2026-09-14 value
    migrated forward by doc_config.cfg_path()), or - with no prompt at
    all - the zero-touch default in AutoLift's AppData folder (per direct
    instruction, 2026-09-14: "Everyone has their own local DB copy... The
    default path for the DB should be in the AppData folder for
    'AutoLift'"). A missing/unreachable configured folder (e.g. it was
    deleted) silently falls back to the same default rather than erroring
    or re-prompting, keeping every run zero-touch.

    Persists the resolved default back to the config the first time, so
    it's visible and editable there (the flat key=value file already
    supports hand-editing `db=` to point elsewhere).
    """
    configured = doc_config.get("db")
    if configured and os.path.isdir(os.path.dirname(configured)):
        return configured
    default = _default_db_path()
    doc_config.set("db", default)
    return default


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

    db_path = _resolve_db_path()
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
