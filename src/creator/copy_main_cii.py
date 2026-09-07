"""
copy_main_cii.py

Standalone tool — mirrors copy_main_c2.py but operates on .CII files.

Copies *_MAIN.CII to a new file in the target folder.

Two-step keyboard-driven prompt in a single window:
  Step 1 — Type the number of lifted nodes, press Enter
             → node fields appear dynamically below
  Step 2 — Tab / Enter through each node field; Enter on the
             last field completes the operation

Naming:
  Nodes supplied  → {prefix}_N10-N20.CII
  0 or blank      → {prefix}_L[next_number].CII

Folder is received as a command-line argument from the right-click
context menu (%V). Falls back to scanning open Explorer windows if
no argument is given.

Requirements:
    pip install pywin32
"""

import os
import re
import shutil
import sys
import ctypes

from ui_dialogs import prompt_nodes, show_message


# ---------------------------------------------------------------------------
# Explorer / filesystem helpers
# ---------------------------------------------------------------------------

def get_explorer_paths() -> list[str]:
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


def find_main_file(folder: str) -> str | None:
    for name in os.listdir(folder):
        if re.match(r'.+_MAIN\.CII$', name, re.IGNORECASE):
            return name
    return None


def find_next_number(folder: str, prefix: str) -> int:
    pattern = re.compile(re.escape(prefix) + r'_L(\d+)\.CII$', re.IGNORECASE)
    numbers = [int(m.group(1)) for f in os.listdir(folder)
               if (m := pattern.match(f))]
    return max(numbers, default=0) + 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # ── Resolve folder ──────────────────────────────────────────────────────
    if len(sys.argv) > 1:
        folder = sys.argv[1]
        if not os.path.isdir(folder):
            show_message("CII Copier", f"Invalid folder path:\n{folder}", error=True)
            sys.exit(1)
        main_file = find_main_file(folder)
        if not main_file:
            show_message("CII Copier",
                         f"No *_MAIN.CII file found in:\n{folder}", error=True)
            sys.exit(1)
    else:
        try:
            paths = get_explorer_paths()
        except ImportError:
            show_message(
                "CII Copier - Setup Required",
                "Missing dependency: pywin32\n\nRun:\n  pip install pywin32",
                error=True)
            sys.exit(1)

        if not paths:
            show_message(
                "CII Copier",
                "No open File Explorer windows found.\n\n"
                "Please open the correct folder in Explorer and try again.",
                error=True)
            sys.exit(1)

        folder = main_file = None
        for path in paths:
            candidate = find_main_file(path)
            if candidate:
                folder, main_file = path, candidate
                break

        if not main_file:
            show_message(
                "CII Copier",
                "No *_MAIN.CII file found in any open Explorer window.\n\n"
                "Searched:\n" + "\n".join(paths),
                error=True)
            sys.exit(1)

    # ── Derive prefix ───────────────────────────────────────────────────────
    prefix = re.sub(r'_MAIN\.CII$', '', main_file, flags=re.IGNORECASE)

    # ── Prompt for lifted nodes ─────────────────────────────────────────────
    nodes = prompt_nodes(prefix)

    if nodes is None:
        sys.exit(0)                             # cancelled

    # ── Build destination filename ──────────────────────────────────────────
    if nodes:
        node_str = "-".join(f"N{n}" for n in nodes)
        new_name = f"{prefix}_{node_str}.CII"
    else:
        new_name = f"{prefix}_L{find_next_number(folder, prefix)}.CII"

    src = os.path.join(folder, main_file)
    dst = os.path.join(folder, new_name)

    if os.path.exists(dst):
        show_message(
            "CII Copier",
            f"Target file already exists:\n{new_name}\n\nNo changes made.",
            error=True)
        sys.exit(1)

    shutil.copy2(src, dst)
    show_message("CII Copier", f"Created:\n{new_name}")


if __name__ == "__main__":
    main()
