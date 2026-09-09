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
