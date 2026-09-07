"""
lift_case_builder.py

Orchestrator for the Full .C2 Lift Creation workflow.

Steps
-----
1. Resolve folder (from %V arg, or FolderSelectDialog)
2. Prompt for node count and node numbers
3. Prompt for per-node spacing and displacement (750/10 defaults)
4. Copy _MAIN.C2 → {prefix}_N10-N20.C2  (preserves load cases)
5. Launch iecho interactively; poll until {prefix}_N10-N20.CII appears;
   terminate iecho on completion or abort
6. Validate entered nodes against restraints found in the exported CII
7. Read, patch, write the .CII
8. Silent iecho: convert patched .CII → .C2 (overwrites step 4 copy)
9. Report result

The .C2 copy (step 4) is always preserved even if later steps fail.
Cancellation before step 4 leaves the filesystem untouched.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import List, Optional

import lift_meta

from iecho import launch_for_export, convert_cii_to_c2, find_iecho, cii_is_current
from neutral_reader import read_neutral_file, read_restrained_nodes
from neutral_patcher import patch_model
from ui_dialogs import (
    prompt_folder,
    prompt_nodes,
    prompt_lift_params,
    poll_for_cii,
    prompt_element_override,
    show_message,
    LiftParams,
)


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def _find_main_input(folder: Path) -> Optional[Path]:
    for f in folder.iterdir():
        if re.match(r'.+_MAIN\.C2$', f.name, re.IGNORECASE):
            return f
    for f in folder.iterdir():
        if re.match(r'.+_MAIN\._A$', f.name, re.IGNORECASE):
            return f
    return None


def _c2_ext(main_input: Path) -> str:
    return main_input.suffix


def _next_ln(folder: Path, prefix: str, ext: str) -> int:
    pattern = re.compile(
        re.escape(prefix) + r'_L(\d+)' + re.escape(ext) + '$', re.IGNORECASE)
    numbers = [int(m.group(1)) for f in folder.iterdir()
               if (m := pattern.match(f.name))]
    return max(numbers, default=0) + 1


def _build_new_name(prefix: str, nodes: List[str], folder: Path, ext: str) -> str:
    if nodes:
        node_str = "-".join(f"N{n}" for n in nodes)
        return f"{prefix}_{node_str}{ext}"
    return f"{prefix}_L{_next_ln(folder, prefix, ext)}{ext}"


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run(initial_folder: Optional[Path] = None) -> None:
    """
    Execute the full lift case creation workflow.

    initial_folder : from %V context menu arg, or None to prompt.
    """

    # ── Verify iecho is available before touching anything ───────────────────
    try:
        find_iecho()
    except FileNotFoundError as e:
        show_message("iecho not found", str(e), error=True)
        sys.exit(1)

    # ── Step 1: Resolve folder ────────────────────────────────────────────────
    # If a valid folder was passed from the context menu (%V) and it already
    # contains a _MAIN file, skip the confirmation dialog entirely.
    if initial_folder is not None and initial_folder.is_dir():
        candidate = _find_main_input(initial_folder)
        if candidate is not None:
            folder = initial_folder
        else:
            # Folder exists but has no _MAIN — show dialog so user can correct
            folder = prompt_folder(initial_folder)
            if folder is None:
                sys.exit(0)
    else:
        folder = prompt_folder(initial_folder)
        if folder is None:
            sys.exit(0)

    main_input = _find_main_input(folder)
    if main_input is None:
        show_message("Lift Creation",
                     f"No *_MAIN.C2 or *_MAIN._A file found in:\n{folder}",
                     error=True)
        sys.exit(1)

    prefix = re.sub(r'_MAIN\.(C2|_A)$', '', main_input.name, flags=re.IGNORECASE)
    ext    = _c2_ext(main_input)

    # ── Step 2: Prompt for lifted nodes ──────────────────────────────────────
    # Nothing has been written to disk yet — cancellation is clean.
    nodes = prompt_nodes(prefix)
    if nodes is None:
        sys.exit(0)

    # ── Step 3: Prompt for per-node parameters ────────────────────────────────
    params: Optional[LiftParams] = None
    if nodes:
        params = prompt_lift_params(prefix, nodes)
        if params is None:
            sys.exit(0)

    # ── Step 4: Copy _MAIN.C2 → new .C2 ─────────────────────────────────────
    # Copying the .C2 (not the .CII) preserves load cases.
    new_c2_name = _build_new_name(prefix, nodes, folder, ext)
    new_c2      = folder / new_c2_name

    if new_c2.exists():
        show_message("Lift Creation",
                     f"Target file already exists:\n{new_c2_name}\n\n"
                     f"No changes made.", error=True)
        sys.exit(1)

    shutil.copy2(main_input, new_c2)

    # Ln fallback — copy only, no patching
    if not nodes:
        show_message("Lift Creation", f"Created (copy only):\n{new_c2_name}")
        return

    # ── Step 5: Interactive iecho export → new .CII ──────────────────────────
    # We export from the NEW .C2 copy so the CII name matches the copy.
    # iecho is launched and the process handle is retained so the polling
    # dialog can terminate it once the file appears (or the user aborts).
    new_cii = new_c2.with_suffix(".CII")

    # A stale .CII from a previous run must not satisfy the wait condition.
    # Remove it before the user exports so the app only accepts a fresh file
    # generated from the current C2 copy.
    if new_cii.exists():
        try:
            new_cii.unlink()
        except OSError:
            pass
    reference_mtime = new_c2.stat().st_mtime

    proc = launch_for_export(new_c2)

    ready = poll_for_cii(
        cii_path=new_cii,
        reference_mtime=reference_mtime,
        c2_name=new_c2_name,
        proc=proc,
    )

    if not ready:
        show_message(
            "Lift Creation",
            f"CII export was not completed. Aborting.\n\n"
            f"Expected neutral file destination:\n  {new_cii}\n\n"
            f"The copied input file has been preserved:\n  {new_c2_name}",
            error=True,
        )
        sys.exit(1)

    # ── Step 6: Validate nodes against restraints in the exported CII ─────────
    # Now that we have the CII, check that every entered node is restrained.
    # This is done after export (not before) so no _MAIN side-effects occur.
    try:
        cii_lines = new_cii.read_text(
            encoding="utf-8", errors="replace").splitlines(keepends=True)
        restrained = read_restrained_nodes(cii_lines)
        not_restrained = [n for n in nodes if int(n) not in restrained]
        if not_restrained:
            bad   = ", ".join(f"N{n}" for n in not_restrained)
            all_r = ", ".join(str(n) for n in sorted(restrained))
            proceed = show_message(
                "Node Validation Warning",
                f"The following nodes have no restraint in {new_c2_name}:\n\n"
                f"  {bad}\n\n"
                f"Restrained nodes in this model:\n{all_r}\n\n"
                f"Proceed anyway?",
                warning_yesno=True,
            )
            if not proceed:
                sys.exit(0)
    except Exception:
        pass   # validation is best-effort; never block the workflow

    # ── Step 7: Read, patch, write .CII ──────────────────────────────────────
    try:
        model = read_neutral_file(new_cii)
    except Exception as e:
        show_message("Lift Creation",
                     f"Failed to read neutral file:\n{new_cii.name}\n\n{e}",
                     error=True)
        sys.exit(1)

    def _override_callback(**kwargs):
        return prompt_element_override(**kwargs)

    try:
        result = patch_model(
            model=model,
            lifted_nodes=[int(n) for n in nodes],
            node_params=params.nodes,
            on_override=_override_callback,
        )
    except Exception as e:
        show_message("Lift Creation",
                     f"Patching failed:\n{e}", error=True)
        sys.exit(1)

    new_cii.write_text("".join(result.modified_lines), encoding="utf-8")

    if result.warnings:
        show_message(
            "Lift Creation — Warnings",
            "The following warnings were raised during patching:\n\n" +
            "\n".join(f"• {w}" for w in result.warnings),
        )

    # ── Step 8: Silent .CII → .C2 (overwrites the step 4 copy) ──────────────
    try:
        output_c2 = convert_cii_to_c2(new_cii)
    except Exception as e:
        show_message(
            "Conversion Failed",
            f"Patched CII written successfully:\n  {new_cii.name}\n\n"
            f"However, silent conversion to C2 failed:\n{e}\n\n"
            f"You can convert manually using iecho.\n"
            f"Note: {new_c2_name} still reflects the unpatched model.",
            error=True,
        )
        sys.exit(1)

    # ── Step 8b: Write documenter sidecar (best-effort) ──────────────────────
    # Feeds the Lift Mark-up Documenter. Never allowed to break lift creation.
    try:
        _write_documenter_sidecar(new_cii, nodes, params, result)
    except Exception as e:
        show_message(
            "Lift Creation — Note",
            f"Lift case created, but the documenter sidecar was not written:\n{e}",
        )

    # ── Step 9: Done ──────────────────────────────────────────────────────────
    disp_summary = (
        f"\nNew displacement nodes: {', '.join(str(n) for n in result.new_disp_nodes)}"
        if result.new_disp_nodes else ""
    )
    show_message(
        "Lift Creation Complete",
        f"Created:\n"
        f"  {new_c2_name}\n"
        f"  {new_cii.name}\n"
        f"{disp_summary}",
    )

# ---------------------------------------------------------------------------
# Documenter handshake
# ---------------------------------------------------------------------------

def _write_documenter_sidecar(new_cii: Path, nodes, params, result) -> None:
    """
    Emit <case>_liftmeta.json next to the generated .CII for the Lift Mark-up
    Documenter. Uses the support<->lift<->distance pairing captured by the
    patcher (PatchResult.lift_points).

    Line number = the job folder name (folder the tool ran in), no size.
    """
    import line_layout as LL

    case_name = new_cii.stem                                # e.g. "46-P-1234_L3"

    # new_cii lives in <line>/00_CII. Resolve the line root and target the
    # hidden sidecar folder <line>/00_CII/.liftdoc.
    line_root = LL.resolve_line_root(str(new_cii.parent))
    if line_root is None:
        # fall back to the .CII's own folder if the structure isn't present
        out_dir = str(new_cii.parent)
        line = os.path.basename(out_dir.rstrip("\\/"))
    else:
        out_dir = LL.sidecar_dir(line_root, create=True)    # makes + hides .liftdoc
        line = LL.line_no_of(line_root)

    # nominal displacement for the note text: mode of per-node values, else default
    if getattr(params, "nodes", None):
        disp_vals = [np_.displacement_mm for np_ in params.nodes]
        disp_nominal = max(set(disp_vals), key=disp_vals.count) if disp_vals else 10.0
    else:
        disp_nominal = 10.0

    lift_points = [
        {
            "node":         lp.lift_node,
            "support_node": (lp.support_node if lp.support_node not in (None, -1) else None),
            "distance_mm":  lp.distance_mm,
            "disp_mm":      lp.displacement_mm,
        }
        for lp in getattr(result, "lift_points", [])
    ]

    lift_meta.write_sidecar(
        out_dir=out_dir,
        line=line,
        case_name=case_name,
        disp_mm=disp_nominal,
        supports=[int(n) for n in nodes],
        lift_points=lift_points,
    )
