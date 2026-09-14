"""
line_new.py
-----------
"Add New Line" — copies the bundled Add_New_Line template
(templates/Add_New_Line/) into a work order's folder as a new line,
renaming the placeholder token in file names. Per direct instruction,
2026-09-14.

The template's own README (templates/Add_New_Line/README.md) documents
exactly what it contains and why. In short: 00_CII/'s real support/config
files are copied verbatim; the two filenames carrying the `[Add_New_Line]`
placeholder are renamed to the real line number; 01_REFS and
02_FINALISATION are created fresh (see line_layout.py) rather than kept
as empty directories in the template itself.
"""

from __future__ import annotations

import os
import shutil
import sys

import line_layout as LL

PLACEHOLDER = "[Add_New_Line]"


def _template_root() -> str:
    """
    Where the bundled Add_New_Line template lives: relative to the
    PyInstaller onefile extraction directory (sys._MEIPASS) when frozen,
    or next to this source file when running from source — both resolve
    to the same templates/Add_New_Line subfolder either way (see
    autolift.spec's datas entry for the frozen case).
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "templates", "Add_New_Line")


def create_line(wo_folder: str, line_no: str) -> str:
    """
    Create <wo_folder>/<line_no> from the bundled template.

    Raises FileExistsError if that folder already exists, or OSError if
    the template itself can't be found (a packaging problem, not a user
    mistake) or the copy fails partway. Never leaves anything behind
    if it fails before any file has actually been written — errors from
    os.makedirs happen before any copy — but a failure MID-copy can leave
    a partial folder; the caller should tell the user to check/remove it.

    Returns the new line folder's absolute path.
    """
    src_cii = os.path.join(_template_root(), LL.CII_DIR)
    if not os.path.isdir(src_cii):
        raise OSError(f"Add_New_Line template not found at: {src_cii}")

    dest_root = os.path.join(wo_folder, line_no)
    if os.path.exists(dest_root):
        raise FileExistsError(f"{dest_root} already exists")

    dest_cii = os.path.join(dest_root, LL.CII_DIR)
    os.makedirs(dest_cii)
    for entry in os.listdir(src_cii):
        shutil.copy2(
            os.path.join(src_cii, entry),
            os.path.join(dest_cii, entry.replace(PLACEHOLDER, line_no)),
        )

    os.makedirs(os.path.join(dest_root, LL.REFS_DIR))
    os.makedirs(os.path.join(dest_root, LL.FINAL_DIR))

    return dest_root
