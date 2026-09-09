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

## Assumptions made — Documenter bug reports (2026-09-09)
- **Natural-sort fix scoped to `cases_for_line` only.** `lines_for_wo` and
  `wos()` sort plain-alphabetically the same way `cases_for_line` used to,
  so the identical "N1000 before N200"-style bug could theoretically apply
  to line numbers or WO numbers too. Not reported, and (unlike cases)
  neither has a manual-reorder UI (`move_line`/`move_wo` don't exist) to
  interact with, so left untouched to keep this fix scoped to what was
  actually reported. Moved to "Open, non-blocking" below - fix the same
  way (`_natural_key` already exists and is reusable) if it's ever
  reported as an issue.
- **Drag-and-drop keeps the Move up/down buttons rather than replacing
  them.** The user asked to prefer dragging over the buttons, not
  necessarily to remove the buttons - keeping both is strictly additive
  and costs nothing, and some users/situations (precise single-step move,
  no mouse) may still prefer them.
- **The phantom-work-order fix does not touch the user's existing live
  database.** The two bad "AutoLift"/"Lifting_Calcs" entries it already
  created are still there - only the Database admin panel (already built,
  Advanced menu) can remove them, from the user's own machine. Flagged in
  TESTING.md rather than attempting anything from this session (no access
  to that database).
- **`DocumenterApp`'s new `("root",)` focus mode reuses the existing
  `_show_blank("Select a work order.")` path** (same one already used when
  a Refresh loses the previous selection) rather than adding new UI/copy
  for "nothing was recognised at launch" - one less state for a user to
  learn, and it was already the right message for "you're at the root,
  pick something."

## Stop-and-ask (resolved 2026-09-09 - user confirmed, fix implemented)
- **RESOLVED**: user replied "You may implement this izup to determine
  whether a vertical section is determined by a y or z section" - read as
  approval to apply the same IZUP-based axis selection to the displacement
  DOF, not just the element-skip check. Implemented: `_displ_dof_index(izup)`
  (DY index 13 for IZUP=0, DZ index 14 for IZUP=1),
  `_build_displmnt_record()` takes an `izup` parameter (default 0,
  backward compatible), `patch_model` passes the same `izup` it already
  computes for the element-skip logic. Verified: 5 new pure-function
  checks (both axes, default-arg backward compat) plus a real round-trip
  against `44002.cii` (IZUP=1) confirming the written DISPLMNT record's
  10mm value lands at DOF index 14 (DZ of vector 3), not 13 (DY) -
  by directly re-parsing the patched file's own bytes, not just trusting
  the function's return value. Original question preserved below for the
  record.
- **Is displacement always applied along the wrong axis for a Z-vertical
  (IZUP=1) file?** While adding the vertical-component element-skip rule
  (see above), found that `neutral_patcher.py`'s displacement application
  is unconditionally hardcoded to global **DY** (`DISP_DOF_INDEX = 13` in
  `_build_displmnt_record` - "DY of vector 3") regardless of the file's
  own IZUP flag. CAESAR II lets a model use either global -Y or global -Z
  as vertical, and this matters here: `44002.cii` (the real sample used
  for all the bend/rigid verification so far in this project) is IZUP=1
  (Z vertical), not the more common IZUP=0 (Y vertical). If a "lift" is
  meant to simulate an imposed vertical displacement, applying it to DY on
  a Z-vertical file would be pushing the pipe sideways, not up - the
  generated lift case's forces/results could be physically wrong for
  every Z-up job, silently.
  - This is **pre-existing behaviour from the original, unmodified
    LiftNeutralFileModifier tool** (Phase 0 carried it over byte-for-byte;
    nothing in this project has touched `DISP_DOF_INDEX` before now) - not
    something introduced by any change in this PR.
  - Not fixed here: this is a change to the tool's actual physical
    output, not an internal refactor, so it's exactly the kind of
    "genuine requirement ambiguity / correctness question with materially
    different results" CLAUDE.md says to stop and ask about, not decide
    unilaterally - especially since I can't verify the right answer by
    reading the neutral file format alone (whether CAESAR's own DOF
    numbering for DY/DZ swaps meaning under IZUP=1, or whether "global Y"
    always literally means the Y axis regardless of which one is
    "vertical", is the kind of thing that needs either your own domain
    knowledge or a real CAESAR II round-trip test to confirm either way).
  - **If you confirm this is real**: the concrete next step is to make
    `_build_displmnt_record`'s `DISP_DOF_INDEX` selection depend on this
    file's IZUP (already parsed via `_read_izup`, exported from
    `neutral_patcher.py`) - DY's index (13) for IZUP=0, DZ's index
    (`(3-1)*6 + 2 = 14`, following the same vector-3 pattern) for IZUP=1 -
    threaded into `patch_model` the same way `izup` already is for the
    element-skip logic. Small, mechanical change once confirmed; not
    attempted here because the *direction* of the fix depends on an
    engineering fact I don't have independent means to verify.
  - **If you tell me this is a non-issue** (e.g. CAESAR's neutral-file DOF
    slots are NOT axis-relative to IZUP, and "DY" always means the
    literal global Y regardless of which axis is vertical): no code
    change needed, and this can be logged as a resolved non-issue instead.

## Open, non-blocking (need input before the relevant build step, not now)
- **Natural-sort for `lines_for_wo`/`wos()`** (see the assumption above) -
  not reported, no manual-reorder UI exists for either yet, so left as
  plain alphabetical. Revisit if line/WO numbering ever produces the same
  kind of confusing order a user would notice.
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
