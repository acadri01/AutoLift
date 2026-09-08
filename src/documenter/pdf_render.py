"""
pdf_render.py
-------------
SheetLayout -> A4 landscape PDF. Vector text, embedded raster image.
render_many() writes the whole set as one document, correctly numbered.
"""

from __future__ import annotations

import io
import math
import os
from typing import List, Sequence, Tuple

from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas as rl_canvas

import cloud_geom
import fonts
import sheet_model as M


def _arrowhead(c, tip: Tuple[float, float], frm: Tuple[float, float]) -> None:
    """Filled triangle at `tip`, pointing away from `frm`."""
    tx, ty = tip
    ang = math.atan2(ty - frm[1], tx - frm[0])
    bx, by = tx - M.ARROW_LEN * math.cos(ang), ty - M.ARROW_LEN * math.sin(ang)
    px, py = -math.sin(ang) * M.ARROW_HALF, math.cos(ang) * M.ARROW_HALF
    p = c.beginPath()
    p.moveTo(tx, ty)
    p.lineTo(bx + px, by + py)
    p.lineTo(bx - px, by - py)
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def _draw_box(c, b: M.TextBox) -> None:
    x, y, w, h = M.box_rect(b)
    if b.border:
        c.setFillColor(white)
        c.setStrokeColor(HexColor(M.RED))
        c.setLineWidth(M.stroke_pt("callout"))
        c.rect(x, y, w, h, stroke=1, fill=1)

    c.setFont(fonts.bold() if b.bold else fonts.regular(), b.size)
    c.setFillColor(HexColor(M.RED))
    ty = y + h - M.BOX_PAD_Y - b.size * 0.85
    for ln in M.box_lines(b):
        if b.align == "center":
            c.drawCentredString(x + w / 2.0, ty, ln)
        else:
            c.drawString(x + M.BOX_PAD_X, ty, ln)
        ty -= b.size * M.LINE_GAP


def _draw_leader(c, b: M.TextBox) -> None:
    if b.tip is None:
        return
    a = M.box_anchor(b)
    c.setStrokeColor(HexColor(M.RED))
    c.setFillColor(HexColor(M.RED))
    c.setLineWidth(M.stroke_pt("callout"))
    c.line(a[0], a[1], b.tip[0], b.tip[1])
    _arrowhead(c, b.tip, a)


def _draw_line(c, ln: M.FreeLine) -> None:
    c.setStrokeColor(HexColor(M.RED))
    c.setFillColor(HexColor(M.RED))
    c.setLineWidth(M.stroke_pt("arrow" if ln.arrow else "line"))
    c.line(ln.p1[0], ln.p1[1], ln.p2[0], ln.p2[1])
    if ln.arrow:
        _arrowhead(c, ln.p2, ln.p1)


def _draw_dim(c, d: M.Dimension) -> None:
    c.setStrokeColor(HexColor(M.RED))
    c.setFillColor(HexColor(M.RED))
    c.setLineWidth(M.stroke_pt("dimension"))

    # the two extension lines
    c.line(d.a1[0], d.a1[1], d.a2[0], d.a2[1])
    c.line(d.b1[0], d.b1[1], d.b2[0], d.b2[1])

    # double-headed arrow between the a1 / b1 ends, heads pointing outward
    c.line(d.a1[0], d.a1[1], d.b1[0], d.b1[1])
    _arrowhead(c, d.a1, d.b1)
    _arrowhead(c, d.b1, d.a1)

    if not d.text:
        return

    mid = ((d.a1[0] + d.b1[0]) / 2.0, (d.a1[1] + d.b1[1]) / 2.0)
    w, h = M.box_size(d.text)
    lp = d.label_pos or (mid[0] - w / 2.0, mid[1] + 5.0)

    lb = M.TextBox(kind="free", text=d.text, x=lp[0], y=lp[1], align="center")
    cx, cy = lp[0] + w / 2.0, lp[1] + h / 2.0
    if math.hypot(cx - mid[0], cy - mid[1]) > max(w, h):
        lb.tip = mid
        _draw_leader(c, lb)
    _draw_box(c, lb)


def _draw_cloud(c, cl: M.Cloud) -> None:
    if len(cl.pts) < 3:
        return
    c.setStrokeColor(HexColor(M.RED))
    c.setFillColor(HexColor(M.RED))
    c.setLineWidth(M.stroke_pt("cloud"))
    poly = cloud_geom.scallops(cl.pts, cl.bulge)
    p = c.beginPath()
    p.moveTo(*poly[0])
    for pt in poly[1:]:
        p.lineTo(*pt)
    c.drawPath(p, stroke=1, fill=0)

    if cl.text:
        w, h = M.box_size(cl.text)
        xs = [q[0] for q in cl.pts]
        ys = [q[1] for q in cl.pts]
        cxm, cym = sum(xs) / len(xs), max(ys) + 8.0
        lp = cl.label_pos or (cxm - w / 2.0, cym)
        lb = M.TextBox(kind="free", text=cl.text, x=lp[0], y=lp[1], align="center")
        # leader from label to cloud centroid if dragged away
        cen = (sum(xs) / len(xs), sum(ys) / len(ys))
        lcx, lcy = lp[0] + w / 2.0, lp[1] + h / 2.0
        if math.hypot(lcx - cen[0], lcy - cen[1]) > max(w, h):
            lb.tip = cen
            _draw_leader(c, lb)
        _draw_box(c, lb)


def _draw_annotations(c, layout: M.SheetLayout) -> None:
    """The red layer only - no backdrop. Shared by lift render and iso overlay."""
    for cl in layout.clouds:
        _draw_cloud(c, cl)
    for ln in layout.lines:
        _draw_line(c, ln)
    for d in layout.dims:
        _draw_dim(c, d)
    for b in layout.boxes:
        if b.kind == "title":
            _draw_box(c, b)
        else:
            _draw_leader(c, b)
            _draw_box(c, b)


def _draw_lift_page(c, layout: M.SheetLayout) -> None:
    im = layout.image
    if im.path and im.w > 0 and os.path.isfile(im.path):
        c.drawImage(im.path, im.x, im.y, width=im.w, height=im.h,
                    preserveAspectRatio=True, anchor="c", mask="auto")
    _draw_annotations(c, layout)


def render(layout: M.SheetLayout, out) -> object:
    """
    Single LIFT sheet -> its own page. `out` may be a path or a file buffer.
    Iso pages are handled by iso_overlay.render_iso_page (they overlay a PDF).
    """
    fonts.register()
    c = rl_canvas.Canvas(out, pagesize=(layout.page_w, layout.page_h))
    c.setTitle(f"{layout.line_no} - {layout.case_name}")
    _draw_lift_page(c, layout)
    c.showPage()
    c.save()
    return out


def render_many(layouts: Sequence[M.SheetLayout], out_path: str, title: str = "") -> str:
    """All-LIFT convenience (single-line export). Mixed sets go via work_order."""
    fonts.register()
    c = rl_canvas.Canvas(out_path, pagesize=(M.PAGE_W, M.PAGE_H))
    c.setTitle(title or "Stress mark-up")
    for lay in layouts:
        _draw_lift_page(c, lay)
        c.showPage()
    c.save()
    return out_path
