from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Optional
import re

from neutral_reader import NeutralModel, ForcMntRecord, VEC_VALUE_COUNT


Vec3 = Tuple[float, float, float]
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?")


# ---------------------------------------------------------------------------
# FORCMNT record handling
# ---------------------------------------------------------------------------
def ensure_record_per_node(existing: List[ForcMntRecord], required_nodes: List[int]) -> List[ForcMntRecord]:
    by_node: Dict[int, ForcMntRecord] = {}
    ordered: List[ForcMntRecord] = []

    for rec in existing:
        if rec.node1 not in by_node:
            clone = ForcMntRecord(
                node1=int(rec.node1),
                vec1=list((rec.vec1 + [0.0] * VEC_VALUE_COUNT)[:VEC_VALUE_COUNT]),
                node2=int(rec.node2),
                vec2=list((rec.vec2 + [0.0] * VEC_VALUE_COUNT)[:VEC_VALUE_COUNT]),
            )
            by_node[clone.node1] = clone
            ordered.append(clone)

    for node in sorted(set(int(n) for n in required_nodes)):
        if node not in by_node:
            rec = ForcMntRecord(node1=node, vec1=[0.0] * VEC_VALUE_COUNT, node2=0, vec2=[0.0] * VEC_VALUE_COUNT)
            by_node[node] = rec
            ordered.append(rec)

    return ordered


def clear_node1_vectors(vec1: List[float]) -> None:
    for i in range(min(len(vec1), VEC_VALUE_COUNT)):
        vec1[i] = 0.0


def write_force_into_vector_slot(vec1: List[float], vector_k: int, fx: float, fy: float, fz: float) -> None:
    if vector_k < 1 or vector_k > 9:
        raise ValueError(f"vector slot must be 1..9, got {vector_k}")
    base = (vector_k - 1) * 6
    vec1[base + 0] = float(fx)
    vec1[base + 1] = float(fy)
    vec1[base + 2] = float(fz)
    vec1[base + 3] = 0.0
    vec1[base + 4] = 0.0
    vec1[base + 5] = 0.0


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def _v13_fmt_node1_line(node: int) -> str:
    return f"    {float(node):.4f}    \n"


def _v13_fmt_node2_line(node2: int) -> str:
    return "       " + (f"{float(node2):.6f}" if node2 != 0 else "0.000000") + "\n"


def _v13_fmt_field(x: float) -> str:
    if abs(x) < 5e-13:
        s = "0.000000"
    else:
        s = f"{x:.1f}"
        if s == "-0.0":
            s = "0.0"
    return f"{s:<13}"


def _v13_format_vec54(vals: List[float], first_indent: str, cont_indent: str) -> List[str]:
    vals = (vals + [0.0] * VEC_VALUE_COUNT)[:VEC_VALUE_COUNT]
    out: List[str] = []
    for li in range(9):
        indent = first_indent if li == 0 else cont_indent
        base = 6 * li
        out.append(indent + "".join(_v13_fmt_field(vals[base + k]) for k in range(6)) + "\n")
    return out


def _v13_format_forcmnt(records: List[ForcMntRecord]) -> List[str]:
    out: List[str] = ["#$ FORCMNT \n"]
    for r in records:
        out.append(_v13_fmt_node1_line(r.node1))
        out.extend(_v13_format_vec54(r.vec1, first_indent="    ", cont_indent="       "))
        out.append(_v13_fmt_node2_line(r.node2))
        out.extend(_v13_format_vec54(r.vec2, first_indent="       ", cont_indent="       "))
    return out


def _v15_g13(x: float) -> str:
    return f"{x:13.6E}"


def _v15_fmt_node1_line(node: int) -> str:
    return "  " + _v15_g13(float(node)) + "\n"


def _v15_fmt_node2_line(node2: int) -> str:
    return "  " + _v15_g13(float(node2)) + "\n"


def _v15_format_vec54(vals: List[float]) -> List[str]:
    vals = (vals + [0.0] * VEC_VALUE_COUNT)[:VEC_VALUE_COUNT]
    out: List[str] = []
    for li in range(9):
        base = 6 * li
        out.append("  " + "".join(_v15_g13(vals[base + k]) for k in range(6)) + "\n")
    return out


def _v15_format_forcmnt(records: List[ForcMntRecord]) -> List[str]:
    out: List[str] = ["#$ FORCMNT \n"]
    for r in records:
        out.append(_v15_fmt_node1_line(r.node1))
        out.extend(_v15_format_vec54(r.vec1))
        out.append(_v15_fmt_node2_line(r.node2))
        out.extend(_v15_format_vec54(r.vec2))
    return out


def _format_forcmnt_by_version(model: NeutralModel, records: List[ForcMntRecord]) -> List[str]:
    if model.version == "v15":
        return _v15_format_forcmnt(records)
    return _v13_format_forcmnt(records)


# ---------------------------------------------------------------------------
# Raw neutral-file helpers
# ---------------------------------------------------------------------------
def _tokenise_numbers(line: str) -> List[str]:
    return _NUM_RE.findall(line.rstrip("\n"))


def _to_int(token: str) -> int:
    return int(round(float(token)))


def _is_integer_like_token(tok: str) -> bool:
    try:
        x = float(tok)
    except ValueError:
        return False
    return abs(x - round(x)) < 1e-6


def _find_section(lines: List[str], header: str) -> Optional[int]:
    target = header.strip().upper()
    for i, line in enumerate(lines):
        if line.strip().upper() == target:
            return i
    return None


def _find_next_section_start(lines: List[str], start_idx: int) -> int:
    for i in range(start_idx + 1, len(lines)):
        if lines[i].lstrip().startswith("#$"):
            return i
    return len(lines)


def _is_element_start_line(line: str) -> bool:
    toks = _tokenise_numbers(line)
    if len(toks) < 6:
        return False
    if not (_is_integer_like_token(toks[0]) and _is_integer_like_token(toks[1])):
        return False
    try:
        return float(toks[0]) > 0 and float(toks[1]) > 0 and float(toks[5]) > 0
    except ValueError:
        return False


def _is_pointer_line(line: str) -> bool:
    toks = _tokenise_numbers(line)
    if len(toks) != 6:
        return False
    return all(_is_integer_like_token(t) for t in toks)


class ElementBlock:
    def __init__(self, block_start: int, block_end: int, n_from: int, n_to: int, pointer_lines: List[int], iel: List[int]):
        self.block_start = block_start
        self.block_end = block_end
        self.n_from = n_from
        self.n_to = n_to
        self.pointer_lines = pointer_lines
        self.iel = iel


def _is_pointer_line_with_count(line: str, expected_count: int) -> bool:
    toks = _tokenise_numbers(line)
    if len(toks) != expected_count:
        return False
    return all(_is_integer_like_token(t) for t in toks)


def _read_iel_values(lines: List[str], pointer_lines: List[int]) -> List[int]:
    vals: List[int] = []
    for idx in pointer_lines:
        vals.extend(_to_int(tok) for tok in _tokenise_numbers(lines[idx]))
    return vals


def _format_pointer_lines(original_lines: List[str], vals: List[int], version: str) -> List[str]:
    # Element IEL layout in the user's v15 CII files is written on four lines:
    #   2 ints, 6 ints, 6 ints, 3 ints  -> 17 total integer items.
    # IEL item 6 is therefore the 6th value of the second 6-int line in this block.
    vals = (vals + [0] * 17)[:17]
    chunks = [vals[0:2], vals[2:8], vals[8:14], vals[14:17]]
    out: List[str] = []
    for chunk in chunks:
        out.append("  " + "".join(f"{int(v):13d}" for v in chunk) + "\n")
    return out


def _collect_element_blocks(lines: List[str]) -> List[ElementBlock]:
    start = _find_section(lines, "#$ ELEMENTS")
    if start is None:
        return []
    end = _find_next_section_start(lines, start)

    starts: List[int] = []
    for i in range(start + 1, end):
        if _is_element_start_line(lines[i]):
            starts.append(i)

    blocks: List[ElementBlock] = []
    for k, bstart in enumerate(starts):
        bend = starts[k + 1] if (k + 1) < len(starts) else end
        first_toks = _tokenise_numbers(lines[bstart])
        if len(first_toks) < 2:
            continue
        n_from = _to_int(first_toks[0])
        n_to = _to_int(first_toks[1])

        # In these neutral files the integer pointer block is the last four integer-like
        # lines in each element block, with counts [2, 6, 6, 3].
        pointer_lines: List[int] = []
        for i in range(bend - 1, bstart, -1):
            cnt = len(_tokenise_numbers(lines[i]))
            if cnt in (2, 3, 6) and all(_is_integer_like_token(t) for t in _tokenise_numbers(lines[i])):
                pointer_lines.append(i)
                if len(pointer_lines) == 4:
                    break
        pointer_lines.reverse()
        if len(pointer_lines) != 4:
            continue
        counts = [len(_tokenise_numbers(lines[i])) for i in pointer_lines]
        if counts != [2, 6, 6, 3]:
            continue

        iel = _read_iel_values(lines, pointer_lines)
        blocks.append(ElementBlock(bstart, bend, n_from, n_to, pointer_lines, iel))

    return blocks


def _parse_fixed_record_section_nodes(lines: List[str], header: str, lines_per_record: int, node_positions: List[int]) -> Dict[int, List[int]]:
    """
    Return {pointer_index: [node_ids...]} where pointer_index is 1-based within the section.
    node_positions are 0-based indices in the flattened numeric record.
    """
    start = _find_section(lines, header)
    if start is None:
        return {}
    end = _find_next_section_start(lines, start)

    data_lines: List[str] = []
    for line in lines[start + 1:end]:
        if line.lstrip().startswith("#$"):
            break
        if line.strip():
            data_lines.append(line)

    out: Dict[int, List[int]] = {}
    ptr = 1
    for i in range(0, len(data_lines), lines_per_record):
        chunk = data_lines[i:i + lines_per_record]
        if len(chunk) < lines_per_record:
            break
        vals: List[float] = []
        for line in chunk:
            for tok in _tokenise_numbers(line):
                try:
                    vals.append(float(tok))
                except ValueError:
                    pass
        nodes: List[int] = []
        for pos in node_positions:
            if pos < len(vals):
                val = vals[pos]
                if val > 0 and abs(val - round(val)) < 1e-6:
                    nodes.append(int(round(val)))
        out[ptr] = nodes
        ptr += 1
    return out



def _parse_bend_pointer_to_nodes(lines: List[str]) -> Dict[int, List[int]]:
    # BEND record: 3 lines, node numbers at items 4, 6, 8 -> positions 3, 5, 7
    return _parse_fixed_record_section_nodes(lines, "#$ BEND", lines_per_record=3, node_positions=[3, 5, 7])



def _parse_sif_tee_nodes(lines: List[str]) -> List[int]:
    # SIF/TEE record: 14 lines = two 7-line halves, first value of each half is tee node.
    start = _find_section(lines, "#$ SIF&TEES")
    if start is None:
        return []
    end = _find_next_section_start(lines, start)

    data_lines: List[str] = []
    for line in lines[start + 1:end]:
        if line.lstrip().startswith("#$"):
            break
        if line.strip():
            data_lines.append(line)

    nodes: List[int] = []
    for i in range(0, len(data_lines), 14):
        chunk = data_lines[i:i + 14]
        if len(chunk) < 14:
            break
        for offset in (0, 7):
            toks = _tokenise_numbers(chunk[offset])
            if toks:
                try:
                    val = float(toks[0])
                except ValueError:
                    continue
                if val > 0 and abs(val - round(val)) < 1e-6:
                    nodes.append(int(round(val)))
    return nodes



def _replace_or_append_forcmnt_section(lines: List[str], model: NeutralModel, new_forcmnt: List[str]) -> List[str]:
    if model.forcmnt_start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if lines and lines[-1].strip():
            return lines + ["\n"] + new_forcmnt
        return lines + new_forcmnt

    start = model.forcmnt_start
    end = model.forcmnt_end if model.forcmnt_end is not None else len(lines)
    return lines[:start] + new_forcmnt + lines[end:]



def _update_control_force_count(lines: List[str], version: str, new_count: int) -> None:
    start = _find_section(lines, "#$ CONTROL")
    if start is None:
        return
    end = _find_next_section_start(lines, start)

    int_lines: List[int] = []
    for i in range(start + 1, end):
        toks = _tokenise_numbers(lines[i])
        if len(toks) == 6 and all(_is_integer_like_token(t) for t in toks):
            int_lines.append(i)
            if len(int_lines) == 4:
                break
    if len(int_lines) < 2:
        return

    # Second integer line in CONTROL contains auxiliary counts. Item 6 = FORCMNT count.
    idx = int_lines[1]
    vals = [_to_int(tok) for tok in _tokenise_numbers(lines[idx])]
    if len(vals) < 6:
        return
    vals[5] = int(new_count)
    lines[idx] = "  " + "".join(f"{v:13d}" for v in vals[:6]) + "\n"



def _choose_bend_force_ptr(bend_nodes: List[int], record_ptr_by_node: Dict[int, int]) -> int:
    for node in bend_nodes:
        ptr = record_ptr_by_node.get(node, 0)
        if ptr > 0:
            return ptr
    return 0



def _apply_force_pointers(lines: List[str], model: NeutralModel, record_ptr_by_node: Dict[int, int]) -> None:
    element_blocks = _collect_element_blocks(lines)
    if not element_blocks:
        return

    bend_ptr_to_nodes = _parse_bend_pointer_to_nodes(lines)
    tee_nodes_in_order = _parse_sif_tee_nodes(lines)

    # In the user's neutral files the stored integer block has two leading integers
    # before the 15-element IEL payload. Within that payload: IEL item 1 (bend ptr)
    # is overall index 2, and IEL item 6 (force/moment ptr) is overall index 7.
    IEL_BEND_PTR_IDX = 2
    IEL_FORCMNT_PTR_IDX = 7

    # 1) Every element with a bend pointer gets a force/moment pointer.
    for block in element_blocks:
        bend_ptr = int(block.iel[IEL_BEND_PTR_IDX]) if len(block.iel) > IEL_BEND_PTR_IDX else 0
        if bend_ptr <= 0:
            continue
        force_ptr = _choose_bend_force_ptr(bend_ptr_to_nodes.get(bend_ptr, []), record_ptr_by_node)
        if force_ptr <= 0:
            # Conservative fallback: if one end node itself has a force record, use it.
            force_ptr = record_ptr_by_node.get(block.n_from, 0) or record_ptr_by_node.get(block.n_to, 0)
        if force_ptr <= 0:
            continue
        block.iel[IEL_FORCMNT_PTR_IDX] = force_ptr

    # 2) For each tee node from SIF&TEES, apply the force/moment pointer to the first element containing that node.
    used_first_element_for_node: Dict[int, bool] = {}
    for tee_node in tee_nodes_in_order:
        if tee_node in used_first_element_for_node:
            continue
        force_ptr = record_ptr_by_node.get(tee_node, 0)
        if force_ptr <= 0:
            continue
        for block in element_blocks:
            if block.n_from == tee_node or block.n_to == tee_node:
                block.iel[IEL_FORCMNT_PTR_IDX] = force_ptr
                used_first_element_for_node[tee_node] = True
                break

    # 3) Write the modified IEL lines back.
    for block in element_blocks:
        new_lines = _format_pointer_lines(lines, block.iel, model.version)
        for j, line_idx in enumerate(block.pointer_lines):
            lines[line_idx] = new_lines[j]


# ---------------------------------------------------------------------------
# Public writer
# ---------------------------------------------------------------------------
def write_forcmnt_and_save(
    *,
    model: NeutralModel,
    forces: Dict[int, Vec3],
    vec_slot: Dict[int, int],
    out_path: Path,
) -> None:
    lines = list(model.lines)

    required_nodes = sorted(set(int(n) for n in model.slug_nodes) | set(int(n) for n in forces.keys()))
    records = ensure_record_per_node(model.forcmnt_records, required_nodes)

    for rec in records:
        if rec.node1 in required_nodes:
            clear_node1_vectors(rec.vec1)
            fx, fy, fz = forces.get(rec.node1, (0.0, 0.0, 0.0))
            slot = int(vec_slot.get(rec.node1, 1))
            write_force_into_vector_slot(rec.vec1, slot, fx, fy, fz)
        # node2 / vec2 preserved as-is

    new_forcmnt = _format_forcmnt_by_version(model, records)
    lines = _replace_or_append_forcmnt_section(lines, model, new_forcmnt)

    record_ptr_by_node: Dict[int, int] = {int(rec.node1): idx + 1 for idx, rec in enumerate(records)}
    _apply_force_pointers(lines, model, record_ptr_by_node)
    _update_control_force_count(lines, model.version, len(records))

    out_path.write_text("".join(lines), encoding="utf-8")
