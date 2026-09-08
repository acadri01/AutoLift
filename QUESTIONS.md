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

## Assumptions made — Phase 0 packaging (2026-09-07)
- Kept the Documenter's fallback verb behaviour: no mode flag / a bare
  folder argument falls back to `lift_documenter.main()`, matching today's
  plain `lift_documenter.exe "%V"` registration. Only an explicit
  `--creator` flag routes to the Creator.
- `copy_main_cii.py` (a standalone side-tool, not part of the main
  workflow) was carried into `src/creator/` but is not wired into
  `launcher.py` or given a context-menu verb — the user asked for "the two"
  verbs (Creator + Documenter), and this tool wasn't one of them. It's
  present in source but currently unreachable from the built exe. Flag if
  it should get its own `--copy-main-cii` mode.
- Verb labels ("Full .C2 Lift Creation", "Open Lift Mark-up Documenter")
  reuse the Creator's exact original label from its own code comment; the
  Documenter's label wasn't given verbatim in its source (the comment only
  says "Registry (folder background): lift_documenter.exe \"%V\"" with no
  label text), so one was written to match the existing style. Cosmetic,
  reversible.
- Context-menu command registration re-checks and rewrites (if stale) on
  *every* launch rather than only once — cheap, and means moving the exe
  self-heals the menu, but it does mean a HKCU registry write on every run.

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
