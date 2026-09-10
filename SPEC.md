# Project: AutoLift

## Goal (1–2 sentences)
Merge two existing CAESAR II piping-stress tools — a lift-case Creator and a
stress mark-up Documenter — into one distributable Windows program for
Kårstø engineers, so they stop juggling two separate exes and re-entering
data by hand between them.

## Users
Piping stress engineers running CAESAR II analyses for lift work orders,
today using two independent exes (`create_lift_case.exe`,
`lift_documenter.exe`) that already hand data to each other via a
filesystem sidecar file, but ship, install, and launch separately.

## Stack / constraints
- **Language/framework**: Python 3.10+, Tkinter GUI, PyInstaller `--onefile`
  Windows exe.
- **Storage**: SQLite (the Documenter's `lift_db.py`) for the mark-up
  database; flat sidecar JSON files (`*_liftmeta.json`) as the
  Creator→Documenter handoff; plain key=value / INI config files.
- **Deploy target**: Windows 10/11 engineering workstations. Distributed as
  a single exe with self-installing, per-user (HKCU) context-menu verbs —
  no separate installer, no admin elevation.
- **Hard constraints (must / must-not)**:
  - Must **not** embed CAESAR II or `iecho.exe` (SPLM/Hexagon licensing) —
    discover and drive the local install only, never bundle it.
  - Must degrade gracefully on a machine without CAESAR II installed —
    document-only features (browsing, marking up, exporting existing
    sidecar-backed cases) must keep working.
  - Must preserve the existing shared/network-drive database model as-is —
    no forced per-machine relocation of a team's `lift_markup.db`.
  - Must not change the sidecar JSON schema, the SQLite schema, or the
    CAESAR neutral-file patching logic without an explicit, logged decision
    — these are the external contracts the two programs (and any
    hand-adopted legacy case) already rely on.
  - Windows-only. No macOS/Linux support.

## In scope (v1)
- **Phase 0 — shipped.** Both programs bundled behind one exe
  (`autolift.spec` → `AutoLift.exe`), self-installing context menus, **zero
  behaviour change** to either program.
- **Phase 1 — in progress.** The fuller in-process merge designed in
  MERGE_PLAN.md, broken into the milestones below.
- See **Milestones** for the ordered, currently-agreed build list.

## Explicitly OUT of scope (do not build)
- Automated support-function placement (deciding whether a location is a
  rest, hold-down, guide, limit stop, or anchor) — confirmed out of scope.
  This stays exactly as manual as it is today (the engineer types r/hd/g/l
  codes in the Documenter).
- Automated `.c2db` force-reading — stays a stub. Lift forces stay
  manual/sidecar entry (`individual_forces` toggle), exactly as today.
- Any CAESAR II or iecho functionality embedded/bundled inside the exe.
- A headless/CLI-only mode (e.g. decoupling `neutral_patcher.py` from
  `tkinter`) — no use case for it right now; logged as a reversible
  assumption in QUESTIONS.md.
- macOS/Linux support.

## Behaviour by example

1. **Create a lift case.** Given a line folder `46-P-1234/00_CII/` containing
   `46-P-1234_MAIN.C2` and nothing else, right-clicking the line folder →
   **"Full .C2 Lift Creation"** → entering lifted nodes `340` and `430` with
   default spacing/displacement → produces `46-P-1234_N340-N430.C2`, the
   patched `46-P-1234_N340-N430.CII`, and a sidecar
   `00_CII/.liftdoc/46-P-1234_N340-N430_liftmeta.json` recording supports
   `[340, 430]` and the two outer lift points.

2. **Pick it up automatically.** Given that sidecar exists, right-clicking
   anywhere in the line/work-order folder → **"Open Lift Mark-up
   Documenter"** → the case `46-P-1234_N340-N430` already appears in the
   tree under its line, with supports and lift points pre-filled — no
   manual re-entry of node numbers or distances.

3. **Single-window creation (Phase 1 target, not yet built).** From inside
   the already-open Documenter window, clicking a new **"Create lift
   case..."** entry point on an open line → the same result as example 1,
   with no second window or process launched.

4. **Issue a work order.** Given a work order with 3 lines, each with lift
   cases whose verdict is `OK`, clicking **"Export work order..."** →
   one PDF: every line's isometric first (alphabetical by line), then every
   lift sheet in the same line order, with `REFER SHEET` callouts on the
   isometrics resolved to the lift sheets' real, final page numbers.

## Acceptance criteria (definition of done)
- [ ] `pyinstaller autolift.spec` builds `AutoLift.exe` cleanly on Windows.
- [ ] Both context-menu verbs self-install on first run (HKCU, no admin
      prompt) and behave identically to the original two separate exes.
- [ ] Each Phase 1 milestone preserves Phase 0's zero-behaviour-change
      guarantee: for a known test case, `.CII`/sidecar output is
      byte-identical before and after that milestone's refactor.
- [ ] TESTING.md's tutorial can be followed successfully, end to end, by
      the user on a real Windows / CAESAR II workstation.
- [ ] No change to the sidecar JSON schema, SQLite schema, or CAESAR
      file-patching logic without an explicit decision logged in
      QUESTIONS.md.

(No "runs from a clean checkout via setup.sh" line — there's no
setup.sh/CI in this repo, and none is feasible for a Windows-only,
CAESAR-II-dependent Tkinter app. Verification is the manual tutorial in
TESTING.md instead. Logged as an assumption in QUESTIONS.md.)

## Milestones

Ordered, currently agreed (see QUESTIONS.md for how this was reached).
Work top-down; each one should land as its own small, reviewable, always-
runnable commit per CLAUDE.md.

1. **Phase 0 — package both programs into one exe.** ✅ **Done** (merged).
   Zero behaviour change; both programs run unmodified behind
   `src/launcher.py`; both context-menu verbs self-install via
   `src/install_context_menu.py`.
2. **`tool_discovery.py`.** Generalize `iecho.find_iecho()` into one service
   resolving iecho.exe, the CAESAR input-GUI exe, and the CAESAR data root
   (config → env → known paths, cached, clear failure message). Wire a
   capability probe into startup; gate CAESAR-driving actions on it.
3. **In-process Creator refactor.** `ui_dialogs.py`'s `tk.Tk()` dialogs →
   `tk.Toplevel(parent)`. `lift_case_builder.run()` → a callable stage that
   returns/raises instead of `sys.exit()`. `neutral_reader/writer/patcher.py`
   and `iecho.py` stay untouched. Verify byte-identical `.CII`/sidecar
   output against a known-good test case before and after.
4. **Single-window integration.** Wire a "Create lift case..." entry point
   into `DocumenterApp`/`LinePanel` that calls the refactored Creator stage
   in-process — no second window, no subprocess.
5. **Zero-touch first-run polish.** Seed `lift_case_config.ini` /
   `lift_doc_tool.cfg` from bundled resources into the persistent app-data
   location on first run; run the `tool_discovery` probe once and cache the
   result. (argv dispatch and HKCU registration already shipped in Phase 0
   — this milestone is just the remaining cfg-seeding + probe-caching
   piece.)
6. **RUN_PENDING completion detection.** A new `.c2db`-mtime watcher (same
   shape as `ui_dialogs.CiiPollingDialog`) — no existing "C2Watchdog"
   pattern was found to reuse, so this is new work. Lowest priority; the
   workflow already closes end-to-end without it (the engineer just
   switches to the Documenter themselves once CAESAR finishes solving).

## Known open decisions (pre-answer what you can)
- First-run DB discovery heuristic for milestone 5 (exactly where/how to
  find an existing `lift_doc_tool.cfg` on a fresh machine so a team's
  shared database is picked up with zero prompts) — not yet specified.
  Needs a concrete answer when milestone 5 starts.
- Whether milestone 6 (RUN_PENDING automation) is worth building at all,
  given it's net-new work with no existing pattern to reuse and the
  workflow already closes without it — flagged, not blocking milestones
  2–5.
