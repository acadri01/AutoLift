"""
preview.py
----------
Render any scope to on-screen page images THROUGH THE REAL EXPORT PIPELINE
(pdf_render / iso_overlay / work_order), so the preview is guaranteed to
match the issued PDF. Pages are rasterised with PyMuPDF.

Scopes
------
  case_pages(db, case_id)     one lift sheet (saved layout or fresh build)
  iso_pages(db, iso_id)       one iso page: original PDF + red overlay;
                              refer tokens preview as 'REFER SHEET [case]'
  line_pages(db, line_id)     full line context: isos first, then every
                              lift case INCLUDING PENDING; sheet numbers
                              show as 'Sheet XX of XX' (real numbers only
                              exist at work-order level)
  wo_pages(db, wo_id, ...)    the complete assembled document, sheet
                              numbers and REFER SHEET references resolved
                              exactly as export would - but nothing is
                              persisted and no watermark is stamped
  layout_pages(lay)           a LIVE layout object (the sheet editor's
                              in-memory state, unsaved edits included)
"""

from __future__ import annotations

import io
import os
import tempfile
from typing import List

from PIL import Image
from pypdf import PdfReader, PdfWriter

import export
import iso_overlay
import pdf_render
import sheet_model as M
import work_order
from lift_db import LiftDb

# target raster width in pixels; pages are downscaled to fit the pane
RASTER_WIDTH = 1400


# --------------------------------------------------------------------------
# Rasterising
# --------------------------------------------------------------------------
def _pdf_bytes_to_images(data: bytes) -> List[Image.Image]:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    out: List[Image.Image] = []
    for pg in doc:
        z = RASTER_WIDTH / max(pg.rect.width, 1.0)
        pix = pg.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
        out.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    doc.close()
    return out


def _writer_to_images(writer: PdfWriter) -> List[Image.Image]:
    buf = io.BytesIO()
    writer.write(buf)
    return _pdf_bytes_to_images(buf.getvalue())


# --------------------------------------------------------------------------
# Scopes
# --------------------------------------------------------------------------
def case_pages(db: LiftDb, case_id: int) -> List[Image.Image]:
    """Exactly what 'Export this sheet' would produce right now."""
    case = db.get_case(case_id)
    lay = export.load_or_build(db, case_id, case["sheet_no"], None)
    buf = io.BytesIO()
    pdf_render.render(lay, buf)
    return _pdf_bytes_to_images(buf.getvalue())


def iso_pages(db: LiftDb, iso_id: int) -> List[Image.Image]:
    """Original iso page + red overlay at native size, tokens previewed."""
    lay = work_order._iso_layout(db, iso_id, None, None)   # Sheet XX of XX
    w = PdfWriter()
    iso_overlay.render_iso_page(lay, w)
    return _writer_to_images(w)


def line_pages(db: LiftDb, line_id: int) -> List[Image.Image]:
    """
    Full line context, export order: this line's isos first, then all its
    lift cases (PENDING included). No resolution, no numbering - that only
    exists at work-order level.
    """
    w = PdfWriter()
    for iso in db.isos_for_line(line_id):
        lay = work_order._iso_layout(db, iso["id"], None, None)
        iso_overlay.render_iso_page(lay, w)
    for c in db.cases_for_line(line_id):
        lay = export.load_or_build(db, c["id"], None, None)
        buf = io.BytesIO()
        pdf_render.render(lay, buf)
        buf.seek(0)
        w.add_page(PdfReader(buf).pages[0])
    return _writer_to_images(w)


def wo_pages(db: LiftDb, wo_id: int, include_pending: bool = False) -> List[Image.Image]:
    """
    The complete work-order document via work_order.export_work_order with
    persist=False - references resolved, sheet numbers real, DB untouched,
    no watermark.
    """
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        work_order.export_work_order(db, wo_id, path,
                                     include_pending=include_pending,
                                     persist=False, preview=False)
        with open(path, "rb") as fh:
            data = fh.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return _pdf_bytes_to_images(data)


def layout_pages(lay: M.SheetLayout) -> List[Image.Image]:
    """A live layout object - the editor's current state, unsaved edits in."""
    if lay.kind == "iso":
        w = PdfWriter()
        iso_overlay.render_iso_page(lay, w)
        return _writer_to_images(w)
    buf = io.BytesIO()
    pdf_render.render(lay, buf)
    return _pdf_bytes_to_images(buf.getvalue())


def source_pdf_page(pdf_path: str, page: int) -> List[Image.Image]:
    """
    The UPLOADED iso page as-is (no overlay) - the identification view shown
    in the iso info section.
    """
    import fitz

    doc = fitz.open(pdf_path)
    pg = doc[page]
    z = RASTER_WIDTH / max(pg.rect.width, 1.0)
    pix = pg.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return [img]
