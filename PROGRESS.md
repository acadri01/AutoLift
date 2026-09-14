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
