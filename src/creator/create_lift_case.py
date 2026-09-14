"""
create_lift_case.py

Entry point for the "Full .C2 Lift Creation" context menu item.

Registered in Windows Explorer as:
    "Full .C2 Lift Creation" → python create_lift_case.py "%V"

Folder resolution priority:
  1. %V command-line argument (right-click on folder background)
  2. First open Explorer window containing a *_MAIN.C2 or *_MAIN._A file
  3. None — FolderSelectDialog opens with empty path for manual entry

In all cases the resolved path is passed as the initial value of
FolderSelectDialog, so the user can confirm or change it before proceeding.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def _get_explorer_paths() -> list[str]:
    """Return paths of all open Explorer windows, ordered front-to-back."""
    import win32com.client, pythoncom
    pythoncom.CoInitialize()
    shell = win32com.client.Dispatch("Shell.Application")
    paths = []
    for w in shell.Windows():
        try:
            p = w.Document.Folder.Self.Path
            if p and os.path.isdir(p):
                paths.append(p)
        except Exception:
            pass
    return paths


def _has_main_input(folder: str) -> bool:
    """Return True if folder contains a *_MAIN.C2 or *_MAIN._A file."""
    try:
        for f in os.listdir(folder):
            if re.match(r'.+_MAIN\.(C2|_A)$', f, re.IGNORECASE):
                return True
    except OSError:
        pass
    return False


def _resolve_initial_folder() -> Path | None:
    """
    Return the best guess for the working folder, or None if undetermined.
    Never exits — the FolderSelectDialog handles all error cases.
    """
    # 1. %V argument from context menu
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if p.is_dir():
            return p

    # 2. Scan open Explorer windows
    try:
        paths = _get_explorer_paths()
    except Exception:
        # pywin32 not available or COM error — fall through to empty dialog
        return None

    # Prefer a window that already contains a _MAIN file
    for p in paths:
        if _has_main_input(p):
            return Path(p)

    # Otherwise use whichever window is open
    if paths:
        return Path(paths[0])

    return None


def main():
    # Write default config file next to exe if it doesn't exist yet
    try:
        from config import write_default_config
        write_default_config()
    except Exception:
        pass

    initial = _resolve_initial_folder()
    from lift_case_builder import run
    ok = run(initial)
    # run() no longer calls sys.exit() itself (so it can be called in-process
    # by a future host window without killing it) — this standalone entry
    # point translates its True/False result into the same exit(0)/exit(1)
    # this program has always used.
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
