"""
tool_discovery.py

Single service for resolving local CAESAR II tool paths and reporting
whether CAESAR-driving actions can run at all. Generalizes the
resolve-and-cache logic that used to live directly in iecho.py so future
CAESAR-adjacent tools can share the same config -> env -> known-paths
lookup order and the same capability-probe pattern, instead of every
caller re-implementing it.

Currently resolves:
    iecho.exe   - the only CAESAR II tool actually driven by this program
                  today (interactive .C2 export, silent .CII -> .C2
                  conversion). Resolution order, unchanged from the
                  original iecho.py:
                      1. lift_case_config.ini's [iecho] path
                      2. IECHO_PATH environment variable
                      3. IECHO_SEARCH_PATHS (hardcoded known install
                         locations)

SPEC.md's Milestone 2 description also names a "CAESAR input-GUI exe" and
a "CAESAR data root" to resolve. Nothing in this codebase drives either of
those today (os.startfile() in line_ui.py opens a .C2 with whatever the OS
has associated with it — CAESAR II's own installer sets that up, nothing
here needs to know the path to do it). Rather than inventing a resolution
scheme with no real caller to validate it against, this module resolves
only what's actually used; see QUESTIONS.md for this logged as an open,
non-blocking item to revisit once a concrete feature needs either path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple, Optional


# ---------------------------------------------------------------------------
# iecho.exe resolution
# ---------------------------------------------------------------------------

IECHO_SEARCH_PATHS: list[Path] = [
    Path(r"C:\Program Files (x86)\Intergraph CAS\CAESAR II v.15.01\iecho.exe"),
    Path(r"C:\Program Files\Intergraph CAS\CAESAR II v.15.01\iecho.exe"),
    Path(r"C:\Program Files (x86)\Hexagon\CAESAR II v.15.01\iecho.exe"),
    Path(r"C:\Program Files\Hexagon\CAESAR II v.15.01\iecho.exe"),
    Path(r"C:\Program Files (x86)\Intergraph CAS\CAESAR II v.15\iecho.exe"),
    Path(r"C:\Program Files\Intergraph CAS\CAESAR II v.15\iecho.exe"),
    Path(r"C:\Program Files (x86)\Hexagon\CAESAR II v.15\iecho.exe"),
    Path(r"C:\Program Files\Hexagon\CAESAR II v.15\iecho.exe"),
    Path(r"C:\Program Files (x86)\Intergraph CAS\CAESAR II v.14\iecho.exe"),
    Path(r"C:\Program Files (x86)\Intergraph CAS\CAESAR II v.13\iecho.exe"),
]

_resolved_iecho: Optional[Path] = None


def find_iecho() -> Path:
    """
    Return the iecho.exe path.
    Caches the result after first successful resolution.
    Raises FileNotFoundError if not found anywhere.
    """
    global _resolved_iecho
    if _resolved_iecho is not None:
        return _resolved_iecho

    # 0. Config file explicit path
    try:
        from config import iecho_path as cfg_iecho_path
        cfg = cfg_iecho_path()
        if cfg:
            p = Path(cfg)
            if p.exists():
                _resolved_iecho = p
                return _resolved_iecho
    except ImportError:
        pass

    # 1. Environment variable override
    env = os.environ.get("IECHO_PATH")
    if env:
        p = Path(env)
        if p.exists():
            _resolved_iecho = p
            return _resolved_iecho

    # 2. Search list
    for candidate in IECHO_SEARCH_PATHS:
        if candidate.exists():
            _resolved_iecho = candidate
            return _resolved_iecho

    raise FileNotFoundError(
        "iecho.exe not found.\n\n"
        "Set the path in lift_case_config.ini, set the IECHO_PATH environment\n"
        "variable, or verify your CAESAR II installation directory."
    )


# ---------------------------------------------------------------------------
# Capability probe
# ---------------------------------------------------------------------------

class CapabilityReport(NamedTuple):
    """Result of probing what CAESAR-driving actions are available."""
    iecho_available: bool
    iecho_path: Optional[Path]
    reason: Optional[str]   # populated only when iecho_available is False


def probe_capabilities() -> CapabilityReport:
    """
    Resolve every known CAESAR tool path and report what's usable, without
    raising. Callers gate CAESAR-driving actions (launch_for_export,
    convert_cii_to_c2, and anything upstream of them) on
    `report.iecho_available` instead of catching FileNotFoundError
    themselves, so every entry point reports the same way.
    """
    try:
        path = find_iecho()
        return CapabilityReport(iecho_available=True, iecho_path=path, reason=None)
    except FileNotFoundError as e:
        return CapabilityReport(iecho_available=False, iecho_path=None, reason=str(e))
