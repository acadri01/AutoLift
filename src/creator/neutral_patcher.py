"""
neutral_patcher.py

Applies live-lift modifications to a parsed NeutralModel:

  1. For each lifted node, identifies the upstream and downstream elements.
     Only the OUTERMOST elements of the lifted group are split.

     The immediate neighbour isn't always the one actually split: a rigid
     element, a reducer, or an expansion joint can't carry an imposed
     displacement; an element with ANY vertical component (a riser, not a
     horizontal run - see _vertical_component and IZUP below) isn't
     suitable for a lift point either; and a bend at EITHER end of an
     element eats into its valid placement zone (T = R * tan(deflection/2),
     deflection computed from the adjacent elements' own geometry, never
     the #$ BEND record's angle fields - see reference/README.md for why).
     A far bend (the end being walked toward) caps how far into the element
     a placement can go; a near bend (the end just arrived at, typically
     after a skip) sets a minimum distance from that end - both are
     checked, not just the far one (checking only the far end was a real
     bug: it let a placement land inside a bend's own tangent zone). A far
     bend that leaves too little room is escaped by walking further out
     (see _walk_to_flexible_element) until an element is found that can
     hold the FULL requested spacing, never silently settling for less on
     a nearer, insufficient element; a near bend can't be escaped that way
     (the next element out has the same problem one hop later), so the
     placement is clamped up to that bend's own minimum clearance instead.
     spacing is preserved as a distance from the RESTRAINED node across
     every hop skipped. Only if the whole pipe run is exhausted without
     finding a fit does this fall back to asking the user (or, headless,
     the existing warn-and-place-at-what's-available behaviour). A SIF/tee
     pointer on the chosen element is warned about, not skipped past.

     "Vertical" depends on the file's own IZUP flag (#$ CONTROL) - CAESAR
     II lets a model use either global -Y or global -Z as vertical, and
     real files in the wild use both (confirmed: reference sample files use
     each convention) - so this is read per file, never assumed.

  2. Splits each outer element at a point 'spacing_mm' from the lifted node,
     inserting a new displacement node. New node number = midpoint rule:
         new_node = from_node + round((to_node - from_node) / 2)
     Collision (node already exists) → increment by ±5 until free.

  3. Injects #$ DISPLMNT records for every new displacement node.
     Displacement: global +Y, vector 3 only, magnitude = displacement_mm.
     All other DOFs = 9999.99 (free).

  4. Updates #$ CONTROL counters:
     - NUMELT            (item 0 of first int line)  += number of splits
     - DISPLMNT count    (item 4 of second int line) += number of new disp nodes

  5. Updates #$ MISCEL_1 RRMAT material ID array:
     - Inserts a duplicate of the split element's material ID at the correct
       position for the new element, BEFORE element splits alter line positions.

Element block structure (v15, 15 lines per element):
  Lines  1-9  : real data  (2X, 6G13.6) — 53 values, 6 per line, last line 5
  Line  10    : Element Name  (7X, I5, 1X, A500)
  Line  11    : Line Number   (7X, I5, 1X, A500)
  Lines 12-15 : IEL integer pointers (2X, 6I13) — layout [2, 6, 6, 3] = 17 values

Public API
----------
    result = patch_model(
        model,
        lifted_nodes,        # List[int]
        spacing_mm,          # float   default 750.0
        displacement_mm,     # float   default 10.0
        on_override,         # Callable | None
    )
    result.modified_lines   # List[str]
    result.new_disp_nodes   # List[int]
    result.warnings         # List[str]
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from neutral_reader import NeutralModel, Element, find_section, find_next_section_start
from ui_dialogs import NodeLiftParams


FREE = 9999.99
# Spec layout is VECTOR-major: [DX1,DY1,DZ1,RX1,RY1,RZ1, DX2,DY2,..., DX9,...,RZ9]
# DY of vector N is at 0-based index (N-1)*6 + 1; DZ of vector N is (N-1)*6 + 2.
# The "lift" displacement is applied in vector 3, along whichever axis this
# file's own IZUP flag (#$ CONTROL - see _read_izup) marks as vertical: DY
# for IZUP=0, DZ for IZUP=1. Getting this wrong applies the displacement
# sideways instead of vertically on a Z-vertical file - see
# _displ_dof_index and QUESTIONS.md's now-resolved "Stop-and-ask" entry.
DISP_DOF_INDEX_Y = 13       # 0-based index in the 54-value array for DY of vector 3
DISP_DOF_INDEX_Z = 14       # 0-based index in the 54-value array for DZ of vector 3


def _displ_dof_index(izup: int) -> int:
    """Which 0-based slot in the 54-value DOF array carries the lift
    displacement, for this file's own vertical axis (see _read_izup)."""
    return DISP_DOF_INDEX_Z if izup == 1 else DISP_DOF_INDEX_Y
BLOCK_LINES = 15            # every element block is exactly 15 lines
REAL_LINES = 9              # lines 0-8: real data
STRING_LINES = 2            # lines 9-10: name + line number
PTR_LINES = 4               # lines 11-14: IEL pointers [2,6,6,3]

_SCI_RE = re.compile(r"[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?")
_INT_RE = re.compile(r"[-+]?\d+")


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class LiftPointInfo:
    """One imposed-displacement lift point, paired with the support it unloads."""
    lift_node: int          # the new displacement BC node
    support_node: int       # the lifted restraint it was placed outside of
    distance_mm: float      # spacing used for THIS split (= along-pipe distance)
    displacement_mm: float  # imposed +Y lift for THIS split


@dataclass
class PatchResult:
    modified_lines: List[str]
    new_disp_nodes: List[int] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    lift_points: List[LiftPointInfo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fixed-stride element block scanner
# ---------------------------------------------------------------------------

@dataclass
class ElementBlock:
    line_start: int         # absolute index in lines[] of the first line
    n_from: int
    n_to: int
    iel: List[int]          # 17 values from the 4 pointer lines


def _scan_element_blocks(lines: List[str]) -> List[ElementBlock]:
    """
    Scan #$ ELEMENTS using a fixed stride of BLOCK_LINES (15) per element.
    The first line of each block contains From/To node as the first two tokens.
    IEL pointer lines are the last 4 lines of each block (indices 11-14).
    """
    start = find_section(lines, "#$ ELEMENTS")
    if start is None:
        return []
    end = find_next_section_start(lines, start)

    blocks: List[ElementBlock] = []
    i = start + 1

    while i + BLOCK_LINES <= end:
        first = lines[i]
        toks = _SCI_RE.findall(first)
        if len(toks) < 2:
            i += 1
            continue

        try:
            n_from = int(round(float(toks[0])))
            n_to   = int(round(float(toks[1])))
            od     = float(toks[5]) if len(toks) > 5 else 0.0
        except (ValueError, IndexError):
            i += 1
            continue

        # Sanity check: valid node numbers and positive OD
        if n_from <= 0 or n_to <= 0 or od <= 0:
            i += 1
            continue

        # Collect IEL from last 4 lines of the fixed-stride block
        ptr_start = i + REAL_LINES + STRING_LINES   # line index 11 within block
        iel: List[int] = []
        for pi in range(ptr_start, ptr_start + PTR_LINES):
            if pi >= end:
                break
            for tok in _SCI_RE.findall(lines[pi]):
                try:
                    iel.append(int(round(float(tok))))
                except ValueError:
                    pass

        blocks.append(ElementBlock(
            line_start=i,
            n_from=n_from,
            n_to=n_to,
            iel=iel,
        ))
        i += BLOCK_LINES

    return blocks


def _find_elements_data_start(lines: List[str]) -> int:
    """
    Return the absolute line index of the first element block in #$ ELEMENTS,
    skipping any blank lines immediately after the section header.
    """
    sec = find_section(lines, "#$ ELEMENTS")
    if sec is None:
        return 0
    i = sec + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    return i


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _element_length(e: Element) -> float:
    return math.sqrt(e.dx ** 2 + e.dy ** 2 + e.dz ** 2)


def _unit_vector(e: Element) -> Tuple[float, float, float]:
    L = _element_length(e)
    if L < 1e-9:
        return (0.0, 0.0, 0.0)
    return (e.dx / L, e.dy / L, e.dz / L)


_VERTICAL_EPS_MM = 1e-6   # floating-point noise guard, not a physical tolerance


def _vertical_component(e: Element, izup: int) -> float:
    """The element's rise/drop (mm) along whichever axis this file's IZUP
    flag (see _read_izup) marks as vertical: global Y if izup==0, global Z
    if izup==1."""
    return e.dz if izup == 1 else e.dy


def _is_vertical(e: Element, izup: int) -> bool:
    """True if the element has ANY vertical component at all - not just a
    dominant one. A lift point needs a horizontal run to sit on; a riser
    (however slight the rise) isn't a candidate."""
    return abs(_vertical_component(e, izup)) > _VERTICAL_EPS_MM


def _midpoint_node(n_from: int, n_to: int) -> int:
    return n_from + round((n_to - n_from) / 2)


def _free_node(candidate: int, existing: Set[int], direction: int) -> int:
    n = candidate
    while n in existing:
        n += direction * 5
    return n


def _upstream_element(node: int, elements: List[Element]) -> Optional[Element]:
    for e in elements:
        if e.n_to == node:
            return e
    return None


def _downstream_element(node: int, elements: List[Element]) -> Optional[Element]:
    for e in elements:
        if e.n_from == node:
            return e
    return None


# ---------------------------------------------------------------------------
# Element auxiliary flags: rigid / reducer / expansion joint / SIF / bend
# ---------------------------------------------------------------------------
# IEL pointer indices within the 17-value array _scan_element_blocks produces
# (2 leading colour/visibility items + the 15 documented auxiliary pointers).
# Confirmed against CAESAR II's own "CAESAR II Neutral File" Users Guide
# chapter (reference/NeutralFile-v15.pdf, "#$ ELEMENTS" -> IEL array
# description) - the same mapping _split_block's own TO_NODE_IDXS comment
# already uses; named here for the skip/clearance logic below.
BEND_PTR_IDX = 2
RIGID_PTR_IDX = 3
EXPJT_PTR_IDX = 4
SIF_PTR_IDX = 12       # "Intersection Auxiliary field" in the vendor doc = SIF&TEES
REDUCER_PTR_IDX = 14

# #$ BEND: a fixed 3-line, 14-value record per bend (radius, weld type, three
# (angle, node) tangent-point pairs, miter count, fitting thickness, seam-weld
# flag, K factor, weld-strength-reduction factor, overlay thickness).
# Confirmed against real #$ BEND bytes, not just the vendor doc's prose - see
# reference/README.md. Only the radius (item 1) is used here: the "angle to
# node position #N" fields are not reliably understood (the same value
# repeats across bends of visibly different orientations in every real
# sample checked), so the actual bend deflection angle used for clearance
# below is computed from the adjacent elements' own geometry instead - see
# _bend_deflection_deg.
BEND_RECORD_LEN = 14


def _read_izup(lines: List[str]) -> int:
    """
    Read the IZUP vertical-axis flag from #$ CONTROL.

    Layout (confirmed against real sample files, not just the vendor doc -
    reference/NeutralFile-v15.pdf's own prose crams the IZUP description
    into the middle of an unrelated bullet, so the byte layout is the
    reliable source here): after the NUMELT/NUMNOZ/NOHGRS/NONAM/NORED/
    NUMFLG line (6 values), the file writes a 13-value auxiliary-data-count
    array in FORTRAN (2X, 6I13) - i.e. 6 values, 6 values, then a FINAL
    line with just the 13th value on its own. That 13th value is IZUP:
    0 = global -Y axis vertical, 1 = global -Z axis vertical. Both
    conventions appear in real files (confirmed: one reference sample uses
    each), so this must be read per file, never assumed to be 0.

    Defaults to 0 (Y vertical, the more common convention) if the file is
    too short/malformed to find it - this flag is advisory (only used to
    decide which delta counts as "vertical" for element-suitability
    checks), so a safe default beats raising.
    """
    start = find_section(lines, "#$ CONTROL")
    if start is None:
        return 0
    six_value_lines: List[int] = []
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("#$"):
            return 0
        toks = _INT_RE.findall(lines[i])
        if len(toks) == 6:
            six_value_lines.append(i)
            if len(six_value_lines) == 3:
                # IZUP is the single value on the next line
                for j in range(i + 1, len(lines)):
                    if lines[j].lstrip().startswith("#$"):
                        return 0
                    jtoks = _INT_RE.findall(lines[j])
                    if jtoks:
                        return int(jtoks[0])
                return 0
    return 0


def _read_bend_radii(lines: List[str]) -> Dict[int, float]:
    """1-based #$ BEND record pointer -> bend radius (record item 1, mm)."""
    start = find_section(lines, "#$ BEND")
    if start is None:
        return {}
    end = find_next_section_start(lines, start)
    vals: List[float] = []
    for ln in lines[start + 1:end]:
        if ln.strip():
            vals.extend(float(t) for t in _SCI_RE.findall(ln))
    radii: Dict[int, float] = {}
    for i in range(len(vals) // BEND_RECORD_LEN):
        radii[i + 1] = vals[i * BEND_RECORD_LEN]
    return radii


def _bend_corner_radii(
    blocks: List["ElementBlock"], bend_radii: Dict[int, float]
) -> Dict[int, float]:
    """
    node -> bend radius, for every real model node that is a bend corner.

    The corner node is the ToNode of whichever element carries that bend's
    pointer (IEL[BEND_PTR_IDX]) - NOT the #$ BEND record's own "node
    position" fields, which are CAESAR's separate, synthetic near/far
    tangent-point node numbers and never appear as a real element endpoint.
    """
    out: Dict[int, float] = {}
    for b in blocks:
        ptr = b.iel[BEND_PTR_IDX] if len(b.iel) > BEND_PTR_IDX else 0
        if ptr > 0 and ptr in bend_radii:
            out[b.n_to] = bend_radii[ptr]
    return out


def _bend_deflection_deg(
    in_vec: Tuple[float, float, float], out_vec: Tuple[float, float, float]
) -> float:
    """
    Deflection (turn) angle in degrees between two unit direction vectors:
    the element arriving at a bend corner and the element leaving it.

    0 deg = straight through, 90 deg = a right-angle elbow, 180 deg = a full
    reversal. This is the dot product angle directly - NOT 180 minus it -
    since a straight run has parallel vectors (dot=1, angle=0 -> no bend)
    and a right-angle elbow has perpendicular vectors (dot=0, angle=90),
    which already matches the elbow's own deflection angle.
    """
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(in_vec, out_vec))))
    return math.degrees(math.acos(dot))


def _bend_tangent_length_mm(radius_mm: float, deflection_deg: float) -> float:
    """Minimum required straight length on EACH side of a bend - standard
    circular-elbow tangent geometry: T = R * tan(deflection / 2)."""
    return radius_mm * math.tan(math.radians(deflection_deg) / 2.0)


def _bend_tangent_at_node(
    node: int,
    elements: List[Element],
    bend_radius_at: Dict[int, float],
) -> Tuple[float, Optional[float], Optional[float]]:
    """
    If `node` is a bend corner, return (tangent_mm, radius_mm, deflect_deg) -
    the minimum straight length required on EITHER side of that bend,
    computed from the two elements meeting there (see _bend_deflection_deg -
    the corner's own geometry, never the #$ BEND record's angle fields).
    Returns (0.0, None, None) if `node` isn't a bend corner, or its adjacent
    elements can't both be found (can't compute a deflection without both).
    """
    radius = bend_radius_at.get(node)
    if not radius:
        return 0.0, None, None
    into_elem = _upstream_element(node, elements)
    out_elem = _downstream_element(node, elements)
    if into_elem is None or out_elem is None:
        return 0.0, None, None
    deflect = _bend_deflection_deg(_unit_vector(into_elem), _unit_vector(out_elem))
    return _bend_tangent_length_mm(radius, deflect), radius, deflect


def _walk_to_flexible_element(
    start_node: int,
    side: str,                                    # "upstream" | "downstream"
    node_spacing: float,
    elements: List[Element],
    iel_by_pair: Dict[Tuple[int, int], List[int]],
    bend_radius_at: Dict[int, float],
    warnings: List[str],
    izup: int = 0,
) -> Optional[Tuple[Element, float, int]]:
    """
    Walk outward from start_node (the support/lift node) in `side` direction
    to find the element a displacement point can actually be placed on:

      - a rigid element, a reducer, or an expansion joint can't carry an
        imposed displacement, so each is skipped in favour of the next
        element further out. node_spacing is preserved as a distance from
        start_node across every hop (per its documented meaning: distance
        from the RESTRAINED node), not reset at each one.
      - an element with ANY vertical component (per this file's IZUP flag -
        see _read_izup/_vertical_component) is skipped the same way - a
        lift point needs a horizontal run to sit on, not a riser.
      - a SIF/tee pointer on the chosen element is warned about, not
        skipped past - it's still eligible for the split.
      - if EITHER end of the chosen element is a bend corner, that bend's
        minimum required tangent length is computed from the adjacent
        elements' own geometry (see _bend_deflection_deg - never from the
        #$ BEND record's angle fields). A bend at the FAR end (away from
        `node`, i.e. the direction being walked toward) caps how far into
        the element a placement can go; a bend at the NEAR end (`node`
        itself - typically the far end of an element skipped the hop
        before) sets a MINIMUM distance a placement must be from that end.
        Checking only the far end was a real bug (fixed 2026-09-09): it let
        a placement land inside a bend's own tangent zone whenever a skip
        happened to land the walk right next to one.
      - whenever the requested spacing doesn't fit in what's actually valid
        here - the element itself is short, a far bend eats into it, or
        both - this element is skipped too, exactly like a rigid element,
        and the next one further out is evaluated. This repeats until an
        element is found that can hold the FULL requested spacing (per
        direct instruction: never silently settle for less on a short or
        bend-adjacent element when a further one could satisfy it). A near
        bend can't be escaped by walking further (the next element out has
        the same node as ITS near end too), so instead of skipping, the
        placement is clamped up to that bend's own minimum clearance.

    Returns (element, local_spacing_mm, far_node), where local_spacing_mm
    is guaranteed to fall within the element's VALID zone - past any near
    bend's minimum clearance, short of any far bend's tangent zone.
    Returns None if the chain runs out or loops - at that point there is
    no automatic answer left, and the caller falls back to asking the user
    (see _resolve_split).
    """
    node = start_node
    remaining = node_spacing
    seen: Set[Tuple[int, int]] = set()

    while True:
        e = (_upstream_element(node, elements) if side == "upstream"
             else _downstream_element(node, elements))
        if e is None:
            return None
        key = (e.n_from, e.n_to)
        if key in seen:
            return None                    # malformed/looping model - bail out
        seen.add(key)

        iel = iel_by_pair.get(key, [])

        def _flag(idx: int) -> bool:
            return len(iel) > idx and iel[idx] > 0

        far_node = e.n_from if side == "upstream" else e.n_to

        if _flag(RIGID_PTR_IDX) or _flag(REDUCER_PTR_IDX) or _flag(EXPJT_PTR_IDX):
            kind = ("a rigid element" if _flag(RIGID_PTR_IDX) else
                    "a reducer" if _flag(REDUCER_PTR_IDX) else "an expansion joint")
            warnings.append(
                f"Element {e.n_from}→{e.n_to} is {kind} — a displacement "
                f"point can't be placed on it. Skipped toward the next "
                f"plain pipe element.")
            remaining -= _element_length(e)
            node = far_node
            continue

        if _is_vertical(e, izup):
            axis = "Z" if izup == 1 else "Y"
            warnings.append(
                f"Element {e.n_from}→{e.n_to} has a vertical component "
                f"({_vertical_component(e, izup):+.1f} mm along global {axis}, "
                f"vertical for this file) — not a horizontal run a lift "
                f"point can sit on. Skipped toward the next element.")
            remaining -= _element_length(e)
            node = far_node
            continue

        if _flag(SIF_PTR_IDX):
            warnings.append(
                f"Element {e.n_from}→{e.n_to} has a SIF/tee pointer — "
                f"verify this lift point placement is acceptable.")

        L = _element_length(e)

        # A bend can sit at EITHER end of this element - the far end (the
        # corner we're walking toward) restricts how far INTO this element a
        # placement can go; a bend at the near end (`node` - where the walk
        # just arrived, e.g. the far end of an element skipped the hop
        # before) restricts how close to the START of this element a
        # placement can be. Missing the near-end case was a real bug: it let
        # a placement land exactly on/inside a bend's own tangent zone
        # whenever a skip (rigid/vertical/too-short/etc.) landed the walk
        # right next to one - reported 2026-09-09 ("this caused a bend to
        # break"). Both must be checked for every candidate element.
        tangent_far, radius_far, deflect_far = _bend_tangent_at_node(
            far_node, elements, bend_radius_at)
        tangent_near, radius_near, deflect_near = _bend_tangent_at_node(
            node, elements, bend_radius_at)

        valid_max = L - tangent_far    # furthest a placement can be from `node`
        valid_min = tangent_near       # closest a placement can be to `node`

        bend_note = ""
        if radius_far is not None:
            bend_note += (
                f" (a bend at node {far_node} - radius {radius_far:.0f} mm, "
                f"{deflect_far:.1f}° turn - needs {tangent_far:.0f} mm "
                f"clearance from that end)")
        if radius_near is not None:
            bend_note += (
                f" (a bend at node {node} - radius {radius_near:.0f} mm, "
                f"{deflect_near:.1f}° turn - needs {tangent_near:.0f} mm "
                f"clearance from that end)")

        if valid_min > valid_max:
            # Bends at both ends (or one very close, tight-radius bend) eat
            # up the entire element - there is no valid placement zone on it
            # at all, regardless of what spacing was requested. Skipped just
            # like a rigid element.
            warnings.append(
                f"Element {e.n_from}→{e.n_to} has no valid placement zone at "
                f"all{bend_note} on a {L:.0f} mm element — skipped toward "
                f"the next element.")
            remaining -= L
            node = far_node
            continue

        if remaining > valid_max:
            # Not enough room here for the full requested spacing - whether
            # because the element itself is short, a bend eats into it, or
            # both. Per direct instruction: never settle for less than
            # requested on this element - walk further out and keep
            # looking, exactly like a rigid element/reducer/expansion joint.
            warnings.append(
                f"Element {e.n_from}→{e.n_to} has only {max(valid_max, 0):.0f} mm "
                f"usable{bend_note or f' (element length {L:.0f} mm)'}, less "
                f"than the requested {remaining:.0f} mm spacing — skipped "
                f"toward the next element.")
            remaining -= L
            node = far_node
            continue

        if remaining < valid_min:
            # The elements skipped on the way out here (rigid/reducer/expjt/
            # vertical, or a bend consuming a whole element) already used up
            # more length than the requested spacing, OR a bend right at
            # `node` itself needs its own tangent clearance - either way the
            # true target point falls somewhere that can't carry a
            # displacement. Clamp to the closest VALID point (the near
            # bend's own tangent clearance, or the very start of this
            # element if there's no near bend) rather than feeding
            # _split_block a spacing that lands inside a bend or goes
            # negative.
            if tangent_near > 0:
                warnings.append(
                    f"Element {e.n_from}→{e.n_to}: a bend at node {node} "
                    f"needs {tangent_near:.0f} mm clearance from this end - "
                    f"placed there instead of the requested "
                    f"{remaining:.0f} mm (which would have landed inside "
                    f"the bend).")
            else:
                warnings.append(
                    f"Element {e.n_from}→{e.n_to}: the requested spacing was "
                    f"entirely used up by skipped rigid/reducer/expansion-"
                    f"joint/vertical/bend elements before reaching here - "
                    f"placed at the start of this element instead.")
            remaining = valid_min

        return e, remaining, far_node


# ---------------------------------------------------------------------------
# Split specification
# ---------------------------------------------------------------------------

@dataclass
class SplitSpec:
    element: Element
    lifted_node: int
    new_node: int
    spacing_mm: float
    side: str               # "upstream" | "downstream"
    _disp_ptr: int = 0      # assigned by patch_model before use


def _resolve_split(
    lifted: int,
    side: str,
    node_spacing: float,
    elements: List[Element],
    iel_by_pair: Dict[Tuple[int, int], List[int]],
    bend_radius_at: Dict[int, float],
    existing_nodes: Set[int],
    on_override: Optional[Callable],
    warnings: List[str],
    izup: int = 0,
) -> Optional[SplitSpec]:
    found = _walk_to_flexible_element(
        lifted, side, node_spacing, elements, iel_by_pair, bend_radius_at,
        warnings, izup)

    if found is None:
        # The walk exhausted the pipe run (or looped) without ever finding
        # an element that could hold the full requested spacing - there is
        # no automatic answer left. Fall back to asking the user (or, with
        # no override callback, the existing warn-and-use-what's-there
        # fallback), pre-filled with the immediate neighbours same as
        # before this element-walk existed.
        problem = (
            f"No {side} element with enough usable length for the "
            f"requested {node_spacing:.0f} mm spacing was found from node "
            f"{lifted} — every candidate was too short, a rigid element / "
            f"reducer / expansion joint / vertical run, or fully consumed "
            f"by a bend's clearance, all the way to the end of the pipe "
            f"run.")
        up_disp = _upstream_element(lifted, elements)
        dn_disp = _downstream_element(lifted, elements)
        fallback_elem = up_disp if side == "upstream" else dn_disp
        if fallback_elem is None:
            warnings.append(f"Node {lifted}: {problem} No {side} element "
                            f"exists at all — {side} split skipped.")
            return None
        candidate = _midpoint_node(fallback_elem.n_from, fallback_elem.n_to)
        direction = -1 if side == "upstream" else +1
        new_node = _free_node(candidate, existing_nodes, direction)
        return _handle_short(
            problem, lifted, up_disp, dn_disp,
            new_node, node_spacing, side,
            elements, existing_nodes, on_override, warnings,
        )

    elem, remaining, _far_node = found
    candidate = _midpoint_node(elem.n_from, elem.n_to)
    direction = -1 if side == "upstream" else +1
    new_node = _free_node(candidate, existing_nodes, direction)
    existing_nodes.add(new_node)
    return SplitSpec(elem, lifted, new_node, remaining, side)


def _determine_splits(
    lifted_nodes: List[int],
    elements: List[Element],
    params_for: Callable,           # (node: int) -> (spacing_mm, displacement_mm)
    existing_nodes: Set[int],
    on_override: Optional[Callable],
    warnings: List[str],
    iel_by_pair: Dict[Tuple[int, int], List[int]],
    bend_radius_at: Dict[int, float],
    izup: int = 0,
) -> List[SplitSpec]:
    sorted_nodes = sorted(lifted_nodes)
    splits: List[SplitSpec] = []
    n = len(sorted_nodes)

    for i, lifted in enumerate(sorted_nodes):
        is_first = (i == 0)
        is_last  = (i == n - 1)

        # Only outermost elements are split
        do_upstream   = is_first
        do_downstream = is_last

        node_spacing, _ = params_for(lifted)

        if do_upstream:
            sp = _resolve_split(
                lifted, "upstream", node_spacing, elements, iel_by_pair,
                bend_radius_at, existing_nodes, on_override, warnings, izup)
            if sp:
                splits.append(sp)

        if do_downstream:
            sp = _resolve_split(
                lifted, "downstream", node_spacing, elements, iel_by_pair,
                bend_radius_at, existing_nodes, on_override, warnings, izup)
            if sp:
                splits.append(sp)

    return splits


def _handle_short(
    problem, lifted, up_elem, dn_elem,
    new_node, spacing_mm, side,
    elements, existing_nodes, on_override, warnings,
) -> Optional[SplitSpec]:
    if on_override:
        override = on_override(
            lifted_node=lifted,
            upstream_from=up_elem.n_from if up_elem else lifted,
            upstream_to=up_elem.n_to if up_elem else lifted,
            downstream_from=dn_elem.n_from if dn_elem else lifted,
            downstream_to=dn_elem.n_to if dn_elem else lifted,
            problem=problem,
        )
        if override is None:
            warnings.append(f"Node {lifted}: {side} override cancelled — split skipped.")
            return None

        if side == "upstream":
            ov_elem = next((e for e in elements
                            if e.n_from == override.upstream_from
                            and e.n_to == override.upstream_to), None)
        else:
            ov_elem = next((e for e in elements
                            if e.n_from == override.downstream_from
                            and e.n_to == override.downstream_to), None)

        if ov_elem is None:
            warnings.append(f"Node {lifted}: overridden element not found — split skipped.")
            return None

        cand = _midpoint_node(ov_elem.n_from, ov_elem.n_to)
        direction = -1 if side == "upstream" else +1
        nn = _free_node(cand, existing_nodes, direction)
        existing_nodes.add(nn)
        return SplitSpec(ov_elem, lifted, nn, spacing_mm, side)
    else:
        # No override callback — use element midpoint, warn
        elem = up_elem if side == "upstream" else dn_elem
        L = _element_length(elem)
        warnings.append(problem + f" Displacement node placed at element midpoint.")
        existing_nodes.add(new_node)
        return SplitSpec(elem, lifted, new_node, min(spacing_mm, L * 0.5), side)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt_v15(x: float) -> str:
    return f"{x:13.6E}"


def _fmt_v13(x: float) -> str:
    if abs(x) < 5e-13:
        s = "0.000000"
    else:
        s = f"{x:.6g}"
    return f"{s:<13}"


def _fmt_real(x: float, version: str) -> str:
    return _fmt_v15(x) if version == "v15" else _fmt_v13(x)


def _fmt_line(values: List[float], version: str) -> str:
    return "  " + "".join(_fmt_real(v, version) for v in values) + "\n"


def _fmt_ptr_line(values: List[int]) -> str:
    return "  " + "".join(f"{v:13d}" for v in values) + "\n"


# ---------------------------------------------------------------------------
# Build two replacement element blocks from one split
# ---------------------------------------------------------------------------

def _split_block(
    original_block: List[str],   # exactly BLOCK_LINES lines
    original: Element,
    new_node: int,
    spacing_mm: float,
    side: str,
    version: str,
    disp_ptr: int,               # 1-based index of the displacement record
) -> List[str]:
    """
    Return 2 * BLOCK_LINES lines replacing the original block.

    side="upstream":   lifted_node is n_to
        sub-A: n_from → new_node   (length = L - spacing_mm)
        sub-B: new_node → n_to     (length = spacing_mm)
        displacement pointer goes on sub-B (the element ending at new_node
        that the displacement is applied to)

    side="downstream": lifted_node is n_from
        sub-A: n_from → new_node   (length = spacing_mm)
        sub-B: new_node → n_to     (length = L - spacing_mm)
        displacement pointer goes on sub-A (the element ending at new_node)
    """
    L  = _element_length(original)
    ux, uy, uz = _unit_vector(original)

    if side == "upstream":
        len_a = max(L - spacing_mm, 1.0)
        len_b = max(spacing_mm, 1.0)
    else:
        len_a = max(spacing_mm, 1.0)
        len_b = max(L - spacing_mm, 1.0)

    dx_a, dy_a, dz_a = ux * len_a, uy * len_a, uz * len_a
    dx_b, dy_b, dz_b = ux * len_b, uy * len_b, uz * len_b

    # Parse original first line tokens (positions 0-1 = from/to, 2-4 = dx/dy/dz, 5+ = rest)
    first_toks = _SCI_RE.findall(original_block[0])
    rest_floats = [float(t) for t in first_toks[5:]]   # OD and beyond (up to 6 per line)

    def _make_first_line(nf: int, nt: int, dx: float, dy: float, dz: float) -> str:
        vals = [float(nf), float(nt), dx, dy, dz] + rest_floats
        return _fmt_line(vals[:6], version)

    # IEL pointer lines: indices 11-14 in the block
    # Layout [2, 6, 6, 3] = 17 values
    # IEL item indices (0-based within 17-value array):
    #   0-1  : leading 2 (element colour / visibility)
    #   2    : bend ptr
    #   3    : rigid ptr
    #   4    : expjt ptr
    #   5    : restrant ptr
    #   6    : displmnt ptr  ← we set this
    #   7    : forcmnt ptr
    #   8    : uniform ptr
    #   9    : wind ptr
    #  10    : offsets ptr
    #  11    : allowbls ptr
    #  12    : sif ptr
    #  13    : nodename ptr
    #  14    : reducer ptr
    #  15    : flange ptr
    #  16    : nozzle ptr
    DISP_IDX = 6   # displacement ptr — set explicitly, never inherited

    # IEL pointer classification:
    #
    # TO-NODE associated — belong to the element whose to-node has that auxiliary.
    # Sub-A ends at new_node (no existing auxiliaries) → zero.
    # Sub-B ends at original to-node → keep.
    #   2  bend
    #   5  restraint
    #   7  force/moment
    #  12  SIF/tee
    #  14  reducer
    #  15  flange
    #  16  nozzle
    TO_NODE_IDXS = [2, 5, 7, 12, 14, 15, 16]

    # SPAN-LEVEL — apply to the pipe element itself, not a specific node.
    # Both sub-elements inherit these.
    #   0  colour        (not a ptr, but carry through)
    #   1  visibility    (not a ptr, but carry through)
    #   3  rigid
    #   4  expansion joint
    #   8  uniform load
    #   9  wind/wave
    #  10  element offsets
    #  11  allowable stress
    #  13  node name

    # Read existing IEL values from original block ptr lines
    orig_iel: List[int] = []
    for pi in range(REAL_LINES + STRING_LINES,
                    REAL_LINES + STRING_LINES + PTR_LINES):
        for tok in _SCI_RE.findall(original_block[pi]):
            try:
                orig_iel.append(int(round(float(tok))))
            except ValueError:
                pass
    orig_iel = (orig_iel + [0] * 17)[:17]

    def _make_ptr_lines(iel: List[int]) -> List[str]:
        chunks = [iel[0:2], iel[2:8], iel[8:14], iel[14:17]]
        return [_fmt_ptr_line(c) for c in chunks]

    # Sub-A always ends at new_node — zero all to-node ptrs and displacement.
    # Sub-B always ends at the original to-node — keep all to-node ptrs.
    # Displacement is set explicitly on whichever sub-element carries new_node
    # as its to-node (downstream: sub-A) or from-node (upstream: sub-B).
    iel_a = list(orig_iel)
    iel_b = list(orig_iel)

    for idx in TO_NODE_IDXS:
        iel_a[idx] = 0
    iel_a[DISP_IDX] = 0
    iel_b[DISP_IDX] = 0   # cleared on both; set explicitly below

    # Displacement ptr is to-node associated like all other ptrs.
    # new_node is always the TO-NODE of sub-A → displacement ptr always on sub-A.
    iel_a[DISP_IDX] = disp_ptr

    # Assemble block A
    block_a = (
        [_make_first_line(original.n_from, new_node, dx_a, dy_a, dz_a)]
        + original_block[1:REAL_LINES]           # lines 1-8: rest of real data unchanged
        + original_block[REAL_LINES:REAL_LINES + STRING_LINES]  # name + line number
        + _make_ptr_lines(iel_a)
    )

    # Assemble block B
    block_b = (
        [_make_first_line(new_node, original.n_to, dx_b, dy_b, dz_b)]
        + original_block[1:REAL_LINES]
        + original_block[REAL_LINES:REAL_LINES + STRING_LINES]
        + _make_ptr_lines(iel_b)
    )

    return block_a + block_b


# ---------------------------------------------------------------------------
# CONTROL counter update
# ---------------------------------------------------------------------------

def _update_control_counts(
    lines: List[str],
    extra_elements: int,
    extra_displacements: int,
) -> None:
    start = find_section(lines, "#$ CONTROL")
    if start is None:
        return

    int_lines: List[int] = []
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("#$"):
            break
        toks = _INT_RE.findall(lines[i])
        if len(toks) == 6:
            int_lines.append(i)
        if len(int_lines) == 4:
            break

    if len(int_lines) < 2:
        return

    # First int line: item 0 = NUMELT
    idx0 = int_lines[0]
    vals0 = [int(t) for t in _INT_RE.findall(lines[idx0])]
    vals0[0] += extra_elements
    lines[idx0] = "  " + "".join(f"{v:13d}" for v in vals0) + "\n"

    # Second int line: item 4 = displacement count
    idx1 = int_lines[1]
    vals1 = [int(t) for t in _INT_RE.findall(lines[idx1])]
    if len(vals1) > 4:
        vals1[4] += extra_displacements
        lines[idx1] = "  " + "".join(f"{v:13d}" for v in vals1) + "\n"


# ---------------------------------------------------------------------------
# DISPLMNT section
# ---------------------------------------------------------------------------

def _build_displmnt_record(
    node: int,
    displacement_mm: float,
    version: str,
    izup: int = 0,
) -> List[str]:
    """
    20 lines per displacement auxiliary block (2 slots x 10 lines each).

    Format mirrors the FORCMNT writer:
      Line 1    : node number on its own line  "  " + G13.6
      Lines 2-10: 54 DOF values in 9 lines of 6

    VECTOR-major storage order:
      [DX1,DY1,DZ1,RX1,RY1,RZ1, DX2,DY2,DZ2,RX2,RY2,RZ2, ..., DX9,...,RZ9]
      one line of 6 values per vector - see _dof_lines below.

    The lift displacement is applied in vector 3, along whichever axis this
    file's own IZUP flag marks as vertical (see _displ_dof_index) - DY for
    IZUP=0, DZ for IZUP=1. Applying it to DY unconditionally would push the
    pipe sideways instead of lifting it on a Z-vertical file.

    Slot 2: node = 0, all FREE.
    """
    F = FREE
    D = displacement_mm

    def _node_line(n: int) -> str:
        if version == "v15":
            return "  " + f"{float(n):13.6E}" + "\n"
        else:
            return f"    {float(n):.4f}    \n"

    def _fmt_val(x: float) -> str:
        if version == "v15":
            return f"{x:13.6E}"
        else:
            if abs(x) < 5e-13:
                return f"{'0.000000':<13}"
            return f"{x:<13.6g}"

    def _vec_line(vals: List[float]) -> str:
        return "  " + "".join(_fmt_val(v) for v in vals) + "\n"

    dof_index = _displ_dof_index(izup)

    def _dof_lines(apply_disp: bool) -> List[str]:
        # Spec layout is VECTOR-major:
        # [DX1,DY1,DZ1,RX1,RY1,RZ1, DX2,DY2,DZ2,RX2,RY2,RZ2, ..., DX9,...,RZ9]
        # Written as 9 lines of 6 values (one line per vector).
        vals54: List[float] = [F] * 54
        if apply_disp:
            vals54[dof_index] = D

        out = []
        for i in range(0, 54, 6):
            out.append(_vec_line(vals54[i:i + 6]))
        return out

    slot1 = [_node_line(node)] + _dof_lines(apply_disp=True)
    slot2 = [_node_line(0)]    + _dof_lines(apply_disp=False)

    return slot1 + slot2


def _count_existing_displmnt_records(lines: List[str]) -> int:
    start = find_section(lines, "#$ DISPLMNT")
    if start is None:
        return 0
    end = find_next_section_start(lines, start)
    non_empty = sum(1 for ln in lines[start+1:end] if ln.strip())
    return non_empty // 20


def _inject_displmnt_section(
    lines: List[str],
    new_record_lines: List[str],
) -> None:
    """Append to existing #$ DISPLMNT or insert after #$ RESTRANT."""
    disp_start = find_section(lines, "#$ DISPLMNT")

    if disp_start is not None:
        disp_end = find_next_section_start(lines, disp_start)
        lines[disp_end:disp_end] = new_record_lines
        return

    # Insert new section
    insert_after = find_section(lines, "#$ RESTRANT")
    if insert_after is None:
        insert_after = find_section(lines, "#$ FORCMNT")
    if insert_after is None:
        insert_after = len(lines) - 1

    insert_at = find_next_section_start(lines, insert_after)
    lines[insert_at:insert_at] = ["#$ DISPLMNT\n"] + new_record_lines


# ---------------------------------------------------------------------------
# MISCEL_1 RRMAT material ID array update
# ---------------------------------------------------------------------------

def _get_numelt_from_control(lines: List[str]) -> int:
    """Read NUMELT (item 0) from the first integer line of #$ CONTROL."""
    start = find_section(lines, "#$ CONTROL")
    if start is None:
        return 0
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("#$"):
            break
        toks = _INT_RE.findall(lines[i])
        if len(toks) == 6:
            return int(toks[0])
    return 0


def _read_rrmat_vals(lines: List[str], numelt: int) -> Tuple[int, int, List[float]]:
    """
    Read exactly `numelt` RRMAT material IDs from #$ MISCEL_1.

    MISCEL_1 contains multiple concatenated sub-arrays. The RRMAT array is
    always the FIRST sub-array and has exactly one entry per element (NUMELT).
    Reading by value count — not by row content — is the only reliable way to
    separate RRMAT from the subsequent integer parameter block, whose values
    also pass an integer-likeness test and would otherwise be consumed.

    Returns (rrmat_start, rrmat_end, vals) where:
      rrmat_start  — absolute line index of first RRMAT data line
      rrmat_end    — absolute line index one past the last RRMAT data line
      vals         — flat list of exactly numelt float values (material IDs)

    Returns (0, 0, []) if section not found.
    """
    sec = find_section(lines, "#$ MISCEL_1")
    if sec is None:
        return 0, 0, []

    rrmat_start = sec + 1
    vals: List[float] = []
    i = rrmat_start

    while i < len(lines) and len(vals) < numelt:
        ln = lines[i]
        if ln.lstrip().startswith("#$"):
            break
        toks = _SCI_RE.findall(ln)
        if not toks:
            break
        vals.extend(float(t) for t in toks)
        i += 1

    # Trim any over-read from the last partial line (shouldn't happen with
    # 6-per-line and NUMELT divisible by 6, but guard anyway)
    vals = vals[:numelt]
    rrmat_end = i   # first line NOT part of RRMAT

    return rrmat_start, rrmat_end, vals


def _write_rrmat_vals(lines: List[str], rrmat_start: int, rrmat_end: int,
                      vals: List[float], version: str) -> None:
    """
    Rewrite the RRMAT lines in-place, replacing lines[rrmat_start:rrmat_end].
    6 values per line, matching the original format.
    """
    def _fmt_rrmat(v: float) -> str:
        if version == "v15":
            return f"{v:.6E}"
        else:
            return f"{round(v):.1f}"

    new_lines: List[str] = []
    for i in range(0, len(vals), 6):
        chunk = vals[i:i + 6]
        new_lines.append("   " + " ".join(_fmt_rrmat(v) for v in chunk) + "\n")

    lines[rrmat_start:rrmat_end] = new_lines


def _update_rrmat(
    lines: List[str],
    rrmat_indices: List[Tuple[int, float]],
    version: str,
    numelt: int,
) -> None:
    """
    Insert new RRMAT material ID entries for each split element.

    rrmat_indices: list of (rrmat_idx, mat_id) pairs in forward file order.
      rrmat_idx is the 0-based ordinal of the element being split within the
      ELEMENTS section. The new entry is inserted immediately AFTER it
      (i.e. at position rrmat_idx + 1 + cumulative_offset).

    numelt: the original element count (NUMELT from CONTROL before any edits),
      used to bound the RRMAT read so the subsequent MISCEL_1 sub-arrays are
      not consumed.

    Must be called BEFORE element splits are written to lines, so that
    line positions in MISCEL_1 have not shifted.
    """
    rrmat_start, rrmat_end, vals = _read_rrmat_vals(lines, numelt)
    if not vals:
        return

    offset = 0
    for rrmat_idx, mat_id in sorted(rrmat_indices):
        insert_at = rrmat_idx + 1 + offset
        # Guard against out-of-range indices
        insert_at = max(0, min(insert_at, len(vals)))
        vals.insert(insert_at, mat_id)
        offset += 1

    _write_rrmat_vals(lines, rrmat_start, rrmat_end, vals, version)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def patch_model(
    model: NeutralModel,
    lifted_nodes: List[int],
    node_params: Optional[List[NodeLiftParams]] = None,
    spacing_mm: float = 750.0,       # fallback when node_params is None
    displacement_mm: float = 10.0,   # fallback when node_params is None
    on_override: Optional[Callable] = None,
) -> PatchResult:

    warnings: List[str] = []
    lines: List[str] = list(model.lines)

    # Apply config-file defaults when no explicit values given
    if spacing_mm == 750.0 or displacement_mm == 10.0:
        try:
            from config import default_spacing_mm, default_displacement_mm
            if spacing_mm == 750.0:
                spacing_mm = default_spacing_mm()
            if displacement_mm == 10.0:
                displacement_mm = default_displacement_mm()
        except ImportError:
            pass

    # Build per-node lookup: node (int) → (spacing_mm, displacement_mm)
    _node_params: dict[int, tuple[float, float]] = {}
    if node_params:
        for np_ in node_params:
            _node_params[int(np_.node)] = (np_.spacing_mm, np_.displacement_mm)

    def _params_for(node: int) -> tuple[float, float]:
        return _node_params.get(node, (spacing_mm, displacement_mm))


    existing_nodes: Set[int] = (
        {e.n_from for e in model.elements} |
        {e.n_to   for e in model.elements}
    )

    # ── 0. Scan element blocks (fixed stride) — moved ahead of split
    # determination so the rigid/reducer/expansion-joint/bend-aware element
    # selection below can inspect each element's IEL pointers and any bend's
    # radius before deciding what to split. ───────────────────────────────────
    blocks = _scan_element_blocks(lines)
    block_map: Dict[Tuple[int, int], ElementBlock] = {
        (b.n_from, b.n_to): b for b in blocks
    }
    iel_by_pair: Dict[Tuple[int, int], List[int]] = {
        (b.n_from, b.n_to): b.iel for b in blocks
    }
    bend_radius_at = _bend_corner_radii(blocks, _read_bend_radii(lines))
    izup = _read_izup(lines)

    # ── 1. Determine splits ──────────────────────────────────────────────────
    splits = _determine_splits(
        lifted_nodes=sorted(lifted_nodes),
        elements=model.elements,
        params_for=_params_for,
        existing_nodes=set(existing_nodes),
        on_override=on_override,
        warnings=warnings,
        iel_by_pair=iel_by_pair,
        bend_radius_at=bend_radius_at,
        izup=izup,
    )

    if not splits:
        warnings.append("No element splits were determined — model unchanged.")
        return PatchResult(modified_lines=lines, warnings=warnings)

    # ── 3. Count existing displacement records before any changes ────────────
    existing_disp_count = _count_existing_displmnt_records(lines)

    # ── 4. Assign displacement record pointers ───────────────────────────────
    for k, sp in enumerate(splits):
        sp._disp_ptr = existing_disp_count + k + 1   # 1-based

    # ── 5. Resolve block positions for each split ────────────────────────────
    splits_with_pos: List[Tuple[int, SplitSpec, ElementBlock]] = []
    for sp in splits:
        key = (sp.element.n_from, sp.element.n_to)
        blk = block_map.get(key)
        if blk is None:
            warnings.append(
                f"Element {sp.element.n_from}→{sp.element.n_to} "
                f"not found in block map — split skipped.")
            continue
        splits_with_pos.append((blk.line_start, sp, blk))

    if not splits_with_pos:
        warnings.append("No blocks located — model unchanged.")
        return PatchResult(modified_lines=lines, warnings=warnings)

    # ── 6. Compute RRMAT indices and update MISCEL_1 BEFORE splits ───────────
    # The ELEMENTS data start is the first non-blank line after #$ ELEMENTS.
    # Each element occupies exactly BLOCK_LINES lines, so the ordinal index of
    # an element within the section is: (block_start - data_start) // BLOCK_LINES
    # This equals its flat index in the RRMAT array.
    #
    # CRITICAL: _update_rrmat must be called HERE, before element splits
    # insert new lines and shift all subsequent line positions in the file.
    #
    # numelt_orig is the element count BEFORE any splits — this is the exact
    # number of RRMAT entries currently in MISCEL_1 and bounds the read so
    # the subsequent MISCEL_1 sub-arrays are not consumed.
    numelt_orig = _get_numelt_from_control(lines)

    data_start = _find_elements_data_start(lines)

    _, _, rrmat_vals_snapshot = _read_rrmat_vals(lines, numelt_orig)

    rrmat_indices: List[Tuple[int, float]] = []
    for _pos, sp, blk in sorted(splits_with_pos, key=lambda x: x[0]):
        rrmat_idx = (blk.line_start - data_start) // BLOCK_LINES
        mat_id = (rrmat_vals_snapshot[rrmat_idx]
                  if rrmat_idx < len(rrmat_vals_snapshot) else 175.0)
        rrmat_indices.append((rrmat_idx, mat_id))

    _update_rrmat(lines, rrmat_indices, model.version, numelt_orig)

    # ── 7. Apply element splits in REVERSE file order ────────────────────────
    splits_with_pos.sort(key=lambda x: x[0], reverse=True)

    new_disp_nodes: List[int] = []
    disp_records: List[List[str]] = []
    lift_points: List[LiftPointInfo] = []

    for _pos, sp, blk in splits_with_pos:
        original_block = lines[blk.line_start: blk.line_start + BLOCK_LINES]
        new_lines = _split_block(
            original_block=original_block,
            original=sp.element,
            new_node=sp.new_node,
            spacing_mm=sp.spacing_mm,
            side=sp.side,
            version=model.version,
            disp_ptr=sp._disp_ptr,
        )
        lines[blk.line_start: blk.line_start + BLOCK_LINES] = new_lines
        new_disp_nodes.append(sp.new_node)
        _, sp_disp_mm = _params_for(sp.lifted_node)
        disp_records.append(
            _build_displmnt_record(sp.new_node, sp_disp_mm, model.version, izup)
        )
        lift_points.append(LiftPointInfo(
            lift_node=sp.new_node,
            support_node=sp.lifted_node,
            distance_mm=sp.spacing_mm,
            displacement_mm=sp_disp_mm,
        ))

    # disp_records were built in reverse file order (splits_with_pos is reversed).
    # Reverse them so record 1 in the file corresponds to ptr=1, record 2 to ptr=2, etc.
    disp_records.reverse()
    new_disp_nodes.reverse()
    lift_points.reverse()

    # ── 8. Inject DISPLMNT records ───────────────────────────────────────────
    all_rec_lines = [ln for rec in disp_records for ln in rec]
    _inject_displmnt_section(lines, all_rec_lines)

    # ── 9. Update CONTROL counters ───────────────────────────────────────────
    _update_control_counts(
        lines,
        extra_elements=len(splits_with_pos),
        extra_displacements=len(disp_records),
    )

    return PatchResult(
        modified_lines=lines,
        new_disp_nodes=new_disp_nodes,
        warnings=warnings,
        lift_points=lift_points,
    )
