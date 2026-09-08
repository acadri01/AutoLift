"""
clipboard_io.py
---------------
Windows clipboard round-tripping for text and images.

Text  : tkinter is adequate.
Images: tkinter is not. Uses PIL.ImageGrab to read and win32clipboard
        CF_DIB to write - this is what preserves fidelity when you paste
        into Word.
"""

from __future__ import annotations

import io
import os
from typing import Optional

from PIL import Image, ImageGrab

try:
    import win32clipboard
    import win32con

    _WIN = True
except ImportError:  # allows lift_calc/lift_db tests off-Windows
    _WIN = False


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------
def copy_text(widget, text: str) -> None:
    """widget = any tkinter widget (needed for the clipboard owner)."""
    widget.clipboard_clear()
    widget.clipboard_append(text)
    widget.update()  # flush - without this the clipboard dies with the app


# --------------------------------------------------------------------------
# Image in
# --------------------------------------------------------------------------
def grab_image() -> Optional[Image.Image]:
    """
    Returns the clipboard image, or None if the clipboard holds no image.
    Handles both raw bitmaps (CAESAR's Ctrl+C / Snipping Tool) and
    file-drop lists (a copied .png in Explorer).
    """
    data = ImageGrab.grabclipboard()

    if isinstance(data, Image.Image):
        return data.convert("RGB")

    if isinstance(data, list) and data:
        for f in data:
            if os.path.isfile(f):
                try:
                    return Image.open(f).convert("RGB")
                except OSError:
                    continue

    return None


def save_png(img: Image.Image, path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, "PNG")
    return path


# --------------------------------------------------------------------------
# Image out
# --------------------------------------------------------------------------
def copy_image_file(path: str) -> bool:
    """
    Puts the PNG on the clipboard as CF_DIB so Word/Excel accept a paste.
    Returns False if the file is missing or we're not on Windows.
    """
    if not _WIN or not path or not os.path.isfile(path):
        return False

    img = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "BMP")
    dib = buf.getvalue()[14:]  # strip the 14-byte BITMAPFILEHEADER
    buf.close()

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, dib)
    finally:
        win32clipboard.CloseClipboard()
    return True
