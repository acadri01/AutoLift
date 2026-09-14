"""
doc_config.py
-------------
Flat key=value settings file (lift_doc_tool.cfg), kept next to the running
executable (or the source tree when not frozen).

One file, appended to: the database path and any future options coexist as
individual `key=value` lines. Reads preserve unknown keys, so writing one
setting never drops another - and writes are atomic (temp file + os.replace)
so the critical db= line can never be left half-written by a crash.

Format (comments and blank lines are ignored on read):

    db=C:/path/to/lift_markup.db
    markup_cloud=1.7
    markup_arrow=1.7
    ...
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Optional

CFG_NAME = "lift_doc_tool.cfg"


def _legacy_app_dir() -> str:
    """Where lift_doc_tool.cfg used to live (co-located with the exe/script)
    before the 2026-09-14 move to a fixed AppData location - kept only to
    migrate an existing file forward, once, on first run after the update."""
    return (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))


def cfg_path() -> str:
    """
    lift_doc_tool.cfg's path, in AutoLift's fixed per-user AppData location
    (see app_paths.autolift_appdata_dir) - independent of wherever the exe
    itself happens to run from, per direct instruction (2026-09-14 -
    "zero-touch first-run", database path defaults into AppData).

    A config file left over from before this change (co-located with the
    exe/script) is migrated in place, once: if the new location has no
    file yet but the legacy one does, it's copied forward so an existing
    `db=` pointer (and any markup_* weight overrides) aren't silently lost
    on the first run after updating.
    """
    import app_paths
    new_path = os.path.join(app_paths.autolift_appdata_dir(), CFG_NAME)
    if not os.path.isfile(new_path):
        legacy = os.path.join(_legacy_app_dir(), CFG_NAME)
        if os.path.isfile(legacy):
            try:
                with open(legacy, "rb") as src, open(new_path, "wb") as dst:
                    dst.write(src.read())
            except OSError:
                pass
    return new_path


def load() -> Dict[str, str]:
    """All key=value pairs. Missing file -> {}. Malformed/blank/comment lines
    are skipped rather than raising."""
    p = cfg_path()
    out: Dict[str, str] = {}
    if not os.path.isfile(p):
        return out
    try:
        with open(p, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.rstrip("\n")
                s = ln.lstrip()
                if not s or s.startswith("#") or "=" not in ln:
                    continue
                k, _, v = ln.partition("=")
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def save(data: Dict[str, str]) -> None:
    """Write the whole mapping back atomically. db first, then the rest sorted
    for stable, readable diffs."""
    p = cfg_path()
    keys = sorted(data.keys(), key=lambda k: (k != "db", k))
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for k in keys:
            fh.write(f"{k}={data[k]}\n")
    os.replace(tmp, p)


def get(key: str, default: Optional[str] = None) -> Optional[str]:
    return load().get(key, default)


def set(key: str, value) -> None:              # noqa: A003 - deliberate simple API
    d = load()
    d[key] = str(value)
    save(d)


def set_many(pairs: Dict[str, object]) -> None:
    d = load()
    for k, v in pairs.items():
        d[k] = str(v)
    save(d)


def unset(*keys: str) -> None:
    d = load()
    if any(k in d for k in keys):
        for k in keys:
            d.pop(k, None)
        save(d)
