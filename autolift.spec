# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller autolift.spec
#
# One exe wrapping the two ORIGINAL, unmodified programs (src/creator =
# LiftNeutralFileModifier, src/documenter = MarkUpGen) behind src/launcher.py,
# which argv-dispatches to whichever program's own main() was requested.
# Replaces create_lift_case.spec and lift_documenter.spec.

block_cipher = None

a = Analysis(
    ['src/launcher.py'],
    pathex=['src', 'src/creator', 'src/documenter', 'src/shared'],
    binaries=[],
    datas=[],
    hiddenimports=[
        # launcher-side
        'install_context_menu',
        # creator (LiftNeutralFileModifier) modules imported by name
        'create_lift_case', 'config', 'copy_main_cii', 'iecho',
        'lift_case_builder', 'neutral_patcher', 'neutral_reader',
        'neutral_writer', 'ui_dialogs',
        # documenter (MarkUpGen) modules imported by name
        'lift_documenter', 'app_ui', 'case_meta_ui', 'doc_config',
        'line_ui', 'wo_ui', 'sheet_canvas', 'export', 'work_order',
        'iso_overlay', 'pdf_render', 'layout_builder', 'catalog',
        'cloud_geom', 'lift_calc', 'lift_db', 'sheet_model',
        'clipboard_io', 'fonts', 'markup_weights_ui', 'preview',
        'preview_pane',
        # shared
        'lift_meta', 'line_layout',
        # third-party bits PyInstaller under-detects (carried over from the
        # two original .spec files)
        'PIL._tkinter_finder', 'PIL.ImageGrab',
        'win32clipboard', 'win32con', 'win32com.client', 'pythoncom',
        'pywintypes',
        'pypdf', 'pypdf._writer', 'pypdf._reader',
        'fitz', 'fitz._fitz',
        'reportlab.pdfgen.canvas',
        'reportlab.pdfbase.ttfonts',
        'reportlab.pdfbase._fontdata',
        'reportlab.graphics.barcode.code128',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AutoLift',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # --noconsole
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
