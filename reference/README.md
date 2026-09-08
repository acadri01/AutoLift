# Reference documentation

Official Hexagon CAESAR II documentation — public vendor material, not proprietary. Copied from
the `acadri01/Conduit` project's `reference/` folder (a separate, independent CAESAR II tool by
the same user) for use here — **always consult these before making any claim about, or writing
code that touches, the neutral file format or CAESAR II's input/output behavior.** A prose summary
in this repo's own docs is a starting point, not a substitute.

- **`NeutralFile-v15.pdf`** — "CAESAR II Neutral File" chapter of the CAESAR II Users Guide (v15
  interface). The authoritative source for `.CII` structure: section layout, fixed-width record
  formats, field-by-field meaning of `#$ CONTROL`, `#$ ELEMENTS`, `#$ AUX_DATA` and its
  subsections, restraint type codes, etc. Read this before touching `neutral_reader.py`,
  `neutral_writer.py`, or `neutral_patcher.py`.
- **`Output-Tab.pdf`** — CAESAR II 15.1 "Output Tab" help: the GUI results-review surface
  (Classic Static Output Processor vs. New Analysis Reviewer).
- **`New-Analysis-Reviewer-Help.pdf`** — the modern results reviewer: supported piping codes,
  navigation, what each report shows.
- **`Static-Analysis-Help.pdf`** — running a static analysis (error check, batch run) and what
  "Send to Text (ASCII) File" / report export actually produces.
- **`Static-Analysis-Output-Help.pdf`** — the Standard Reports themselves (Code Compliance,
  Restraints, Displacements, Stresses, …) and the Report Template Editor.
- **`B31.3-2024.pdf`** — the full ASME B31.3-2024 piping code, for reference.

## What's deliberately not here

The `pipe-stress-engineering/` subfolder from Conduit (excerpts from a commercial textbook, plus a
material-database printout) was **not** copied over — out of scope for what AutoLift needs right
now, and licensing terms for that material weren't cleared for this repo. If a future task needs
it, copy it in deliberately at that point rather than reflexively.

## Empirical cross-check available, not copied here

Conduit's own `docs/neutral-file/WALKTHROUGH.md` and `SPEC.md` document real, byte-level
verification of several sections against actual real-sample `.cii` files (not just this vendor
PDF's prose) — notably `#$ BEND` (confirmed: field 1 is a plain radius number, not a
Short/Long/3D/5D preset pointer; the record's angle fields are *not* reliably understood and
should not be relied on) and `#$ RESTRANT` (confirmed: an element must carry a pointer to its
restraint record, or CAESAR silently ignores it). Worth re-consulting (in the Conduit repo, not
copied here) before extending this repo's own neutral-file logic — see PROGRESS.md/QUESTIONS.md
here for where that cross-check already informed AutoLift's rigid/bend element-selection logic.
