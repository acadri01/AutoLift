"""
catalog.py
----------
Every annotation the dataset can produce, whether or not it's currently on
the sheet.

The editor palette shows the catalog minus what's already placed. Drag an
entry onto the canvas to place it; delete it from the canvas and it returns
to the palette. Nothing is ever lost by deleting.

A Spec is: an id, a palette label, a group, and a factory that builds the
item at a drop point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import lift_calc as calc
import sheet_model as M


@dataclass
class Spec:
    item_id: str
    label: str                       # palette display
    group: str
    make: Callable[[float, float], object]   # (x, y) -> TextBox | Dimension | FreeLine
    reusable: bool = False           # free items never leave the palette


def _tb(item_id: str, kind: str, text: str, anchor: str = "nw",
        leader: bool = True, align: str = "left", size: float = M.FONT_SIZE,
        bold: bool = False) -> Callable:
    def make(x: float, y: float) -> M.TextBox:
        b = M.TextBox(kind=kind, box_id=item_id, text=text, x=x, y=y,
                      anchor=anchor, align=align, size=size, bold=bold)
        if leader:
            b.tip = (x + 60.0, y - 40.0)
        return b
    return make


def build(case: Dict, supports: List[Dict], lifts: List[Dict],
          note_text: str = "", sheet_text: str = "Sheet XX of XX",
          line_no: str = "") -> List[Spec]:
    """The full catalog for this case."""
    out: List[Spec] = []
    individual = bool(case.get("individual_forces"))
    forces = [lp.get("force_n") for lp in lifts]

    # ---- General ----------------------------------------------------
    out.append(Spec("title", "STRESS MARK-UP (title)", "General",
                    _tb("title", "title", "STRESS MARK-UP", "n", False,
                        "center", M.TITLE_SIZE, True)))
    out.append(Spec("sheet", f"{sheet_text}", "General",
                    _tb("sheet", "sheet", sheet_text, "se", False, "center")))
    if note_text:
        out.append(Spec("note", "Note block", "General",
                        _tb("note", "note", note_text, "n", False)))
    if line_no:
        out.append(Spec("lineno", f"Line number  ({line_no})", "General",
                        _tb("lineno", "free", line_no, "sw", False)))
    if case.get("case_name"):
        out.append(Spec("casename", f"Lift case  ({case['case_name']})", "General",
                        _tb("casename", "free", case["case_name"], "sw", False)))
    if case.get("verdict_reason"):
        out.append(Spec("reason", "Verdict reason", "General",
                        _tb("reason", "free", case["verdict_reason"], "nw", False)))
    if lifts:
        out.append(Spec("calc", "Force calculation", "General",
                        _tb("calc", "free",
                            calc.force_derivation(lifts, individual), "nw", False)))

    # ---- Supports ---------------------------------------------------
    for s in supports:
        n = s["node"]
        out.append(Spec(f"sup{n}", f"Node {n}  -  support", "Supports",
                        _tb(f"sup{n}", "callout",
                            calc.function_text(n, s.get("fn_codes") or ""), "nw")))

    # ---- Lift points ------------------------------------------------
    for lp in lifts:
        n = lp["node"]
        pk = calc.point_doc_kg(lp.get("force_n"), forces, individual)
        out.append(Spec(f"lift{n}", f"Node {n}  -  lift point", "Lift points",
                        _tb(f"lift{n}", "callout",
                            calc.lift_label(n, lp.get("disp_mm") or 0, pk), "ne")))

    # ---- Dimensions -------------------------------------------------
    for lp in lifts:
        if not lp.get("distance_mm") or not lp.get("support_node"):
            continue
        did = f"dim{lp['node']}-{lp['support_node']}"
        txt = f"{lp['distance_mm']:g} mm"

        def mk(x: float, y: float, did=did, txt=txt) -> M.Dimension:
            return M.Dimension(dim_id=did, text=txt,
                               a1=(x - 80.0, y), a2=(x - 80.0, y - 45.0),
                               b1=(x + 80.0, y), b2=(x + 80.0, y - 45.0))

        out.append(Spec(did, f"{txt}   node {lp['node']} to {lp['support_node']}",
                        "Dimensions", mk))

    # ---- Free items - always available ------------------------------
    out.append(Spec("__text", "Text box...", "Free",
                    lambda x, y: M.TextBox(kind="free", text="", x=x, y=y,
                                           anchor="nw"), reusable=True))
    out.append(Spec("__label", "Plain label (no border)...", "Free",
                    lambda x, y: M.TextBox(kind="free", text="", x=x, y=y,
                                           anchor="nw", border=False), reusable=True))
    out.append(Spec("__arrow", "Arrow", "Free",
                    lambda x, y: M.FreeLine(p1=(x - 40, y - 30), p2=(x, y),
                                            arrow=True), reusable=True))
    out.append(Spec("__line", "Line", "Free",
                    lambda x, y: M.FreeLine(p1=(x - 50, y), p2=(x + 50, y),
                                            arrow=False), reusable=True))
    out.append(Spec("__dim", "Dimension...", "Free",
                    lambda x, y: M.Dimension(text="000 mm",
                                             a1=(x - 70, y), a2=(x - 70, y - 45),
                                             b1=(x + 70, y), b2=(x + 70, y - 45)),
                    reusable=True))
    return out


def placed_ids(lay: M.SheetLayout) -> set:
    return ({b.box_id for b in lay.boxes if b.box_id}
            | {d.dim_id for d in lay.dims if d.dim_id}
            | {l.line_id for l in lay.lines if l.line_id})


def unplaced(specs: List[Spec], lay: M.SheetLayout) -> List[Spec]:
    have = placed_ids(lay)
    return [s for s in specs if s.reusable or s.item_id not in have]


GROUP_ORDER = ("Supports", "Lift points", "Dimensions", "Refer sheets", "Clouds", "General", "Free")


def grouped(specs: List[Spec]) -> List[Tuple[str, List[Spec]]]:
    out = []
    for g in GROUP_ORDER:
        items = [s for s in specs if s.group == g]
        if items:
            out.append((g, items))
    return out


# --------------------------------------------------------------------------
# Iso-page catalog
# --------------------------------------------------------------------------
def build_iso(line_no: str, lift_case_names: List[str],
              note_text: str = "") -> List[Spec]:
    """
    Palette for an iso page.

    - one "REFER SHEET -> <case>" per lift case on this line. The box text is
      a live token "@@REF:<case>@@" that the exporter swaps for the resolved
      sheet number. box_id = "ref:<case>" so it can only be placed once.
    - a manual bordered callout for a cloud that has no lift case.
    - clouds, free items, title, note, sheet number.
    """
    out: List[Spec] = []

    # NB: title, note and sheet-number are auto-placed on the sheet as
    # standing furniture (layout_builder.ensure_iso_furniture), so they are
    # NOT offered in the palette.

    for cn in lift_case_names:
        rid = f"ref:{cn}"
        out.append(Spec(rid, f"REFER SHEET ->  {cn}", "Refer sheets",
                        _tb(rid, "refer", f"@@REF:{cn}@@", "nw", leader=True)))

    # cloud + free items
    out.append(Spec("__cloud", "Revision cloud (draw vertices)", "Clouds",
                    lambda x, y: M.Cloud(pts=[]), reusable=True))
    out.append(Spec("__refman", "Manual callout (cloud, no lift case)", "Clouds",
                    lambda x, y: M.TextBox(kind="free", text="", x=x, y=y,
                                           anchor="nw", tip=(x + 70, y - 45)),
                    reusable=True))
    out.append(Spec("__text", "Text box...", "Free",
                    lambda x, y: M.TextBox(kind="free", text="", x=x, y=y, anchor="nw"),
                    reusable=True))
    out.append(Spec("__callout", "Callout (with arrow)", "Free",
                    lambda x, y: M.TextBox(kind="free", text="", x=x, y=y,
                                           anchor="nw", tip=(x + 70, y - 45)),
                    reusable=True))
    out.append(Spec("__arrow", "Arrow", "Free",
                    lambda x, y: M.FreeLine(p1=(x - 40, y - 30), p2=(x, y), arrow=True),
                    reusable=True))
    out.append(Spec("__line", "Line", "Free",
                    lambda x, y: M.FreeLine(p1=(x - 50, y), p2=(x + 50, y), arrow=False),
                    reusable=True))
    return out


ISO_GROUP_ORDER = ("Refer sheets", "Clouds", "General", "Free")


def grouped_iso(specs: List[Spec]) -> List[Tuple[str, List[Spec]]]:
    out = []
    for g in ISO_GROUP_ORDER:
        items = [s for s in specs if s.group == g]
        if items:
            out.append((g, items))
    return out
