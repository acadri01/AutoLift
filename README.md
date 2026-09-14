# AutoLift

Automating lifting work for Kårstø: one distributable Windows program that
wraps two CAESAR II piping-stress tools — a **lift-case Creator** and a
**mark-up Documenter** — behind a single exe and a pair of right-click
context-menu verbs.

> **Status**: Phase 0 (packaging) is built and merged — the two programs run
> exactly as they always have, just shipped as one exe with self-installing
> context menus. The fuller in-process merge (single window, automated
> workflow state) is designed in [MERGE_PLAN.md](MERGE_PLAN.md) but paused.
> See [SPEC.md](SPEC.md) for current scope and [PROGRESS.md](PROGRESS.md) /
> [QUESTIONS.md](QUESTIONS.md) for the running build log.

## Workflow

This is the most important thing to understand about the project: **what an
engineer actually does, end to end, and how the two tools hand work to each
other.**

### The engineering workflow

```
 1. NEW LINE                 A work-order/line folder exists with a
                              *_MAIN.C2 CAESAR input file, modelled by the
                              engineer in CAESAR II's own input GUI.
                              (Not part of this program — CAESAR II itself.)

 2. CREATE LIFT CASE          Right-click the line folder -> "Full .C2 Lift
    (the Creator)             Creation". The engineer enters which nodes are
                              being lifted and the spacing/displacement per
                              node. The Creator:
                                - copies *_MAIN.C2 to a new lift-case .C2
                                - launches CAESAR's iecho INTERACTIVELY so
                                  the engineer exports a .CII neutral file
                                  (there is no silent .C2->.CII path in
                                  CAESAR - this step always needs a human)
                                - validates the entered nodes against the
                                  model's actual restraints (warns, doesn't
                                  block, if they don't match)
                                - patches the .CII: splits the outer
                                  elements around the lifted nodes, injects
                                  the imposed-displacement records
                                - converts the patched .CII back to .C2
                                  SILENTLY (this direction has no GUI step)
                                - writes a small JSON "sidecar" file
                                  recording which nodes, which supports,
                                  and what distances were used

 3. RUN                       The engineer opens the new .C2 in CAESAR's
    (external, user-driven)   input GUI as normal and runs the solve. This
                              program does not run CAESAR's solver itself.

 4. MARK UP & DOCUMENT        Right-click any folder in the job -> "Open
    (the Documenter)          Lift Mark-up Documenter". It automatically
                              picks up every sidecar the Creator wrote (no
                              re-entry of node/support/distance data), and
                              the engineer:
                                - pastes in a screenshot of the CAESAR model
                                - types in the solved lift forces (CAESAR's
                                  .c2db results database isn't read
                                  automatically yet - see SPEC.md)
                                - tags each support's function (rest / hold
                                  -down / guide / limit stop / anchor)
                                - reviews/edits the auto-generated note text
                                  and mark-up sheet layout
                                - sets a verdict (OK / NOT OK / PENDING)
                              Then exports a single lift sheet, a full line
                              preview, or the whole work order as one
                              issue-ready PDF (isometrics first, then every
                              lift sheet, with REFER SHEET cross-references
                              resolved automatically).
```

### How the two tools actually connect

There is **no live connection** between the Creator and the Documenter —
only a filesystem handoff, and it already works end to end:

- The Creator writes `<case>_liftmeta.json` into a hidden
  `<line>/00_CII/.liftdoc/` folder next to the lift case it just built.
- The Documenter watches that same folder (on open, or via its "Sync cases"
  button) and ingests every sidecar it finds into its own SQLite database —
  idempotently, so re-running the ingest is always safe.
- A legacy or hand-created `.C2` file that never went through the Creator
  can be adopted the same way ("Add existing case..." in the Documenter),
  writing the identical sidecar format by hand.

This handshake, plus the job-folder layout convention it depends on
(`00_CII` / `01_REFS` / `02_FINALISATION`), is implemented once and shared
byte-for-byte between both programs — see `src/shared/`.

### What's actually built vs. designed

| | Status |
|---|---|
| Both programs run, unmodified, behind one exe | **Shipped** (Phase 0) |
| Both context-menu verbs self-install (HKCU, no admin) | **Shipped** (Phase 0) |
| Single-window app (no second Tk root for lift creation) | Designed, paused — [MERGE_PLAN.md](MERGE_PLAN.md) "Phase 1+" |
| Automatic run-complete / force-read detection | Designed, paused |
| Automated support-function (rest/hold-down/guide/limit-stop/anchor) placement | Not yet started — see [SPEC.md](SPEC.md) |

## Requirements

- **Windows 10/11** — both programs use `ctypes.windll`, `pywin32`, and
  Tkinter; this does not run on macOS/Linux.
- **CAESAR II** (with `iecho.exe`) installed locally for the Creator's
  CAESAR-driving steps. The Documenter's document-only features (mark-up,
  export) work without CAESAR present.
- Python 3.10+ and the packages in `requirements.txt`, only if you're
  *building* the exe — an end user just runs the built `AutoLift.exe`.

## Building and running

See **[TESTING.md](TESTING.md)** for the full step-by-step tutorial
(clone → install → build → run → verify both context-menu verbs), including
what to check and what to report back.

Quick reference, once prerequisites are installed:

```
pip install -r requirements.txt pyinstaller
pyinstaller autolift.spec
dist\AutoLift.exe
```

## Repository layout

```
src/
  creator/      LiftNeutralFileModifier, unmodified — the lift-case Creator
  documenter/   MarkUpGen, unmodified — the mark-up Documenter
  shared/       lift_meta.py, line_layout.py — the sidecar/folder contract
                both programs already shared byte-for-byte before the merge
  launcher.py   Single PyInstaller entry point; argv-dispatches to either
                program's own, untouched main()
  install_context_menu.py
                Self-installs both HKCU context-menu verbs on every launch
autolift.spec   One PyInstaller build -> dist/AutoLift.exe
requirements.txt
```

## Project docs

- [SPEC.md](SPEC.md) — goal, scope, acceptance criteria, milestones
- [MERGE_PLAN.md](MERGE_PLAN.md) — the full merge design, including the
  paused Phase 1+ work
- [TESTING.md](TESTING.md) — how to build and test the program
- [PROGRESS.md](PROGRESS.md) — running build log
- [QUESTIONS.md](QUESTIONS.md) — assumptions made and open questions
