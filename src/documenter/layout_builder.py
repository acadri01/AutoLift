"""
layout_builder.py
-----------------
Parametric prefill. Every annotation exists and already says the right
thing; you only drag.

refresh_text() re-runs the parametrics into an existing layout without
touching a single coordinate.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import lift_calc as calc
import sheet_model as M


def sheet_label(sheet_no: Optional[int], total: Optional[int]) -> str:
    n = f"{sheet_no:02d}" if sheet_no else "XX"
    t = f"{total:02d}" if total else "XX"
    return f"Sheet {n} of {t}"


def ensure_iso_furniture(lay: M.SheetLayout, page_w: float, page_h: float,
                         note_text: str = "", sheet_no: Optional[int] = None,
                         total: Optional[int] = None) -> None:
    """
    Guarantee an iso page has its standing furniture - title (top-centre),
    note (bottom-left), sheet number (bottom-right) - creating any that are
    missing and refreshing note/sheet text. Positions of existing boxes are
    never moved. Used by both the editor and the exporter so they agree.
    """
    if not lay.box("title"):
        lay.boxes.append(M.TextBox(kind="title", box_id="title",
                                   text="STRESS MARK-UP",
                                   x=page_w / 2, y=page_h - M.MARGIN, anchor="n",
                                   align="center", size=M.TITLE_SIZE, bold=True))

    nb = lay.box("isonote")
    if nb:
        if note_text:
            nb.text = note_text
    else:
        lay.boxes.append(M.TextBox(kind="note", box_id="isonote",
                                   text=note_text or "Note:\n",
                                   x=M.MARGIN, y=M.MARGIN + 90, anchor="sw",
                                   w=360.0))

    txt = sheet_label(sheet_no, total)
    sb = lay.box("sheet")
    if sb:
        sb.text = txt
    else:
        lay.boxes.append(M.TextBox(kind="sheet", box_id="sheet", text=txt,
                                   x=page_w - M.MARGIN, y=M.MARGIN, anchor="se",
                                   align="center"))


def build_iso(line_no: str, page_w: float, page_h: float,
              note_text: str = "", sheet_no: Optional[int] = None,
              total: Optional[int] = None) -> M.SheetLayout:
    """A fresh iso layout with furniture placed."""
    lay = M.SheetLayout(kind="iso", line_no=line_no,
                        page_w=page_w, page_h=page_h)
    ensure_iso_furniture(lay, page_w, page_h, note_text, sheet_no, total)
    return lay


def build(case: Dict, supports: List[Dict], lifts: List[Dict],
          image_path: Optional[str], image_px: Optional[tuple],
          note_text: str = "", sheet_no: Optional[int] = None,
          total: Optional[int] = None) -> M.SheetLayout:

    lay = M.SheetLayout(case_name=case.get("case_name", ""),
                        line_no=case.get("line_no", ""))

    if image_path and image_px:
        lay.image = M.ImageItem(path=image_path)
        lay.image.fit_page(image_px[0], image_px[1], top_reserve=34.0)

    cx, cy = M.PAGE_W / 2.0, M.PAGE_H / 2.0

    # title
    tw, th = M.box_size("STRESS MARK-UP", M.TITLE_SIZE, bold=True)
    lay.boxes.append(M.TextBox(kind="title", box_id="title", text="STRESS MARK-UP",
                               x=cx, y=M.PAGE_H - M.MARGIN, anchor="n",
                               align="center", size=M.TITLE_SIZE, bold=True))

    # sheet number
    st = sheet_label(sheet_no, total)
    sw, sh = M.box_size(st)
    lay.boxes.append(M.TextBox(kind="sheet", box_id="sheet", text=st,
                               x=M.PAGE_W - M.MARGIN, y=M.MARGIN, anchor="se", align="center"))

    # note
    if note_text:
        nw, nh = M.box_size(note_text)
        lay.boxes.append(M.TextBox(kind="note", box_id="note", text=note_text,
                                   x=cx, y=M.PAGE_H - 118.0, anchor="n"))

    # lift callouts - parked right
    individual = bool(case.get("individual_forces"))
    forces = [lp.get("force_n") for lp in lifts]
    for i, lp in enumerate(lifts):
        pk = calc.point_doc_kg(lp.get("force_n"), forces, individual)
        lay.boxes.append(M.TextBox(
            kind="callout", box_id=f"lift{lp['node']}",
            text=calc.lift_label(lp["node"], lp.get("disp_mm") or 0, pk),
            x=M.PAGE_W - M.MARGIN, y=M.PAGE_H - 150.0 - i * 58.0, anchor="ne",
            tip=(cx + 70.0, cy + 30.0 - i * 30.0)))

    # support callouts - parked left
    for i, s in enumerate(supports):
        lay.boxes.append(M.TextBox(
            kind="callout", box_id=f"sup{s['node']}",
            text=calc.function_text(s["node"], s.get("fn_codes") or ""),
            x=M.MARGIN, y=M.PAGE_H - 150.0 - i * 58.0, anchor="nw",
            tip=(cx - 70.0, cy - 20.0 - i * 30.0)))

    # dimensions - parked as a sane 4-point shape, ready to drag onto the pipe
    for i, lp in enumerate(lifts):
        if not lp.get("distance_mm") or not lp.get("support_node"):
            continue
        y_arrow = cy - 70.0 - i * 46.0
        y_free = y_arrow - 46.0
        lay.dims.append(M.Dimension(
            dim_id=f"dim{lp['node']}-{lp['support_node']}",
            a1=(cx - 95.0, y_arrow), a2=(cx - 95.0, y_free),
            b1=(cx + 95.0, y_arrow), b2=(cx + 95.0, y_free),
            text=f"{lp['distance_mm']:g} mm"))

    return lay


def refresh_text(lay: M.SheetLayout, supports: List[Dict], lifts: List[Dict],
                 note_text: str = "", sheet_no: Optional[int] = None,
                 total: Optional[int] = None,
                 sheet_override: Optional[str] = None,
                 individual: bool = False) -> None:
    """Positions untouched. Call after any force / function / sheet-no edit."""
    forces = [lp.get("force_n") for lp in lifts]

    for lp in lifts:
        b = lay.box(f"lift{lp['node']}")
        if b:
            pk = calc.point_doc_kg(lp.get("force_n"), forces, individual)
            b.text = calc.lift_label(lp["node"], lp.get("disp_mm") or 0, pk)

    for s in supports:
        b = lay.box(f"sup{s['node']}")
        if b:
            b.text = calc.function_text(s["node"], s.get("fn_codes") or "")

    n = lay.box("note")
    if n and note_text:
        n.text = note_text

    sb = lay.box("sheet")
    if sb:
        sb.text = sheet_override or sheet_label(sheet_no, total)

    for lp in lifts:
        d = lay.dim(f"dim{lp['node']}-{lp.get('support_node')}")
        if d and lp.get("distance_mm"):
            d.text = f"{lp['distance_mm']:g} mm"
