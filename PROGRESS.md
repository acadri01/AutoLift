running status log Claude appends to (skim this from mobile)

- 2026-09-07: Mapped both source trees (LiftNeutralFileModifier,
  MarkUpGen) module-by-module against HANDOFF.md's proposal; confirmed the
  real connection today is a filesystem sidecar handshake
  (`_liftmeta.json` under `00_CII/.liftdoc`), not any live process link.
- 2026-09-07: Walked the workflow re-design with the user; converged on
  final architecture and wrote MERGE_PLAN.md (dropped RESTRAINTS_TAGGED as
  a separate stage, full in-process refactor of the Creator into the
  merged app, DB/install location preserved as-is, HKCU context-menu
  registration). Ready to start Build sequencing step 1.
- 2026-09-07: User descoped to packaging-only: bundle both programs into
  one distributable exe with self-installed context menus, zero behaviour
  change, no GUI refactor. Marked the fuller merge plan PAUSED (kept in
  MERGE_PLAN.md as Phase 1+) and built Phase 0 instead: both trees copied
  unmodified into `src/creator/` + `src/documenter/`, shared
  `lift_meta.py`/`line_layout.py` (verified byte-identical) deduplicated
  into `src/shared/`, new `src/launcher.py` (argv-dispatch to each
  program's untouched `main()`, sys.path wiring only) and
  `src/install_context_menu.py` (HKCU self-install of both verbs, idempotent),
  one combined `autolift.spec` + root `requirements.txt`. All files
  py_compile-clean. `lift_doc_tool.cfg` deliberately excluded (runtime
  state with a real deployed path, not source).
- 2026-09-07: Could not build or run the actual .exe / test the registry
  install or either GUI in this session — this dev environment is Linux,
  and both programs are Windows-native (win32com, ctypes.windll, winreg,
  tkinter GUIs). `pyinstaller autolift.spec` and a smoke test of both
  context-menu verbs need to happen on a Windows machine.
- 2026-09-08: PR #1 (Phase 0 packaging) merged by the user via GitHub
  comment ("This looks good. Proceed"). Restarted this branch from the
  merged main per convention.
- 2026-09-08: Filled in SPEC.md collaboratively. Confirmed with the user
  that the support-placement-automation language that had appeared in
  CLAUDE.md was erroneous boilerplate (since removed by the user) — not a
  real requirement, so it's explicitly OUT of scope in SPEC.md. Milestone
  list (SPEC.md's "## Milestones") is Phase 0 (done) followed by Phase 1
  broken into 5 smaller milestones (tool_discovery, in-process Creator
  refactor, single-window integration, zero-touch first-run polish,
  RUN_PENDING detection) per the user's explicit request to split it up
  rather than one big "Phase 1" entry. MERGE_PLAN.md's "Phase 1+" section
  un-paused and pointed at SPEC.md as the authoritative ordering.
- 2026-09-08: Wrote README.md (workflow section is the centrepiece, per
  the user's request) and TESTING.md (tutorial-first, per CLAUDE.md's
  mandate). Both are honest about what's actually been verified in this
  Linux dev session (py_compile only) versus what still needs a real
  Windows/CAESAR II run — TESTING.md's "Test this now" section asks for
  exactly that.
- 2026-09-08: User confirmed Phase 0 (build + both context-menu verbs)
  works on a real Windows machine.
- 2026-09-08: Cloned acadri01/Conduit (read-only, same user's separate
  clean-room CAESAR II tool) to pull reference material. Copied
  `reference/*.pdf` (vendor CAESAR II docs) + a rewritten README into
  AutoLift's own new `reference/` folder, deliberately excluding Conduit's
  `pipe-stress-engineering/` subfolder per direct instruction. Conduit's
  `docs/neutral-file/WALKTHROUGH.md` and its `fixtures/real-samples/*.cii`
  (real CAESAR files, not copied into AutoLift) supplied byte-level
  ground truth for the `#$ BEND` record layout used below.
- 2026-09-08: Three feature requests implemented:
  1. **Context menu grouped under one "AutoLift" submenu.** Rewrote
     `install_context_menu.py` to nest both verbs under a single cascading
     parent entry (`SubCommands=""` + nested `shell` key, standard Explorer
     convention) instead of two flat top-level items, and to clean up the
     old flat keys on next launch so an upgrade doesn't leave duplicates.
  2. **Archive/delete a lift case.** Added `archived`/`archived_at` columns
     to `lift_cases` (mirrors the existing `lines`/`work_orders` pattern),
     `archive_case`/`restore_case`/`archived_cases`/`purge_case` to
     `lift_db.py`, an "Archive case" button in the case detail view and a
     tree right-click "Archive case" entry, a third "Archived lift cases"
     pane + restore button in the Archive browser, and cases nested under
     lines (with permanent delete) in the Database admin panel.
  3. **Rigid/reducer/expansion-joint-aware, bend-clearance-aware lift-point
     placement** — the significant one. `neutral_patcher.py`'s element
     selection now walks past a rigid element, reducer, or expansion joint
     next to a support/lift node (none of which can carry an imposed
     displacement) to find the next plain pipe element, preserving the
     configured spacing as a distance from the support node across every
     skipped hop; and if the chosen element's far node is a bend corner,
     computes that bend's minimum required tangent length
     (`T = R * tan(deflection/2)`) from the ADJACENT ELEMENTS' OWN GEOMETRY
     (unit-vector dot product), not the `#$ BEND` record's angle fields —
     confirmed via Conduit's own real-sample cross-check that those fields
     aren't reliably understood — and shrinks the placement spacing to
     leave that tangent length clear, or walks past the element entirely if
     the bend would consume it. A SIF/tee pointer on the chosen element is
     warned about, not skipped past. IEL pointer indices (bend=2, rigid=3,
     expjt=4, SIF/intersection=12, reducer=14) and the `#$ BEND` record's
     3-line/14-value layout were verified two ways: against
     `reference/NeutralFile-v15.pdf`'s own "IEL array" description, and
     directly against real `#$ ELEMENTS`/`#$ BEND` bytes in Conduit's
     `fixtures/real-samples/44002.cii`. The plain "too-short" case (no
     rigid/bend involved) still routes through the existing
     `ElementOverrideDialog` path unchanged — only genuinely new, mechanical
     situations (skip, bend clamp) get the new auto-handling.
- 2026-09-08: Verified the new patcher logic three ways before considering
  it done enough to hand off: (1) pure unit checks of the angle/tangent
  geometry math (straight/45°/90°/180° cases, known R·tan(Δ/2) values);
  (2) a full `read_neutral_file` → `patch_model` → `read_neutral_file`
  round-trip against the real `44002.cii` sample, lifting a node bracketed
  by two rigid elements on one side and one on the other — correctly
  multi-hop-skipped all three, the patched file re-parsed cleanly, and
  `#$ CONTROL`'s `NUMELT` matched the new element count exactly;
  (3) the same round-trip lifting a node next to a real 90° bend (radius
  381 mm) — the computed deflection angle (90.0°, from the real element
  geometry) and tangent length (381 mm) matched hand-calculation exactly,
  and the spacing reduction (750→500 mm) was arithmetically exact. Cannot
  verify the ultimate real-world question — does the patched file still
  convert through `iecho.exe` and open correctly in CAESAR II — from this
  Linux session; asked for that in TESTING.md's "Test this now".
- 2026-09-08: Real-machine bug report: the grouped "AutoLift" context menu
  showed the parent entry but no children, even after an Explorer restart.
  Root cause (confirmed against Microsoft's own docs, not guessed): a
  cascade-menu parent key using `SubCommands` must NOT have a `(Default)`
  value set — the label must come from `MUIVerb` instead. My first version
  set `(Default)` and never set `MUIVerb`. Fixed in
  `install_context_menu.py`: parent label now written to `MUIVerb`, and
  `ensure_installed()` explicitly deletes any stray `(Default)` value on
  the parent key so an existing (already-broken) install self-heals too,
  not just fresh ones.
- 2026-09-09: Direct instruction (PR comment): when the requested spacing
  exceeds what's actually usable on the chosen upstream/downstream
  element — whether because the element itself is short, a bend eats into
  it, or both — `neutral_patcher.py` must keep walking further out and
  evaluate the next element, repeating until one is found that can hold
  the FULL requested spacing, rather than settling for less on a nearby
  insufficient one. This generalizes the existing rigid/reducer/expjt skip
  in `_walk_to_flexible_element`: it's now one unified
  `if remaining > usable: skip` check covering all four reasons an element
  can't take the placement, not two separate code paths. The old
  same-element "clamp spacing to what's available" behaviour for a
  bend shortfall is gone — replaced by walking past, matching what already
  happened for a fully bend-consumed element. `_resolve_split`'s
  `_handle_short`/override-dialog fallback is now reached only when the
  walk is fully exhausted (ran out of pipe) or loops, using the ORIGINAL
  immediate neighbour as its pre-filled default (unchanged from the
  dialog's original pre-walk behaviour). Re-verified: rewrote the pure-
  function test suite (10 checks, all passing) plus the two real-
  `44002.cii` round-trip cases from before — both now walk further than
  they used to (node 50's upstream side now also skips a 500mm too-short
  element it previously stopped at; node 35's bend case now walks past
  the bend-adjacent element entirely instead of clamping to 500mm), files
  still re-parse cleanly, `NUMELT` still matches.
- 2026-09-09: Started Milestone 2 (`tool_discovery.py`) — moved
  `iecho.find_iecho()`'s config→env→known-paths resolution logic into a
  new `src/creator/tool_discovery.py`, unchanged in order/behaviour/error
  message, plus a `probe_capabilities()` capability probe returning a
  `CapabilityReport` (iecho_available/iecho_path/reason) instead of
  raising. `iecho.py` now re-exports `find_iecho` from there so no other
  caller needed to change. `lift_case_builder.run()`'s existing "verify
  iecho before touching anything" startup check now goes through
  `probe_capabilities()` — same user-visible message and exit behaviour,
  but the gate is now a reusable pattern future entry points (e.g.
  milestone 4's in-Documenter "Create lift case...") can call before
  offering a CAESAR-driving action at all, not just catch its failure.
  Added `tool_discovery` to `autolift.spec`'s hiddenimports. Deliberately
  did NOT invent resolution for the "CAESAR input-GUI exe" / "CAESAR data
  root" SPEC.md also names for this milestone — nothing in the codebase
  drives either yet, so guessing a scheme had no real caller to validate
  against; logged as an open, non-blocking item in QUESTIONS.md instead.
  Verified: `py_compile` clean on all three touched files; a headless
  script exercising `tool_discovery.find_iecho()`/`probe_capabilities()`
  directly (env-var resolution, cache reset, unavailable→available
  transition) and `iecho.find_iecho()`'s re-export all pass; confirmed
  `lift_case_builder.py`'s full import chain still resolves cleanly
  (tkinter/win32 stubbed) after the `find_iecho` → `probe_capabilities`
  swap.
- 2026-09-09: Started Milestone 3's lower-risk half — converted
  `lift_case_builder.run()`'s every `sys.exit(0)`/`sys.exit(1)` call into
  `return True`/`return False` (True = completed or cleanly cancelled by
  the user, False = stopped on an error — both cases already show their
  own dialog, so the caller doesn't need the message repeated). `run()` no
  longer kills the host process, which is what makes it safe to call
  in-process later (Milestone 4). `create_lift_case.py`'s `main()` now
  translates that return value into `sys.exit(0 if ok else 1)` — preserves
  today's exact process-exit-code behaviour for the standalone exe/context
  menu invocation, just moved to the one place that still needs to exit
  the process. Removed the now-unused `import sys` from
  `lift_case_builder.py`. Deliberately did NOT touch `ui_dialogs.py`'s
  `tk.Tk()` → `tk.Toplevel(parent)` conversion in this pass — that's a
  6-class, 844-line GUI refactor I can't visually verify from this Linux
  session, and doing it without being able to see the actual dialogs run
  is a real regression risk; leaving it as the next Milestone-3 step
  rather than rushing a change I can't check. Verified: `py_compile`
  clean; headless checks (dialogs stubbed) of all three return-value
  paths — iecho-unavailable → False, folder-prompt-cancelled → True,
  full success (copy-only fallback) → True with the same message text as
  before.
- 2026-09-09: Real-machine testing feedback: bare `pyinstaller
  autolift.spec` (Step 3) doesn't reliably work — pip's console-script
  `pyinstaller.exe` lands in a `Scripts` folder that isn't always on
  `PATH` on Windows, so the command itself can go unrecognized even
  though the package installed fine. `python -m PyInstaller autolift.spec`
  works instead (asks the same Python you `pip install`'d into to run the
  module directly, no PATH dependency). TESTING.md's Step 3 and "Test this
  now" now lead with the `python -m PyInstaller` form.
- 2026-09-09: Three real-machine bug reports from the Documenter, fixed:
  1. **Case order was alphabetical, not numeric.** `lift_db.py`'s
     `cases_for_line` sorted `ORDER BY seq, case_name` - fine once
     `move_case` has been used (seq drives it), but the case_name tiebreak
     for untouched (seq=0) rows was a plain string sort, so "N1000" sorted
     before "N200" ('1' < '2' as characters). Added `_natural_key()` (splits
     on digit runs, compares them as ints) and re-sort in Python instead of
     relying on SQL's `ORDER BY ... case_name`; `move_case`'s existing
     manual-reorder behaviour is untouched (still takes priority once used).
     Scoped to `cases_for_line` only - `lines_for_wo`/`wos()` use the same
     plain alphabetical pattern and could have the identical latent bug,
     but weren't reported and have no seq-based manual-reorder UI to
     interact with, so left as-is; flagged in QUESTIONS.md.
  2. **Reordering via Move up/down was "click, wait for a full panel
     rebuild, click again" for a multi-step move** - user asked for
     drag-and-drop instead. Added `_bind_drag_reorder()` in `line_ui.py`
     (click-drag-release on the existing case/iso Listboxes - live reorder
     during drag with no DB write or rebuild, single persist + refresh on
     release) plus new `lift_db.py` methods `reorder_cases`/`reorder_isos`
     (set every row's seq to match a full given order in one transaction,
     refusing - no partial write - if the id set doesn't match the line's
     current cases/isos exactly). Move up/down buttons kept alongside drag,
     not removed.
  3. **Phantom "work order" created for non-job folders** - right-clicking
     the `AutoLift` install folder itself, or a container folder that just
     holds several real work orders (`Lifting_Calcs` in the report), showed
     up as bogus entries in the Work orders tree (screenshot confirmed both
     "AutoLift" and "Lifting_Calcs" listed alongside real WOs). Root cause:
     `lift_documenter.main()`'s fallback for `LL.classify(folder) ==
     "unknown"` called `db.get_or_create_wo(basename(folder), folder)` -
     writing a DB record for literally any folder that wasn't a recognised
     line or work order. Fixed by adding a `("root",)` focus mode to
     `DocumenterApp` (opens at the tree root, "Select a work order.", via
     the existing `_show_blank` path already used elsewhere - no new UI)
     and routing the "unknown" case there instead of creating a WO record.
     Confirmed via a synthetic folder tree that `LL.classify()` really does
     return "unknown" for both folder shapes from the report, and that real
     line/WO folders still classify correctly. **Does not retroactively
     clean up the two existing phantom entries in the user's live
     database** - those need deleting via the existing Database admin panel
     (Advanced menu); can't be done from this session. Flagged in
     TESTING.md's "Test this now".
  Verified: `py_compile` clean on all five touched files (`lift_db.py`,
  `line_ui.py`, `app_ui.py`, `lift_documenter.py`, plus re-checking
  `line_layout.py` unchanged); headless SQLite tests of natural-sort
  ordering, `reorder_cases`/`reorder_isos` (including the refuse-on-
  mismatch path), and `LL.classify()` against a synthetic
  `Lifting_Calcs/{AutoLift,WO.../line/00_CII}` tree; a standalone
  reimplementation of the drag-motion index bookkeeping against a fake
  Listbox stub (both drag-down and drag-up), since real Tkinter isn't
  available in this Linux session to exercise the actual bound handlers.
- 2026-09-09: Real-machine PR-comment report: an element with a vertical
  component (a riser) was being placed on instead of skipped, and a
  question about why the requested spacing seemed to shrink per hop.
  1. **Vertical-component skip.** `neutral_patcher.py`'s
     `_walk_to_flexible_element` now rejects any candidate element with a
     nonzero rise/drop along whichever axis is vertical, exactly like it
     already does for rigid/reducer/expjt elements - a lift point needs a
     horizontal run to sit on, not a riser. Which axis counts as vertical
     is NOT hardcoded: CAESAR II lets a model use either global -Y or
     global -Z as vertical (the `#$ CONTROL` section's IZUP flag), and
     real files use both - confirmed by checking Conduit's own real
     samples: `44002.cii` (the exact file used for all the earlier
     bend/rigid verification) is actually IZUP=1 (Z vertical), while
     `TESTv15.cii`/`NEWTEST.cii` are IZUP=0 (Y vertical). Added
     `_read_izup()` (byte-verified against all three real files) and
     `_vertical_component`/`_is_vertical`, threaded an `izup` parameter
     (default 0, backward compatible) through `_walk_to_flexible_element`
     -> `_resolve_split` -> `_determine_splits`, computed once in
     `patch_model` from the file being patched. IZUP's own documentation
     in reference/NeutralFile-v15.pdf is misleading on its own (the flag's
     description is crammed into the middle of an unrelated bullet, not
     given its own numbered item) - confirmed the real byte layout
     directly against three real sample files instead of trusting the
     prose alone.
  2. **"Requested spacing reduced per element" - clarified as intentional,
     not a bug.** This is the distance-from-support preservation the
     walk-past logic has had since the 2026-09-09 walk-past-insufficiency
     change: skipping a 65mm element on a 750mm request correctly leaves
     685mm (750-65) needed on the next one, so the total distance from the
     original support node still comes out to 750mm once a fit is found -
     confirmed against the user's own screenshot numbers (1450->1480
     skipped, 65mm long -> next ask correctly shown as 685mm). No code
     change; explained in the PR reply.
  **Separately flagged, NOT changed**: while tracing this, found that
  displacement application is unconditionally hardcoded to global DY
  (`DISP_DOF_INDEX`, `_build_displmnt_record`) regardless of IZUP - so for
  an IZUP=1 (Z-vertical) file, the "lift" displacement may be getting
  applied along the WRONG axis, a real engineering-correctness question
  about pre-existing (never modified by this project) behaviour. This
  wasn't part of what was asked, is a change to actual physical output
  (not internal refactor), and directly affects generated lift case
  results, so per CLAUDE.md this is a stop-and-ask item, not something to
  silently fix - logged in QUESTIONS.md and raised explicitly in the PR
  reply rather than touched.
  Verified: `py_compile` clean; `_read_izup` byte-checked against all
  three real sample files in Conduit's `fixtures/real-samples/`; 6 new
  synthetic pure-function checks (riser skip under IZUP=0, a dz-only jog
  correctly NOT flagged under IZUP=0 vs. correctly flagged under IZUP=1,
  default-izup backward compatibility) added to the running scratch test
  suite (16/16 passing including all prior checks, two of which needed
  their own fixtures fixed - an old test's "next" element was arbitrarily
  vertical and is now correctly caught by the new rule, a fixture
  limitation, not a code defect); a full `read_neutral_file` ->
  `patch_model` -> `read_neutral_file` round trip against the real,
  IZUP=1 `44002.cii`, lifting a node bracketed by two vertical (dz-only)
  runs and three rigid elements - correctly skipped all of them and
  landed on genuinely horizontal elements on both sides, patched file
  re-parses cleanly, NUMELT matches.
- 2026-09-09: Real-machine PR-comment report, with warning-dialog and
  isometric screenshots: "this caused a bend to break, exactly as we
  discussed it shouldn't." Root cause was a real, pre-existing
  architectural gap in `_walk_to_flexible_element` - not something
  introduced by the vertical-skip change, just newly exposed by it landing
  the walk in more real scenarios than before. The bend-clearance
  calculation only ever checked a bend at the FAR end of a candidate
  element (the corner being walked toward) - never at its NEAR end (the
  node the walk just arrived at, typically the far end of whatever was
  skipped the hop before). When the fallback "requested spacing exhausted,
  clamp to the start of this element" path fired, it clamped to distance
  0 unconditionally, even when that exact point (`node`) was itself a bend
  corner needing its own tangent clearance from that side - placing the
  displacement inside the bend's own tangent zone.
  Fixed by computing tangent clearance at BOTH ends of every candidate
  element: added `_bend_tangent_at_node()` (factored out of the existing
  far-node calculation, reused for both), giving `valid_min` (a near
  bend's own minimum clearance, 0 if none) and `valid_max` (unchanged -
  full length minus a far bend's tangent, if any). Three cases instead of
  two: `valid_min > valid_max` (bends at both ends, or one very tight one,
  leave no valid zone on the element at all - skip it entirely regardless
  of what was requested, new); `remaining > valid_max` (too far in for
  this element - walk further, same as before, just renamed from
  `usable`); `remaining < valid_min` (would land inside a near bend, or
  the whole element run was already used up by skips - clamp UP to
  `valid_min`, generalizing the old "clamp to 0" fallback, which was
  really just the `valid_min == 0` case all along). Warnings now name
  which end's bend is responsible when a near-clearance clamp fires,
  distinct from the old generic "entirely used up by skips" message
  (still used when there's no near bend involved).
  Verified: `py_compile` clean; re-ran the full scratch suite after fixing
  two OLD test fixtures whose "next" element happened to share a bend
  corner with the one being walked past (previously invisible to the near
  check, now correctly caught - confirmed via hand deflection/tangent
  calculation, not just re-asserted) - not a regression, the fix working
  as intended on cases the suite already had; added 2 new tests
  reproducing the exact reported scenario (support -> far-bend-too-short
  skip -> two vertical skips -> lands next to a shared bend corner ->
  correctly clamps to that bend's own 200mm tangent, not 0) and a
  combined-both-ends case (neither bend's tangent alone exceeds the
  element's length, but together they leave no valid zone - skipped
  regardless of how small the request is); all 20 checks passing. Re-ran
  the real IZUP=1 `44002.cii` round trip (node 35, same as the prior
  vertical-skip verification) - it turns out this exact file already has
  two of the affected real bend corners (nodes 30 and 80, radius 381mm,
  the same bends already used for earlier verification work): confirms
  the OLD code would have placed a displacement directly on those bend
  corners on a real file, and the fix now correctly clamps 381mm clear of
  each instead. File still re-parses cleanly, NUMELT matches.
- 2026-09-09: User answered the IZUP mechanism question, then approved
  the "Stop-and-ask" displacement-axis fix ("You may implement this izup
  to determine whether a vertical section is determined by a y or z
  section"). Implemented: `_displ_dof_index(izup)` picks DY's slot (index
  13) for IZUP=0 or DZ's slot (index 14) for IZUP=1 in the 54-value
  VECTOR-major DOF array; `_build_displmnt_record()` now takes an `izup`
  parameter (default 0, so any other caller is unaffected) instead of
  unconditionally writing `DISP_DOF_INDEX`; `patch_model` passes the same
  `izup` it already reads once per file for the element-skip logic.
  Also fixed a stale/contradictory docstring in `_build_displmnt_record`
  that described a "DOF-major" layout while the actual code (and its own
  inline comment) used VECTOR-major - noticed while adding the IZUP
  branch, harmless (docs-only) but confusing to leave next to new code.
  Marked QUESTIONS.md's "Stop-and-ask" entry resolved rather than
  deleting it, so the reasoning trail for why this was ever a stop-and-ask
  item (not something to have silently changed) stays visible.
  Verified: `py_compile` clean; 5 new pure-function checks in the scratch
  suite (`_displ_dof_index` for both IZUP values, `_build_displmnt_record`
  re-parsed back into its 54-value array to confirm exactly one non-FREE
  DOF at the expected index for each IZUP value, and that omitting `izup`
  still defaults to DY) - 25/25 checks passing; a real round trip against
  `44002.cii` (IZUP=1) - re-parsed the PATCHED file's own `#$ DISPLMNT`
  bytes directly (not just the function's return value) and confirmed the
  10mm displacement value lands at DOF index 14 (DZ of vector 3), with
  index 13 (DY) still FREE.
- 2026-09-14: Real-machine report (with a CAESAR "Between Element Nodes"
  measurement) surfaces a deeper issue than the previous two placement
  bugs: `_walk_to_flexible_element` has always measured "distance from
  support" as cumulative element-length subtraction, which only equals
  true straight-line distance when the walked path never changes
  direction. Now that walking through vertical risers and past bends is
  routine (per the vertical-skip and near-bend fixes), that assumption
  breaks down - in the reported case, a 750mm request produced a walked
  path length of 1509.7mm, a straight-line 3D distance of 1384.49mm, and a
  horizontal-plane distance of only 495.6mm, depending on which "distance
  from support" is meant. Verified the user's own arithmetic
  (sqrt(309.12^2+387.39^2) = 495.6, matching their report) and confirmed
  the three figures are all genuinely different (not a measurement error
  on their end). This is a requirement-definition question, not an
  implementation bug in settled behaviour, so per CLAUDE.md it's logged as
  a new "Stop-and-ask" in QUESTIONS.md with three concrete options put to
  the user, rather than guessed at - the placement algorithm has now had
  three rounds of user-reported issues and a wrong guess here would cost
  more time than asking once. No code changed.

- 2026-09-14: User confirmed a hybrid design ("This is perfect. Build this
  now.") for the "distance from support" Stop-and-ask: horizontal-plane
  distance (option B), with a fall-back to a from/to-node override dialog
  only for whichever side(s) genuinely can't reach it (option C, no more
  clamping), prompting only for the relevant side unless a single lifted
  node's upstream AND downstream are both exhausted at once. Implemented in
  `neutral_patcher.py`: `_horizontal_delta()` projects an element's own
  delta onto the two axes this file's IZUP flag doesn't mark vertical;
  `_walk_to_flexible_element` now tracks the walk's horizontal-plane
  position relative to the support and solves a quadratic in the
  along-element parameter for the point matching the requested distance,
  replacing the old `remaining -= length` running subtraction entirely -
  no clamping anywhere; an element whose valid (bend-adjusted) zone never
  crosses the target is skipped just like a rigid element. `_resolve_split`/
  `_handle_short` replaced with `_resolve_splits_for_node`/
  `_resolve_via_override`: both of a lifted node's needed sides are tried
  first, then a SINGLE combined override call carries only the field(s)
  for the side(s) actually exhausted. `ui_dialogs.py`: `ElementOverride`'s
  four fields are now `Optional[int] = None`; `ElementOverrideDialog`/
  `prompt_element_override` take a `sides` parameter and only render/
  require the relevant row(s). Verified via a rewritten
  `/tmp/verify_bend_logic.py` (hand-computed quadratic roots for every
  bend/vertical/rigid scenario, plus new tests for the single-vs-combined
  override call shape) and a real round-trip against `44002.cii` and
  `TESTv15.cii` - the exact reported scenario (support 1450, 750mm
  request) now lands at 685mm into the far element with NO clamp needed at
  all, since the vertical risers correctly contribute zero to horizontal
  position instead of being wrongly subtracted from a length budget.
  QUESTIONS.md's Stop-and-ask entry marked resolved. Still outstanding: a
  live CAESAR II round-trip and a real-machine check of the new dialog UX
  (both need a Windows session).

- 2026-09-14: Completed Milestone 3's remaining piece — `ui_dialogs.py`'s
  `tk.Tk()` dialogs now support `tk.Toplevel(parent)`. Per CLAUDE.md's
  continuous-progress rule (this is a routine, SPEC.md-directed engineering
  call, not a stop-and-ask item), rather than leave it deferred again.
  Added two shared helpers, `_new_dialog_root(parent)` and
  `_run_modal(root, parent)`: with `parent=None` (every current caller,
  unchanged) they do exactly what every dialog did before this commit -
  `tk.Tk()` then `.mainloop()`, byte-for-byte - so today's standalone tool
  is provably unaffected. With a `parent` given (no caller passes one yet;
  this is groundwork for Milestone 4's in-Documenter entry point), they
  use `tk.Toplevel(parent)` + `.transient(parent)`, then `.grab_set()` +
  `.wait_window()` instead of a second `mainloop()` - the standard pattern
  for a modal child dialog inside a host app's already-running event loop.
  All 5 dialog classes (FolderSelectDialog, NodePromptDialog,
  LiftParamsDialog, CiiPollingDialog, ElementOverrideDialog) and their
  convenience wrappers (`prompt_folder`, `prompt_nodes`,
  `prompt_lift_params`, `poll_for_cii`, `prompt_element_override`) now take
  an optional trailing `parent` parameter. `show_message` (a native Win32
  `MessageBoxW`, not a Tkinter dialog) is out of scope - untouched.
  Verified: `py_compile` clean; since this Linux container has no real
  `tkinter` (confirmed - `import tkinter` fails outright, and installing
  `python3-tk` via apt targets a different Python build than the one this
  project runs on, so a real Tk window genuinely cannot be instantiated
  here), wrote a targeted logic test that `exec`s just the two new helper
  functions' own source against a fake `tk` module recording calls -
  confirms `parent=None` produces exactly `[mainloop()]` and a given
  `parent` produces exactly `[transient(parent), grab_set(), wait_window()]`
  with no second mainloop. `neutral_reader/writer/patcher.py` and
  `iecho.py` untouched, per SPEC.md's milestone-3 scope. **Still
  unverified** (needs a real Windows/Tkinter session): that a dialog
  actually renders and behaves correctly end-to-end, in both the
  standalone exe and (once Milestone 4 wires a caller) embedded in a host
  window - flagged in TESTING.md.

- 2026-09-14: Completed Milestone 4 — wired a "Create lift case..." entry
  point into `DocumenterApp`'s nav-tree right-click menu (line level),
  calling the now-in-process-safe Creator stage directly: no second
  window, no subprocess, matching SPEC.md's milestone 4 wording exactly.
  `app_ui.py`'s new `_create_lift_case(line_id)` resolves the line's
  `00_CII` folder (added `line_layout.cii_dir()`, a small helper mirroring
  the existing `refs_dir`/`final_dir` pattern) as the Creator's starting
  folder when it already exists (falls back to `None`, letting the
  Creator's own FolderSelectDialog prompt, exactly like the standalone
  entry point's own resolution fallback), then calls
  `lift_case_builder.run(initial_folder=..., parent=self)` — DocumenterApp
  IS a `tk.Tk`, so it's a valid `parent` for every dialog `run()` opens
  (per Milestone 3's `tk.Toplevel(parent)` support). On success, ingests
  the freshly written sidecar (`db.ingest_sidecars`, the same call
  `LinePanel`'s existing "Check for new cases" button already uses),
  reloads the line's tree leaves, and refreshes the line panel's overview
  if it's the one currently showing. `launcher.py` already puts
  `src/creator` on `sys.path` before dispatching to either program, so no
  new cross-package plumbing was needed beyond the lazy
  `import lift_case_builder` inside the new method (matching the existing
  lazy-cross-import pattern `lift_case_builder.py`'s own
  `_write_documenter_sidecar` already uses for `line_layout`).
  Verified: `py_compile` clean; a headless import of `app_ui.py` against a
  full stub of `tkinter`/`tkinter.ttk`/`messagebox`/`filedialog` plus its
  sibling documenter modules (this Linux container has no real `tkinter` -
  same constraint as Milestone 3); then called `_create_lift_case`
  directly against a fake `DocumenterApp`-like object and a stubbed
  `lift_case_builder.run`, confirming: `flush()` runs first, the resolved
  `00_CII` folder and `self` (as `parent`) are passed to `run()` exactly,
  `ingest_sidecars`/`reload_line` run only after a successful result, and
  the currently-shown line panel's `show_overview()` fires only when it's
  the SAME line just processed. **Still unverified** (needs a real
  Windows/Tkinter session): actually clicking "Create lift case..." from
  the Documenter and watching a dialog open as a child of the main window
  rather than its own separate top-level window - flagged in TESTING.md.

- 2026-09-14: Investigated Milestone 5 ("zero-touch first-run polish")
  before starting it, per CLAUDE.md's stop-and-ask criteria. Found the
  existing "First-run DB discovery" open question in QUESTIONS.md was
  under-specified (no concrete options, no "what to do once answered"),
  and on closer reading of the actual current behaviour, the real gap is
  narrower than the note assumed: `config.py`/`doc_config.py` already
  co-locate both config files next to the single merged `autolift.exe`
  (so a team running one shared exe copy already shares both configs with
  zero extra work — Phase 0's merge already solved that half), the
  Creator already seeds its own `lift_case_config.ini` on first run, and
  the Documenter's `_ask_db()` already has a working (one-click, not
  silent) first-run flow. What's actually still open is narrower and
  hinges entirely on a real-world fact only the user has: whether AutoLift
  is deployed as one shared install or per-seat copies - the latter is
  the only case "zero-touch discovery" would even need to solve, and
  guessing the discovery heuristic wrong risks a real data-integrity
  mistake (scattering a team onto separate databases, or auto-adopting
  the wrong shared one), not just a cosmetic issue. Rewrote the
  QUESTIONS.md entry as a proper blocking Stop-and-ask with concrete
  branches and an explicit "what I'll do once you answer" for each. No
  code changed for this milestone; nothing currently working is affected
  by leaving it open. Posted to the user on the PR rather than guessing.

- 2026-09-14: Implemented Milestone 5 per the user's PR answer ("Everyone
  has their own local DB copy... The default path for the DB should be in
  the AppData folder for 'AutoLift'"). New `src/shared/app_paths.py`
  (`autolift_appdata_dir()` → `%LOCALAPPDATA%\AutoLift`, created on
  demand). `config.py` (Creator) and `doc_config.py` (Documenter) both
  resolve their config files there now instead of "next to the exe," each
  migrating a pre-existing exe-adjacent file forward automatically, once,
  so no one's current settings/DB pointer is lost by the change.
  `lift_documenter.py`'s old one-click "choose a database location"
  first-run dialog is gone entirely — the database now defaults straight
  into `%LOCALAPPDATA%\AutoLift\lift_markup.db` with zero prompts, and
  silently re-defaults there if a configured location ever becomes
  unreachable rather than erroring or re-prompting. Marked
  `MERGE_PLAN.md`'s "Data / install location" section (which had assumed
  a shared-network-drive model from one sample config file) superseded
  rather than leaving it to mislead a future reader; updated SPEC.md's
  milestone 2/3/4/5 entries to reflect what's actually built. The
  optional "merge another engineer's database" idea from the same PR
  reply is logged in QUESTIONS.md as a future enhancement, not built —
  it's a materially bigger feature (reconciling two independent SQLite
  databases) that deserves its own scoping pass. `autolift.spec` gained
  `app_paths` in hiddenimports. Verified: `py_compile` clean; headless
  tests against the real functions (this container has no `tkinter`, so
  `lift_documenter` was imported against a minimal stub of its GUI-heavy
  siblings) covering fresh-path resolution, legacy-config migration for
  both config files (including that non-`db` keys survive), the full
  `write_default_config()` → `default_spacing_mm()` round-trip, the
  zero-touch default with no prompt and its persistence back to the
  config, and silent recovery when a configured path's folder no longer
  exists. **Still unverified** (needs a real Windows session): that a
  genuinely fresh machine actually gets a working, empty database with no
  dialogs at all on first launch.

- 2026-09-14: Follow-up PR comment: "But if someone has a legacy version
  of the DB, it should be possible to migrate the information to the new
  DB." The earlier Milestone 5 pass only migrated the CONFIG file forward
  (so `db=` kept pointing at wherever the database already was); it never
  actually moved the database's own data into the new AppData location.
  Fixed in `lift_documenter.py`'s `_resolve_db_path()`: when the
  configured `db=` points at a real legacy `.db` file that isn't already
  the AppData default, its data (plus any `-journal`/`-wal`/`-shm`
  companion files) is copied into the AppData default once (never
  overwriting an AppData database that already has real data), the
  legacy file is left in place untouched, and the config is repointed at
  the new copy. Verified with a real SQLite file this time (actual
  `CREATE TABLE`/`INSERT`/read-back through the migrated copy, not just
  path assertions): data survives migration, the legacy file is
  untouched, repeat calls are a stable no-op, and an already-populated
  AppData database is never clobbered by a different legacy one.

- 2026-09-14: Second follow-up PR comment, same thread: "I assume this
  includes the rest of the relevant information as well such as images
  and isos?" It didn't — a real gap: `lift_db.py`'s screenshots and
  ingested iso PDFs live as files beside the `.db` file
  (`db_dir/images/<line>/<case>.png`, `db_dir/isos/<line>/<file>`), not
  as rows/BLOBs inside it, so the previous database-only migration would
  have carried the DB's rows forward while leaving every actual image/PDF
  file behind at the old location — the tree would have looked complete
  but screenshots/iso previews would all 404. Fixed: `_copy_db_file` in
  `lift_documenter.py` now also copies the `images/` and `isos/`
  subdirectories alongside the `.db` file (`shutil.copytree`,
  `dirs_exist_ok=True`), matching the exact directory names `lift_db.py`'s
  own `_prune_line_dirs` uses. Verified with a headless test planting a
  real fake screenshot + iso PDF at those exact paths and confirming both
  migrate with byte-identical content while the legacy copies survive
  untouched; re-ran the earlier no-clobber test too, still holds.

- 2026-09-14: User requested four new features (create work order, create
  line from a template, a case-creation button instead of right-click,
  and detection of CAESAR's .C2/._A file-expansion issue in prepip.exe)
  and explicitly asked for a to-do list to confirm before proceeding — no
  code changed this round, per that instruction. Posted the to-do list on
  the PR with two flagged blockers: (1) whether the requested
  "FINALIZATION" folder is a new WO-level concept or the existing
  per-line `02_FINALISATION`, and (2) the attached `Add_New_Line.zip`
  template couldn't be fetched (this session's GitHub access is
  repo-scoped only; a direct `user-attachments` CDN link 403'd) — asked
  the user to commit it into the repo or re-share it another way. Also
  surfaced a real correctness finding from the user's own domain
  knowledge: `lift_case_builder.py`'s `_find_main_input()` silently falls
  back from `_MAIN.C2` to `_MAIN._A` with no warning, which the user says
  produces an incomplete/incorrect lift case when CAESAR II (prepip.exe)
  has the file open — logged as a real bug to fix (Phase 1: detect + a
  manual-fallback prompt; Phase 2, explicitly deferred by the user until
  Phase 1 is confirmed working: automate collapsing it via Ctrl+O).

- 2026-09-14: User re-uploaded `Add_New_Line.zip` directly (resolving the
  earlier unreachable-attachment blocker) and added two more UI points:
  remove `line_ui.py`'s per-line "Sync cases" button (the overall
  `DocumenterApp.refresh()` already covers the same ingest via
  `_rescan_from_disk()`, for every loaded line, not just one), and unify
  the three requested creation actions (new WO / new line / new case)
  into a single button whose label/action changes with tree context,
  rather than separate buttons or right-click entries. Inspected the
  template (original upload:
  `/root/.claude/uploads/ccea8e4c-0a82-5e5b-998d-8277c5461143/f86bdf4f-Add_New_Line.zip`,
  extracted to `/tmp/add_new_line_inspect/extracted` this session): it's
  exactly `line_layout.py`'s existing per-line structure
  (00_CII/01_REFS/02_FINALISATION) with the token `[Add_New_Line]`
  appearing ONLY in the top-level folder name and two filenames inside
  00_CII (`_Flange_Leakage_TRNC.xlsm`, `_MAIN.C2`) - confirmed by
  grepping every file's actual bytes, not just names - so this is now a
  fully-scoped, mechanical feature once committed into the repo. This
  also sharpens (doesn't resolve) the still-open "FINALIZATION folder for
  create-work-order" question - now clearer that it would be a genuinely
  NEW, WO-level folder if built as literally described, not the per-line
  one the template already has. No code changed yet - posted an updated
  to-do list on the PR per the user's explicit request, still awaiting
  confirmation before implementing any of it.

- 2026-09-14: Built all 5 items from the confirmed WO/Line/case-creation
  to-do list (both blockers answered on the PR: the FINALIZATION folder
  is a new WO-level concept, sibling to line folders; button labels use
  Title Case).
  - `line_layout.py`: added `WO_FINALIZATION_DIR`/`wo_finalization_dir()`
    (a new, WO-level folder distinct from the existing per-line
    `FINAL_DIR`/`final_dir()`), documented in the module's Structure
    diagram.
  - `src/documenter/templates/Add_New_Line/00_CII/`: the real template
    files committed into the repo (byte-verified against the user's
    upload via md5sum), plus a README explaining what it's for.
    `autolift.spec` bundles it via `datas` and lists `line_new` in
    hiddenimports.
  - New `src/documenter/line_new.py`: `create_line(wo_folder, line_no)`
    copies the bundled template into `<wo_folder>/<line_no>/00_CII`,
    renaming the two placeholder filenames, and creates `01_REFS`/
    `02_FINALISATION` directly via `line_layout.py`'s own constants
    (no empty directories carried in the template itself, since git
    doesn't track those and it avoids a stray `.gitkeep` leaking into
    every new line).
  - `app_ui.py`: one toolbar button (`_create_btn`) whose label/action
    follow the tree selection (`_update_create_button`, called from
    `_on_select`) - "New Work Order" at the root, "Add New Line" in a
    work order, "New Lift Case" in a line or a case within one.
    `_create_work_order()` infers the right parent folder from existing
    work orders' own folders (majority vote; falls back to a folder
    picker when there are none yet), creates `<parent>/<WO>/FINALIZATION`,
    registers in the DB, refreshes, and selects it. `_create_line()`
    calls `line_new.create_line()` and does the same DB/refresh/select
    dance. Removed the right-click "Create lift case..." entry (Milestone
    4) - the button replaces it. Also fixed a real bug caught while
    writing this: `filedialog` was used in the new WO-creation fallback
    but was never imported at module level - added it.
  - `line_ui.py`: removed the per-line "Sync cases" button and its
    `sync_cases()` method - the overall Refresh button's
    `_rescan_from_disk()` already re-ingests every currently-loaded
    line's sidecars, a strict superset.
  - `ui_dialogs.py`/`lift_case_builder.py`: new `MainExpandedDialog`/
    `prompt_main_expanded()` (Phase 1 of the CAESAR `.C2`/`._A` fix) -
    when `_find_main_input()` would otherwise silently accept a
    `*_MAIN._A` file with no `*_MAIN.C2` alongside it (meaning
    prepip.exe has the model open and expanded), the workflow now stops,
    tells the user to close CAESAR II or use File > Open (Ctrl+O) to
    collapse it back, and polls (no timeout) for `*_MAIN.C2` to reappear
    before continuing. Phase 2 (automating the collapse itself) explicitly
    NOT built, per the user's own instruction to get the fallback working
    first.
  Verified: `py_compile` clean across every touched file; headless tests
  (this container has no real `tkinter`) against the REAL functions for
  every piece - `_update_create_button`'s context detection for every
  tree-node kind (root/wo/line/case/iso), `_infer_wo_parent_dir`'s
  majority-vote logic, `_create_work_order`/`_create_line` end-to-end
  against a real filesystem (folder creation, FINALIZATION subfolder,
  duplicate-number rejection, missing-WO-folder handling, the
  no-existing-WOs folder-picker fallback and its cancellation),
  `line_new.create_line()` against the real bundled template (byte-exact
  file copies, correct renames, both error paths), and the CAESAR
  expansion detection's three real scenarios (successful collapse
  proceeds normally, abort cleanly cancels before any further prompt, a
  normal `.C2`-only folder never triggers the new dialog at all). Re-ran
  every earlier regression suite from this session (bend-logic geometry,
  AppData/DB migration, Milestone-4 parent-threading) - all still pass.
  **Still unverified** (needs a real Windows/Tkinter session): actually
  clicking through the new toolbar button and the CAESAR-open detection
  dialog in the real app - flagged in TESTING.md.

- 2026-09-14: Built Phase 2 of the CAESAR `.C2`/`._A` fix, per the user's
  confirmation that Phase 1 works well and explicit go-ahead: "Let's
  automate the collapse of the *MAIN.C2 file. In the task manager I am
  able to see two Caesar II windows when the file is expanded. We have
  to find the one with the prepip.exe bring it forward and send Ctrl +
  O. I would like as much of this to be a background process, apart from
  bringing the window forward obviously." New `src/creator/
  prepip_automation.py`: `find_prepip_window()` enumerates top-level
  windows (pywin32's `EnumWindows`), skipping invisible/untitled ones,
  and matches each candidate's OWNING PROCESS executable name (via
  `OpenProcess`/`GetModuleFileNameEx`, not window title text, since the
  user noted multiple CAESAR-branded windows can be visible at once and
  only one is actually prepip.exe) against `prepip.exe` case-insensitively
  (using `ntpath.basename`, not `os.path.basename`, so the Windows-style
  backslash path from the Win32 API parses correctly regardless of which
  OS this code happens to run under - not just the real Windows target).
  `try_collapse_main_file()` brings that window to the foreground
  (`SetForegroundWindow`, with an `IsIconic`/`ShowWindow(SW_RESTORE)`
  check first) and sends Ctrl+O (`keybd_event`), matching the manual fix
  already documented. `lift_case_builder.py`'s Step 1b now calls this
  ONCE, silently, before showing `MainExpandedDialog` - "as much of this
  to be a background process" - with the whole call wrapped in a bare
  `try/except` so any failure (pywin32 missing, no window found, the OS
  refusing the foreground change - a well-known Windows restriction) is
  swallowed and falls straight through to Phase 1's existing
  poll-and-manual-instructions dialog, never blocking or crashing the
  workflow. `MainExpandedDialog`'s text updated to explain the window
  jump (since it now happens automatically, unprompted) while still
  giving the manual steps as a fallback. `autolift.spec` gained
  `prepip_automation` plus `win32api`/`win32gui`/`win32process` in
  hiddenimports (imported lazily inside functions, where PyInstaller's
  static analysis is most likely to miss them).
  Verified via headless tests against a fully mocked pywin32 (this
  container has neither pywin32 nor a real Windows display): window
  discovery correctly finds ONLY the true prepip.exe window among a mix
  of visible/invisible/untitled/wrong-process windows; the
  ntpath-vs-os.path fix confirmed necessary and sufficient (this exact
  test failed before that fix, on this Linux container, exactly
  illustrating why explicit `ntpath` matters); the full happy path
  (window found → foreground → exact Ctrl-down/O-down/O-up/Ctrl-up
  keystroke sequence); a refused foreground change correctly returns
  False with no keystrokes sent; no matching window correctly returns
  False with nothing attempted; and, integrated into `lift_case_builder.py`,
  confirmed `try_collapse_main_file()` is called automatically before the
  fallback dialog on `._A` detection, AND that an exception raised inside
  it (simulating a real pywin32 crash) never breaks the workflow - it
  still falls through to the existing manual-fallback dialog exactly as
  before. **Still unverified** (needs a real Windows/CAESAR II session):
  whether `SetForegroundWindow`/`keybd_event` actually work as expected
  against a real prepip.exe window (the well-known Windows
  foreground-window restriction can sometimes block a background
  process from stealing focus even when called correctly - flagged, not
  something this container can test).

- 2026-09-14: Real-machine report on the first Phase 2 build: "It does
  not seem to do anything?" Rewrote `prepip_automation.py` from pywin32 to
  calling `user32.dll`/`kernel32.dll` directly via `ctypes` (matching the
  pattern already used elsewhere - `line_layout.py`'s `_hide()`,
  `ui_dialogs.py`'s `show_message()`), targeting two well-documented
  Win32 issues the first version was exposed to and couldn't rule out
  without real Windows access:
  1. The original process-name lookup (`GetModuleFileNameEx`) needs
     `PROCESS_VM_READ`, a fairly strong permission that can silently fail
     to open a process running at a different privilege level (e.g. an
     elevated CAESAR II against a non-elevated AutoLift) - the window
     would then just never match, no error anywhere. Replaced with
     `QueryFullProcessImageNameW` under
     `PROCESS_QUERY_LIMITED_INFORMATION`, a much lower bar and the modern
     recommended approach.
  2. `SetForegroundWindow` is deliberately restricted by Windows - a
     background process normally can't just steal focus on its own (the
     OS's "foreground lock"). The first version never worked around this
     at all. Added the standard, documented fix: `AttachThreadInput` with
     the target window's owning thread before calling
     `SetForegroundWindow`, detached again afterward.
  Also fixed a real, previously-latent correctness risk while rewriting:
  every ctypes call that returns/accepts a window or process handle now
  has an explicit `c_void_p` prototype - handles are pointer-sized (8
  bytes on 64-bit Windows), and ctypes silently truncates an undeclared
  pointer argument to 32 bits, which would itself look exactly like
  "nothing happened," with no exception raised anywhere.
  Added a debug trace: every attempt appends what it found/did to
  `%LOCALAPPDATA%\AutoLift\prepip_automation.log` (window count, each
  visible/titled window's resolved process name, which one matched,
  whether `AttachThreadInput`/`SetForegroundWindow` succeeded) - not
  shown to the user, but gives something concrete to look at if this
  still doesn't work, rather than guessing blind a third time.
  `autolift.spec`: removed `win32api`/`win32gui`/`win32process` from
  hiddenimports (added for the now-replaced pywin32 version; confirmed
  nothing else in the codebase imports them) - `prepip_automation` itself
  stays listed since it's still imported lazily.
  Verified via headless tests against fully mocked `ctypes.windll`
  equivalents (this container has neither a real Windows API nor pywin32,
  and `ctypes.windll`/`ctypes.WINFUNCTYPE` don't even exist as attributes
  on Linux - confirmed directly): window discovery correctly matches only
  a visible, titled, prepip.exe-owned window among a realistic mix
  (including two windows on the SAME prepip.exe process where only the
  visible one should count); the `AttachThreadInput` sequencing (attached
  before `SetForegroundWindow`, detached after, in that order); the exact
  Ctrl+O keystroke sequence; both the foreground-refused and
  no-window-found paths degrading cleanly to `False`; the debug log
  actually being written with the right content; and, re-running the
  earlier integration tests, that `lift_case_builder.py`'s call site,
  the fall-through on exception, and every other CAESAR-detection
  scenario still all pass unchanged.
  **Still unverified** (needs the user's real machine, same caveat as
  before - this container simply cannot exercise real Win32 window/focus
  behaviour): whether this actually works now. If it still doesn't, the
  new log file should make the next round of feedback far more specific
  than "does not seem to do anything."

- 2026-09-14: Third real-machine follow-up on the CAESAR automation, same
  day: "it seems like it happens before the dialogue explaining it opens.
  So perhaps have the dialogue open, then bring forward, then do the open
  file command. Allow some time between each?" Correct diagnosis - the
  first two passes ran the whole sequence (find window, bring forward,
  send Ctrl+O) synchronously in `lift_case_builder.py`, BEFORE
  `MainExpandedDialog` ever opened, meaning AutoLift's own dialog would
  open right afterward and immediately steal focus back (its
  `_focus_window()` forces topmost/focus), likely interrupting whatever
  CAESAR was doing in response to the keystroke before it could register.
  Fixed by moving the whole sequence's OWNERSHIP into the dialog itself,
  with real delays between each step:
  - `prepip_automation.py`: `try_collapse_main_file()` replaced with two
    separate functions, `bring_prepip_forward()` (find + foreground) and
    `send_ctrl_o()` (just the keystroke), each independently loggable/
    callable.
  - `ui_dialogs.py`'s `MainExpandedDialog`: now shows itself fully FIRST
    (unchanged from before), THEN schedules `bring_prepip_forward()` via
    `root.after(600ms, ...)` - giving the dialog time to actually paint
    on screen - and only schedules `send_ctrl_o()` via a SECOND
    `root.after(500ms, ...)` once `bring_prepip_forward()` found and
    focused a window, giving Windows time to actually complete the
    foreground-window transition before the keystroke fires. Neither
    step blocks the Tkinter event loop (no `time.sleep()` anywhere) -
    both delays are scheduled callbacks, so the dialog itself (and its
    own poll-for-`.C2` loop) stays fully responsive throughout.
  - `lift_case_builder.py`'s Step 1b no longer imports/calls
    `prepip_automation` at all - that responsibility moved entirely into
    the dialog, which is the only thing that can correctly sequence
    "after I'm visible" in the first place.
  - Dialog wording adjusted from "AutoLift just tried..." (past tense,
    was already inaccurate under the old synchronous ordering too) to
    "In a moment, AutoLift will try..." matching the new sequencing.
  Verified via headless tests: `prepip_automation`'s split API (each
  function does exactly one thing, `bring_prepip_forward()` never sends a
  keystroke on its own, `send_ctrl_o()` never raises even if the
  underlying call fails, the log still records each step); the dialog's
  own `_start_automation`/`_send_automation_keystroke` orchestration
  (using a fake Tk root whose `.after()` just records scheduled
  callbacks, invoked manually to simulate the delay firing) - confirms
  the keystroke is genuinely deferred to a second, separate scheduled
  callback rather than firing immediately, that finding no window
  schedules nothing further, and that an exception at either stage is
  swallowed without propagating; and re-ran every earlier regression
  suite (bend-logic geometry, AppData/DB migration, Milestone-4
  parent-threading, the CAESAR-detection scenarios with the
  `lift_case_builder.py` call site updated to confirm it no longer
  touches `prepip_automation` directly at all) - all still pass.
  **Still unverified** (same caveat as every round of this feature): the
  actual real-machine timing/behavior. The debug log
  (`prepip_automation.log`) still applies unchanged and should now show
  two separate timestamped blocks per attempt (one for the foreground
  step, one for the keystroke) rather than one, making the actual gap
  between them visible if it's ever worth tuning the delay values.

- 2026-09-14: User confirmed the CAESAR automation sequencing fix worked
  ("That worked."), then flagged a second stray refresh button I'd
  missed: "I can see you didn't remove the refresh for the line number."
  The earlier "one refresh button" pass only removed `line_ui.py`'s
  per-line "Sync cases" button (the data-sync one); missed a SEPARATE
  in-panel "Refresh" button inside `LinePanel.show_overview()`'s own
  "Line preview" pane, whose command was just `self.show_overview` (a
  pure re-render of the already-known data, not a disk sync) - also
  redundant now that the overall Refresh button is the one and only
  refresh control. Removed it (and the now-empty button-bar frame it
  lived in). Confirmed `PreviewPane`'s own "Refresh" button (used for the
  full-page PDF/iso viewer, both in `line_ui.py` and `wo_ui.py`) is a
  genuinely different feature - re-rasterizing PDF pages at the current
  size, not a data sync - and left untouched; it isn't what "refresh for
  the line number" referred to.
- Merged PR #2 into `main` (squash `df4f14c`) after user confirmation
  ("I confirm everything works. Let's merge with the main branch"). Restarted
  the working branch from `main` per CLAUDE.md's merged-PR handling and
  updated TESTING.md: "Test this now" now says plainly there's nothing
  outstanding (previous round collapsed into a reference `<details>` block),
  and Step 1's "get the code" instructions point at `main` instead of the
  now-merged feature branch.
- Updated README.md to match what's actually shipped: Status blurb now
  covers the bend-aware placement, AppData migration, WO/Line/case-creation
  UI, and CAESAR automation work merged since Phase 0 (was still describing
  Phase 0 as current); fixed the "Sync cases" button reference (removed,
  now the overall Refresh button) in the Creator/Documenter handshake
  section; noted the new WO-level FINALIZATION folder alongside the
  existing per-line one; and rewrote the "built vs. designed" table to
  reflect current reality instead of the pre-Milestone-3 snapshot.
- Documenter fit-to-screen pass, per user request + confirmed item-by-item:
  main window (`DocumenterApp`) now opens maximized on launch; work-order
  panel's lines table gained a real vertical scrollbar (previously fixed
  height=9 with no way to see more lines); case screenshot thumbnail cap
  shrunk (460,320)->(420,220) to free vertical space on the case screen;
  and an iso's "isonote" standing-furniture box (layout_builder.
  ensure_iso_furniture) now only exists while its note text is non-empty,
  in both the editor and the export, reappearing the moment a note is
  typed again. Skipped per user: resizing the Archive browser, fixing
  CaseMetaDialog's lift-points overflow.
- Added "Export this line..." to LinePanel (per user request, mid-review):
  exports just the selected line's isos + lift cases via the existing
  work_order.plan/export_work_order line_order filter (no new export
  logic needed), defaulting the filename to
  "<wo_no>_<line_no>_STRESS_MARKUP.pdf". Whole-work-order export in
  WoPanel is unchanged.
- Updated TESTING.md's Step 1 + "Test this now" pointer for PR #5: since
  the fit-to-screen/single-line-export work isn't merged to main yet,
  the tutorial now checks out claude/repo-mapping-modules-xomccd (this
  PR's branch) instead of main, and compares against PR #5 instead of
  main's commit history - same pattern used before each earlier PR merged.
