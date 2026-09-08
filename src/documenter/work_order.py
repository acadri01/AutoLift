"""
work_order.py
-------------
Assemble the issue-ready work-order PDF.

Order: every iso page first (index), alphabetical by line; then every lift
sheet, grouped by line in the same order. Sheet numbers assigned across the
whole document. REFER SHEET tokens on iso pages resolved to real numbers.
"""

from __future__ import annotations

import io
import re
from typing import Dict, List, Optional, Tuple

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas

import export
import fonts
import iso_overlay
import layout_builder as LB
import pdf_render
import sheet_model as M
from lift_db import LiftDb

REF_TOKEN = re.compile(r"@@REF:(.+?)@@")


def _case_included(case, include_pending: bool) -> bool:
    """
    Work-order inclusion rule:
      OK       -> always included
      PENDING  -> only if the 'Include PENDING' option is on
      NOT OK   -> excluded unless the case's force_include override is set
    """
    v = case["verdict"]
    if v == "PENDING":
        return include_pending
    if v == "NOT OK":
        try:
            return bool(case["force_include"])
        except (IndexError, KeyError):
            return False
    return True                                   # OK (and any legacy value)


# --------------------------------------------------------------------------
def plan(db: LiftDb, wo_id: int, line_order: Optional[List[int]] = None,
         include_pending: bool = False) -> Dict:
    """
    Build the page plan. line_order = list of line_ids; default alphabetical.
    Returns {"pages": [...], "sheet_of_case": {case_name: n}, "total": n}
    Each page: {"kind","line_id","line_no","iso_id"|"case_id","sheet_no"}
    """
    lines = db.lines_for_wo(wo_id)
    by_id = {l["id"]: l for l in lines}
    order = line_order or [l["id"] for l in sorted(lines, key=lambda r: r["line_no"])]

    iso_pages, lift_pages = [], []
    excluded: set = set()
    for lid in order:
        ln = by_id[lid]
        for iso in db.isos_for_line(lid):
            iso_pages.append({"kind": "iso", "line_id": lid, "line_no": ln["line_no"],
                              "iso_id": iso["id"]})
        for c in db.cases_for_line(lid):
            if not _case_included(c, include_pending):
                excluded.add(c["case_name"])
                continue
            lift_pages.append({"kind": "lift", "line_id": lid, "line_no": ln["line_no"],
                               "case_id": c["id"], "case_name": c["case_name"]})

    pages = iso_pages + lift_pages
    sheet_of_case = {}
    for i, p in enumerate(pages, start=1):
        p["sheet_no"] = i
        if p["kind"] == "lift":
            sheet_of_case[p["case_name"]] = i
    return {"pages": pages, "sheet_of_case": sheet_of_case,
            "excluded": excluded, "total": len(pages)}


def _strip_ref_phrase(text: str, case_name: str) -> str:
    """
    Remove a whole 'REFER SHEET' phrase whose token is an excluded case, so
    the callout doesn't dangle. Handles the token alone or prefixed with the
    literal 'REFER SHEET' the user typed/previewed. Collapses leftover blank
    lines.
    """
    tok = f"@@REF:{case_name}@@"
    # 'REFER SHEET @@REF:x@@' or bare '@@REF:x@@' -> gone
    text = re.sub(r"(?i)REFER\s*SHEET\s*" + re.escape(tok), "", text)
    text = text.replace(tok, "")
    lines = [ln for ln in text.split("\n")]
    # drop lines that became empty purely from the strip
    lines = [ln for ln in lines if ln.strip() != ""] or [""]
    return "\n".join(lines)


def _resolve_refs(lay: M.SheetLayout, sheet_of_case: Dict[str, int],
                  excluded: Optional[set] = None) -> None:
    """
    Swap @@REF:<case>@@ tokens for 'REFER SHEET n'.
      * case in the export set      -> 'REFER SHEET n'
      * case known but EXCLUDED     -> phrase removed (intentionally not issued)
      * case unknown (typo/deleted) -> 'REFER SHEET ?? (name)'
    Applies to both text boxes and cloud labels.
    """
    excluded = excluded or set()

    def fix(text: str) -> str:
        if "@@REF:" not in text:
            return text
        for name in REF_TOKEN.findall(text):
            if name in excluded and name not in sheet_of_case:
                text = _strip_ref_phrase(text, name)
        def repl(m):
            n = sheet_of_case.get(m.group(1))
            return f"REFER SHEET {n}" if n else f"REFER SHEET ?? ({m.group(1)})"
        return REF_TOKEN.sub(repl, text)

    for b in lay.boxes:
        b.text = fix(b.text)
    for cl in lay.clouds:
        cl.text = fix(cl.text)


def _iso_layout(db: LiftDb, iso_id: int, sheet_no: int, total: int) -> M.SheetLayout:
    iso = db.get_iso(iso_id)
    pdf = db.abs(iso["src_pdf"])
    pw, ph = _iso_page_size(pdf, iso["src_page"])
    if iso["layout_json"]:
        lay = M.SheetLayout.from_json(iso["layout_json"])
    else:
        lay = M.SheetLayout(kind="iso", line_no=db.line_no(iso["line_id"]),
                            page_w=pw, page_h=ph)
    lay.iso_pdf, lay.iso_page = pdf, iso["src_page"]
    # ensure title / note / sheet furniture exists and text is current
    LB.ensure_iso_furniture(lay, pw, ph, iso["note"] or "", sheet_no, total)
    return lay


def _iso_page_size(pdf: str, page: int) -> Tuple[float, float]:
    r = PdfReader(pdf)
    b = r.pages[page].mediabox
    return float(b.width), float(b.height)


def reference_report(db: LiftDb, wo_id: int,
                     line_order: Optional[List[int]] = None,
                     include_pending: bool = False) -> List[Dict]:
    """
    What each iso cross-reference resolves to - for the pre-export check.
    Rows: {iso_sheet, line, token, target_case, resolved, status}
      status: 'ok' | 'broken' (target not in the set) | 'manual' (free remark)
    """
    p = plan(db, wo_id, line_order, include_pending)
    soc, total = p["sheet_of_case"], p["total"]
    excluded = p["excluded"]
    rows: List[Dict] = []

    for page in p["pages"]:
        if page["kind"] != "iso":
            continue
        lay = _iso_layout(db, page["iso_id"], page["sheet_no"], total)
        for b in lay.boxes:
            for tok in REF_TOKEN.findall(b.text):
                n = soc.get(tok)
                if n:
                    status, resolved = "ok", n
                elif tok in excluded:
                    status, resolved = "excluded", "not issued (NOT OK)"
                else:
                    status, resolved = "broken", "MISSING"
                rows.append({"iso_sheet": page["sheet_no"], "line": page["line_no"],
                             "target_case": tok, "resolved": resolved,
                             "status": status})
        for cl in lay.clouds:
            for tok in REF_TOKEN.findall(cl.text or ""):
                n = soc.get(tok)
                if n:
                    status, resolved = "ok", n
                elif tok in excluded:
                    status, resolved = "excluded", "not issued (NOT OK)"
                else:
                    status, resolved = "broken", "MISSING"
                rows.append({"iso_sheet": page["sheet_no"], "line": page["line_no"],
                             "target_case": tok, "resolved": resolved,
                             "status": status})
            if cl.text and "@@REF:" not in cl.text:
                rows.append({"iso_sheet": page["sheet_no"], "line": page["line_no"],
                             "target_case": cl.text[:30], "resolved": "-",
                             "status": "manual"})
    return rows


def export_work_order(db: LiftDb, wo_id: int, out_path: str,
                      line_order: Optional[List[int]] = None,
                      include_pending: bool = False,
                      persist: bool = True, preview: bool = False) -> Dict:
    """
    preview=True: same pages and resolved references, but stamps a PREVIEW
    watermark and does NOT persist sheet numbers or layouts - use it to
    check REFER SHEET resolution before issuing the real document.
    """
    p = plan(db, wo_id, line_order, include_pending)
    soc, total = p["sheet_of_case"], p["total"]
    excluded = p["excluded"]
    writer = PdfWriter()
    persist = persist and not preview

    for page in p["pages"]:
        if page["kind"] == "iso":
            lay = _iso_layout(db, page["iso_id"], page["sheet_no"], total)
            _resolve_refs(lay, soc, excluded)
            if preview:
                _watermark(lay)
            iso_overlay.render_iso_page(lay, writer)
            if persist:
                db.set_iso_layout(page["iso_id"], lay.to_json())
        else:
            cid = page["case_id"]
            if persist:
                db.set_sheet_no(cid, page["sheet_no"])
            lay = export.load_or_build(db, cid, page["sheet_no"], total)
            if persist:
                db.set_layout(cid, lay.to_json())
            if preview:
                _watermark(lay)
            buf = io.BytesIO()
            pdf_render.render(lay, buf)
            buf.seek(0)
            writer.add_page(PdfReader(buf).pages[0])

    if preview:
        writer.add_metadata({"/Title": f"{db.get_wo(wo_id)['wo_no']} (PREVIEW)"})
    with open(out_path, "wb") as fh:
        writer.write(fh)
    return p


def _watermark(lay: M.SheetLayout) -> None:
    pw = lay.page_w if lay.kind != "iso" else M.PAGE_W
    ph = lay.page_h if lay.kind != "iso" else M.PAGE_H
    lay.boxes.append(M.TextBox(
        kind="free", text="PREVIEW", x=pw / 2, y=ph * 0.12, anchor="c",
        border=False, align="center", size=26, bold=True))
