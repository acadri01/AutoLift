from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# -----------------------------
# Common data model (version-agnostic)
# -----------------------------
VEC_VALUE_COUNT = 54  # 9 vectors * 6


@dataclass
class Element:
    idx: int
    n_from: int
    n_to: int
    dx: float
    dy: float
    dz: float
    od_mm: float
    thk_mm: float


@dataclass
class ForcMntRecord:
    node1: int
    vec1: List[float]  # 54
    node2: int         # usually 0
    vec2: List[float]  # 54


@dataclass
class NeutralModel:
    version: str              # "v13" | "v15" | future
    path: Path
    lines: List[str]          # original text, keepends=True

    elements: List[Element]

    bend_nodes: List[int]
    tee_nodes: List[int]
    slug_nodes: List[int]

    # FORCMNT block
    forcmnt_start: Optional[int]
    forcmnt_end: Optional[int]
    forcmnt_records: List[ForcMntRecord]


# -----------------------------
# Shared helpers
# -----------------------------
def find_section(lines: List[str], header: str) -> Optional[int]:
    for i, ln in enumerate(lines):
        if ln.strip().upper() == header.upper():
            return i
    return None


def find_next_section_start(lines: List[str], start_idx: int) -> int:
    for i in range(start_idx + 1, len(lines)):
        if lines[i].lstrip().startswith("#$"):
            return i
    return len(lines)


# -----------------------------
# Detection
# -----------------------------
def detect_version(lines: List[str]) -> str:
    """
    Read version from the #$ VERSION block.

    Expected:
      #$ VERSION
          5.00000      13.0000        1252
      or
          5.00000      15.0000        1252

    We read the first numeric line after the header and take the 2nd number.
    """
    i = find_section(lines, "#$ VERSION")
    if i is None:
        return "v13"

    # find first numeric-looking line after the header
    j = i + 1
    while j < len(lines):
        s = lines[j].strip()
        if not s:
            j += 1
            continue
        if s.startswith("#$"):
            break
        # must start like a number line
        if s[0] not in "+-0123456789":
            j += 1
            continue

        toks = _SCI_RE.findall(s)
        if len(toks) >= 2:
            try:
                ver = int(round(float(toks[1])))
                if ver >= 15:
                    return "v15"
                return "v13"
            except ValueError:
                pass
        break

    return "v13"


# -----------------------------
# v13 parsing
# -----------------------------
_NUM_RE_V13 = re.compile(r"[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?")
_NODE_TOKEN_4Z = re.compile(r"[-+]?\d+\.0{4}$")
_NODE_LINE_RE_V13 = re.compile(r"^\s*[-+]?\d+\.\d+\s*$")
_NODE_SUFFIX_4Z = re.compile(r"\.0{4}$")
_TOKEN_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?")


def _v13_is_node_line(line: str) -> bool:
    s = line.strip()
    if not _NODE_LINE_RE_V13.match(line):
        return False
    return _NODE_TOKEN_4Z.match(s) is not None


def _v13_parse_node(line: str) -> int:
    return int(round(float(line.strip())))


def _v13_numbers(line: str) -> List[float]:
    return [float(x) for x in _NUM_RE_V13.findall(line)]


def _v13_tokens(line: str) -> List[str]:
    return _TOKEN_RE.findall(line)


def _v13_token_to_node(tok: str) -> Optional[int]:
    if _NODE_SUFFIX_4Z.search(tok) is None:
        return None
    try:
        return int(round(float(tok)))
    except ValueError:
        return None


def _v13_extract_nodes_from_aux(lines: List[str], aux_header: str, field_index: int) -> List[int]:
    i = find_section(lines, aux_header)
    if i is None:
        return []
    end = find_next_section_start(lines, i)
    out: List[int] = []
    for ln in lines[i + 1:end]:
        s = ln.strip()
        if not s or s[0] not in "+-0123456789":
            continue
        toks = _v13_tokens(s)
        if len(toks) > field_index:
            n = _v13_token_to_node(toks[field_index])
            if n is not None and n > 0:
                out.append(n)
    return out


def _v13_parse_elements(lines: List[str]) -> List[Element]:
    start = find_section(lines, "#$ ELEMENTS")
    if start is None:
        return []
    end = find_next_section_start(lines, start)

    elems: List[Element] = []
    i = start + 1

    def is_element_start(line: str) -> bool:
        s = line.strip()
        if not s or s[0] not in "+-0123456789":
            return False
        toks = _v13_tokens(s)
        if len(toks) < 2:
            return False
        n1 = _v13_token_to_node(toks[0])
        n2 = _v13_token_to_node(toks[1])
        return (n1 is not None and n2 is not None)

    while i < end:
        if not lines[i].strip():
            i += 1
            continue
        if lines[i].lstrip().startswith("#$"):
            break
        if not is_element_start(lines[i]):
            i += 1
            continue
        if i + 13 >= end:
            break

        t1 = _v13_tokens(lines[i].strip())
        n_from = _v13_token_to_node(t1[0])
        n_to = _v13_token_to_node(t1[1])
        if n_from is None or n_to is None:
            i += 1
            continue

        dx = float(t1[2]) if len(t1) > 2 else 0.0
        dy = float(t1[3]) if len(t1) > 3 else 0.0
        dz = float(t1[4]) if len(t1) > 4 else 0.0
        od_mm = float(t1[5]) if len(t1) > 5 else 0.0

        thk_mm = 0.0
        t2 = _v13_tokens(lines[i + 1].strip())
        if t2:
            try:
                thk_mm = float(t2[0])
            except ValueError:
                thk_mm = 0.0

        idx = len(elems)
        elems.append(Element(idx=idx, n_from=int(n_from), n_to=int(n_to),
                            dx=dx, dy=dy, dz=dz, od_mm=od_mm, thk_mm=thk_mm))
        i += 14

    return elems


def _v13_parse_forcmnt(lines: List[str]) -> Tuple[Optional[int], Optional[int], List[ForcMntRecord]]:
    start = find_section(lines, "#$ FORCMNT")
    if start is None:
        return None, None, []
    end = find_next_section_start(lines, start)

    i = start + 1
    recs: List[ForcMntRecord] = []

    def read_n(idx: int, n: int) -> Tuple[List[float], int]:
        vals: List[float] = []
        while idx < end and len(vals) < n:
            if lines[idx].lstrip().startswith("#$"):
                break
            if not lines[idx].strip():
                idx += 1
                continue
            vals.extend(_v13_numbers(lines[idx]))
            idx += 1
        vals = (vals + [0.0] * n)[:n]
        return vals, idx

    while i < end:
        while i < end and not lines[i].strip():
            i += 1
        if i >= end:
            break
        if not _v13_is_node_line(lines[i]):
            i += 1
            continue

        node1 = _v13_parse_node(lines[i]); i += 1
        vec1, i = read_n(i, VEC_VALUE_COUNT)

        # node2 single numeric line (not .0000 style)
        while i < end and not lines[i].strip():
            i += 1
        node2 = 0
        if i < end and not lines[i].lstrip().startswith("#$"):
            nums = _v13_numbers(lines[i])
            if nums:
                node2 = int(round(nums[0]))
            i += 1

        vec2, i = read_n(i, VEC_VALUE_COUNT)
        recs.append(ForcMntRecord(node1=node1, vec1=vec1, node2=node2, vec2=vec2))

    return start, end, recs


# -----------------------------
# v15 parsing
# -----------------------------
_SCI_RE = re.compile(r"[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?")

def _is_integer_like(x: float, tol: float = 1e-6) -> bool:
    return abs(x - round(x)) < tol

def _v15_is_node_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    toks = _SCI_RE.findall(s)
    return len(toks) == 1


def _v15_parse_node(line: str) -> int:
    return int(round(float(_SCI_RE.findall(line.strip())[0])))


def _v15_extract_nodes_from_aux(lines: List[str], aux_header: str, field_index: int) -> List[int]:
    i = find_section(lines, aux_header)
    if i is None:
        return []
    end = find_next_section_start(lines, i)

    out: List[int] = []

    for ln in lines[i + 1:end]:
        s = ln.strip()
        if not s or s[0] not in "+-0123456789":
            continue

        toks = _SCI_RE.findall(s)

        if len(toks) > field_index:
            try:
                val = float(toks[field_index])
            except ValueError:
                continue

            # Only accept values that are actually node-like integers
            if val > 0 and _is_integer_like(val):
                out.append(int(round(val)))

    return out


def _v15_parse_g13_fields(line: str, width: int = 13) -> List[float]:
    """
    v15 FORCMNT is effectively FORTRAN "2X, 6G13.6" style and may have run-together values.
    Parse by 13-char chunks after trimming the common 2-space lead.
    """
    s = line.rstrip("\n")
    if len(s) >= 2 and s[:2] == "  ":
        s = s[2:]
    vals: List[float] = []
    for i in range(0, len(s), width):
        chunk = s[i:i + width]
        if not chunk.strip():
            continue
        try:
            vals.append(float(chunk))
        except ValueError:
            break
    return vals


def _v15_parse_elements(lines: List[str]) -> List[Element]:
    """
    v15 ELEMENTS parser:
    - Do NOT assume fixed record length.
    - Identify element start lines by:
        * at least 6 numeric tokens
        * first two tokens are integer-like node IDs (>0)
        * OD > 0 and thickness line exists next with plausible thickness
    """
    start = find_section(lines, "#$ ELEMENTS")
    if start is None:
        return []
    end = find_next_section_start(lines, start)

    elems: List[Element] = []

    def is_element_start(line: str) -> Optional[Tuple[int, int, float, float, float, float]]:
        s = line.strip()
        if not s or s[0] not in "+-0123456789":
            return None

        toks = _SCI_RE.findall(s)
        if len(toks) < 6:
            return None

        try:
            n1f = float(toks[0])
            n2f = float(toks[1])
            if n1f <= 0 or n2f <= 0:
                return None
            if not _is_integer_like(n1f) or not _is_integer_like(n2f):
                return None

            n_from = int(round(n1f))
            n_to   = int(round(n2f))

            dx = float(toks[2])
            dy = float(toks[3])
            dz = float(toks[4])
            od_mm = float(toks[5])

            # basic plausibility
            if od_mm <= 0.0:
                return None

            return (n_from, n_to, dx, dy, dz, od_mm)
        except ValueError:
            return None

    i = start + 1
    while i < end:
        if not lines[i].strip():
            i += 1
            continue
        if lines[i].lstrip().startswith("#$"):
            break

        start_info = is_element_start(lines[i])
        if start_info is None:
            i += 1
            continue

        n_from, n_to, dx, dy, dz, od_mm = start_info

        # thickness: first number on the *next* line (if present)
        thk_mm = 0.0
        if i + 1 < end:
            t2 = _SCI_RE.findall(lines[i + 1].strip())
            if t2:
                try:
                    thk_mm = float(t2[0])
                except ValueError:
                    thk_mm = 0.0

        # plausibility filter: thickness must be >=0 and not absurd
        # (don’t be too strict; just avoid obvious mis-detections)
        if thk_mm < 0.0 or thk_mm > max(200.0, 0.49 * od_mm):
            # treat as false positive "element start"
            i += 1
            continue

        idx = len(elems)
        elems.append(
            Element(
                idx=idx,
                n_from=n_from,
                n_to=n_to,
                dx=dx,
                dy=dy,
                dz=dz,
                od_mm=od_mm,
                thk_mm=thk_mm,
            )
        )

        i += 1  # keep scanning; we do not rely on record length

    return elems


def _v15_parse_forcmnt(lines: List[str]) -> Tuple[Optional[int], Optional[int], List[ForcMntRecord]]:
    start = find_section(lines, "#$ FORCMNT")
    if start is None:
        return None, None, []
    end = find_next_section_start(lines, start)

    i = start + 1
    recs: List[ForcMntRecord] = []

    def read_vec54(idx: int) -> Tuple[List[float], int]:
        vals: List[float] = []
        while idx < end and len(vals) < VEC_VALUE_COUNT:
            if lines[idx].lstrip().startswith("#$"):
                break
            if not lines[idx].strip():
                idx += 1
                continue
            vals.extend(_v15_parse_g13_fields(lines[idx]))
            idx += 1
        vals = (vals + [0.0] * VEC_VALUE_COUNT)[:VEC_VALUE_COUNT]
        return vals, idx

    while i < end:
        while i < end and not lines[i].strip():
            i += 1
        if i >= end:
            break
        if not _v15_is_node_line(lines[i]):
            i += 1
            continue

        node1 = _v15_parse_node(lines[i]); i += 1
        vec1, i = read_vec54(i)

        while i < end and not lines[i].strip():
            i += 1
        node2 = 0
        if i < end and not lines[i].lstrip().startswith("#$"):
            nums = _v15_parse_g13_fields(lines[i])
            if nums:
                node2 = int(round(nums[0]))
            i += 1

        vec2, i = read_vec54(i)
        recs.append(ForcMntRecord(node1=node1, vec1=vec1, node2=node2, vec2=vec2))

    return start, end, recs


# -----------------------------
# Public API
# -----------------------------
def read_neutral_file(path: Path) -> NeutralModel:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)

    version = detect_version(lines)

    if version == "v15":
        bend = _v15_extract_nodes_from_aux(lines, "#$ BEND", 3)
        tee = _v15_extract_nodes_from_aux(lines, "#$ SIF&TEES", 0)
        elems = _v15_parse_elements(lines)
        fstart, fend, frecs = _v15_parse_forcmnt(lines)
    else:
        bend = _v13_extract_nodes_from_aux(lines, "#$ BEND", 3)
        tee = _v13_extract_nodes_from_aux(lines, "#$ SIF&TEES", 0)
        elems = _v13_parse_elements(lines)
        fstart, fend, frecs = _v13_parse_forcmnt(lines)

    slug = sorted(set(bend) | set(tee))

    return NeutralModel(
        version=version,
        path=path,
        lines=lines,
        elements=elems,
        bend_nodes=sorted(set(bend)),
        tee_nodes=sorted(set(tee)),
        slug_nodes=slug,
        forcmnt_start=fstart,
        forcmnt_end=fend,
        forcmnt_records=frecs,
    )

def read_restrained_nodes(lines: List[str]) -> set:
    """
    Return the set of node numbers that have at least one active restraint
    in the #$ RESTRANT section.

    Each restraint auxiliary block is 24 lines (6 DOF slots × 4 lines each).
    The first line of each DOF slot contains:
      [0] node number   [1] restraint type   [2..] stiffness, gap, …

    A slot is active when node > 0 AND restraint type > 0.
    """
    import re as _re
    _SCI = _re.compile(r"[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?")

    start = find_section(lines, "#$ RESTRANT")
    if start is None:
        return set()
    end = find_next_section_start(lines, start)

    LINES_PER_AUX = 24
    LINES_PER_DOF = 4

    data = lines[start + 1:end]
    restrained: set = set()

    for block in range(len(data) // LINES_PER_AUX):
        base = block * LINES_PER_AUX
        for dof in range(6):
            ln = data[base + dof * LINES_PER_DOF]
            toks = _SCI.findall(ln)
            if len(toks) < 2:
                continue
            try:
                node  = int(round(float(toks[0])))
                rtype = int(round(float(toks[1])))
            except ValueError:
                continue
            if node > 0 and rtype > 0:
                restrained.add(node)

    return restrained