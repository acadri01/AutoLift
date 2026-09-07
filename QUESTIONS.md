where Claude parks non-blocking questions + logs assumptions

## Assumptions made (decide-and-proceed, logged not blocked on)
- `neutral_patcher.py`'s existing `from ui_dialogs import NodeLiftParams`
  import is left as-is in the merge (drags in tkinter at import time). No
  headless/CLI mode is in scope, so decoupling it was judged not worth the
  risk of touching validated CAESAR-format-sensitive code for no behavioural
  gain. Reversible later if a headless mode is ever wanted.
- `show_message()` in `ui_dialogs.py` (native `MessageBoxW`) is kept as-is
  in the Toplevel refactor — it's already parent-agnostic and needs no
  change to work from within the merged single-window app.
- Registry rework targets HKCU only (per user decision) — no HKLM/elevated
  fallback path is being built unless later requested.

## Open, non-blocking (need input before the relevant build step, not now)
- RUN_PENDING → FORCES_READ completion detection: HANDOFF.md referenced an
  existing "C2Watchdog" `.c2db`-mtime-watch pattern that does not appear in
  either provided codebase. Currently planned as new work (step 7 of the
  build sequence in MERGE_PLAN.md). If a C2Watchdog module exists elsewhere,
  point Claude at it before that step starts so it isn't rebuilt from
  scratch.
- First-run DB discovery on a fresh machine: the plan assumes it should
  "find and reuse the existing lift_doc_tool.cfg next to wherever the
  previous exes were run from, if discoverable." The exact discovery
  heuristic (where to look, what counts as "discoverable") isn't specified
  yet and will need a concrete answer when zero-touch first-run (build step
  6) is implemented.
