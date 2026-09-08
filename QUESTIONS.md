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

## Assumptions made — SPEC.md / README.md / TESTING.md (2026-09-08)
- Dropped the template's "tests pass; app runs from a clean checkout via
  setup.sh" acceptance-criteria line entirely rather than adapting it —
  there's no setup.sh or CI in this repo, and none is realistic for a
  Windows-only, CAESAR-II-dependent Tkinter app. TESTING.md's manual
  tutorial is the substitute verification path. Reversible/cosmetic if a
  real automated check is ever wanted.
- TESTING.md's build/run instructions are written correctly against the
  actual `autolift.spec`/`requirements.txt`, but the literal console output
  shown is described functionally, not copied from a real run — this dev
  session is Linux and cannot execute the Windows build. Flagged explicitly
  in TESTING.md itself rather than presented as verified.
- README.md's workflow section presents the CAESAR-run step (RUN_PENDING)
  as "external, user-driven" without implying any detection exists yet —
  matches SPEC.md Milestone 6 being unbuilt.

## Assumptions made — context menu, case archive, rigid/bend logic (2026-09-08)
- **Spacing is measured cumulatively from the support node, across every
  skipped rigid/reducer/expansion-joint element** — not reset to "distance
  from wherever the first plain pipe element happens to start." This
  follows directly from `config.py`'s own docstring ("Distance from
  restrained node to new displacement BC node"), and was judged
  low-risk/reversible enough to proceed on rather than block on, but it's
  the single most important behavioural assumption in the new patcher logic
  — flag it explicitly if a real CAESAR check shows the placement should be
  measured differently.
- **Bend clearance shortfall auto-clamps and warns; it does NOT open the
  existing `ElementOverrideDialog`.** The plain "element shorter than
  requested spacing" case (no bend involved) still goes through that
  dialog, unchanged. Reasoning: a bend-clearance shortfall has one
  mechanically correct fix (shrink spacing to the available tangent-clear
  length, or walk past if that's zero) — there's no "which element did you
  actually mean" ambiguity for the dialog to resolve, unlike the pre-
  existing short-element case.
- **A SIF/tee pointer warns but never blocks or skips** — matches the
  literal instruction ("there should be a warning"), not treated as a
  reason to walk further like rigid/reducer/expansion-joint.
- **`copy_main_cii.py`** still has no context-menu verb (see the Phase-0
  entry above) — untouched by this round.
- Real `.cii` sample files used to verify the rigid/bend logic (from
  `acadri01/Conduit`'s `fixtures/real-samples/`) were **not** copied into
  this repo — only the vendor PDF reference material was, per the explicit
  instruction to exclude Conduit's `pipe-stress-engineering/` folder and
  the general instruction to only copy the `reference/` folder. If AutoLift
  ever wants its own fixture-backed automated tests for `neutral_patcher.py`
  (flagged as valuable, not yet built — see TESTING.md's developer
  reference section), sourcing/licensing a sample file for AutoLift's own
  use would need a separate decision, not assumed here.

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
