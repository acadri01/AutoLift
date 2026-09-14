"""
prepip_automation.py
---------------------
Phase 2 of the CAESAR .C2/._A file-expansion fix (see lift_case_builder.py
and ui_dialogs.MainExpandedDialog): automates collapsing an expanded
CAESAR II model back to *_MAIN.C2 by finding the prepip.exe window,
bringing it to the foreground, and sending Ctrl+O (File > Open) - exactly
the manual fix already documented, just triggered automatically. Per
direct instruction (2026-09-14): "In the task manager I am able to see
two Caesar II windows when the file is expanded. We have to find the one
with the prepip.exe bring it forward and send Ctrl + O. I would like as
much of this to be a background process, apart from bringing the window
forward obviously."

This is a single, best-effort attempt - not a loop, and never the only
path: MainExpandedDialog still polls for *_MAIN.C2 to reappear regardless
of whether this does anything, so a user who prefers to do it by hand (or
whose window couldn't be found/brought forward) is never stuck waiting on
automation that didn't work.

Windows-only (pywin32, already a project dependency - see win32com/
win32clipboard usage elsewhere). Every failure mode (pywin32 unavailable,
no matching window found, the OS refusing a foreground-window change -
a well-known Windows restriction when the calling process didn't itself
just receive input) is swallowed and reported as "did nothing", never
raised - this must never be able to crash or block lift case creation.
"""

from __future__ import annotations

import ntpath
from typing import List, Optional

PREPIP_EXE_NAME = "prepip.exe"

# Virtual key codes (Win32) for the Ctrl+O keystroke.
_VK_CONTROL = 0x11
_VK_O = 0x4F


def _process_exe_name(pid: int) -> str:
    """Best-effort lowercase basename of the executable running as `pid`,
    or "" if it can't be determined (access denied, process gone, etc.).
    Uses ntpath explicitly (not os.path) since GetModuleFileNameEx always
    returns a Windows-style backslash path - correct regardless of which
    OS this happens to run under, not just on the real Windows target."""
    try:
        import win32api
        import win32con
        import win32process
    except ImportError:
        return ""
    try:
        handle = win32api.OpenProcess(
            win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
            False, pid)
    except Exception:
        return ""
    try:
        path = win32process.GetModuleFileNameEx(handle, 0)
        return ntpath.basename(path).lower()
    except Exception:
        return ""
    finally:
        try:
            win32api.CloseHandle(handle)
        except Exception:
            pass


def find_prepip_window() -> Optional[int]:
    """
    The window handle of the first visible, titled top-level window
    belonging to a running prepip.exe process, or None if none is found
    (pywin32 unavailable, prepip.exe not running, or every match denied
    access - all treated the same: nothing to automate).
    """
    try:
        import win32gui
        import win32process
    except ImportError:
        return None

    found: List[int] = []

    def _callback(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if _process_exe_name(pid) == PREPIP_EXE_NAME:
                found.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_callback, None)
    except Exception:
        return None
    return found[0] if found else None


def _bring_to_foreground(hwnd: int) -> bool:
    try:
        import win32con
        import win32gui
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        return False


def _send_ctrl_o() -> None:
    """Simulate Ctrl+O on whatever window currently has focus - meant to
    be called immediately after successfully bringing prepip.exe's window
    to the foreground."""
    import win32api
    import win32con
    win32api.keybd_event(_VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(_VK_O, 0, 0, 0)
    win32api.keybd_event(_VK_O, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(_VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def try_collapse_main_file() -> bool:
    """
    Best-effort, single attempt: find prepip.exe's window, bring it to
    the foreground, and send Ctrl+O (File > Open) - the same action a
    user already takes by hand to collapse an expanded model back to
    *_MAIN.C2.

    Returns True if a prepip.exe window was found and brought to the
    foreground (Ctrl+O was sent to it) - NOT a guarantee the file
    actually collapsed, only that the attempt was made. Returns False on
    any failure (pywin32 unavailable, no matching window, foreground
    change refused). Either way, the caller's own polling
    (MainExpandedDialog) is what actually confirms success, and the
    manual instructions remain the fallback.
    """
    hwnd = find_prepip_window()
    if hwnd is None:
        return False
    if not _bring_to_foreground(hwnd):
        return False
    try:
        _send_ctrl_o()
    except Exception:
        return False
    return True
