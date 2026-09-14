"""
app_paths.py
------------
Where AutoLift's per-user files (config, database) live: a fixed OS
AppData location, independent of wherever the exe itself happens to be run
from - so config/DB survive an exe move/reinstall/read-only exe folder,
and so a fresh machine needs zero clicks to get a working default.

Location: %LOCALAPPDATA%\\AutoLift  ("Local", not "Roaming" - each
engineer's database is their own local copy, per direct instruction
(2026-09-14): "Everyone has their own local DB copy... The default path
for the DB should be in the AppData folder for 'AutoLift'.").

Falls back to ~/.autolift on any platform where LOCALAPPDATA isn't set
(never expected on the real Windows deployment target - only avoids
crashing this module's own dev-machine/CI checks run outside Windows).

Nothing here imports tkinter or touches an existing config file's
contents - see config.py/doc_config.py for the one-time migration of a
pre-existing exe-adjacent config into this location.
"""

from __future__ import annotations

import os

APP_NAME = "AutoLift"


def autolift_appdata_dir() -> str:
    """<LOCALAPPDATA>\\AutoLift (or ~/.autolift as a non-Windows fallback),
    created if missing."""
    base = os.environ.get("LOCALAPPDATA")
    d = os.path.join(base, APP_NAME) if base else os.path.expanduser("~/.autolift")
    os.makedirs(d, exist_ok=True)
    return d
