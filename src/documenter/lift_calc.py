"""
lift_calc.py
------------
Pure functions. No UI, no DB, no I/O. Everything here is unit-testable.

Two jobs:
  1. Lift force N -> documented kg, with the derivation shown.
  2. Support function codes -> mark-up text block.
  3. The parametric note block.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence

# --------------------------------------------------------------------------
# Constants - single point of truth
# --------------------------------------------------------------------------
G = 9.81                # m/s^2
LOAD_FACTOR = 1.2       # applied to the raw reaction
ROUND_TO_KG = 100       # documented value rounds UP to this increment


# --------------------------------------------------------------------------
# Force
# --------------------------------------------------------------------------
def raw_kg(force_n: float) -> float:
    """1.2 * F / g  ->  kg, unrounded."""
    return force_n * LOAD_FACTOR / G


def roundup(value: float, increment: int = ROUND_TO_KG) -> int:
    """Round UP to the nearest increment. 400.1 -> 500 at increment 100."""
    return int(math.ceil(value / increment) * increment)


def documented_kg(forces_n: Sequence[float]) -> Optional[int]:
    """
    The mark-up shows one equal force at every lift point.
    That value is the roundup of the MAXIMUM processed force in the case.
    Returns None if no forces have been entered yet.
    """
    vals = [f for f in forces_n if f is not None]
    if not vals:
        return None
    return roundup(max(raw_kg(f) for f in vals))


def documented_kg_one(force_n: Optional[float]) -> Optional[int]:
    """Per-point documented value: ROUNDUP(1.2 * F / g) for a single force."""
    if force_n is None:
        return None
    return roundup(raw_kg(force_n))


def point_doc_kg(force_n: Optional[float], forces_n: Sequence[float],
                 individual: bool) -> Optional[int]:
    """
    The documented kg to show at ONE lift point:
      individual=False -> the case-governing value (max), as before
      individual=True  -> that point's own rounded value
    """
    if individual:
        return documented_kg_one(force_n)
    return documented_kg(forces_n)


def force_derivation(lift_points: List[Dict], individual: bool = False) -> str:
    """
    lift_points: [{"node": 325, "force_n": 3850.0}, ...]
    Renders the calculation steps for retrieval / checking.

    individual=False: one governing value applied at every point (default).
    individual=True : each point documents its own ROUNDUP(1.2*F/g); no
                      single governing value.
    """
    entered = [lp for lp in lift_points if lp.get("force_n") is not None]
    if not entered:
        return "No lift forces entered."

    lines: List[str] = [
        f"Processing:  m = F x {LOAD_FACTOR} / g,   g = {G} m/s^2",
        "",
    ]

    if individual:
        for lp in entered:
            f = float(lp["force_n"])
            doc = roundup(raw_kg(f))
            lines.append(
                f"  Node {lp['node']:>5}:  F = {f:>10,.1f} N"
                f"   ->  {f:,.1f} x {LOAD_FACTOR} / {G} = {raw_kg(f):>8.1f} kg"
                f"   ->  {doc} kg"
            )
        lines += [
            "",
            "  Each lift point is documented with its own value above.",
        ]
        return "\n".join(lines)

    for lp in entered:
        f = float(lp["force_n"])
        lines.append(
            f"  Node {lp['node']:>5}:  F = {f:>10,.1f} N"
            f"   ->  {f:,.1f} x {LOAD_FACTOR} / {G} = {raw_kg(f):>8.1f} kg"
        )

    peak = max(raw_kg(float(lp["force_n"])) for lp in entered)
    peak_node = max(entered, key=lambda lp: float(lp["force_n"]))["node"]
    doc = roundup(peak)

    lines += [
        "",
        f"  Governing:   node {peak_node}  ->  {peak:.1f} kg",
        f"  Documented:  ROUNDUP({peak:.1f} kg, {ROUND_TO_KG}) = {doc} kg",
        "",
        f"  {doc} kg applied at every lift point in this case.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Support functions
# --------------------------------------------------------------------------
# entry code -> display text. Order of this dict IS the display order.
FUNCTION_MAP = {
    "r": "Rest",
    "hd": "Hold Down",
    "g": "Guide",
    "l": "Limit Stop",
}

_SPLIT = re.compile(r"[,\s+/]+")


def parse_functions(raw: str) -> List[str]:
    """
    'r hd g'  /  'R,HD,G'  /  'r+hd+g'  ->  ['r','hd','g'] in canonical order.
    Unknown codes are dropped silently; validate_functions reports them.
    """
    tokens = {t.lower() for t in _SPLIT.split(raw.strip()) if t}
    return [code for code in FUNCTION_MAP if code in tokens]


def validate_functions(raw: str) -> List[str]:
    """Returns the list of unrecognised tokens."""
    tokens = [t.lower() for t in _SPLIT.split(raw.strip()) if t]
    return [t for t in tokens if t not in FUNCTION_MAP]


def function_text(node: int, raw_codes: str) -> str:
    """
    -> 'Node 430\\nRest + Hold Down + Guide + Limit Stop'
    Only the entered functions appear, always in canonical order.
    When all four (r, hd, g, l) are present, the support is fully fixed and
    the text collapses to 'Anchor'.
    """
    codes = parse_functions(raw_codes)
    if not codes:
        return f"Node {node}"
    if set(codes) == set(FUNCTION_MAP.keys()):
        return f"Node {node}\nAnchor"
    return f"Node {node}\n" + " + ".join(FUNCTION_MAP[c] for c in codes)


# --------------------------------------------------------------------------
# Lift point label (the annotation beside each arrow)
# --------------------------------------------------------------------------
def lift_label(node: int, disp_mm: float, doc_kg: Optional[int]) -> str:
    """
    -> 'Node 325\\nLift 10 mm\\n500 kg'
    """
    d = f"{disp_mm:g}"
    if doc_kg is None:
        return f"Node {node}\nLift {d} mm"
    return f"Node {node}\nLift {d} mm\n{doc_kg} kg"


# --------------------------------------------------------------------------
# Note block
# --------------------------------------------------------------------------
def _join(items: Sequence) -> str:
    """[325] -> '325';  [325,475] -> '325 & 475';  [1,2,3] -> '1, 2 & 3'"""
    s = [str(i) for i in items]
    if len(s) == 1:
        return s[0]
    return ", ".join(s[:-1]) + " & " + s[-1]


def note_text(
    lift_nodes: Sequence[int],
    support_nodes: Sequence[int],
    disp_mm: float,
) -> str:
    """
    2 supports:
      'Due to lifts at nodes 325 & 475, supports at nodes 340 & 430 will lift
       approx. 10 mm.
       Lift shall take place simultaneously.'
    1 support:
      '... support at node 340 will lift approx. 10 mm. ...'
    """
    if not lift_nodes or not support_nodes:
        return ""

    lift_part = (
        f"lift at node {lift_nodes[0]}"
        if len(lift_nodes) == 1
        else f"lifts at nodes {_join(lift_nodes)}"
    )
    sup_part = (
        f"support at node {support_nodes[0]}"
        if len(support_nodes) == 1
        else f"supports at nodes {_join(support_nodes)}"
    )

    return (
        f"Due to {lift_part}, {sup_part} will lift approx. {disp_mm:g} mm.\n"
        f"Lift shall take place simultaneously."
    )
