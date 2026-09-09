# Testing AutoLift

This document is two things:

1. A **step-by-step tutorial** — follow it top to bottom the first time,
   even if you've never built a Python project before.
2. A **living reference** you come back to whenever you need to test a
   change. The **"Test this now"** section at the top always holds the
   single current ask — check there first.

> **Honesty note on verification**: this project is currently built and
> reviewed from a Linux container that cannot run Windows, Tkinter GUIs, or
> `pywin32`/`winreg`. Every command below is correct against the actual
> `autolift.spec` / `requirements.txt` in this repo, and every Python file
> has been syntax-checked (`py_compile`), but **no one has run the actual
> Windows build yet**. Where this doc can't show verified real output, it
> says so plainly instead of inventing example output — that's a deliberate
> choice, not an oversight. The first time you run each step, please report
> back what you actually saw so this doc can be locked in as verified.

---

## Test this now

**First: update your local checkout.** See "Getting the latest changes"
under Step 1 below (`git checkout claude/repo-mapping-modules-xomccd` then
`git pull`), then rebuild with `python -m PyInstaller autolift.spec` (Step
3 — that exact form, not bare `pyinstaller`, which doesn't reliably work
on Windows). Compare `git log -1 --oneline` against what's shown at the
top of [PR #2](https://github.com/acadri01/AutoLift/pull/2) to confirm
you're on the latest commit.

1. **Three Documenter fixes from your report — please re-check all three:**
   - **Case order was alphabetical, not numeric by node** ("node 1000
     before node 200"). Fixed: the tree/preview/export now sort by node
     number (a "natural sort" — digit runs compare as numbers, not
     characters) whenever you haven't manually reordered a line's cases.
     Open a line with several lift cases whose node numbers aren't all the
     same digit-length and confirm they now read low to high.
   - **Reordering is now drag-and-drop**, not just Move up/down (both
     still work). In a line's overview, grab a row in the "Isometrics" or
     "Lift cases" list and drag it to a new position — it should move
     live as you drag, and the tree + preview should update once you
     release. Please test dragging both up and down, and across more than
     one position in a single drag.
   - **The Documenter no longer creates a phantom "work order"** for a
     folder that isn't actually one (this is what made "AutoLift" and
     "Lifting_Calcs" show up in your Work orders tree — see your
     screenshot). Right-clicking a folder that isn't a line or a work
     order now opens the Documenter at the tree root ("Select a work
     order.") instead of inventing an entry for that folder. **Your
     existing database still has the two old phantom entries** — this fix
     only stops new ones; remove "AutoLift" and "Lifting_Calcs" yourself
     via **Advanced → Database admin...** (select each, delete) whenever
     convenient. Also worth confirming: right-clicking your `AutoLift`
     install folder or the `Lifting_Calcs` container folder no longer adds
     anything new to the tree.

2. **New engineering logic in the Creator.** `neutral_patcher.py` walks
   past a rigid element, reducer, or expansion joint next to a lift/support
   node (instead of splitting it, which CAESAR can't accept a displacement
   on) to find the next plain pipe element. If the requested spacing
   doesn't fit what's actually usable on a candidate element — because the
   element itself is too short, a bend eats into it, or both — the walk
   keeps going outward, repeating until it finds an element that can hold
   the FULL requested spacing, never silently settling for less on a
   nearby insufficient element. Only if the whole pipe run is exhausted
   does it fall back to the override dialog. Checked so far against real
   `.cii` files (structural validity, sane numbers) and pure-function
   geometry unit checks — **still unverified**: whether a patched `.CII`
   actually converts through `iecho.exe` and opens correctly in CAESAR II,
   and whether the placement itself looks right to an engineer. If you
   have a job with a lift point near a rigid support, a bend, or a short
   element, please run "Full .C2 Lift Creation" on it, watch for the
   warning messages (they name exactly which elements were skipped and
   why), open the result in CAESAR II, and report back.

Lower priority, internal refactors that should be behaviour-preserving
(worth a quick sanity pass, not a dedicated test session): the grouped
"AutoLift" context-menu submenu (previously confirmed working, re-check
after pulling if you see anything odd), `tool_discovery.py`'s iecho.exe
path resolution, and `lift_case_builder.run()` returning a value instead
of calling `sys.exit()` directly. None of these should change what you
see or click through — if they do, that's a real regression worth
reporting.

---

## Prerequisites

- **Windows 10 or 11.** This program will not run on macOS or Linux.
- **Python 3.10 or later** — [python.org](https://www.python.org/downloads/)
  or the Microsoft Store. During install, tick **"Add python.exe to PATH."**
- **Git** (or download the repo as a ZIP from GitHub if you don't have Git).
- **CAESAR II** (with `iecho.exe` findable — default install paths are
  already known to the Creator) if you want to test the CAESAR-driving
  steps end to end. Not required just to build the exe or test the
  Documenter's document-only features.

## Step 1 — Get the code

**First time only:**

```
git clone https://github.com/acadri01/AutoLift.git
cd AutoLift
git checkout claude/repo-mapping-modules-xomccd
```

(That branch is the current work-in-progress being tested — it's the head
of [PR #2](https://github.com/acadri01/AutoLift/pull/2). Once that PR is
merged, `main` will have it and this checkout step won't be needed.)

(If you downloaded a ZIP from GitHub instead, extract it and `cd` into the
extracted folder — skip the `git` commands, but you'll need to re-download
the ZIP each time there's an update, since the steps below don't apply.)

### Getting the latest changes (every time after the first)

I never rewrite history on this branch — I only add commits — so a plain
`git pull` always works cleanly, no force needed:

```
cd AutoLift
git checkout claude/repo-mapping-modules-xomccd
git pull
```

Two things worth knowing:

- **Check for local changes first if you're unsure**: run `git status`
  before pulling. "nothing to commit, working tree clean" means you're
  safe to pull. `dist/`, `build/`, and `__pycache__/` are already
  gitignored, so build output never interferes.
- **If you do have local changes you don't want** (e.g. you edited a file
  to poke at something): `git stash` before pulling, or
  `git checkout -- .` to discard them, then pull.

You can always confirm you're on the latest commit with
`git log -1 --oneline` and compare against what's shown at the top of
[PR #2](https://github.com/acadri01/AutoLift/pull/2).

## Step 2 — Install the Python dependencies

From inside the `AutoLift` folder:

```
pip install -r requirements.txt
pip install pyinstaller
```

This installs: Pillow, pywin32, reportlab, pypdf, pymupdf, and PyInstaller
itself. `pywin32` will only install successfully on Windows — that's
expected, since the whole program is Windows-only.

**What to expect**: pip prints a line per package as it downloads and
installs, ending with something like `Successfully installed pillow-... 
pywin32-... reportlab-... pypdf-... pymupdf-... pyinstaller-...` (exact
versions depend on what's current on PyPI when you run it — not something
this doc can pin down for you in advance).

## Step 3 — Build the exe

```
python -m PyInstaller autolift.spec
```

(Confirmed on a real Windows machine: the bare `pyinstaller autolift.spec`
command can fail to run there — Windows doesn't always put the `Scripts`
folder pip installs console scripts into on your `PATH`, so the
`pyinstaller` command itself may not be found even though the package is
installed. Running it as `python -m PyInstaller` instead always works,
since it just asks the same Python you used for `pip install` to run the
module directly — no `PATH` dependency. Use `python -m PyInstaller` from
here on; if bare `pyinstaller` happens to work for you too, that's fine,
but don't rely on it.)

PyInstaller will analyze `src/launcher.py` and everything it (and the two
bundled programs) import, then produce a single-file executable. This
takes a minute or two the first time.

**What to expect**: a scrolling build log, ending with PyInstaller
reporting the EXE build completed and where it wrote the output. The exe
itself will be at:

```
dist\AutoLift.exe
```

If this step fails, the error will most likely be a missing hidden import
(a module PyInstaller's static analysis didn't discover on its own). Report
the exact traceback — `autolift.spec`'s `hiddenimports` list is easy to
extend once we know what's missing.

## Step 4 — Run it once

Double-click `dist\AutoLift.exe`, or from a terminal:

```
dist\AutoLift.exe
```

With no folder argument, this falls back to the Documenter's own default
behaviour (opens against the current working directory). On this first
run, it also silently writes two registry keys under
`HKCU\Software\Classes\Directory\Background\shell\` — no dialog, no admin
prompt.

**What to expect**: either the Lift Mark-up Documenter's first-run "choose
a database location" prompt (if no `lift_doc_tool.cfg` exists yet next to
the exe) or its main window, depending on whether a database is already
configured. No console window should appear (the build is `--noconsole`).

## Step 5 — Verify both context-menu verbs

Right-click empty space inside **any** folder in Windows Explorer. You
should see two new entries:

- **Full .C2 Lift Creation**
- **Open Lift Mark-up Documenter**

Right-click a folder that actually contains a CAESAR job (a `*_MAIN.C2`
file, and ideally a `00_CII`/`01_REFS`/`02_FINALISATION` structure) to test
each verb functionally:

- **Full .C2 Lift Creation** should behave exactly like the old
  `create_lift_case.exe` did: prompt for a folder if needed, prompt for
  lifted nodes and parameters, launch iecho interactively, patch the file,
  and report success.
- **Open Lift Mark-up Documenter** should behave exactly like the old
  `lift_documenter.exe` did: open the Documenter's window at that line or
  work order.

If either verb misbehaves compared to what you remember from the original
separate exes, that's a real bug in the packaging (launcher argv handling
or `sys.path` wiring) — not expected, and worth reporting immediately with
the exact steps you took.

## Step 6 — Moving or updating the exe

Because `install_context_menu.py` re-checks and rewrites the registry
command on every launch, moving `AutoLift.exe` to a new folder and running
it once should update both context-menu verbs to the new path automatically
— no manual registry editing, no separate uninstall/reinstall step.

---

## Developer reference

### What's actually being tested

Phase 0 (the current state of the repo) intentionally makes **zero
behavioural changes** to either original program — see MERGE_PLAN.md.
Testing it is therefore mostly testing the *packaging*: do both programs
still work, unmodified, when launched through the new shared exe and argv
dispatch, instead of their own separate exes?

### No automated test suite exists yet

There are currently no unit tests, no `pytest` config, and no CI in this
repo. If/when automated tests are added, the modules with the least
Windows/GUI/CAESAR coupling are the cheapest to start with — they're pure
functions or pure data transforms:

- `src/documenter/lift_calc.py` — force → documented kg, support-function
  text, note-block text. No I/O, no UI.
- `src/documenter/cloud_geom.py` — revision-cloud scallop geometry.
- `src/shared/lift_meta.py` — sidecar JSON schema round-trip
  (`write_sidecar` / `read_sidecar`).
- `src/creator/neutral_reader.py` / `neutral_writer.py` — CAESAR neutral
  file parsing/formatting, given a sample `.CII` fixture (would need a
  real, license-clean sample file to test against).
- `src/creator/tool_discovery.py`'s `find_iecho()` / `probe_capabilities()`
  — pure path resolution (config → env → known paths) plus a
  no-raise capability report, no Windows/CAESAR needed to exercise the
  logic itself (only the actual found paths are Windows-specific).
- `src/creator/neutral_patcher.py`'s `_bend_deflection_deg`,
  `_bend_tangent_length_mm`, `_read_bend_radii`, and `_bend_corner_radii` —
  pure geometry/parsing functions, no I/O, no CAESAR needed. Already
  spot-checked by hand during development (straight/45°/90°/180° deflection
  cases, known `R·tan(Δ/2)` tangent values, and a real `#$ BEND` byte
  fragment) but not committed as a real test file yet — worth formalizing
  first if this repo ever adds a test suite, since it's the highest-stakes
  pure logic in the codebase.

Everything else (both `ui_dialogs.py`/Tkinter, `iecho.py`'s subprocess
calls, `lift_db.py`'s SQLite access, PDF rendering) either needs Windows,
CAESAR II, or a real display to exercise meaningfully, which is why the
manual tutorial above is the primary test method for now.

### How to add a fixture / test

Not yet established — flag this in QUESTIONS.md if/when automated tests
are prioritized, so the fixture convention (where sample `.CII`/`.C2`
files live, how they're anonymized/synthetic to avoid shipping a real
client's model) is decided deliberately rather than improvised.
