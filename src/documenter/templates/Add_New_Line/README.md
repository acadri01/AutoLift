# Add_New_Line template

Bundled starter content for the Documenter's "Add New Line" action
(`line_new.py`). Provided by direct instruction, 2026-09-14.

`00_CII/` holds the real per-line CAESAR support/config files (unchanged
across every new line) plus two files whose name carries the
`[Add_New_Line]` placeholder token:

- `[Add_New_Line]_Flange_Leakage_TRNC.xlsm`
- `[Add_New_Line]_MAIN.C2` (a blank starter CAESAR model)

`line_new.create_line()` copies this folder's contents into
`<WorkOrder>/<LineNumber>/00_CII/`, replacing `[Add_New_Line]` in those
two filenames with the real line number, and creates the line's other two
standard folders (`01_REFS`, `02_FINALISATION` — see `line_layout.py`)
directly rather than carrying empty directories in this template.

None of these files' own CONTENTS contain the placeholder token (verified
by inspecting every file's actual bytes when this was built) — only the
two filenames do.
