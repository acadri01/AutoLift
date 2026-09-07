"""
case_meta_ui.py
---------------
Adopt LEGACY lift case files (created before the sidecar handshake) and
edit case data for any case, legacy or generated.

Design: on confirm, a REAL <case>_liftmeta.json is written to
<line>/00_CII/.liftdoc - exactly what create_lift_case.exe would have
produced - and the normal ingest path runs. Downstream, a legacy case is
indistinguishable from a generated one, and re-ingest on every open stays
idempotent.

Detection: .C2 files in <line>/00_CII, excluding *_MAIN.C2 and files whose
stem is already a known case name. Lifted SUPPORT nodes are parsed from the
"_N325-N475" filename convention of the copy tool; everything else is
entered in the dialog, whose fields mirror the sidecar schema:

    disp_mm, supports[node...],
    lift_points[node, support_node, distance_mm, disp_mm]

Editing an existing case rewrites its sidecar and re-ingests. The upsert
preserves entered forces and support functions for unchanged nodes; nodes
removed from the case are pruned (their forces/functions go with them).
"""

from __future__ import annotations

import os
import re
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

import lift_meta
import line_layout as LL
from lift_db import LiftDb

PAD = 6

# stem ends with _N<digits>(-N<digits>)*  -> lifted support nodes
_NODES_RE = re.compile(r"_((?:N\d+)(?:-N\d+)*)$", re.IGNORECASE)

# CAESAR II unpacks an open .C2 into working files that share the job stem with
# an underscore extension (<stem>._A, <stem>._P, ...). Recognising these means a
# case that is currently OPEN in CAESAR - so has no packed .C2 on disk - is
# still detected.
_WORKING_EXT_RE = re.compile(r"^\._[a-z0-9]{1,2}$", re.IGNORECASE)


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------
def parse_support_nodes(stem: str) -> List[int]:
    """'46-P-4611_N325-N475' -> [325, 475].  '..._L3' -> []."""
    m = _NODES_RE.search(stem)
    if not m:
        return []
    return [int(t[1:]) for t in m.group(1).split("-")]


def _case_stem(filename: str) -> Optional[str]:
    """
    The case stem a file contributes, or None if it isn't a case file.
    Recognises a packed '<stem>.c2' or an unpacked working file '<stem>._A'.
    """
    if filename.lower().endswith(".c2"):
        return filename[:-3]
    root, ext = os.path.splitext(filename)
    if _WORKING_EXT_RE.match(ext):
        return root
    return None


def candidate_files(line_root: str, known_case_names: List[str]) -> List[str]:
    """
    Case files in <line>/00_CII whose stem is not the MAIN file and not already
    a case in the database. A case counts whether it is packed (<stem>.C2) or
    currently OPEN in CAESAR (unpacked working files <stem>._A, ._P, ...).
    Each stem is listed once. Returns stems (case names), sorted.
    """
    cii = os.path.join(line_root, LL.CII_DIR)
    if not os.path.isdir(cii):
        cii = line_root                      # tolerate flat legacy layouts
    known = {n.lower() for n in known_case_names}
    seen: Dict[str, str] = {}                # lower stem -> original-case stem
    try:
        for f in os.listdir(cii):
            stem = _case_stem(f)
            if stem is None:
                continue
            if stem.upper().endswith("_MAIN"):
                continue
            key = stem.lower()
            if key in known or key in seen:
                continue
            seen[key] = stem
    except OSError:
        pass
    return sorted(seen.values(), key=str.lower)


# --------------------------------------------------------------------------
# Persist
# --------------------------------------------------------------------------
def write_and_ingest(db: LiftDb, wo_id: int, line_root: str,
                     meta: Dict) -> int:
    """Write the sidecar where the generator would, then normal ingest."""
    out_dir = LL.sidecar_dir(line_root, create=True)
    lift_meta.write_sidecar(
        out_dir,
        line=meta["line"],
        case_name=meta["case_name"],
        disp_mm=meta["disp_mm"],
        supports=[s["node"] for s in meta["supports"]],
        lift_points=meta["lift_points"],
    )
    return db.upsert_case_from_meta(wo_id, meta, line_root)


# --------------------------------------------------------------------------
# File picker (detected candidates)
# --------------------------------------------------------------------------
def pick_case_file(parent, line_root: str,
                   known_case_names: List[str]) -> Optional[str]:
    """Modal list of detected legacy files. Returns the chosen stem."""
    cands = candidate_files(line_root, known_case_names)
    if not cands:
        messagebox.showinfo(
            "Add existing case",
            "No unregistered case files found in 00_CII.\n\n"
            "(Packed .C2 files and cases currently open in CAESAR are both "
            "detected. The MAIN file and cases already in the database are "
            "excluded.)",
            parent=parent)
        return None

    win = tk.Toplevel(parent)
    win.title("Add existing case")
    win.transient(parent); win.grab_set(); win.resizable(False, True)
    ttk.Label(win, text="Detected case files not yet in the database:",
              padding=PAD).pack(anchor="w")
    lb = tk.Listbox(win, height=min(14, max(4, len(cands))), width=48,
                    activestyle="dotbox")
    for s in cands:
        lb.insert("end", s)
    lb.selection_set(0)
    lb.pack(fill="both", expand=True, padx=PAD)
    chosen: List[Optional[str]] = [None]

    def ok(*_):
        sel = lb.curselection()
        if sel:
            chosen[0] = cands[sel[0]]
        win.destroy()

    bar = ttk.Frame(win, padding=PAD); bar.pack(fill="x")
    ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right")
    ttk.Button(bar, text="Next >", command=ok).pack(side="right", padx=PAD)
    lb.bind("<Double-Button-1>", ok)
    lb.bind("<Return>", ok)
    lb.focus_set()
    win.wait_window()
    return chosen[0]


# --------------------------------------------------------------------------
# Case data dialog - fields mirror the sidecar schema
# --------------------------------------------------------------------------
class CaseMetaDialog(tk.Toplevel):
    """
    initial = {
        "line": str, "case_name": str, "disp_mm": float|None,
        "supports": [{"node": int}, ...],
        "lift_points": [{"node","support_node","distance_mm","disp_mm"}, ...]
    }
    .result is the completed dict (same shape, all values validated),
    or None if cancelled.
    """

    def __init__(self, parent, title: str, initial: Dict):
        super().__init__(parent)
        self.title(title)
        self.transient(parent); self.grab_set(); self.resizable(False, False)
        self.result: Optional[Dict] = None
        self._initial = initial
        self._lp_rows: List[Dict[str, tk.StringVar]] = []
        self._build()
        self.wait_window()

    # ------------------------------------------------------------------
    def _build(self):
        ini = self._initial
        frm = ttk.Frame(self, padding=PAD); frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=f"Line {ini['line']}    ·    case {ini['case_name']}",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0,
                                                      columnspan=2, sticky="w")

        ttk.Label(frm, text="Imposed lift (mm):").grid(row=1, column=0,
                                                       sticky="w", pady=(PAD, 2))
        self.v_disp = tk.StringVar(
            value="" if ini.get("disp_mm") is None else f"{ini['disp_mm']:g}")
        ttk.Entry(frm, textvariable=self.v_disp, width=10
                  ).grid(row=1, column=1, sticky="w", pady=(PAD, 2))

        ttk.Label(frm, text="Lifted support nodes\n(space separated):",
                  justify="left").grid(row=2, column=0, sticky="w", pady=2)
        self.v_sups = tk.StringVar(
            value=" ".join(str(s["node"]) for s in ini.get("supports", [])))
        ttk.Entry(frm, textvariable=self.v_sups, width=28
                  ).grid(row=2, column=1, sticky="w", pady=2)

        lpf = ttk.LabelFrame(frm, text="Lift points  (as the generator sidecar)",
                             padding=PAD)
        lpf.grid(row=3, column=0, columnspan=2, sticky="ew", pady=PAD)
        for c, t in enumerate(("Node", "Support node", "Distance mm",
                               "Lift mm (blank = case value)")):
            ttk.Label(lpf, text=t, font=("Segoe UI", 8, "bold")
                      ).grid(row=0, column=c, sticky="w", padx=3)
        self._lpf = lpf

        # When exactly one support is known, every lift point references it -
        # prefill the support-node column so only distances need typing.
        sole_support: Optional[int] = None
        sups0 = ini.get("supports") or []
        if len(sups0) == 1:
            sole_support = sups0[0]["node"]
        self._sole_support = sole_support

        rows = ini.get("lift_points") or [{}, {}]      # the outer pair
        for lp in rows:
            self._add_lp_row(lp)

        bar2 = ttk.Frame(frm); bar2.grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Button(bar2, text="Add lift point row",
                   command=lambda: self._add_lp_row({})).pack(side="left")
        ttk.Label(bar2, text="   blank rows are ignored",
                  foreground="#777", font=("Segoe UI", 8)).pack(side="left")

        bar = ttk.Frame(frm); bar.grid(row=5, column=0, columnspan=2,
                                       sticky="e", pady=(PAD, 0))
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="Save", command=self._ok
                   ).pack(side="right", padx=PAD)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())

    def _add_lp_row(self, lp: Dict):
        r = len(self._lp_rows) + 1
        sup_default = lp.get("support_node")
        if sup_default is None:
            sup_default = getattr(self, "_sole_support", None)
        row = {
            "node": tk.StringVar(value="" if lp.get("node") is None else str(lp["node"])),
            "support_node": tk.StringVar(
                value="" if sup_default is None else str(sup_default)),
            "distance_mm": tk.StringVar(
                value="" if lp.get("distance_mm") is None else f"{lp['distance_mm']:g}"),
            "disp_mm": tk.StringVar(
                value="" if lp.get("disp_mm") is None else f"{lp['disp_mm']:g}"),
        }
        widths = (9, 11, 11, 11)
        for c, key in enumerate(("node", "support_node", "distance_mm", "disp_mm")):
            e = ttk.Entry(self._lpf, textvariable=row[key], width=widths[c])
            e.grid(row=r, column=c, sticky="w", padx=3, pady=2)
            if r == 1 and c == 0:
                e.focus_set()
        self._lp_rows.append(row)

    # ------------------------------------------------------------------
    @staticmethod
    def _f(v: str) -> Optional[float]:
        v = v.strip().replace(",", ".")
        return float(v) if v else None

    @staticmethod
    def _i(v: str) -> Optional[int]:
        v = v.strip()
        return int(v) if v else None

    def _ok(self):
        ini = self._initial
        try:
            disp = self._f(self.v_disp.get())
            if disp is None or disp <= 0:
                raise ValueError("Imposed lift (mm) must be a positive number.")

            sup_tokens = [t for t in re.split(r"[,\s]+", self.v_sups.get().strip()) if t]
            supports = [{"node": int(t)} for t in sup_tokens]
            if not supports:
                raise ValueError("Enter at least one lifted support node.")

            lift_points = []
            for row in self._lp_rows:
                n = self._i(row["node"].get())
                if n is None:
                    continue                        # blank row
                lift_points.append({
                    "node": n,
                    "support_node": self._i(row["support_node"].get()),
                    "distance_mm": self._f(row["distance_mm"].get()) or 0.0,
                    "disp_mm": self._f(row["disp_mm"].get()) or disp,
                })
            if not lift_points:
                raise ValueError("Enter at least one lift point node.")

        except ValueError as ex:
            messagebox.showwarning("Case data", str(ex), parent=self)
            return

        self.result = {
            "schema": lift_meta.SCHEMA_VERSION,
            "line": ini["line"],
            "case_name": ini["case_name"],
            "disp_mm": disp,
            "supports": supports,
            "lift_points": lift_points,
        }
        self.destroy()
