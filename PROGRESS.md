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
