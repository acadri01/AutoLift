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


def _app_dir() -> str:
    return (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))


def cfg_path() -> str:
    return os.path.join(_app_dir(), CFG_NAME)


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
