"""
line_layout.py
--------------
Single source of truth for the job folder structure, shared by BOTH the
lift generator and the documenter so they never disagree about where things
live.

Structure
---------
    <WorkOrder>/
        <LineNumber>/
            00_CII/                CAESAR files; generator runs here
                .liftdoc/          HIDDEN sidecar folder
                    <case>_liftmeta.json
            01_REFS/               isometrics (upload from here)
            02_FINALISATION/       issued PDFs (export to here)

Rules
-----
* line_no  = the LineNumber folder name.
* A folder "is a line root" if it directly contains a 00_CII subfolder.
* The sidecar folder is <line>/00_CII/.liftdoc  (created on demand).
* From ANY folder at or below a line root (the line folder itself, 00_CII,
  01_REFS, 02_FINALISATION, or .liftdoc) we can resolve upward to the line
  root, and from there to the work order (its parent).

Nothing here imports tkinter, the DB, or reportlab - pure path logic.
"""

from __future__ import annotations

import os
from typing import List, Optional

CII_DIR = "00_CII"
REFS_DIR = "01_REFS"
FINAL_DIR = "02_FINALISATION"
SIDECAR_DIR = ".liftdoc"          # hidden, inside 00_CII
SIDECAR_SUFFIX = "_liftmeta.json"

# how far up we're willing to walk looking for a line root
_MAX_UP = 6


def _norm(p: str) -> str:
    return os.path.abspath(p.rstrip("\\/"))


def is_line_root(folder: str) -> bool:
    """True if `folder` directly contains a 00_CII subfolder."""
    return os.path.isdir(os.path.join(folder, CII_DIR))


def sidecar_dir(line_root: str, create: bool = False) -> str:
    """<line>/00_CII/.liftdoc"""
    d = os.path.join(line_root, CII_DIR, SIDECAR_DIR)
    if create:
        os.makedirs(d, exist_ok=True)
        _hide(d)
    return d


def refs_dir(line_root: str) -> str:
    return os.path.join(line_root, REFS_DIR)


def final_dir(line_root: str) -> str:
    return os.path.join(line_root, FINAL_DIR)


def _hide(path: str) -> None:
    """Set the Windows hidden attribute (no-op elsewhere / on failure)."""
    try:
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x02
        ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Upward resolution - the crux of "line mode from anywhere"
# --------------------------------------------------------------------------
def resolve_line_root(folder: str) -> Optional[str]:
    """
    Given any folder at or below a line, return the line root (the folder
    that contains 00_CII). Returns None if no line root is found within
    _MAX_UP levels.

    Handles all of:
        <line>                         -> <line>
        <line>/00_CII                  -> <line>
        <line>/00_CII/.liftdoc         -> <line>
        <line>/01_REFS                 -> <line>
        <line>/02_FINALISATION         -> <line>
    """
    cur = _norm(folder)

    # the folder itself is a line root
    if is_line_root(cur):
        return cur

    # walk up: a parent is the line root if IT contains 00_CII
    for _ in range(_MAX_UP):
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        if is_line_root(parent):
            return parent
        cur = parent
    return None


def line_no_of(line_root: str) -> str:
    return os.path.basename(_norm(line_root))


def work_order_root(line_root: str) -> str:
    """The work-order folder is the line root's parent."""
    return os.path.dirname(_norm(line_root))


def work_order_no(line_root: str) -> str:
    return os.path.basename(work_order_root(line_root))


# --------------------------------------------------------------------------
# Classification for the documenter entry point
# --------------------------------------------------------------------------
def classify(folder: str) -> str:
    """
    'line' if `folder` resolves to a line root (from at or below it).
    'wo'   if `folder` is a work order: any of its immediate children is a
           line root.
    'unknown' otherwise.
    """
    if resolve_line_root(folder) is not None:
        return "line"

    try:
        for name in os.listdir(folder):
            sub = os.path.join(folder, name)
            if os.path.isdir(sub) and is_line_root(sub):
                return "wo"
    except OSError:
        pass
    return "unknown"


def line_roots_in_wo(wo_folder: str) -> List[str]:
    """Immediate child folders that are line roots, sorted (alphabetical)."""
    out: List[str] = []
    try:
        for name in sorted(os.listdir(wo_folder)):
            sub = os.path.join(wo_folder, name)
            if os.path.isdir(sub) and is_line_root(sub):
                out.append(sub)
    except OSError:
        pass
    return out


# --------------------------------------------------------------------------
# Sidecar discovery (documenter side)
# --------------------------------------------------------------------------
def find_sidecars(line_root: str) -> List[str]:
    """All *_liftmeta.json in <line>/00_CII/.liftdoc, sorted."""
    d = sidecar_dir(line_root, create=False)
    if not os.path.isdir(d):
        return []
    return sorted(
        os.path.join(d, f) for f in os.listdir(d)
        if f.lower().endswith(SIDECAR_SUFFIX.lower())
    )
