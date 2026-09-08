"""
fonts.py
--------
Helvetica, the built-in PDF standard font. No TTF, no embedding, no
licensing question - every PDF reader has it, and reportlab knows its
metrics natively.

register() is a no-op kept for call-site compatibility.
"""

from __future__ import annotations

_REGULAR = "Helvetica"
_BOLD = "Helvetica-Bold"


def register():
    """No-op - Helvetica is a standard-14 PDF font, always available."""
    return _REGULAR, _BOLD


def regular() -> str:
    return _REGULAR


def bold() -> str:
    return _BOLD


def tk_family() -> str:
    """Family name for the on-screen tkinter preview."""
    return "Helvetica"
