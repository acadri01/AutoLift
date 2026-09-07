"""
ui_dialogs.py

All tkinter dialogs for the Caesar II lift case toolset.

Dialogs
-------
FolderSelectDialog      Browse for or type a folder path. Pre-populated with
                        any path passed in (e.g. from %V context menu argument).
                        Returns Path or None (cancelled).

NodePromptDialog        Two-phase: enter count → node fields appear dynamically.
                        Returns List[str] (node numbers) or None (cancelled).
                        Empty list → fallback to Ln auto-numbering.

LiftParamsDialog        Per-node spacing and displacement with shared defaults.
                        One row per lifted node; defaults pre-filled to 750/10.
                        Returns LiftParams or None (cancelled).

CiiPollingDialog        Shown while waiting for the user to export a CII file
                        from iecho. Polls every second; closes automatically
                        when the file appears with mtime > reference mtime.
                        Terminates the iecho process on both success and abort.
                        Returns True (file ready) or False (user aborted).

ElementOverrideDialog   Shown only when a proposed element break has a geometry
                        problem (element shorter than spacing). Allows the user
                        to confirm or override from/to nodes for each side.
                        Returns ElementOverride or None (cancelled).
"""

from __future__ import annotations

import subprocess
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data classes returned by dialogs
# ---------------------------------------------------------------------------

@dataclass
class NodeLiftParams:
    """Per-node lift parameters."""
    node: str
    spacing_mm: float
    displacement_mm: float


@dataclass
class LiftParams:
    """Lift parameters for all nodes."""
    nodes: List[NodeLiftParams]

    @property
    def spacing_mm(self) -> float:
        return self.nodes[0].spacing_mm if self.nodes else 750.0

    @property
    def displacement_mm(self) -> float:
        return self.nodes[0].displacement_mm if self.nodes else 10.0


@dataclass
class ElementOverride:
    """Per-lifted-node override for which element to break on each side."""
    upstream_from: int
    upstream_to: int
    downstream_from: int
    downstream_to: int


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _center(root: tk.Tk | tk.Toplevel) -> None:
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"+{x}+{y}")


def _focus_window(root: tk.Tk | tk.Toplevel) -> None:
    """Raise the window to the front and claim keyboard focus."""
    root.lift()
    root.attributes("-topmost", True)
    root.focus_force()
    root.after(200, lambda: root.attributes("-topmost", False))


def _label(parent, text, bold=False, italic=False, fg=None,
           wraplength=340, anchor="w", justify="left"):
    font = ["Segoe UI", 9]
    if bold:
        font.append("bold")
    if italic:
        font.append("italic")
    kw = dict(text=text, font=tuple(font), anchor=anchor,
              wraplength=wraplength, justify=justify)
    if fg:
        kw["fg"] = fg
    return tk.Label(parent, **kw)


def _entry(parent, var, width=12, justify="center"):
    return tk.Entry(parent, textvariable=var, width=width,
                    font=("Segoe UI", 10), justify=justify)


def _btn(parent, text, command, default=False, width=10):
    return tk.Button(parent, text=text, width=width,
                     font=("Segoe UI", 9), command=command,
                     default="active" if default else "normal")


# ---------------------------------------------------------------------------
# FolderSelectDialog
# ---------------------------------------------------------------------------

class FolderSelectDialog:
    """
    Ask the user to confirm or change the working folder.

    result : Path or None (cancelled)
    """

    def __init__(self, initial_path: Optional[Path] = None):
        self.result: Optional[Path] = None

        self.root = tk.Tk()
        self.root.title("Lift Case — Select Folder")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

        self._path_var = tk.StringVar(
            value=str(initial_path) if initial_path else "")
        self._build_ui()
        _center(self.root)
        _focus_window(self.root)
        self.root.mainloop()

    def _build_ui(self):
        pad = dict(padx=14, pady=6)

        _label(self.root, "Lift Case Creation",
               bold=True, wraplength=420).grid(
            row=0, column=0, columnspan=3, sticky="w", **pad)

        _label(self.root,
               "Select the folder containing the *_MAIN.C2 file:",
               wraplength=420).grid(
            row=1, column=0, columnspan=3, sticky="w",
            padx=14, pady=(0, 4))

        path_entry = tk.Entry(
            self.root, textvariable=self._path_var, width=48,
            font=("Segoe UI", 9), justify="left")
        path_entry.grid(row=2, column=0, columnspan=2,
                        sticky="ew", padx=(14, 4), pady=4)
        path_entry.bind("<Return>", lambda e: self._confirm())
        path_entry.bind("<Escape>", lambda e: self._cancel())

        _btn(self.root, "Browse…", self._browse, width=8).grid(
            row=2, column=2, padx=(0, 14), pady=4)

        tk.Frame(self.root, height=1, bg="#cccccc").grid(
            row=3, column=0, columnspan=3,
            sticky="ew", padx=14, pady=(6, 0))

        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=(8, 12))
        _btn(btn_frame, "OK", self._confirm, default=True).pack(
            side="left", padx=6)
        _btn(btn_frame, "Cancel", self._cancel).pack(side="left", padx=6)

        self.root.bind("<Escape>", lambda e: self._cancel())

    def _browse(self):
        current = self._path_var.get().strip()
        initial = current if current and Path(current).is_dir() else None
        chosen = filedialog.askdirectory(
            title="Select folder containing *_MAIN.C2",
            initialdir=initial,
            parent=self.root,
        )
        if chosen:
            self._path_var.set(chosen)

    def _confirm(self):
        raw = self._path_var.get().strip()
        if not raw:
            messagebox.showerror("No folder selected",
                                 "Please select a folder.",
                                 parent=self.root)
            return
        p = Path(raw)
        if not p.is_dir():
            messagebox.showerror("Invalid folder",
                                 f"Folder not found:\n{raw}",
                                 parent=self.root)
            return
        self.result = p
        self.root.destroy()

    def _cancel(self):
        self.result = None
        self.root.destroy()


# ---------------------------------------------------------------------------
# NodePromptDialog
# ---------------------------------------------------------------------------

class NodePromptDialog:
    """
    Two-phase keyboard-driven dialog.

    Phase 1 — count field only.
              Enter confirms count → node fields appear.
              Blank / 0 → result = [] (fallback to Ln numbering).

    Phase 2 — node fields generated dynamically.
              Enter advances through each field.
              Enter on last field → confirms.

    result : List[str]  — node numbers as strings, or [] for Ln fallback
             None       — user cancelled
    """

    def __init__(self, prefix: str):
        self.prefix = prefix
        self.result: Optional[List[str]] = None

        self.root = tk.Tk()
        self.root.title("Lift Case — Node Selection")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

        self._node_entries: list[tuple[tk.Entry, tk.StringVar]] = []
        self._build_static_ui()
        _center(self.root)
        _focus_window(self.root)
        self.root.mainloop()

    def _build_static_ui(self):
        pad = dict(padx=12, pady=5)

        _label(self.root, f"Line:  {self.prefix}", bold=True).grid(
            row=0, column=0, columnspan=2, sticky="w", **pad)

        _label(self.root,
               "Number of lifted nodes  (1 or more)\n"
               "Leave blank or enter 0 to use auto Ln numbering:").grid(
            row=1, column=0, columnspan=2, sticky="w",
            padx=12, pady=(0, 6))

        self._count_var = tk.StringVar()
        self._count_entry = _entry(self.root, self._count_var, width=6)
        self._count_entry.grid(row=2, column=0, columnspan=2, pady=4)
        self._count_entry.focus_set()
        self._count_entry.bind("<Return>", lambda e: self._on_count_enter())
        self._count_entry.bind("<Escape>", lambda e: self._cancel())

        self._sep = tk.Frame(self.root, height=1, bg="#cccccc")

        self._preview_var = tk.StringVar(value="")
        self._preview_label = _label(self.root, "", fg="#555555",
                                     wraplength=360)
        self._preview_label.configure(textvariable=self._preview_var)

        self._btn_frame = tk.Frame(self.root)
        self._ok_btn = _btn(self._btn_frame, "OK", self._finish, default=True)
        self._ok_btn.pack(side="left", padx=6)
        _btn(self._btn_frame, "Cancel", self._cancel).pack(side="left", padx=6)
        self._ok_btn.config(state="disabled")

        self.root.bind("<Escape>", lambda e: self._cancel())
        self._repack_buttons()

    def _repack_buttons(self):
        next_row = 3 + len(self._node_entries)
        self._sep.grid_remove()
        self._preview_label.grid_remove()
        self._btn_frame.grid_remove()

        if self._node_entries:
            self._sep.grid(row=next_row, column=0, columnspan=2,
                           sticky="ew", padx=12, pady=(6, 0))
            self._preview_label.grid(row=next_row + 1, column=0,
                                     columnspan=2, sticky="w",
                                     padx=12, pady=(4, 0))
            self._btn_frame.grid(row=next_row + 2, column=0,
                                 columnspan=2, pady=(8, 10))
        else:
            self._btn_frame.grid(row=next_row, column=0,
                                 columnspan=2, pady=(8, 10))

    def _on_count_enter(self):
        raw = self._count_var.get().strip()

        if raw == "" or raw == "0":
            self.result = []
            self.root.destroy()
            return

        if not raw.isdigit() or int(raw) < 1:
            messagebox.showerror(
                "Invalid input",
                "Enter a whole number ≥ 1, or leave blank / 0 for auto Ln.",
                parent=self.root)
            self._count_entry.select_range(0, tk.END)
            return

        self._count_entry.config(state="disabled")
        self._build_node_fields(int(raw))

    def _build_node_fields(self, count: int):
        for i in range(count):
            row = 3 + i
            _label(self.root, f"Node {i + 1}:").grid(
                row=row, column=0, sticky="e", padx=(12, 4), pady=3)

            var = tk.StringVar()
            entry = _entry(self.root, var)
            entry.grid(row=row, column=1, sticky="w",
                       padx=(0, 12), pady=3)
            var.trace_add("write", lambda *_: self._update_preview())

            is_last = (i == count - 1)
            entry.bind("<Return>", self._on_node_enter(i, is_last))
            entry.bind("<Escape>", lambda e: self._cancel())
            self._node_entries.append((entry, var))

        self._ok_btn.config(state="normal")
        self._repack_buttons()
        self._update_preview()
        self._node_entries[0][0].focus_set()

    def _on_node_enter(self, index: int, is_last: bool):
        def handler(event):
            if is_last:
                self._finish()
            else:
                self._node_entries[index + 1][0].focus_set()
            return "break"
        return handler

    def _update_preview(self):
        nodes = [v.get().strip() for _, v in self._node_entries
                 if v.get().strip()]
        if nodes:
            node_str = "-".join(f"N{n}" for n in nodes)
            name = f"{self.prefix}_{node_str}.C2"
        else:
            name = f"{self.prefix}_Ln.C2  (auto-numbered)"
        self._preview_var.set(f"Output: {name}")

    def _finish(self):
        nodes = [v.get().strip() for _, v in self._node_entries]
        for n in nodes:
            if not n:
                messagebox.showerror("Missing input",
                                     "All node fields must be filled in.",
                                     parent=self.root)
                return
            if not n.isdigit():
                messagebox.showerror("Invalid input",
                                     f"'{n}' is not a valid node number.\n"
                                     "Enter digits only.",
                                     parent=self.root)
                return
        self.result = nodes
        self.root.destroy()

    def _cancel(self):
        self.result = None
        self.root.destroy()


# ---------------------------------------------------------------------------
# LiftParamsDialog
# ---------------------------------------------------------------------------

class LiftParamsDialog:
    """
    Per-node spacing and displacement parameters.

    One row per lifted node. Defaults pre-filled (750 mm spacing, 10 mm
    displacement). Tab/Return advance through fields row by row.

    result : LiftParams or None (cancelled)
    """

    DEFAULT_SPACING_MM = 750.0   # overridden from config at runtime
    DEFAULT_DISP_MM    = 10.0    # overridden from config at runtime

    def __init__(self, prefix: str, nodes: List[str]):
        from config import default_spacing_mm, default_displacement_mm
        self.DEFAULT_SPACING_MM = default_spacing_mm()
        self.DEFAULT_DISP_MM    = default_displacement_mm()
        self.prefix = prefix
        self.prefix = prefix
        self.nodes  = nodes
        self.result: Optional[LiftParams] = None

        self.root = tk.Tk()
        self.root.title("Lift Case — Parameters")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

        self._row_vars: List[tuple[tk.StringVar, tk.StringVar]] = []
        self._entries:  List[tuple[tk.Entry, tk.Entry]] = []

        self._build_ui()
        _center(self.root)
        _focus_window(self.root)
        self.root.mainloop()

    def _build_ui(self):
        pad = dict(padx=14, pady=5)

        _label(self.root, f"Line:  {self.prefix}", bold=True).grid(
            row=0, column=0, columnspan=3, sticky="w", **pad)

        _label(self.root,
               "Set spacing and displacement for each lifted node.\n"
               "Spacing: distance from node to new displacement BC node (mm).\n"
               "Displacement applied in global +Y (vector 3).",
               fg="#444444", italic=True, wraplength=420).grid(
            row=1, column=0, columnspan=3, sticky="w",
            padx=14, pady=(0, 6))

        for col, txt in enumerate(["Node", "Spacing (mm)", "Displacement (mm)"]):
            _label(self.root, txt, bold=True).grid(
                row=2, column=col, padx=10, pady=(0, 4), sticky="w")

        tk.Frame(self.root, height=1, bg="#cccccc").grid(
            row=3, column=0, columnspan=3,
            sticky="ew", padx=10, pady=(0, 4))

        all_entries: List[tk.Entry] = []

        for i, node in enumerate(self.nodes):
            row = 4 + i
            _label(self.root, f"N{node}", bold=True).grid(
                row=row, column=0, padx=(14, 6), pady=3, sticky="w")

            sp_var   = tk.StringVar(value=str(self.DEFAULT_SPACING_MM))
            disp_var = tk.StringVar(value=str(self.DEFAULT_DISP_MM))

            sp_entry   = _entry(self.root, sp_var,   width=12)
            disp_entry = _entry(self.root, disp_var, width=12)

            sp_entry.grid(  row=row, column=1, padx=6, pady=3)
            disp_entry.grid(row=row, column=2, padx=6, pady=3)

            sp_entry.bind("<Escape>",   lambda e: self._cancel())
            disp_entry.bind("<Escape>", lambda e: self._cancel())

            self._row_vars.append((sp_var, disp_var))
            self._entries.append((sp_entry, disp_entry))
            all_entries.extend([sp_entry, disp_entry])

        for idx, entry in enumerate(all_entries):
            is_last = (idx == len(all_entries) - 1)
            next_e  = all_entries[idx + 1] if not is_last else None
            entry.bind("<Return>", self._advance_handler(next_e, is_last))

        tk.Frame(self.root, height=1, bg="#cccccc").grid(
            row=4 + len(self.nodes), column=0, columnspan=3,
            sticky="ew", padx=10, pady=(6, 0))

        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=5 + len(self.nodes), column=0,
                       columnspan=3, pady=(8, 12))
        _btn(btn_frame, "OK", self._confirm, default=True).pack(
            side="left", padx=6)
        _btn(btn_frame, "Cancel", self._cancel).pack(side="left", padx=6)

        self.root.bind("<Escape>", lambda e: self._cancel())

        if self._entries:
            e = self._entries[0][0]
            e.focus_set()
            e.select_range(0, tk.END)

    def _advance_handler(self, next_entry: Optional[tk.Entry], is_last: bool):
        def handler(event):
            if is_last:
                self._confirm()
            else:
                next_entry.focus_set()
                next_entry.select_range(0, tk.END)
            return "break"
        return handler

    def _confirm(self):
        node_params: List[NodeLiftParams] = []
        for i, (node, (sp_var, disp_var)) in enumerate(
                zip(self.nodes, self._row_vars)):

            try:
                spacing = float(sp_var.get().strip())
                if spacing <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Invalid input",
                    f"Node N{node}: spacing must be a positive number (mm).",
                    parent=self.root)
                self._entries[i][0].focus_set()
                return

            try:
                disp = float(disp_var.get().strip())
                if disp <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Invalid input",
                    f"Node N{node}: displacement must be a positive number (mm).",
                    parent=self.root)
                self._entries[i][1].focus_set()
                return

            node_params.append(NodeLiftParams(
                node=node, spacing_mm=spacing, displacement_mm=disp))

        self.result = LiftParams(nodes=node_params)
        self.root.destroy()

    def _cancel(self):
        self.result = None
        self.root.destroy()


# ---------------------------------------------------------------------------
# CiiPollingDialog
# ---------------------------------------------------------------------------

class CiiPollingDialog:
    """
    Shown while waiting for the user to export a CII file from iecho.

    Polls every second for:
      - cii_path to exist
      - cii_path.mtime > reference_mtime

    Closes automatically when both conditions are met.
    Also closes (and kills iecho) if the user clicks Abort.

    The iecho process is always terminated when this dialog closes,
    whether by success, abort, or timeout.

    result : True  — file ready
             False — aborted or timed out
    """

    POLL_INTERVAL_MS = 1000
    MAX_WAIT_S       = 300     # overridden from config at runtime

    def __init__(
        self,
        cii_path: Path,
        reference_mtime: float,
        c2_name: str,
        proc: Optional[subprocess.Popen] = None,
    ):
        from config import poll_timeout_s
        self.MAX_WAIT_S      = poll_timeout_s()
        self.cii_path        = cii_path
        self.reference_mtime = reference_mtime
        self.c2_name         = c2_name
        self.proc            = proc
        self.result: bool    = False
        self._start          = time.time()

        self.root = tk.Tk()
        self.root.title("Waiting for CII Export")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._abort)

        self._build_ui()
        _center(self.root)
        self._raise()
        self._poll()
        self.root.mainloop()

    def _raise(self):
        """Bring the dialog to the front above iecho and claim keyboard focus."""
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.focus_force()
        # Remove topmost after a short delay so it doesn't permanently
        # sit above other windows once the user starts interacting with iecho.
        self.root.after(500, lambda: self.root.attributes("-topmost", False))

    def _build_ui(self):
        pad = dict(padx=16, pady=8)

        _label(self.root,
               "Please export the neutral file from iecho:",
               bold=True, wraplength=400).grid(
            row=0, column=0, sticky="w", **pad)

        _label(self.root,
               f"In the iecho window:\n"
               f"  1. Select  \"Convert CAESAR II Input File to Neutral File\"\n"
               f"  2. Browse to:  {self.c2_name}\n"
               f"  3. Click Convert",
               wraplength=400, justify="left").grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 8))

        _label(self.root,
               f"Waiting for:\n{self.cii_path.name}",
               fg="#333333", italic=True, wraplength=400).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 4))

        self._status_var = tk.StringVar(value="Waiting...")
        tk.Label(self.root, textvariable=self._status_var,
                font=("Segoe UI", 9), fg="#0055aa",
                wraplength=400, anchor="w").grid(
            row=3, column=0, sticky="w", padx=16, pady=(0, 8))

        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=4, column=0, pady=(4, 12))
        _btn(btn_frame, "Abort", self._abort, width=12).pack()

    def _poll(self):
        elapsed = time.time() - self._start

        if elapsed > self.MAX_WAIT_S:
            self._status_var.set("Timed out after 5 minutes.")
            self.result = False
            self.root.after(2000, self._close)
            return

        if self.cii_path.exists():
            mtime = self.cii_path.stat().st_mtime
            if mtime > self.reference_mtime:
                self._status_var.set(f"✓  Found: {self.cii_path.name}")
                self.result = True
                self.root.after(800, self._close)
                return
            else:
                self._status_var.set(
                    "File found but older than C2 — waiting for fresh export...")
        else:
            mins, secs = divmod(int(elapsed), 60)
            timer = f"{mins}:{secs:02d}" if mins else f"{secs}s"
            self._status_var.set(f"Waiting... ({timer})")

        self.root.after(self.POLL_INTERVAL_MS, self._poll)

    def _close(self):
        """Terminate iecho (if still running) then destroy the dialog."""
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.root.destroy()

    def _abort(self):
        self.result = False
        self._close()


# ---------------------------------------------------------------------------
# ElementOverrideDialog
# ---------------------------------------------------------------------------

class ElementOverrideDialog:
    """
    Shown when a proposed element break has a geometry problem.

    result : ElementOverride or None (cancelled)
    """

    def __init__(
        self,
        lifted_node: int,
        upstream_from: int,
        upstream_to: int,
        downstream_from: int,
        downstream_to: int,
        problem: str,
    ):
        self.result: Optional[ElementOverride] = None

        self.root = tk.Tk()
        self.root.title(f"Element Override — Node {lifted_node}")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

        self._build_ui(
            lifted_node, upstream_from, upstream_to,
            downstream_from, downstream_to, problem,
        )
        _center(self.root)
        _focus_window(self.root)
        self.root.mainloop()

    def _build_ui(self, lifted_node, up_from, up_to, dn_from, dn_to, problem):
        pad = dict(padx=12, pady=5)

        _label(self.root, f"Lifted node: {lifted_node}",
               bold=True).grid(row=0, column=0, columnspan=4,
                                sticky="w", **pad)

        _label(self.root, f"⚠  {problem}",
               fg="#cc4400", wraplength=420).grid(
            row=1, column=0, columnspan=4, sticky="w",
            padx=12, pady=(0, 8))

        for col, txt in enumerate(["Side", "From node", "To node", ""]):
            _label(self.root, txt, bold=True).grid(
                row=2, column=col, padx=8, pady=2)

        _label(self.root, "Upstream").grid(
            row=3, column=0, padx=8, pady=4, sticky="e")
        self._up_from = tk.StringVar(value=str(up_from))
        self._up_to   = tk.StringVar(value=str(up_to))
        _entry(self.root, self._up_from, width=8).grid(
            row=3, column=1, padx=4, pady=4)
        _entry(self.root, self._up_to, width=8).grid(
            row=3, column=2, padx=4, pady=4)

        _label(self.root, "Downstream").grid(
            row=4, column=0, padx=8, pady=4, sticky="e")
        self._dn_from = tk.StringVar(value=str(dn_from))
        self._dn_to   = tk.StringVar(value=str(dn_to))
        _entry(self.root, self._dn_from, width=8).grid(
            row=4, column=1, padx=4, pady=4)
        _entry(self.root, self._dn_to, width=8).grid(
            row=4, column=2, padx=4, pady=4)

        _label(self.root,
               "Override the From/To nodes if the suggested elements are incorrect.",
               fg="#555555", italic=True, wraplength=420).grid(
            row=5, column=0, columnspan=4, sticky="w",
            padx=12, pady=(4, 8))

        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=6, column=0, columnspan=4, pady=(4, 10))
        _btn(btn_frame, "OK", self._confirm, default=True).pack(
            side="left", padx=6)
        _btn(btn_frame, "Cancel", self._cancel).pack(side="left", padx=6)

        self.root.bind("<Return>", lambda e: self._confirm())
        self.root.bind("<Escape>",  lambda e: self._cancel())

    def _confirm(self):
        try:
            uf = int(self._up_from.get().strip())
            ut = int(self._up_to.get().strip())
            df = int(self._dn_from.get().strip())
            dt = int(self._dn_to.get().strip())
        except ValueError:
            messagebox.showerror("Invalid input",
                                 "All node fields must be integers.",
                                 parent=self.root)
            return
        self.result = ElementOverride(
            upstream_from=uf, upstream_to=ut,
            downstream_from=df, downstream_to=dt,
        )
        self.root.destroy()

    def _cancel(self):
        self.result = None
        self.root.destroy()


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def show_message(title: str, message: str,
                 error: bool = False,
                 warning_yesno: bool = False) -> bool:
    """
    Native Windows MessageBox.

    warning_yesno=True  → Yes/No dialog, warning icon, No is default.
                          Returns True if Yes, False if No.
    error=True          → Error icon, OK button. Returns True.
    default             → Info icon, OK button. Returns True.
    """
    import ctypes
    if warning_yesno:
        flags = 0x04 | 0x30 | 0x100   # MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2
        result = ctypes.windll.user32.MessageBoxW(0, message, title, flags)
        return result == 6             # IDYES == 6
    icon = 0x10 if error else 0x40
    ctypes.windll.user32.MessageBoxW(0, message, title, icon)
    return True


def prompt_folder(initial_path: Optional[Path] = None) -> Optional[Path]:
    d = FolderSelectDialog(initial_path)
    return d.result


def prompt_nodes(prefix: str) -> Optional[List[str]]:
    d = NodePromptDialog(prefix)
    return d.result


def prompt_lift_params(prefix: str, nodes: List[str]) -> Optional[LiftParams]:
    d = LiftParamsDialog(prefix, nodes)
    return d.result


def poll_for_cii(
    cii_path: Path,
    reference_mtime: float,
    c2_name: str,
    proc: Optional[subprocess.Popen] = None,
) -> bool:
    """Show CiiPollingDialog. Returns True when file is ready."""
    d = CiiPollingDialog(cii_path, reference_mtime, c2_name, proc)
    return d.result


def prompt_element_override(
    lifted_node: int,
    upstream_from: int, upstream_to: int,
    downstream_from: int, downstream_to: int,
    problem: str,
) -> Optional[ElementOverride]:
    d = ElementOverrideDialog(
        lifted_node, upstream_from, upstream_to,
        downstream_from, downstream_to, problem,
    )
    return d.result
