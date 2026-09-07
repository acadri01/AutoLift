"""
iecho.py

Wrapper around Caesar II's iecho.exe for two distinct operations:

    launch_for_export(c2_path)
        Opens iecho interactively so the user can export a .CII neutral file.
        Returns the Popen process handle immediately — caller is responsible
        for polling (use ui_dialogs.poll_for_cii) and terminating the process.

    convert_cii_to_c2(cii_path)
        Silently converts a .CII neutral file back to a .C2 input file.
        Blocks until complete.
        Returns the output .C2 Path on success.
        Raises RuntimeError on failure.

iecho.exe path resolution order:
    1. IECHO_PATH environment variable
    2. IECHO_SEARCH_PATHS list (hardcoded, covers common install locations)
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Path resolution
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

_resolved: Optional[Path] = None


def find_iecho() -> Path:
    """
    Return the iecho.exe path.
    Caches the result after first successful resolution.
    Raises FileNotFoundError if not found anywhere.
    """
    global _resolved
    if _resolved is not None:
        return _resolved

    # 0. Config file explicit path
    try:
        from config import iecho_path as cfg_iecho_path
        cfg = cfg_iecho_path()
        if cfg:
            p = Path(cfg)
            if p.exists():
                _resolved = p
                return _resolved
    except ImportError:
        pass

    # 1. Environment variable override
    env = os.environ.get("IECHO_PATH")
    if env:
        p = Path(env)
        if p.exists():
            _resolved = p
            return _resolved

    # 2. Search list
    for candidate in IECHO_SEARCH_PATHS:
        if candidate.exists():
            _resolved = candidate
            return _resolved

    raise FileNotFoundError(
        "iecho.exe not found.\n\n"
        "Set the path in lift_case_config.ini, set the IECHO_PATH environment\n"
        "variable, or verify your CAESAR II installation directory."
    )


# ---------------------------------------------------------------------------
# Interactive export  (.C2 → .CII)
# ---------------------------------------------------------------------------

def launch_for_export(c2_path: Path) -> subprocess.Popen:
    """
    Launch iecho.exe so the user can export a .CII neutral file.

    The process is started detached — this call returns immediately.
    The caller receives the Popen handle and is responsible for:
      - Polling for the output .CII file (use ui_dialogs.poll_for_cii)
      - Terminating the process once done (success or abort)

    Parameters
    ----------
    c2_path : Path
        Path to the .C2 file whose folder iecho should open in.

    Returns
    -------
    subprocess.Popen
        Handle to the running iecho process.
    """
    iecho = find_iecho()

    return subprocess.Popen(
        [str(iecho)],
        cwd=str(c2_path.parent),
        creationflags=subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )


# ---------------------------------------------------------------------------
# Silent conversion  (.CII → .C2)
# ---------------------------------------------------------------------------

SILENT_TIMEOUT_S = 60   # fallback if config not available


def convert_cii_to_c2(cii_path: Path) -> Path:
    """
    Silently convert a .CII neutral file to a .C2 Caesar input file.

    Parameters
    ----------
    cii_path : Path
        Path to the .CII file to convert.

    Returns
    -------
    Path
        Path to the produced .C2 file (same stem, same directory).

    Raises
    ------
    FileNotFoundError
        If iecho.exe is not found, or the input file does not exist.
    RuntimeError
        If iecho returns a non-zero exit code, times out, or the output
        file is not found after conversion.
    """
    iecho = find_iecho()

    if not cii_path.exists():
        raise FileNotFoundError(f"CII file not found: {cii_path}")

    expected_c2 = cii_path.with_suffix(".C2")

    try:
        from config import silent_timeout_s
        timeout = silent_timeout_s()
    except ImportError:
        timeout = SILENT_TIMEOUT_S

    try:
        result = subprocess.run(
            [str(iecho), str(cii_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cii_path.parent),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"iecho.exe timed out after {timeout}s converting:\n"
            f"{cii_path.name}"
        )

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"iecho.exe returned exit code {result.returncode} "
            f"converting {cii_path.name}.\n\n{detail}"
        )

    if not expected_c2.exists():
        raise RuntimeError(
            f"iecho.exe completed (exit 0) but expected output was not found:\n"
            f"{expected_c2}\n\n"
            "Verify that the CII file is valid."
        )

    return expected_c2


# ---------------------------------------------------------------------------
# Validity check
# ---------------------------------------------------------------------------

def cii_is_current(cii_path: Path, input_path: Path) -> bool:
    """
    Return True if cii_path exists AND its mtime is later than input_path's mtime.
    """
    if not cii_path.exists() or not input_path.exists():
        return False
    return cii_path.stat().st_mtime > input_path.stat().st_mtime
