# MERGE_PLAN — LiftNeutralFileModifier + MarkUpGen → AutoLift

> STATUS: descoped by the user after this plan was written. Everything below
> (in-process GUI refactor, callable-stage Creator, workflow state-machine
> changes) is PAUSED, not abandoned — kept here as the documented next phase,
> but nothing in it is being built right now. See "Phase 0" immediately below
> for what is actually being built instead.

## Phase 0 (current, in progress) — packaging only, zero behaviour change

The user's revised instruction: bundle the two programs into one
distributable .exe that also self-installs both context-menu verbs, with
**no refactoring of the GUI or anything else** — both programs must keep
functioning exactly as they do today, just packaged together.

What this means concretely, and what it explicitly rules out (everything
under "Phase 1+" below, until asked for again):

- `src/creator/` and `src/documenter/` hold the two programs' original
  files, copied in unmodified (byte-identical — verified with `diff` before
  copying). `src/shared/` holds one copy of `lift_meta.py`/`line_layout.py`
  (the two trees' copies were already byte-identical, so de-duplicating
  them into one file changes nothing either program does).
- `src/launcher.py` (new file) is the one PyInstaller entry point. It puts
  all three source directories on `sys.path` (so the existing bare
  `import lift_meta` / `import lift_db` style imports in the untouched
  files keep resolving), then dispatches on an argv mode flag to either
  program's own, unmodified `main()` — passing that program exactly the
  argv shape it already expects (its own folder-path arg from `%V`).
- `src/install_context_menu.py` (new file) silently (re)installs both
  context-menu verbs under **HKCU** (per-user, no elevation) every launch,
  self-healing if the exe is moved. Replaces the two separate registrations
  the old exes used to need done by hand.
- `lift_doc_tool.cfg` (the Documenter's runtime DB-location file) is
  intentionally **not** committed — it's generated state, not source, and
  the one seen in the provided zip held a real deployed network path. DB
  location/behaviour is otherwise untouched: same cfg format, same
  first-run prompt, same shared-store model as discussed and preserved.
- `autolift.spec` (new) replaces `create_lift_case.spec` and
  `lift_documenter.spec` with one PyInstaller build producing one `AutoLift.exe`.

Not part of Phase 0 — deferred to Phase 1+ below, unchanged from before:
`ui_dialogs.py` staying `tk.Tk()`-per-dialog (not `Toplevel`), no in-process
"Create lift case" action inside `DocumenterApp`, no workflow state-machine
changes, no zero-touch DB discovery logic. The two programs remain two
separate, independent code paths that happen to ship in one exe.

---

## Phase 1+ (paused — the fuller merge, not being built right now)

Below is the plan as originally converged on, before the user descoped to
Phase 0. Restart here if/when asked to continue the deeper merge.

## Goal (unchanged, firm)
One self-contained, easily-downloadable Windows program, launched from the
left-click / context menu, replacing two separate exes (`create_lift_case.exe`,
`lift_documenter.exe`) with one. CAESAR II / iecho remain external,
discovered-not-embedded (SPLM/Hexagon licensing).

## Workflow — final

```
NEW → LIFT_CREATED → RUN_PENDING → FORCES_READ → MARKED_UP
```

Changed from the original proposal:

- **`RESTRAINTS_TAGGED` dropped as a separate stage.** There is no silent
  `.C2 → .CII` export (`iecho.launch_for_export` is interactive-only) so a
  standalone "read restraints first" step would cost a second interactive
  CAESAR round-trip per line. The existing Creator design — enter node
  numbers, export once, patch, then validate against restraints as a
  post-hoc warning the user can override — stays as the single "Create Lift"
  action. Nothing is lost: the restraint check still happens, just after the
  one export instead of gating a second one.
- **`RUN_PENDING → FORCES_READ` transition detection is unverified, not
  reused.** HANDOFF.md's "C2Watchdog pattern already exists" claim does not
  match either provided codebase — no such module exists in
  LiftNeutralFileModifier or MarkUpGen. Treat this as new work: an
  `.c2db`-mtime poller, same shape as `ui_dialogs.CiiPollingDialog`. If a
  C2Watchdog module exists elsewhere, surface it before this is built so it
  isn't duplicated.
- **`FORCES_READ` = manual/sidecar, confirmed as already fully implemented.**
  `line_ui.py`'s force entry (`_save_force`, `individual_forces` toggle) *is*
  this stage. No `.c2db` force reader exists anywhere; stays deferred exactly
  as HANDOFF.md scoped it.
- **State derivation from disk/DB presence, no new schema — confirmed
  already true.** `lift_cases` already carries `screenshot`, `layout_json`,
  `verdict`, `sheet_no`. No migration needed for state tracking.

## Architecture

**Single envelope exe**, `DocumenterApp` (from `app_ui.py`) as the shell,
argv-dispatched:

- bare folder arg → today's `lift_documenter.py` behaviour (open at that
  line/WO)
- `--new-line <dir>` → seed the tree at a freshly created line, same as
  `create_lift_case.py`'s folder resolution today
- `--open <file>` → open directly to a case/iso

**Merge depth: full in-process refactor** (not a child-process shell-out).
Concretely:

- `ui_dialogs.py`: every `tk.Tk()` dialog (`FolderSelectDialog`,
  `NodePromptDialog`, `LiftParamsDialog`, `CiiPollingDialog`,
  `ElementOverrideDialog`) becomes `tk.Toplevel(parent)`, parented to the
  running `DocumenterApp`. `show_message` stays a native `MessageBoxW` call
  (no change needed — it's already parent-agnostic).
- `lift_case_builder.run()` is restructured into a callable stage (e.g.
  `create_lift_case(app, line_root) -> Result`) that returns/raises instead
  of `sys.exit(0)`/`sys.exit(1)` at each early-out. Step numbering and
  sequencing (folder → nodes → params → copy → export → validate → patch →
  convert → sidecar) are unchanged — only the control-flow plumbing changes,
  not the CAESAR-facing logic.
- `neutral_reader.py`, `neutral_writer.py`, `neutral_patcher.py`,
  `iecho.py` — **untouched**. This is validated, CAESAR-format-sensitive
  code; the merge only changes how it's *invoked*, never its internals.
  `neutral_patcher.py`'s existing `from ui_dialogs import NodeLiftParams`
  import stays as-is — no headless/tkinter-free mode is in scope, so
  decoupling it buys nothing.
- New entry point on `LinePanel` (or a toolbar action on `DocumenterApp`):
  "Create lift case..." — invokes the refactored Creator stage against the
  currently-open line, then runs the same sidecar-ingest path
  `sync_cases()` already uses. No second window, no subprocess.

**Shared modules**: `lift_meta.py` and `line_layout.py` — currently
byte-identical, hand-copied into both trees — become single modules in the
merged package. `case_meta_ui.py`'s legacy-adoption path (manually authoring
a sidecar for a `.C2` the Creator never touched) is kept as-is; it's a
distinct, still-needed capability, not a duplicate of the Creator's sidecar
write.

**New: `tool_discovery.py`.** Generalizes `iecho.find_iecho()` into one
service resolving iecho.exe, the CAESAR input-GUI exe, and the CAESAR data
root — config → env → known install paths, cached, clear failure message
(same shape as the existing `find_iecho`, just widened). Runs once at
startup. Every CAESAR-driving action ("Create lift case...", eventually
"Open in CAESAR") gates on this probe; document-only mode (browse, mark up,
export existing sidecar-backed cases) works with zero CAESAR tools present,
exactly as HANDOFF.md's graceful-degradation constraint requires.

## Data / install location — preserved, not redesigned

The DB stays exactly where it is today: a `lift_doc_tool.cfg`-pointed
SQLite file, typically on a shared project drive (confirmed from the
provided `lift_doc_tool.cfg`, which points at a live network share serving
multiple engineers on one work order). The merged app does **not** change
this model or auto-relocate anyone's database.

- **Fresh machine, existing shared DB already in use by the team**: first
  run should find and reuse the existing `lift_doc_tool.cfg` next to
  wherever the previous exes were run from, if discoverable, or otherwise
  behave exactly as `lift_documenter.py` does today for a new install —
  point it at the team's existing shared `lift_markup.db`.
- **Migrating an install to a new location** (e.g. moving off the two old
  exes onto the merged one): a one-time copy of the existing DB (and cfg)
  to the new install location is an acceptable path, not a schema or
  location redesign. This is a deployment/copy step, not new application
  logic.
- No changes to `lift_db.py`'s schema or `doc_config.py`'s file format are
  needed for the merge itself.

## Zero-touch first run

Detected by the persistent cfg's absence at the expected location. Silent,
no dialogs, no manual file edits:

1. Seed `lift_case_config.ini` + `lift_doc_tool.cfg` from bundled
   `_MEIPASS` resources into the persistent app-data location (never edits
   the bundle itself — the existing `--onefile` trap note in HANDOFF.md
   still applies).
2. Run the `tool_discovery` probe once; cache the result in cfg.
3. Register **HKCU** (per-user, no elevation) context-menu verbs pointing at
   the running exe's own path, replacing the two separate verbs the old
   exes installed.
4. Resolve the DB path per the section above — reuse an existing shared DB
   if the machine/team already has one configured; otherwise behave as
   today's first-run does.

Registry rework is still its own small deliverable near the end, tested on
a clean machine, per HANDOFF.md's original note.

## Deferred (unchanged from HANDOFF.md)

- `.c2db` force reader — stays a stub; FORCES_READ stays manual/sidecar.
- Hierarchy-DB persistence redesign — explicitly out of scope (see Data
  section above).

## Newly-flagged unknowns (found during this pass, not in original HANDOFF.md)

- **RUN_PENDING completion detection has no existing implementation** to
  reuse (see Workflow section). Needs building fresh, or an existing
  C2Watchdog module needs to be located and provided.
- **`GENERATOR_SIDECAR_PATCH.md`** (in LiftNeutralFileModifier) describes a
  superseded flat-folder sidecar convention that doesn't match the current
  code (`line_layout.sidecar_dir()` / `.liftdoc`). Not a blocker — the real
  code already reflects the newer convention — but the file itself should
  not be treated as current documentation when merging.

## Build sequencing

Small, reviewable, always-runnable commits per CLAUDE.md. Proposed order:

1. Scaffold the merged package layout; move both trees in with shared
   `lift_meta.py`/`line_layout.py` deduplicated. No behaviour change —
   verify both tools still run from their existing entry points inside the
   new layout.
2. `tool_discovery.py` + capability-gated UI (buttons disabled when probe
   fails), wired into `DocumenterApp` startup.
3. `ui_dialogs.py` → `Toplevel` refactor, `lift_case_builder.run()` →
   callable stage. Verify the Creator flow still produces byte-identical
   `.CII`/sidecar output against a known-good test case before and after.
4. "Create lift case..." entry point wired into `LinePanel`/`DocumenterApp`.
5. argv dispatch (`--new-line`, `--open`) + single PyInstaller spec
   replacing the two existing `.spec` files.
6. Zero-touch first-run sequence (cfg seeding, tool_discovery probe,
   HKCU registration).
7. RUN_PENDING detection (new `.c2db`-mtime watcher), if no existing
   C2Watchdog module is provided in the meantime.
