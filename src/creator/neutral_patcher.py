"""
neutral_patcher.py

Applies live-lift modifications to a parsed NeutralModel:

  1. For each lifted node, identifies the upstream and downstream elements.
     Only the OUTERMOST elements of the lifted group are split.

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
# DY of vector N is at 0-based index (N-1)*6 + 1
# We apply displacement in Y (DY) of vector 3: index (3-1)*6 + 1 = 13
DISP_DOF_INDEX = 13         # 0-based index in the 54-value array for DY of vector 3
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


def _determine_splits(
    lifted_nodes: List[int],
    elements: List[Element],
    params_for: Callable,           # (node: int) -> (spacing_mm, displacement_mm)
    existing_nodes: Set[int],
    on_override: Optional[Callable],
    warnings: List[str],
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

        up_elem = _upstream_element(lifted, elements)
        dn_elem = _downstream_element(lifted, elements)
        node_spacing, _ = params_for(lifted)

        if do_upstream:
            if up_elem is None:
                warnings.append(
                    f"Node {lifted}: no upstream element found — upstream split skipped.")
            else:
                L = _element_length(up_elem)
                candidate = _midpoint_node(up_elem.n_from, up_elem.n_to)
                new_node  = _free_node(candidate, existing_nodes, direction=-1)

                if L < node_spacing:
                    problem = (
                        f"Upstream element {up_elem.n_from}→{up_elem.n_to} "
                        f"is {L:.0f} mm — shorter than spacing {node_spacing:.0f} mm.")
                    sp = _handle_short(
                        problem, lifted, up_elem, dn_elem,
                        new_node, node_spacing, "upstream",
                        elements, existing_nodes, on_override, warnings,
                    )
                else:
                    existing_nodes.add(new_node)
                    sp = SplitSpec(up_elem, lifted, new_node, node_spacing, "upstream")

                if sp:
                    splits.append(sp)

        if do_downstream:
            if dn_elem is None:
                warnings.append(
                    f"Node {lifted}: no downstream element found — downstream split skipped.")
            else:
                L = _element_length(dn_elem)
                candidate = _midpoint_node(dn_elem.n_from, dn_elem.n_to)
                new_node  = _free_node(candidate, existing_nodes, direction=+1)

                if L < node_spacing:
                    problem = (
                        f"Downstream element {dn_elem.n_from}→{dn_elem.n_to} "
                        f"is {L:.0f} mm — shorter than spacing {node_spacing:.0f} mm.")
                    sp = _handle_short(
                        problem, lifted, up_elem, dn_elem,
                        new_node, node_spacing, "downstream",
                        elements, existing_nodes, on_override, warnings,
                    )
                else:
                    existing_nodes.add(new_node)
                    sp = SplitSpec(dn_elem, lifted, new_node, node_spacing, "downstream")

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
) -> List[str]:
    """
    20 lines per displacement auxiliary block (2 slots x 10 lines each).

    Format mirrors the FORCMNT writer:
      Line 1    : node number on its own line  "  " + G13.6
      Lines 2-10: 54 DOF values in 9 lines of 6

    DOF-major storage order (matches Caesar display):
      values  1-9:  DX for vectors 1-9
      values 10-18: DY for vectors 1-9  <- DY vec3 = value 12
      values 19-27: DZ for vectors 1-9
      values 28-36: RX for vectors 1-9
      values 37-45: RY for vectors 1-9
      values 46-54: RZ for vectors 1-9

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

    def _dof_lines(apply_disp: bool) -> List[str]:
        # Spec layout is VECTOR-major:
        # [DX1,DY1,DZ1,RX1,RY1,RZ1, DX2,DY2,DZ2,RX2,RY2,RZ2, ..., DX9,...,RZ9]
        # Written as 9 lines of 6 values (one line per vector).
        # DY of vector 3 = 0-based index (3-1)*6 + 1 = 13 = DISP_DOF_INDEX
        vals54: List[float] = [F] * 54
        if apply_disp:
            vals54[DISP_DOF_INDEX] = D

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

    # ── 1. Determine splits ──────────────────────────────────────────────────
    splits = _determine_splits(
        lifted_nodes=sorted(lifted_nodes),
        elements=model.elements,
        params_for=_params_for,
        existing_nodes=set(existing_nodes),
        on_override=on_override,
        warnings=warnings,
    )

    if not splits:
        warnings.append("No element splits were determined — model unchanged.")
        return PatchResult(modified_lines=lines, warnings=warnings)

    # ── 2. Scan element blocks (fixed stride) ────────────────────────────────
    blocks = _scan_element_blocks(lines)
    block_map: Dict[Tuple[int, int], ElementBlock] = {
        (b.n_from, b.n_to): b for b in blocks
    }

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
            _build_displmnt_record(sp.new_node, sp_disp_mm, model.version)
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
