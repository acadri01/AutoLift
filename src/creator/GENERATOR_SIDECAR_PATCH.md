# Lift Generator → Documenter Handshake — VERIFIED against your actual code

My earlier guide was written from chat summaries and got the internals wrong.
This version is built and tested against the files you uploaded
(neutral_patcher.py, lift_case_builder.py, ui_dialogs.py). Two patched files
are provided ready to drop in:

* neutral_patcher_PATCHED.py
* lift_case_builder_PATCHED.py

plus lift_meta.py (copy into the generator folder).

--------------------------------------------------------------------------
## What I got wrong before, and the correction
--------------------------------------------------------------------------

1. SplitSpec ALREADY carries the pairing. I feared the support<->lift link
   was discarded and proposed deriving it from n_from/n_to. Not needed —
   SplitSpec(element, lifted_node, new_node, spacing_mm, side) already holds
   it. lifted_node is the support; new_node is the lift point; spacing_mm is
   the along-pipe distance. Exact, no geometry.

2. Only the OUTER elements are split. _determine_splits sets
   do_upstream = is_first, do_downstream = is_last. So for supports
   [340, 430] you get exactly TWO lift points — one upstream of the first
   support, one downstream of the last — not two per support. This matches
   your original example sheet (supports 340 & 430 -> lifts 325 & 475, the
   outer pair). Inner supports in a 3+ run get no lift point of their own;
   they are bracketed by the outer pair. The documenter's "supports" list
   still records every lifted support; "lift_points" records the two
   imposed-displacement nodes.

Verified with your example's numbers:

    SplitSpec: lift_node=335  support=340  spacing=900  side=upstream
    SplitSpec: lift_node=435  support=430  spacing=750  side=downstream

--------------------------------------------------------------------------
## The changes (already applied in the PATCHED files)
--------------------------------------------------------------------------

### neutral_patcher.py — 5 small edits

1. New LiftPointInfo dataclass (lift_node, support_node, distance_mm,
   displacement_mm).
2. PatchResult gains  lift_points: List[LiftPointInfo].
3. lift_points: List[LiftPointInfo] = []  declared beside new_disp_nodes.
4. Inside the reverse-order split loop, alongside
   new_disp_nodes.append(sp.new_node):

       lift_points.append(LiftPointInfo(
           lift_node=sp.new_node,
           support_node=sp.lifted_node,
           distance_mm=sp.spacing_mm,
           displacement_mm=sp_disp_mm,
       ))

   (sp_disp_mm is already computed one line above for the DISPLMNT record.)
5. lift_points.reverse() next to the existing new_disp_nodes.reverse(), and
   lift_points=lift_points added to the returned PatchResult.

The three early-return PatchResult(...) paths (no splits / no blocks) are
untouched — lift_points defaults to empty, which is correct.

### lift_case_builder.py — 2 edits

1. Add  import os  and  import lift_meta  at the top.
2. New Step 8b, right before Step 9's show_message, calling a best-effort
   helper _write_documenter_sidecar(new_cii, nodes, params, result). If it
   throws, the user sees a note but the lift case is unaffected.

The helper derives:
* line      = job folder name (the .CII's parent), no size — matches the
  documenter's folder-name convention.
* case_name = .CII stem (e.g. 46-P-1234_L3).
* disp_mm   = the most common per-node displacement (fallback 10.0), used
  only for the note text; each lift point still carries its own disp_mm.
* supports  = the restraint nodes you entered (nodes).
* lift_points = from PatchResult.lift_points.

--------------------------------------------------------------------------
## Deploy
--------------------------------------------------------------------------

1. Replace your two files with the PATCHED versions (or apply the 7 edits
   above by hand — they're small).
2. Copy lift_meta.py into the generator folder
   (LiftingAutomations/LiftingFileCreator/).
3. Add lift_meta.py to create_lift_case.spec if you bundle by explicit
   list; PyInstaller will otherwise follow the  import lift_meta.
4. Rebuild the generator exe as usual.

No change to ui_dialogs.py, neutral_reader.py, neutral_writer.py, iecho.py,
config.py, or the entry point.

--------------------------------------------------------------------------
## Verified end-to-end (this session, against your code)
--------------------------------------------------------------------------

* _determine_splits -> correct SplitSpec pairing for [340, 430].
* Patched PatchResult exposes lift_points; LiftPointInfo present.
* _write_documenter_sidecar writes 46-P-1234_L3_liftmeta.json.
* Documenter's lift_meta.read_sidecar reads it back:
  supports [340, 430], lift_points (335<->340 @900, 435<->430 @750).
* support_node = None (unpaired lift) round-trips.

What is NOT tested here: the full patch_model line-surgery, because that
needs a real .CII (none was provided). The lift_points capture sits in the
same loop as the already-working new_disp_nodes/disp_records logic and
copies fields off the same sp object, so it runs whenever a split is
applied — but confirm on a real model during your first generator run by
checking the emitted JSON matches the case you built.

--------------------------------------------------------------------------
## One thing to confirm on first real run
--------------------------------------------------------------------------

For a short-element case that triggers _handle_short (the override path),
SplitSpec is still returned with a valid new_node, lifted_node, and a
possibly-reduced spacing_mm (e.g. min(spacing_mm, L*0.5)). In that case
distance_mm in the sidecar reflects the ACTUAL spacing used, not the
nominal — which is what you want on the mark-up. Just be aware the
documented distance may differ from the 750/900 you typed if an override
shortened it.
