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
- **Phase 2 CAESAR-collapse automation, decide-and-proceed details
  (2026-09-14)**: within the user's explicit go-ahead ("find the one with
  prepip.exe, bring it forward, send Ctrl+O"), a few routine engineering
  calls: (1) match the target window by its OWNING PROCESS's executable
  name (`prepip.exe`, via `OpenProcess`/`GetModuleFileNameEx`), not by
  window title text - the user's own description ("two Caesar II
  windows") implies title text alone can't reliably tell them apart; (2)
  a SINGLE attempt, not a retry loop - repeatedly stealing focus/sending
  Ctrl+O every poll tick would be disruptive if the user is mid-task
  elsewhere; `MainExpandedDialog`'s existing poll (Phase 1) is what
  actually confirms success or lets the user finish it by hand; (3) every
  failure mode (pywin32 missing, no window found, the OS refusing the
  foreground change) degrades silently to "did nothing" rather than
  surfacing a separate error - the existing Phase 1 dialog already
  explains what to do either way, so a second failure message would be
  redundant, and this must never be able to block/crash lift case
  creation on its own.
- **Phase 2 rewrite, pywin32 → ctypes (2026-09-14, same day, after a
  real-machine "does not seem to do anything" report)**: switched from
  pywin32 to calling `user32.dll`/`kernel32.dll` directly via `ctypes`
  (matching `line_layout.py`/`ui_dialogs.py`'s existing pattern) and
  added the standard `AttachThreadInput` workaround for Windows'
  foreground-lock restriction, `QueryFullProcessImageNameW` under
  `PROCESS_QUERY_LIMITED_INFORMATION` for cross-privilege process-name
  lookup, and explicit `c_void_p` prototypes to avoid 64-bit handle
  truncation - three concrete, well-documented candidates for exactly
  this "silently does nothing" symptom, not a guess. Also added a debug
  log (`%LOCALAPPDATA%\AutoLift\prepip_automation.log`) so the NEXT
  report, if there is one, can be specific rather than another blind
  guess. This wasn't escalated back to the user as a question - it's a
  bug-fix/robustness pass within the already-approved Phase 2 automation,
  not a new design decision.
- **Phase 2 sequencing fix (2026-09-14, same day, third round - the user
  correctly diagnosed the real bug)**: "it seems like it happens before
  the dialogue explaining it opens. So perhaps have the dialogue open,
  then bring forward, then do the open file command. Allow some time
  between each?" This wasn't a guess to escalate - it's a precise,
  correct bug report: the first two passes ran the whole automation
  sequence synchronously BEFORE `MainExpandedDialog` ever opened, so
  AutoLift's own dialog (which forces itself to the front on open) would
  immediately steal focus back right after stealing it FOR CAESAR,
  racing/interrupting whatever CAESAR was doing with the keystroke.
  Implemented exactly as suggested: the dialog now opens first, and the
  automation is split into two functions
  (`bring_prepip_forward`/`send_ctrl_o`) that the dialog itself schedules
  with real delays via `root.after()` (600ms before bringing the window
  forward, another 500ms before sending Ctrl+O) - no `time.sleep()`
  anywhere, so the dialog's own UI and polling stay fully responsive
  throughout. `lift_case_builder.py` no longer touches
  `prepip_automation` at all; only `MainExpandedDialog` does, since it's
  the only thing that can correctly know "I'm visible now."
- **Milestone 3's `tk.Tk()` → `tk.Toplevel(parent)` refactor (2026-09-14)**:
  built now rather than deferred again, since it's a routine engineering
  call already directed by SPEC.md's milestone wording, not a genuine
  requirement ambiguity. Made it strictly additive to de-risk it: every
  dialog's new `parent` parameter defaults to `None`, and with `None` the
  code path is byte-for-byte what ran before (`tk.Tk()` + `.mainloop()`)
  — no current caller passes a `parent`, so today's standalone tool's
  behaviour is unchanged by construction, not just by review. The
  `tk.Toplevel(parent)` + `grab_set()`/`wait_window()` path is new,
  unexercised groundwork for Milestone 4's not-yet-built in-Documenter
  entry point. `show_message()` confirmed left as-is (see above) — it's a
  native `MessageBoxW`, not a `tk.Tk()` dialog, so out of SPEC.md's
  milestone-3 scope.

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

## Stop-and-ask (resolved 2026-09-14 - user answered both blockers, implemented)
- **RESOLVED**: user replied "there is a finalisation folder within the
  line number, but this is mainly for the user. There should be one for
  the full work order which sits together with the line numbers, thus
  the exported markup for the full wo may be saved there" (confirms the
  NEW, WO-level FINALIZATION folder, separate from the per-line one) and
  "For point three, caps for first letter of each word" (Title Case
  button labels). Both applied; all five items below are now built and
  pushed - see PROGRESS.md for the implementation/verification log.
  Original request and both blockers preserved below for the record.
- Original entries, preserved for context: user requested four new
  features (create work order, create line from a template, a "Create
  new case" button instead of right-click, and detection of CAESAR's
  `.C2`/`._A` file-expansion issue) and explicitly asked for a to-do list
  to confirm before proceeding - posted on the PR, no code changed yet.
  - **`Add_New_Line.zip` — RESOLVED**: the user re-uploaded it directly
    (not the earlier unreachable GitHub attachment link). Inspected it:
    ```
    [Add_New_Line]/
      00_CII/
        AIBEL-GRN.FIL, CONTROLU, valve.hed, C2.HPL, frp.hed, caesar.cfg,
        expjt.hed                              (unchanged - CAESAR site config)
        [Add_New_Line]_Flange_Leakage_TRNC.xlsm  (rename)
        [Add_New_Line]_MAIN.C2                   (rename - a blank starter model)
      01_REFS/                                   (empty)
      02_FINALISATION/                           (empty)
    ```
    Exactly matches `line_layout.py`'s existing per-line convention
    (`CII_DIR`/`REFS_DIR`/`FINAL_DIR`) - confirms this is the SAME
    `02_FINALISATION` already in the codebase, not a new concept. Checked
    every file's CONTENT (not just names) for the `[Add_New_Line]` token -
    only the top-level folder name and the two filenames inside `00_CII`
    contain it; nothing inside any file's bytes does. So "create line" is
    now a well-defined, mechanical feature: prompt for a line number, copy
    this bundled template tree under the selected work order's folder,
    renaming the top folder and those two files (string-substituting the
    token), leaving every other file's name and bytes untouched. Needs the
    template committed into the repo (e.g. `src/documenter/templates/
    Add_New_Line/`) and added to `autolift.spec`'s bundled data files.
  - **"FINALIZATION" folder scope for "create work order" — still open**:
    now that the line template confirms `02_FINALISATION` is per-LINE
    (nested inside `[Add_New_Line]/`, not at the WO root), the original
    question sharpens rather than resolves: the "create work order"
    request describes a folder created directly inside the bare WO folder
    itself ("a folder for the work order... with a FINALIZATION folder
    within") - which would be a NEW, WO-level concept, structurally
    different from any per-line folder, since today's WO folders hold
    only line-number subfolders and nothing else. Is that really wanted
    (a second, WO-wide export location, separate from each line's own
    02_FINALISATION), or was the user describing the per-line one loosely
    while thinking about "create work order" and "create line" together?
    Guessing wrong here creates a real, empty folder in every future work
    order's structure - not cosmetic. Concrete next step once answered: if
    new, add a `FINALIZATION_DIR`/helper to `line_layout.py` (mirroring
    `refs_dir`/`final_dir`/`cii_dir`) and create it alongside the WO
    folder in "create work order"; if it means the per-line one, no WO-
    level change needed - "create line" (now unblocked) already covers it.
  - **Two new UI decisions from the same-day follow-up, not blocking, just
    logged as scope**: (1) `line_ui.py`'s per-line "Sync cases" button is
    to be removed - `DocumenterApp.refresh()` already calls
    `_rescan_from_disk()`, which ingests sidecars for every currently-
    loaded line, i.e. a strict superset of what "Sync cases" does, so the
    overall Refresh button already covers it; (2) the three creation
    actions (new WO / new line / new case) become ONE button at a fixed
    location (proposed: `DocumenterApp`'s left-panel toolbar, beside
    "Refresh"/"View archive"), whose label and action change based on
    tree context - "New work order" at the Work Orders root, "Add new
    line" inside a WO, "New lift case" inside a line (or a case within
    one) - replacing the separate right-click entry and button ideas from
    the first to-do list.

## Stop-and-ask (resolved 2026-09-14 - user answered on the PR, implemented)
- **RESOLVED**: user replied "Everyone has their own local DB copy, but
  merging databases in the DB admin may be a good option if someone takes
  over another person's files. The default path for the DB should be in
  the AppData folder for 'AutoLift'." Read as: (1) confirms the per-seat
  model (no cross-machine discovery needed - each engineer's DB is
  independently theirs), (2) the concrete zero-touch default: both
  `lift_case_config.ini` and `lift_doc_tool.cfg`, plus the database
  itself, now default into `%LOCALAPPDATA%\AutoLift\` with NO first-run
  prompt at all, and (3) a "merge another engineer's database" action in
  Database admin is a possible FUTURE enhancement ("may be a good
  option"), not a firm ask - logged below under "Open, non-blocking"
  rather than built now, since it's a materially bigger feature (comparing/
  merging two SQLite databases, resolving overlapping WO/line/case
  records) that deserves its own scoping pass if/when actually wanted.
  Implemented: new `src/shared/app_paths.py` (`autolift_appdata_dir()`,
  `%LOCALAPPDATA%\AutoLift`, created on demand); `config.py`'s
  `_config_path()` and `doc_config.py`'s `cfg_path()` both resolve there
  now instead of "next to the exe," each with a one-time, self-healing
  migration of a pre-existing exe-adjacent config forward (so no one's
  existing settings/DB pointer is silently lost by this change).
  `lift_documenter.py`'s old one-click "choose a database location"
  first-run dialog (`_ask_db`) is removed entirely - `_resolve_db_path()`
  now defaults straight into the AppData folder with zero prompts, and
  silently re-defaults there if a configured location ever becomes
  unreachable (e.g. deleted), rather than erroring or re-prompting.
  `MERGE_PLAN.md`'s "Data / install location" section (which had assumed
  a shared-network-drive model from one sample config file, not a direct
  instruction) is marked superseded rather than silently left to mislead
  a future reader. Verified via headless tests exercising the real
  functions (this container has no real `tkinter`, so `lift_documenter`
  was imported against a minimal stub of its GUI-heavy siblings):
  fresh-path resolution, legacy-config migration (both `config.py` and
  `doc_config.py`, including that non-`db` keys like `markup_cloud`
  survive the migration), the full `write_default_config()` →
  `default_spacing_mm()` round-trip through the new location, the
  zero-touch default path with no prompt, its persistence back to the
  config, and silent recovery when a configured `db=` path's folder no
  longer exists.
  **Follow-up (same day, PR comment)**: "But if someone has a legacy
  version of the DB, it should be possible to migrate the information to
  the new DB." Correct catch — the first pass above only migrated the
  CONFIG file forward (so the `db=` pointer kept working), but never
  actually moved the DATABASE's own data into the new AppData location,
  meaning it would keep living wherever it always had, forever invisible
  outside that old spot. Fixed: `_resolve_db_path()` now, when the
  configured `db=` points at a real legacy `.db` file that isn't already
  the AppData default, copies that file's actual data into the AppData
  default (a copy, not a move - the legacy file is left untouched) and
  repoints the config at the new copy, so every following run uses the
  single canonical AppData location. Never overwrites an AppData database
  that already exists and has real data in it (checked before copying) -
  important since two different old locations could otherwise clobber
  each other on two different first-runs-after-update. This is
  same-person, same-machine data continuity, not the cross-engineer
  "merge another person's database" idea from earlier in the same
  reply - that one is still correctly left as a future enhancement below,
  since reconciling two INDEPENDENT people's overlapping records is a
  materially different (and harder) problem than carrying one person's
  own data forward. Verified via a new headless test with a real SQLite
  file (actual `CREATE TABLE`/`INSERT`/read-back, not just path
  assertions): the legacy DB's real data lands in the migrated copy, the
  legacy file survives untouched, a second run is a stable no-op, and an
  already-populated AppData database is never overwritten by a different
  legacy one.
  **Second follow-up (same day, PR comment)**: "I assume this includes
  the rest of the relevant information as well such as images and isos?"
  It did NOT, and this was a real gap, not a hypothetical one:
  `lift_db.py`'s own module docstring documents that screenshots and
  ingested iso PDFs are `db_dir/images/<line>/<case>.png` and
  `db_dir/isos/<line>/<file>` - files sitting BESIDE the `.db` file, not
  rows/BLOBs inside it (confirmed against `image_path()`/`iso_dir()`/
  `abs()`, which all build paths relative to `self.dir`, the database's
  own directory). The database-file-only migration above would have
  copied the DB's rows (which still reference those relative paths) while
  leaving the actual image/PDF files behind at the old location -
  everything would have looked fine in the tree, but every screenshot and
  iso preview would 404. Fixed: `_copy_db_file` (in `lift_documenter.py`)
  now also copies the `images/` and `isos/` subdirectories (via
  `shutil.copytree(..., dirs_exist_ok=True)`) alongside the `.db` file
  itself, using the same directory names `lift_db.py`'s own
  `_prune_line_dirs` already uses. Verified via a new headless test that
  plants a real fake screenshot and iso PDF at the exact
  `db_dir/images/<line>/<case>.png` / `db_dir/isos/<line>/<file>` paths
  `lift_db.py` itself would use, migrates, and confirms both land at the
  new location with byte-identical content while the legacy copies remain
  untouched. Original question preserved below for the record.
- Original question, preserved for context: **What should "zero-touch
  first-run" actually mean for config/DB location, and is it worth
  building?** SPEC.md's milestone 5 says to
  "seed `lift_case_config.ini` / `lift_doc_tool.cfg` from bundled
  resources into the persistent app-data location on first run" and
  "run the `tool_discovery` probe once and cache the result." Before
  touching this, I checked what actually happens today (unchanged from
  the two original programs, per `launcher.py`'s "no behaviour changed"
  guarantee):
  - Both configs already resolve to the SAME folder today - the one
    containing the single merged `autolift.exe` (`config.py`'s
    `_config_path()` and `doc_config.py`'s `cfg_path()` both use
    `Path(sys.executable).parent` when frozen). So a team running one
    shared copy of the exe (from a network drive, say) already gets one
    shared `lift_case_config.ini` AND `lift_doc_tool.cfg`, with zero
    extra work - Phase 0's merge already solved the "do both configs
    agree" half of this for free.
  - The Creator already seeds its own default `lift_case_config.ini` on
    first run (`config.write_default_config()`, called from
    `create_lift_case.main()` - pre-existing, unmodified).
  - The Documenter already has a working (if not silent) first-run flow:
    `lift_documenter.py`'s `_ask_db()` shows one message + one folder
    picker the very first time, explicitly telling the user to "Pick a
    location OUTSIDE the job folders - one database serves every work
    order," then persists the choice to `lift_doc_tool.cfg`. Every
    subsequent launch is already silent.
  - So the REAL gap milestone 5 is asking to close is narrower than it
    first reads: not "make configs agree" (already true) and not "handle
    first run at all" (already handled, just not silently) - it's
    specifically "make even the FIRST launch need zero clicks by
    auto-discovering a team's already-existing shared database/config,"
    which only matters at all if AutoLift is deployed as a PER-SEAT
    install (each engineer gets their own local copy of the exe) rather
    than run from one shared location. If it's always run from one
    shared copy, there's nothing left to build here.
  - This is a real product decision, not a coding one: how AutoLift is
    actually rolled out to engineers at Kårstø (one shared network
    install vs. per-machine copies) decides whether "discovery" is
    needed at all, and if per-seat, exactly where to look (a fixed
    company file-share path? a value baked in at install time? scanning
    common install locations?) is something only you know, not something
    inferable from the code. Guessing here risks either scattering a
    team onto silently-separate databases, or auto-adopting the wrong
    shared one - a data-integrity mistake, not a cosmetic one.
  - **Not attempted**: no code changed for milestone 5. The already-working
    one-click-on-first-run behaviour above is left exactly as-is - nothing
    is broken or regressed by leaving this open.
  - Concrete next step once you answer:
    - **If AutoLift always runs from one shared location** (network
      share, shared login, etc.): milestone 5 is effectively done already
      by the Phase-0 merge; the only remaining polish is caching
      `tool_discovery.probe_capabilities()`'s result across separate
      process launches (e.g. a small `probed_at`/`iecho_path` pair
      written into whichever config file already exists) so it isn't
      re-run on every single context-menu click - a small, unambiguous
      change I can make without further input if you'd like it.
    - **If each engineer gets their own local install**: tell me the
      actual convention (a fixed path, an environment variable, a value
      the installer sets) for where to find the team's shared
      `lift_doc_tool.cfg`/database, and whether `lift_case_config.ini`
      should be shared the same way or stay per-seat (it only holds
      spacing/displacement/iecho-path defaults, which arguably SHOULD be
      per-seat if different engineers' machines have iecho installed in
      different places). Once you tell me the convention, I'll wire it
      into `config.py`/`doc_config.py` right where `write_default_config()`
      /`_ask_db()` already live, with the existing prompt as the fallback
      when nothing is found.

## Stop-and-ask (resolved 2026-09-14 - user confirmed a hybrid design, implemented)
- **RESOLVED**: user chose a hybrid of options (B) and (C): "I think we
  should go for something along the lines of option 3. The program should
  use the method discussed in option 2 to determine the length. However,
  if this length is exhausted before a suitable placement is found, this
  should fall back to the user to provide the element to be used by
  requiring the from and to nodes. I would prefer that the user is then
  not prompted for both lifting points, only the one that is relevant. If
  both sides have exhausted the requested length, then the dialogue with
  both inputs should be provided." - confirmed after I sent back a written
  understanding summary ("This is perfect. Build this now.").
  Implemented: `_walk_to_flexible_element` now tracks the walk's actual
  horizontal-plane position relative to the support (`_horizontal_delta`)
  and solves a quadratic in the along-element parameter `s` for the point
  matching the requested horizontal-plane distance, per candidate element -
  no more `remaining -= length` running subtraction. There is NO clamping
  left anywhere in the walk: an element whose valid zone (bend-adjusted)
  never crosses the target distance is skipped exactly like a rigid
  element, and the walk continues outward. Only when a side's walk is
  genuinely exhausted (`None`) does it fall back to the override dialog -
  and `_resolve_splits_for_node`/`_resolve_via_override` now try BOTH of a
  lifted node's needed sides first, then issue a SINGLE combined
  `on_override` call containing only the field(s) for the side(s) actually
  exhausted (both sides' fields together only when both come up empty at
  once). `ElementOverride`'s four fields are now `Optional[int] = None`,
  and `ElementOverrideDialog`/`prompt_element_override` take a `sides`
  parameter that controls which row(s) render - the user is never asked to
  confirm a side that already resolved on its own.
  Verified against the exact reported scenario (support 1450, request
  750mm) in `/tmp/verify_bend_logic.py`: the two vertical risers now
  correctly contribute ZERO to the horizontal position (rather than having
  their own lengths wrongly subtracted from a length budget), so the true
  750mm target is found at 685mm into the far element - comfortably clear
  of the shared bend's 200mm clearance, with no clamp needed at all. Also
  re-ran end-to-end against real sample files (44002.cii, TESTv15.cii);
  both produce clean warnings and, where the pipe run genuinely can't
  reach 750mm on a side, correctly fall back to the (headless, no-dialog)
  midpoint placement with an explicit warning rather than a silently wrong
  number.
  Still outstanding: a live CAESAR II verification of a patched file, and
  a real-machine check of the new override-dialog UX (only relevant
  side(s) shown) - both need a Windows session, see TESTING.md.
- Original question, preserved for context: **What should "750 mm from the
  support" mean once the walk crosses a direction change (a vertical riser,
  a bend)?** Real-machine report, with
  a CAESAR "Between Element Nodes" measurement: `_walk_to_flexible_element`
  has always measured "distance from support" as the SUM OF ELEMENT
  LENGTHS walked (`remaining -= _element_length(e)` at every hop) - this
  exactly equals straight-line distance only when the walked path is
  dead straight. Once the path changes direction - which the vertical-skip
  and near-bend fixes made routine rather than exceptional - cumulative
  path length and actual straight-line distance from the support diverge,
  sometimes a lot: in the reported case (support 1450, requested 750mm,
  walk skips a too-short bend-adjacent element, two vertical risers, then
  clamps 152mm past a bend at node 1540), the walked path length is
  1509.7mm, CAESAR's straight-line 3D distance between the support and the
  resulting lift node is 1384.49mm, and the horizontal-plane distance
  (ignoring the vertical rise) is only 495.6mm - three genuinely different
  numbers, none of them 750mm. The user computed the horizontal figure
  themselves and flagged it as clearly wrong; they also called the
  resulting placement (152mm past a bend) "strange" on its own terms,
  independent of which distance definition is used.
  - Not fixed here: this is a genuine requirement ambiguity, not an
    implementation bug in a design that's otherwise settled - CLAUDE.md's
    stop-and-ask criteria applies squarely ("branches lead to materially
    different products"). Guessing wrong a third time on the placement
    algorithm wastes more of the user's time than asking once.
  - Options put to the user (see the PR reply): (A) true 3D straight-line
    distance from the support to the lift point, which would need a real
    geometric solve (distance from a fixed point to a point moving along a
    line segment is quadratic in the segment parameter) rather than the
    current running-subtraction bookkeeping; (B) horizontal-plane-only
    distance (matches the exact calculation the user did, and is arguably
    the more physically relevant one for rigging clearance); (C) a more
    conservative strategy change - stop walking through direction changes
    at all once the immediate colinear run is exhausted, and fall back to
    the override dialog instead of mechanically hunting for a
    mathematically-valid-but-awkward spot several hops away.
  - Concrete next step once a definition is chosen: (A) or (B) both
    replace the `remaining -= length` running subtraction in
    `_walk_to_flexible_element` with an actual geometric check - track the
    support node's absolute position (from the model's element chain,
    summing dx/dy/dz from the original support node) and, for each
    candidate element, solve for the point along it whose distance (3D for
    A, projected onto the horizontal plane for B) from that absolute
    position equals `node_spacing`, walking further if the element's own
    span of achievable distances doesn't reach it. (C) is a much smaller
    change - stop `_walk_to_flexible_element` after the FIRST skip that
    isn't collinear with the original element's direction, and route
    straight to `_handle_short`/the override dialog from there.

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
- **"Merge another engineer's database" in Database admin** (per direct
  instruction, 2026-09-14: "merging databases in the DB admin may be a
  good option if someone takes over another person's files") - a real
  feature idea, explicitly hedged as optional ("may be"), not built.
  Would need its own scoping pass before implementation: how to reconcile
  overlapping work-order/line/case records between two independent
  SQLite databases (same WO number created independently on two
  machines? same case name, different data?), what "merge" should do on
  a genuine conflict (keep both? prefer one? ask per-conflict?), and
  where in `_open_db_admin`'s existing UI it belongs. Revisit if/when
  this scenario (taking over a colleague's files) actually comes up.
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
- First-run DB discovery on a fresh machine: superseded by the fuller
  "Stop-and-ask (blocking - Milestone 5 ...)" entry above (2026-09-14),
  which found the actual gap is narrower than originally assumed here and
  put concrete options to the user.
