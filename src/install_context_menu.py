"""
install_context_menu.py
------------------------
Silently (re)installs AutoLift's Windows Explorer folder-background context
menu, nesting both verbs under one cascading "AutoLift" parent entry rather
than two flat top-level items — replacing both the old separate
create_lift_case.exe / lift_documenter.exe registrations AND this program's
own earlier flat (non-nested) registration.

Scope: HKCU only (per-user, no admin elevation required). Idempotent - safe
to call on every launch; only writes when a key is missing or its command
no longer points at the current exe path (so moving/updating the exe
self-heals the menu on next run).

Menu installed, under Directory\\Background\\shell (right-click empty space
in a folder):

    AutoLift                                  (parent, cascading submenu)
      -> Full .C2 Lift Creation               --creator "%V"
      -> Open Lift Mark-up Documenter         --documenter "%V"

Cascading submenus for a Windows Explorer shell verb use the standard
SubCommands="" + nested `shell` subkey convention - see MENU_KEY below.

IMPORTANT (found via real-machine testing, 2026-09-08): the parent verb's
display label must come from MUIVerb, NOT the key's (Default) value -
Microsoft's own docs are explicit that "The (Default) value for the
[cascade menu] subkey should not be set." A first version of this file got
that backwards (set (Default), no MUIVerb): the parent showed up with the
right label but its children never appeared, on a real Windows machine,
even after an Explorer restart. ensure_installed() below explicitly
deletes any stray (Default) value on the parent key for exactly that
reason - on an existing install from that earlier version, simply not
setting it going forward wouldn't remove what's already there.
"""

from __future__ import annotations

import sys

MENU_KEY = "AutoLift"
MENU_LABEL = "AutoLift"

VERBS = [
    {
        "key": "Creator",
        "label": "Full .C2 Lift Creation",
        "flag": "--creator",
    },
    {
        "key": "Documenter",
        "label": "Open Lift Mark-up Documenter",
        "flag": "--documenter",
    },
]

BASE = r"Software\Classes\Directory\Background\shell"

# Flat top-level keys from this program's own earlier (pre-submenu) install -
# cleaned up on the next launch so an upgrade doesn't leave duplicate items.
_LEGACY_FLAT_KEYS = ["AutoLift.Creator", "AutoLift.Documenter"]


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


def _set_default_value(winreg, key_path: str, value: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, value)


def _get_value(winreg, key_path: str, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            val, _ = winreg.QueryValueEx(k, name)
            return val
    except FileNotFoundError:
        return None


def _get_default_value(winreg, key_path: str):
    return _get_value(winreg, key_path, None)


def _set_named_value(winreg, key_path: str, name: str, value: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _delete_default_value(winreg, key_path: str) -> None:
    """Remove a (Default) value if one is set - a cascade-menu parent key
    must not have one (see the module docstring)."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS
        ) as k:
            winreg.DeleteValue(k, "")
    except FileNotFoundError:
        pass


def _remove_key_tree(winreg, key_path: str) -> None:
    """Best-effort recursive delete - a missing key is not an error."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS
        ) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _remove_key_tree(winreg, f"{key_path}\\{sub}")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
    except FileNotFoundError:
        pass


def ensure_installed(force: bool = False) -> None:
    import winreg

    for legacy_key in _LEGACY_FLAT_KEYS:
        _remove_key_tree(winreg, f"{BASE}\\{legacy_key}")

    parent_key = f"{BASE}\\{MENU_KEY}"
    shell_key = f"{parent_key}\\shell"

    # The parent's label comes from MUIVerb, never (Default) - a (Default)
    # value on a cascade-menu key stops its children from showing (see the
    # module docstring). Explicitly remove any stray one left by an earlier
    # version of this file.
    _delete_default_value(winreg, parent_key)
    if _get_value(winreg, parent_key, "MUIVerb") != MENU_LABEL or force:
        _set_named_value(winreg, parent_key, "MUIVerb", MENU_LABEL)
    if _get_value(winreg, parent_key, "SubCommands") != "" or force:
        _set_named_value(winreg, parent_key, "SubCommands", "")

    for verb in VERBS:
        verb_key = f"{shell_key}\\{verb['key']}"
        command_key = f"{verb_key}\\command"
        wanted = _command_for(verb["flag"])

        if _get_default_value(winreg, verb_key) != verb["label"] or force:
            _set_default_value(winreg, verb_key, verb["label"])

        if _get_default_value(winreg, command_key) != wanted or force:
            _set_default_value(winreg, command_key, wanted)


if __name__ == "__main__":
    ensure_installed(force=True)
    print("AutoLift context menu installed for the current user.")
