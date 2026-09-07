"""
install_context_menu.py
------------------------
Silently (re)installs AutoLift's two Windows Explorer folder-background
context-menu verbs, both pointing at THIS exe with a mode flag, replacing
the two separate registrations the old create_lift_case.exe / lift_documenter.exe
used to install by hand.

Scope: HKCU only (per-user, no admin elevation required). Idempotent - safe
to call on every launch; only writes when a key is missing or its command
no longer points at the current exe path (so moving/updating the exe
self-heals the menu on next run).

Verbs installed, both under Directory\\Background\\shell (right-click empty
space in a folder):
    AutoLift.Creator     "Full .C2 Lift Creation"           -> --creator "%V"
    AutoLift.Documenter  "Open Lift Mark-up Documenter"     -> --documenter "%V"
"""

from __future__ import annotations

import sys

VERBS = [
    {
        "key": "AutoLift.Creator",
        "label": "Full .C2 Lift Creation",
        "flag": "--creator",
    },
    {
        "key": "AutoLift.Documenter",
        "label": "Open Lift Mark-up Documenter",
        "flag": "--documenter",
    },
]

BASE = r"Software\Classes\Directory\Background\shell"


def _exe_path() -> str:
    """Path this context-menu command should invoke."""
    if getattr(sys, "frozen", False):
        return sys.executable
    # Dev/source run: re-invoke through the same interpreter + this launcher.
    return f'"{sys.executable}" "{sys.argv[0]}"'


def _command_for(flag: str) -> str:
    exe = _exe_path()
    if getattr(sys, "frozen", False):
        return f'"{exe}" {flag} "%V"'
    return f'{exe} {flag} "%V"'


def ensure_installed(force: bool = False) -> None:
    import winreg

    for verb in VERBS:
        verb_key = f"{BASE}\\{verb['key']}"
        command_key = f"{verb_key}\\command"
        wanted = _command_for(verb["flag"])

        current = None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, command_key) as k:
                current, _ = winreg.QueryValueEx(k, None)
        except FileNotFoundError:
            pass

        if current == wanted and not force:
            continue

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, verb_key) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, verb["label"])
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_key) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, wanted)


if __name__ == "__main__":
    ensure_installed(force=True)
    print("AutoLift context-menu verbs installed for the current user.")
