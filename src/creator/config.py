"""
config.py

Reads and provides access to lift_case_config.ini, located in the same
directory as the running executable (or script).

All settings have hardcoded fallbacks so the tool works without a config file.

Config file location: next to the .exe / .py entry point.
Config file name:     lift_case_config.ini

Example lift_case_config.ini
-----------------------------
[defaults]
# Distance from restrained node to new displacement BC node (mm)
spacing_mm = 750

# Applied displacement magnitude in global +Y, vector 3 (mm)
displacement_mm = 10

[iecho]
# Full path to iecho.exe. Leave blank to use automatic search.
path =

# Timeout for silent CII → C2 conversion (seconds)
silent_timeout_s = 60

# Maximum time to wait for user to complete interactive export (seconds)
poll_timeout_s = 300
"""

from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Hardcoded fallbacks
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "spacing_mm":        750.0,
    "displacement_mm":   10.0,
    "path":              "",
    "iecho_path":        "",
    "silent_timeout_s":  60,
    "poll_timeout_s":    300,
}


# ---------------------------------------------------------------------------
# Locate config file
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    """
    Return the path of lift_case_config.ini, co-located with the executable
    (PyInstaller) or the entry-point script (plain Python).
    """
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller .exe — use the folder containing the exe
        base = Path(sys.executable).parent
    else:
        # Running as plain Python — use the folder containing this file
        base = Path(__file__).parent
    return base / "lift_case_config.ini"


# ---------------------------------------------------------------------------
# Config singleton
# ---------------------------------------------------------------------------

_cfg: Optional[configparser.ConfigParser] = None


def _load() -> configparser.ConfigParser:
    global _cfg
    if _cfg is None:
        _cfg = configparser.ConfigParser()
        p = _config_path()
        if p.exists():
            _cfg.read(p, encoding="utf-8")
    return _cfg


def _get_float(section: str, key: str) -> float:
    cfg = _load()
    try:
        return float(cfg.get(section, key))
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        return float(_DEFAULTS.get(key, 0.0))


def _get_int(section: str, key: str) -> int:
    cfg = _load()
    try:
        return int(cfg.get(section, key))
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        return int(_DEFAULTS.get(key, 0))


def _get_str(section: str, key: str) -> str:
    cfg = _load()
    try:
        return cfg.get(section, key).strip()
    except (configparser.NoSectionError, configparser.NoOptionError):
        return str(_DEFAULTS.get(key, ""))


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------

def default_spacing_mm() -> float:
    """Default distance from restrained node to displacement BC node (mm)."""
    return _get_float("defaults", "spacing_mm")


def default_displacement_mm() -> float:
    """Default applied displacement magnitude in global +Y (mm)."""
    return _get_float("defaults", "displacement_mm")


def iecho_path() -> str:
    """
    Explicit path to iecho.exe, or empty string to use automatic search.
    Maps to the IECHO_PATH environment variable override in iecho.py.
    """
    return _get_str("iecho", "path")


def silent_timeout_s() -> int:
    """Timeout for silent iecho CII → C2 conversion (seconds)."""
    return _get_int("iecho", "silent_timeout_s")


def poll_timeout_s() -> int:
    """Maximum wait time for user to complete interactive iecho export (seconds)."""
    return _get_int("iecho", "poll_timeout_s")


# ---------------------------------------------------------------------------
# Config file generator
# ---------------------------------------------------------------------------

def write_default_config() -> Path:
    """
    Write a default lift_case_config.ini next to the executable if one does
    not already exist. Returns the path written (or existing path).
    """
    p = _config_path()
    if p.exists():
        return p

    content = f"""\
[defaults]
# Distance from restrained node to new displacement BC node (mm)
spacing_mm = {int(_DEFAULTS['spacing_mm'])}

# Applied displacement magnitude in global +Y, vector 3 (mm)
displacement_mm = {int(_DEFAULTS['displacement_mm'])}

[iecho]
# Full path to iecho.exe. Leave blank to use automatic search.
path =

# Timeout for silent CII to C2 conversion (seconds)
silent_timeout_s = {_DEFAULTS['silent_timeout_s']}

# Maximum time to wait for user to complete interactive export (seconds)
poll_timeout_s = {_DEFAULTS['poll_timeout_s']}
"""
    p.write_text(content, encoding="utf-8")
    return p
