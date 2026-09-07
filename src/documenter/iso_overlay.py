"""
iso_overlay.py
--------------
Iso pages keep their original PDF. We render the red annotation layer to a
transparent overlay at the SAME page size, then stamp it on top with pypdf.
The scan/vector iso is never rasterised or recompressed.

assemble_work_order() builds the whole issue-ready document:
    all iso pages first (the index, alphabetical by line),
    then the lift sheets, grouped by line in the same order.
Sheet numbers and every REFER SHEET cross-reference are resolved here.
"""

from __future__ import annotations

import io
import os
from typing import Dict, List, Optional, Tuple

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas

import fonts
import pdf_render
import sheet_model as M


# --------------------------------------------------------------------------
def _page_size(pdf_path: str, page_index: int) -> Tuple[float, float]:
    r = PdfReader(pdf_path)
    box = r.pages[page_index].mediabox
    return float(box.width), float(box.height)


def render_iso_page(layout: M.SheetLayout, writer: PdfWriter) -> None:
    """Append one iso page (original + red overlay) to writer."""
    reader = PdfReader(layout.iso_pdf)
    base = reader.pages[layout.iso_page]
    w, h = float(base.mediabox.width), float(base.mediabox.height)

    # overlay at the native page size (NOT the A3 constant - iso keeps its own)
    buf = io.BytesIO()
    fonts.register()
    c = rl_canvas.Canvas(buf, pagesize=(w, h))
    _draw_overlay(c, layout)
    c.showPage()
    c.save()
    buf.seek(0)

    overlay = PdfReader(buf).pages[0]
    base.merge_page(overlay)          # stamp on top, original untouched beneath
    writer.add_page(base)


def _draw_overlay(c, layout: M.SheetLayout) -> None:
    """Same primitives as pdf_render, minus the background image."""
    for cl in layout.clouds:
        pdf_render._draw_cloud(c, cl)
    for ln in layout.lines:
        pdf_render._draw_line(c, ln)
    for d in layout.dims:
        pdf_render._draw_dim(c, d)
    for b in layout.boxes:
        pdf_render._draw_leader(c, b)
        pdf_render._draw_box(c, b)


# --------------------------------------------------------------------------
# Work-order assembly
# --------------------------------------------------------------------------
class SheetRef:
    """One page in the final document, with its resolved sheet number."""
    def __init__(self, kind: str, line_no: str, key: str, label: str):
        self.kind = kind          # iso | lift
        self.line_no = line_no
        self.key = key            # iso: "line|page";  lift: case_name
        self.label = label
        self.sheet_no: Optional[int] = None


def plan_sheets(lines_in_order: List[Dict]) -> List[SheetRef]:
    """
    lines_in_order: [{"line_no": str,
                      "isos":  [{"key","label"}...],
                      "lifts": [{"key","label"}...]}, ...]
    Returns the page order (all isos, then all lifts) with sheet_no assigned.
    """
    refs: List[SheetRef] = []
    for ln in lines_in_order:
        for iso in ln["isos"]:
            refs.append(SheetRef("iso", ln["line_no"], iso["key"], iso["label"]))
    for ln in lines_in_order:
        for lf in ln["lifts"]:
            refs.append(SheetRef("lift", ln["line_no"], lf["key"], lf["label"]))

    for i, r in enumerate(refs, start=1):
        r.sheet_no = i
    return refs


def lift_sheet_number(refs: List[SheetRef], case_name: str) -> Optional[int]:
    for r in refs:
        if r.kind == "lift" and r.key == case_name:
            return r.sheet_no
    return None
