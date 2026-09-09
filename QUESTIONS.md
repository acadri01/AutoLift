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
- **Superseded 2026-09-09 (see the entry below): bend clearance shortfall
  no longer auto-clamps.** This originally said a bend-clearance shortfall
  would shrink spacing to what's tangent-clear (or walk past only if that
  left zero usable length) without opening `ElementOverrideDialog`, while
  a plain too-short element (no bend) still went through that dialog. Per
  a direct instruction, that same-element clamp is gone: ANY shortfall —
  too-short, bend-adjacent, or both — now walks further out instead,
  and the dialog is reached only once the whole pipe run is exhausted.
  Left here (not deleted) so the reasoning trail for why a dialog was
  ever in the loop at all stays visible.
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

## Assumptions made — generalized walk-past-insufficiency (2026-09-09)
- **Direct instruction, not an assumption**, but logging the implementation
  choice: "insufficient" is now ONE unified concept in
  `_walk_to_flexible_element` (`if remaining > usable: skip`) covering all
  four reasons an element can't take the placement — rigid, reducer,
  expansion joint, and now also plain-too-short and bend-shortfall. Judged
  low-risk/reversible to implement as a single check rather than keeping
  the reasons as separate code paths that happen to behave the same, since
  that's less likely to drift out of sync if one reason's handling changes
  later.
- **`_resolve_split`'s fallback (override dialog / headless
  warn-and-place) now always pre-fills with the ORIGINAL immediate
  neighbour of the lifted node**, not wherever the walk happened to stop
  before giving up. Reasoning: it's the most conservative, nearest-to-
  support default, and matches what the dialog showed before this walk
  logic existed at all — an engineer overriding by hand is most likely
  thinking about the element right next to the support, not one several
  hops out that the walk rejected.

## Assumptions made — Milestone 2, tool_discovery.py (2026-09-09)
- **Only iecho.exe resolution was actually generalized into
  `tool_discovery.py`.** SPEC.md's milestone 2 wording also names a
  "CAESAR input-GUI exe" and a "CAESAR data root" to resolve, but nothing
  in this codebase drives either today — `os.startfile()` in `line_ui.py`
  just opens a `.C2` with whatever CAESAR II's own installer already
  associated it with; no path lookup is needed for that to work. Building
  a resolution scheme for two paths with no real caller to validate it
  against risked guessing wrong (which directory layout? cached how?
  probed how?) for no present benefit, so it's deferred rather than
  invented. `tool_discovery.py`'s module docstring explains this. Moved to
  "Open, non-blocking" below since it isn't blocking any current
  milestone — flag it again once a concrete feature (e.g. an "open input
  file in CAESAR II" button, or a data-root-relative file browser) needs
  one of these paths, and I'll design its resolution against that real
  need instead of a guess.
- **`probe_capabilities()` gates the Creator's existing startup check**,
  replacing the direct `find_iecho()` try/except that was already there
  in `lift_case_builder.run()` — same user-visible outcome (same error
  message text, same `show_message` + `sys.exit(1)`), just routed through
  one shared capability-probe pattern so future entry points (e.g.
  milestone 4's single-window "Create lift case..." button) can reuse
  `report.iecho_available` to grey out/hide the action instead of letting
  it fail after the user has already started.
- `iecho.py` keeps re-exporting `find_iecho` (`from tool_discovery import
  find_iecho`) so every existing `from iecho import ... find_iecho ...`
  caller works unchanged — didn't touch call sites beyond
  `lift_case_builder.py`'s startup gate, which needed the richer
  `CapabilityReport` instead of a bare exception.

## Assumptions made — Milestone 3, run() return-value contract (2026-09-09)
- **`run()`'s new return contract is just `bool`** (True = done or cleanly
  cancelled, False = stopped on error) rather than something richer (an
  enum, a result object with the created file paths, etc.). Every path
  already communicates the actual outcome to the user via `show_message`
  before returning, and there's no current caller (Milestone 4's
  single-window integration hasn't been built yet) that needs more detail
  than "did it finish". Reversible/low-risk — richer if a real caller
  needs it once Milestone 4 starts.
- **Cancelling out of the "nodes have no restraint, proceed anyway?"
  warning now returns True (not False)** — matches the original
  `sys.exit(0)` it replaced (the engineer chose not to proceed; that's a
  clean stop, not an error), consistent with every other cancel path.

## Open, non-blocking (need input before the relevant build step, not now)
- **CAESAR input-GUI exe / CAESAR data root resolution** (see the
  Milestone 2 assumption above) — SPEC.md's milestone 2 wording names
  these, but no current feature drives either, so `tool_discovery.py` only
  resolves iecho.exe for now. Needs a concrete consuming feature before a
  resolution scheme for these two is worth designing.
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
