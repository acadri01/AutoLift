"""
export.py
---------
Single-sheet and whole-set export.

Sheet numbers are prefilled from the export order (sorted by lift case name)
and are overridable per case. They live on the case (lift_cases.sheet_no),
so they survive between sessions.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from PIL import Image

import catalog
import layout_builder as LB
import lift_calc as calc
import pdf_render
import sheet_model as M
from lift_db import LiftDb


# --------------------------------------------------------------------------
def _note_for(db: LiftDb, case, sups, lifts) -> str:
    if case["note_override"] is not None:
        return case["note_override"]
    return calc.note_text([lp["node"] for lp in lifts],
                          [s["node"] for s in sups],
                          case["disp_mm"] or 0)


def load_or_build(db: LiftDb, case_id: int, sheet_no: Optional[int] = None,
                  total: Optional[int] = None) -> M.SheetLayout:
    """
    Saved layout if there is one (positions preserved, text refreshed).
    Otherwise a fresh parametric build.
    """
    case = db.get_case(case_id)
    sups = [dict(r) for r in db.supports_for(case_id)]
    lifts = [dict(r) for r in db.lifts_for(case_id)]
    note = _note_for(db, case, sups, lifts)

    img = db.abs_image(case["screenshot"])
    px = Image.open(img).size if img else None

    saved = db.get_layout(case_id)
    if saved:
        try:
            lay = M.SheetLayout.from_json(saved)
            # image may have been re-pasted since the layout was saved
            if img and (lay.image.path != img or lay.image.w <= 0):
                lay.image = M.ImageItem(path=img)
                lay.image.fit_page(px[0], px[1])
            LB.refresh_text(lay, sups, lifts, note, sheet_no, total,
                            individual=bool(case["individual_forces"]))
            return lay
        except (ValueError, KeyError, TypeError):
            pass  # schema drift -> rebuild

    d = dict(case)
    d["line_no"] = db.line_no(case["line_id"])
    return LB.build(d, sups, lifts, img, px, note, sheet_no, total)


def export_one(db: LiftDb, case_id: int, out_path: str) -> str:
    case = db.get_case(case_id)
    lay = load_or_build(db, case_id, case["sheet_no"], None)
    return pdf_render.render(lay, out_path)


# --------------------------------------------------------------------------
def specs_for(db: LiftDb, case_id: int, sheet_no: Optional[int] = None,
              total: Optional[int] = None) -> List:
    """The palette catalog for this case."""
    case = db.get_case(case_id)
    sups = [dict(r) for r in db.supports_for(case_id)]
    lifts = [dict(r) for r in db.lifts_for(case_id)]
    line_no = db.line_no(case["line_id"])
    return catalog.build(dict(case), sups, lifts,
                         _note_for(db, case, sups, lifts),
                         LB.sheet_label(sheet_no or case["sheet_no"], total),
                         line_no)
