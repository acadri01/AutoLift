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

Rewritten (second pass, same day) after a real-machine report that the
first version ("does not seem to do anything") didn't work. Switched from
pywin32 to calling user32.dll/kernel32.dll directly via ctypes - the same
pattern already used elsewhere in this project (line_layout.py's _hide(),
ui_dialogs.py's show_message()) - to fix two well-documented Win32 issues
the pywin32 version was exposed to:

  1. The original process-name lookup (GetModuleFileNameEx) needs
     PROCESS_VM_READ, a fairly strong permission that can silently fail
     to open a process running at a different privilege level (e.g. an
     elevated CAESAR II against a non-elevated AutoLift) - the process
     would then just never match, with no visible error. Replaced with
     QueryFullProcessImageNameW under PROCESS_QUERY_LIMITED_INFORMATION,
     a much lower bar, and the modern recommended way to get a process's
     image path.
  2. SetForegroundWindow is deliberately restricted by Windows - a
     background process generally can't just steal focus on its own
     (the OS's "foreground lock" behaviour). The standard, documented
     workaround - AttachThreadInput with the target window's thread
     first - is now done here; the first version didn't do this at all.

Every ctypes call that returns or accepts a window/process handle uses an
explicit c_void_p prototype - handles are pointer-sized (8 bytes on 64-bit
Windows), and ctypes silently truncates undeclared pointer arguments to
32 bits, which is exactly the kind of bug that would look like "nothing
happened" with no error anywhere.

A trace of each attempt is appended to a log file in AutoLift's AppData
folder (see app_paths.py) - not shown to the user, but gives something
concrete to look at if this still doesn't work rather than guessing a
third time blind.

This is a single, best-effort attempt - not a loop, and never the only
path: MainExpandedDialog still polls for *_MAIN.C2 to reappear regardless
of whether this does anything, so a user who prefers to do it by hand (or
whose window couldn't be found/brought forward) is never stuck waiting on
automation that didn't work.

Windows-only. Every failure mode is swallowed and reported as "did
nothing", never raised - this must never be able to crash or block lift
case creation.
"""

from __future__ import annotations

import ntpath
import time
from typing import List, Optional

PREPIP_EXE_NAME = "prepip.exe"
LOG_FILE_NAME = "prepip_automation.log"

SW_RESTORE = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
KEYEVENTF_KEYUP = 0x0002
_VK_CONTROL = 0x11
_VK_O = 0x4F
_MAX_PATH = 1024

_log_lines: List[str] = []


def _log(msg: str) -> None:
    _log_lines.append(msg)


def _flush_log() -> None:
    """Best-effort: append this attempt's trace to AppData, so a report
    of "it didn't work" can point at something concrete next time."""
    if not _log_lines:
        return
    try:
        import os
        import app_paths
        path = os.path.join(app_paths.autolift_appdata_dir(), LOG_FILE_NAME)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            for line in _log_lines:
                f.write(line + "\n")
    except Exception:
        pass
    finally:
        _log_lines.clear()


# ---------------------------------------------------------------------------
# ctypes plumbing - isolated behind small accessors so every failure mode
# and every downstream function can be exercised headlessly against a fake
# stand-in, without ever touching the real (Windows-only) ctypes.windll.
# ---------------------------------------------------------------------------

def _user32():
    import ctypes
    return ctypes.windll.user32


def _kernel32():
    import ctypes
    return ctypes.windll.kernel32


def _configure_prototypes() -> None:
    """
    Explicit argtypes/restype for every handle/pointer-bearing call below.
    Without this, ctypes' default (guessed) marshalling treats an
    undeclared pointer argument as a 32-bit int, silently truncating a
    64-bit HWND/HANDLE on 64-bit Windows - a real, silent-failure risk,
    not a theoretical one. Idempotent; cheap enough to call every attempt
    rather than track whether it's already been done.
    """
    import ctypes

    u32 = _user32()
    k32 = _kernel32()

    u32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    u32.EnumWindows.restype = ctypes.c_bool

    u32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    u32.IsWindowVisible.restype = ctypes.c_bool

    u32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    u32.GetWindowTextLengthW.restype = ctypes.c_int

    u32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    u32.GetWindowTextW.restype = ctypes.c_int

    u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    u32.GetWindowThreadProcessId.restype = ctypes.c_ulong

    u32.IsIconic.argtypes = [ctypes.c_void_p]
    u32.IsIconic.restype = ctypes.c_bool

    u32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u32.ShowWindow.restype = ctypes.c_bool

    u32.BringWindowToTop.argtypes = [ctypes.c_void_p]
    u32.BringWindowToTop.restype = ctypes.c_bool

    u32.AttachThreadInput.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_bool]
    u32.AttachThreadInput.restype = ctypes.c_bool

    u32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    u32.SetForegroundWindow.restype = ctypes.c_bool

    u32.GetForegroundWindow.argtypes = []
    u32.GetForegroundWindow.restype = ctypes.c_void_p

    u32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, ctypes.c_void_p]
    u32.keybd_event.restype = None

    k32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
    k32.OpenProcess.restype = ctypes.c_void_p

    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    k32.CloseHandle.restype = ctypes.c_bool

    k32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    k32.QueryFullProcessImageNameW.restype = ctypes.c_bool

    k32.GetCurrentThreadId.argtypes = []
    k32.GetCurrentThreadId.restype = ctypes.c_ulong


def _enum_top_level_windows() -> List[int]:
    """
    Every top-level window handle currently on the desktop, via
    EnumWindows. Isolated in its own function since constructing the
    EnumWindows callback needs ctypes.WINFUNCTYPE, which - like
    ctypes.windll - only exists when actually running on Windows; every
    function downstream of the hwnd list this returns is plain, portable
    logic that a test can exercise directly by monkeypatching this one
    function.
    """
    import ctypes

    _configure_prototypes()
    hwnds: List[int] = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _callback(hwnd, _lparam):
        hwnds.append(hwnd)
        return True

    _user32().EnumWindows(proto(_callback), None)
    return hwnds


def _window_title(hwnd: int) -> str:
    import ctypes
    length = _user32().GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32().GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _window_thread_and_process(hwnd: int) -> "tuple[int, int]":
    """(thread_id, process_id) owning `hwnd`."""
    import ctypes
    pid = ctypes.c_ulong(0)
    thread_id = _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return thread_id, pid.value


def _process_exe_name(pid: int) -> str:
    """
    Best-effort lowercase basename of the executable running as `pid`, or
    "" if it can't be determined (access denied, process gone, etc.).
    Uses QueryFullProcessImageNameW under PROCESS_QUERY_LIMITED_INFORMATION
    (a much lower bar than the PROCESS_VM_READ the original pywin32-based
    version needed), and ntpath.basename (not os.path.basename) since the
    Windows-style backslash path this returns needs to parse correctly
    regardless of which OS this happens to run under.
    """
    import ctypes
    handle = _kernel32().OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(_MAX_PATH)
        size = ctypes.c_ulong(_MAX_PATH)
        ok = _kernel32().QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        if not ok:
            return ""
        return ntpath.basename(buf.value).lower()
    except Exception:
        return ""
    finally:
        _kernel32().CloseHandle(handle)


def find_prepip_window() -> Optional[int]:
    """
    The window handle of the first visible, titled top-level window
    belonging to a running prepip.exe process, or None if none is found
    (ctypes/Win32 unavailable, prepip.exe not running, or every candidate
    denied access - all treated the same: nothing to automate).
    """
    try:
        hwnds = _enum_top_level_windows()
    except Exception as e:
        _log(f"EnumWindows failed: {e}")
        return None

    _log(f"enumerated {len(hwnds)} top-level windows")
    u32 = _user32()
    candidates = 0
    for hwnd in hwnds:
        try:
            if not u32.IsWindowVisible(hwnd):
                continue
            title = _window_title(hwnd)
            if not title:
                continue
            candidates += 1
            _, pid = _window_thread_and_process(hwnd)
            exe = _process_exe_name(pid)
            _log(f"  hwnd={hwnd} pid={pid} exe={exe!r} title={title!r}")
            if exe == PREPIP_EXE_NAME:
                _log(f"matched prepip.exe window: hwnd={hwnd}")
                return hwnd
        except Exception as e:
            _log(f"  hwnd={hwnd}: error {e}")
            continue
    _log(f"no prepip.exe window found among {candidates} visible/titled windows")
    return None


def _bring_to_foreground(hwnd: int) -> bool:
    """
    Restore the window if minimized, then bring it to the foreground.
    AttachThreadInput with the target window's owning thread is the
    standard, documented workaround for Windows' foreground-lock
    restriction (a background process normally can't call
    SetForegroundWindow successfully on its own).
    """
    try:
        u32 = _user32()
        k32 = _kernel32()

        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, SW_RESTORE)

        target_thread, _ = _window_thread_and_process(hwnd)
        current_thread = k32.GetCurrentThreadId()

        attached = False
        if target_thread and target_thread != current_thread:
            attached = bool(u32.AttachThreadInput(current_thread, target_thread, True))
            _log(f"AttachThreadInput({current_thread}, {target_thread}) -> {attached}")

        try:
            u32.BringWindowToTop(hwnd)
            set_ok = u32.SetForegroundWindow(hwnd)
            _log(f"SetForegroundWindow(hwnd={hwnd}) -> {bool(set_ok)}")
        finally:
            if attached:
                u32.AttachThreadInput(current_thread, target_thread, False)

        fg = u32.GetForegroundWindow()
        ok = fg == hwnd
        _log(f"GetForegroundWindow() -> {fg} (target was {hwnd}) -> {'OK' if ok else 'MISMATCH'}")
        return ok
    except Exception as e:
        _log(f"_bring_to_foreground failed: {e}")
        return False


def _send_ctrl_o() -> None:
    """Simulate Ctrl+O on whatever window currently has focus - meant to
    be called immediately after successfully bringing prepip.exe's window
    to the foreground."""
    u32 = _user32()
    u32.keybd_event(_VK_CONTROL, 0, 0, None)
    u32.keybd_event(_VK_O, 0, 0, None)
    u32.keybd_event(_VK_O, 0, KEYEVENTF_KEYUP, None)
    u32.keybd_event(_VK_CONTROL, 0, KEYEVENTF_KEYUP, None)


def try_collapse_main_file() -> bool:
    """
    Best-effort, single attempt: find prepip.exe's window, bring it to
    the foreground, and send Ctrl+O (File > Open) - the same action a
    user already takes by hand to collapse an expanded model back to
    *_MAIN.C2.

    Returns True if a prepip.exe window was found and brought to the
    foreground (Ctrl+O was sent to it) - NOT a guarantee the file
    actually collapsed, only that the attempt was made. Returns False on
    any failure. Either way, the caller's own polling (MainExpandedDialog)
    is what actually confirms success, and the manual instructions remain
    the fallback. A trace of the attempt is always flushed to AppData's
    prepip_automation.log, success or failure.
    """
    _log_lines.clear()
    try:
        hwnd = find_prepip_window()
        if hwnd is None:
            return False
        if not _bring_to_foreground(hwnd):
            return False
        try:
            _send_ctrl_o()
            _log("Ctrl+O sent")
        except Exception as e:
            _log(f"_send_ctrl_o failed: {e}")
            return False
        return True
    finally:
        _flush_log()
