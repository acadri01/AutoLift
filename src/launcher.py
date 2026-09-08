"""
launcher.py
-----------
Single distributable entry point for AutoLift. Wraps the two ORIGINAL,
UNMODIFIED programs (src/creator = LiftNeutralFileModifier's
create_lift_case.py, src/documenter = MarkUpGen's lift_documenter.py) behind
one exe, dispatched by argv, so one PyInstaller build produces one .exe that
both context-menu verbs point at.

No behaviour of either program is changed here. This file only:
  1. Puts both source trees (+ the shared lift_meta.py/line_layout.py) on
     sys.path, so their existing bare `import lift_meta` / `import lift_db`
     style imports keep resolving without any changes to those files.
  2. Silently (re)installs the two context-menu verbs if missing or stale.
  3. Strips its own mode flag off sys.argv and calls the matching program's
     original, untouched main() with argv shaped exactly as that program
     already expects (a single optional folder-path argument, %V).

Registered verbs:
    --creator      -> create_lift_case.main()   ("Full .C2 Lift Creation")
    --documenter   -> lift_documenter.main()    ("Open Lift Mark-up Documenter")
No mode flag (bare folder arg, or none) falls back to the documenter, matching
today's plain `lift_documenter.exe "%V"` registration.
"""

from __future__ import annotations

import os
import sys

_SRC = os.path.dirname(os.path.abspath(__file__))
for _sub in ("creator", "documenter", "shared"):
    _p = os.path.join(_SRC, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _install_context_menu_best_effort() -> None:
    """Never let a registry hiccup stop the actual tool from running."""
    try:
        import install_context_menu
        install_context_menu.ensure_installed()
    except Exception:
        pass


def main() -> int:
    _install_context_menu_best_effort()

    args = sys.argv[1:]
    mode = args[0] if args else ""

    if mode == "--creator":
        sys.argv = [sys.argv[0]] + args[1:]
        import create_lift_case
        create_lift_case.main()
        return 0

    if mode == "--documenter":
        sys.argv = [sys.argv[0]] + args[1:]
        import lift_documenter
        return lift_documenter.main()

    if mode == "--install-context-menu":
        import install_context_menu
        install_context_menu.ensure_installed(force=True)
        return 0

    # Backward-compatible fallback: no recognised mode flag - treat argv
    # exactly as today's plain `lift_documenter.exe "%V"` registration does.
    import lift_documenter
    return lift_documenter.main()


if __name__ == "__main__":
    sys.exit(main())
