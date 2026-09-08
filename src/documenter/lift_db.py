"""
lift_db.py
----------
SQLite store. Hierarchy: work_orders -> lines -> (line_isos, lift_cases).

Independent of job folders; location in lift_doc_tool.cfg.
Screenshots -> db_dir/images/<line>/<case>.png
Iso PDFs    -> db_dir/isos/<line>/<file>   (copied in on ingest)

Archiving (soft): work_orders.archived and lines.archived flag rows out of the
active views without deleting anything. wo_id is retained, so an archived line
still knows its work order. Readers exclude archived rows by default; the
archive browser and admin tools pass include_archived=True.

Purging (hard): admin-only. Deletes rows (ON DELETE CASCADE handles children)
and, with delete_files=True, the db-managed copies (iso PDFs + screenshots)
under db_dir. External job folders (lines.folder / lift_cases.folder) are never
touched.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY, wo_no TEXT NOT NULL UNIQUE,
    folder TEXT, archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT,
    created TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS lines (
    id INTEGER PRIMARY KEY,
    wo_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    line_no TEXT NOT NULL, folder TEXT, seq INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT,
    created TEXT NOT NULL, UNIQUE(wo_id, line_no));

CREATE TABLE IF NOT EXISTS line_isos (
    id INTEGER PRIMARY KEY,
    line_id INTEGER NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL DEFAULT 0, src_pdf TEXT NOT NULL,
    src_page INTEGER NOT NULL DEFAULT 0, note TEXT, layout_json TEXT,
    created TEXT NOT NULL, updated TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS lift_cases (
    id INTEGER PRIMARY KEY,
    line_id INTEGER NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
    case_name TEXT NOT NULL, folder TEXT, disp_mm REAL, screenshot TEXT,
    note_override TEXT, verdict TEXT NOT NULL DEFAULT 'PENDING',
    verdict_reason TEXT, sheet_no INTEGER, layout_json TEXT,
    force_include INTEGER NOT NULL DEFAULT 0,
    individual_forces INTEGER NOT NULL DEFAULT 0,
    seq INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL, updated TEXT NOT NULL, UNIQUE(line_id, case_name));

CREATE TABLE IF NOT EXISTS supports (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES lift_cases(id) ON DELETE CASCADE,
    node INTEGER NOT NULL, fn_codes TEXT NOT NULL DEFAULT '',
    seq INTEGER NOT NULL DEFAULT 0, UNIQUE(case_id, node));

CREATE TABLE IF NOT EXISTS lift_points (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES lift_cases(id) ON DELETE CASCADE,
    node INTEGER NOT NULL, support_node INTEGER, distance_mm REAL,
    disp_mm REAL, force_n REAL, seq INTEGER NOT NULL DEFAULT 0,
    UNIQUE(case_id, node));

CREATE INDEX IF NOT EXISTS ix_lines_wo   ON lines(wo_id);
CREATE INDEX IF NOT EXISTS ix_cases_line ON lift_cases(line_id);
CREATE INDEX IF NOT EXISTS ix_isos_line  ON line_isos(line_id);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)


class LiftDb:
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.dir = os.path.dirname(self.path)
        os.makedirs(self.dir, exist_ok=True)
        self.cx = sqlite3.connect(self.path)
        self.cx.row_factory = sqlite3.Row
        self.cx.execute("PRAGMA foreign_keys = ON")
        self.cx.executescript(SCHEMA)
        self._migrate()
        self.cx.commit()

    def _migrate(self) -> None:
        """Additive, idempotent column adds for databases created earlier."""
        cols = {r["name"] for r in
                self.cx.execute("PRAGMA table_info(lift_cases)").fetchall()}
        if "force_include" not in cols:
            self.cx.execute(
                "ALTER TABLE lift_cases ADD COLUMN "
                "force_include INTEGER NOT NULL DEFAULT 0")
        if "individual_forces" not in cols:
            self.cx.execute(
                "ALTER TABLE lift_cases ADD COLUMN "
                "individual_forces INTEGER NOT NULL DEFAULT 0")
        if "seq" not in cols:
            self.cx.execute(
                "ALTER TABLE lift_cases ADD COLUMN "
                "seq INTEGER NOT NULL DEFAULT 0")

        lcols = {r["name"] for r in
                 self.cx.execute("PRAGMA table_info(lines)").fetchall()}
        if "archived" not in lcols:
            self.cx.execute(
                "ALTER TABLE lines ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            self.cx.execute("ALTER TABLE lines ADD COLUMN archived_at TEXT")

        wcols = {r["name"] for r in
                 self.cx.execute("PRAGMA table_info(work_orders)").fetchall()}
        if "archived" not in wcols:
            self.cx.execute(
                "ALTER TABLE work_orders ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            self.cx.execute("ALTER TABLE work_orders ADD COLUMN archived_at TEXT")

    def close(self) -> None:
        self.cx.close()

    # -- paths ------------------------------------------------------------
    def image_path(self, line_no: str, case_name: str) -> str:
        d = os.path.join(self.dir, "images", _safe(line_no))
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, _safe(case_name) + ".png")

    def iso_dir(self, line_no: str) -> str:
        d = os.path.join(self.dir, "isos", _safe(line_no))
        os.makedirs(d, exist_ok=True)
        return d

    def abs_image(self, rel: Optional[str]) -> Optional[str]:
        return self.abs(rel)

    def abs(self, rel: Optional[str]) -> Optional[str]:
        if not rel:
            return None
        p = os.path.join(self.dir, rel)
        return p if os.path.isfile(p) else None

    def rel(self, absolute: str) -> str:
        return os.path.relpath(absolute, self.dir)

    # -- work orders ------------------------------------------------------
    def get_or_create_wo(self, wo_no: str, folder: str = "") -> int:
        row = self.cx.execute("SELECT id FROM work_orders WHERE wo_no=?", (wo_no,)).fetchone()
        if row:
            if folder:
                self.cx.execute("UPDATE work_orders SET folder=? WHERE id=?", (folder, row["id"]))
                self.cx.commit()
            return row["id"]
        cur = self.cx.execute("INSERT INTO work_orders (wo_no, folder, created) VALUES (?,?,?)",
                              (wo_no, folder, _now()))
        self.cx.commit()
        return cur.lastrowid

    def get_wo(self, wo_id: int) -> Optional[sqlite3.Row]:
        return self.cx.execute("SELECT * FROM work_orders WHERE id=?", (wo_id,)).fetchone()

    def wos(self, include_archived: bool = False) -> List[sqlite3.Row]:
        """Work orders, alphabetical. Archived excluded unless asked."""
        if include_archived:
            return self.cx.execute(
                "SELECT * FROM work_orders ORDER BY wo_no").fetchall()
        return self.cx.execute(
            "SELECT * FROM work_orders WHERE archived=0 ORDER BY wo_no").fetchall()

    def lines_for_wo(self, wo_id: int,
                     include_archived: bool = False) -> List[sqlite3.Row]:
        """Lines of a work order. Archived excluded unless asked (this is what
        keeps archived lines out of the tree, the WO overview and exports)."""
        if include_archived:
            return self.cx.execute(
                "SELECT * FROM lines WHERE wo_id=? ORDER BY line_no",
                (wo_id,)).fetchall()
        return self.cx.execute(
            "SELECT * FROM lines WHERE wo_id=? AND archived=0 ORDER BY line_no",
            (wo_id,)).fetchall()

    # -- archive (soft) ---------------------------------------------------
    def archive_wo(self, wo_id: int) -> None:
        self.cx.execute("UPDATE work_orders SET archived=1, archived_at=? WHERE id=?",
                        (_now(), wo_id))
        self.cx.commit()

    def restore_wo(self, wo_id: int) -> None:
        self.cx.execute("UPDATE work_orders SET archived=0, archived_at=NULL WHERE id=?",
                        (wo_id,))
        self.cx.commit()

    def archive_line(self, line_id: int) -> None:
        self.cx.execute("UPDATE lines SET archived=1, archived_at=? WHERE id=?",
                        (_now(), line_id))
        self.cx.commit()

    def restore_line(self, line_id: int) -> None:
        self.cx.execute("UPDATE lines SET archived=0, archived_at=NULL WHERE id=?",
                        (line_id,))
        self.cx.commit()

    def archived_wos(self) -> List[sqlite3.Row]:
        return self.cx.execute(
            "SELECT * FROM work_orders WHERE archived=1 ORDER BY wo_no").fetchall()

    def archived_lines(self) -> List[sqlite3.Row]:
        """Archived lines with their work-order number (regardless of whether
        the work order itself is archived)."""
        return self.cx.execute(
            "SELECT l.*, w.wo_no AS wo_no "
            "FROM lines l JOIN work_orders w ON w.id = l.wo_id "
            "WHERE l.archived=1 ORDER BY w.wo_no, l.line_no").fetchall()

    # -- lines ------------------------------------------------------------
    def get_or_create_line(self, wo_id: int, line_no: str, folder: str = "") -> int:
        row = self.cx.execute("SELECT id FROM lines WHERE wo_id=? AND line_no=?",
                              (wo_id, line_no)).fetchone()
        if row:
            if folder:
                self.cx.execute("UPDATE lines SET folder=? WHERE id=?", (folder, row["id"]))
                self.cx.commit()
            return row["id"]
        cur = self.cx.execute("INSERT INTO lines (wo_id, line_no, folder, created) VALUES (?,?,?,?)",
                              (wo_id, line_no, folder, _now()))
        self.cx.commit()
        return cur.lastrowid

    def get_line(self, line_id: int) -> Optional[sqlite3.Row]:
        return self.cx.execute("SELECT * FROM lines WHERE id=?", (line_id,)).fetchone()

    def line_no(self, line_id: int) -> str:
        r = self.get_line(line_id)
        return r["line_no"] if r else ""

    # -- isos -------------------------------------------------------------
    def ingest_iso(self, line_id: int, src_pdf: str, page: int) -> int:
        line_no = self.line_no(line_id)
        dest = os.path.join(self.iso_dir(line_no), _safe(os.path.basename(src_pdf)))
        if os.path.abspath(src_pdf) != os.path.abspath(dest):
            shutil.copy2(src_pdf, dest)
        seq = self.cx.execute("SELECT COALESCE(MAX(seq),-1)+1 AS n FROM line_isos WHERE line_id=?",
                              (line_id,)).fetchone()["n"]
        cur = self.cx.execute(
            "INSERT INTO line_isos (line_id, seq, src_pdf, src_page, created, updated) VALUES (?,?,?,?,?,?)",
            (line_id, seq, self.rel(dest), page, _now(), _now()))
        self.cx.commit()
        return cur.lastrowid

    def isos_for_line(self, line_id: int) -> List[sqlite3.Row]:
        return self.cx.execute("SELECT * FROM line_isos WHERE line_id=? ORDER BY seq, id",
                               (line_id,)).fetchall()

    def move_iso(self, line_id: int, iso_id: int, delta: int) -> bool:
        """
        Reorder an iso within its line by swapping seq with its neighbour.
        delta = -1 (up) or +1 (down). Returns True if a move happened.
        Normalises seq to 0..n-1 first so upload-order rows (all seq 0 in
        older data) become individually orderable.
        """
        isos = list(self.isos_for_line(line_id))
        # normalise to a dense 0..n-1 sequence in current display order
        for i, r in enumerate(isos):
            if r["seq"] != i:
                self.cx.execute("UPDATE line_isos SET seq=? WHERE id=?", (i, r["id"]))
        idx = next((i for i, r in enumerate(isos) if r["id"] == iso_id), None)
        if idx is None:
            return False
        j = idx + delta
        if j < 0 or j >= len(isos):
            self.cx.commit()
            return False
        a, b = isos[idx]["id"], isos[j]["id"]
        self.cx.execute("UPDATE line_isos SET seq=? WHERE id=?", (j, a))
        self.cx.execute("UPDATE line_isos SET seq=? WHERE id=?", (idx, b))
        self.cx.execute("UPDATE line_isos SET updated=? WHERE id IN (?,?)",
                        (_now(), a, b))
        self.cx.commit()
        return True

    def get_iso(self, iso_id: int) -> Optional[sqlite3.Row]:
        return self.cx.execute("SELECT * FROM line_isos WHERE id=?", (iso_id,)).fetchone()

    def set_iso_layout(self, iso_id: int, layout_json: Optional[str]) -> None:
        self.cx.execute("UPDATE line_isos SET layout_json=?, updated=? WHERE id=?",
                        (layout_json, _now(), iso_id))
        self.cx.commit()

    def set_iso_note(self, iso_id: int, note: Optional[str]) -> None:
        self.cx.execute("UPDATE line_isos SET note=?, updated=? WHERE id=?", (note, _now(), iso_id))
        self.cx.commit()

    def delete_iso(self, iso_id: int) -> None:
        self.cx.execute("DELETE FROM line_isos WHERE id=?", (iso_id,))
        self.cx.commit()

    # -- cases ------------------------------------------------------------
    def cases_for_line(self, line_id: int) -> List[sqlite3.Row]:
        return self.cx.execute(
            "SELECT * FROM lift_cases WHERE line_id=? ORDER BY seq, case_name",
            (line_id,)).fetchall()

    def move_case(self, line_id: int, case_id: int, delta: int) -> bool:
        """
        Reorder a lift case within its line by swapping seq with its neighbour.
        delta = -1 (up) or +1 (down). Returns True if a move happened.
        Normalises seq to 0..n-1 first so legacy rows (all seq 0, ordered by
        case_name) become individually orderable - mirrors move_iso.
        """
        cases = list(self.cases_for_line(line_id))
        # normalise to a dense 0..n-1 sequence in current display order
        for i, r in enumerate(cases):
            if r["seq"] != i:
                self.cx.execute("UPDATE lift_cases SET seq=? WHERE id=?", (i, r["id"]))
        idx = next((i for i, r in enumerate(cases) if r["id"] == case_id), None)
        if idx is None:
            return False
        j = idx + delta
        if j < 0 or j >= len(cases):
            self.cx.commit()
            return False
        a, b = cases[idx]["id"], cases[j]["id"]
        self.cx.execute("UPDATE lift_cases SET seq=? WHERE id=?", (j, a))
        self.cx.execute("UPDATE lift_cases SET seq=? WHERE id=?", (idx, b))
        self.cx.execute("UPDATE lift_cases SET updated=? WHERE id IN (?,?)",
                        (_now(), a, b))
        self.cx.commit()
        return True

    def get_case(self, case_id: int) -> Optional[sqlite3.Row]:
        return self.cx.execute("SELECT * FROM lift_cases WHERE id=?", (case_id,)).fetchone()

    def find_case(self, line_id: int, case_name: str) -> Optional[sqlite3.Row]:
        return self.cx.execute("SELECT * FROM lift_cases WHERE line_id=? AND case_name=?",
                               (line_id, case_name)).fetchone()

    def upsert_case_from_meta(self, wo_id: int, meta: Dict[str, Any], folder: str) -> int:
        line_id = self.get_or_create_line(wo_id, meta["line"], folder)
        existing = self.find_case(line_id, meta["case_name"])
        if existing:
            case_id = existing["id"]
            self.cx.execute("UPDATE lift_cases SET folder=?, disp_mm=?, updated=? WHERE id=?",
                            (folder, meta.get("disp_mm"), _now(), case_id))
        else:
            cur = self.cx.execute(
                "INSERT INTO lift_cases (line_id, case_name, folder, disp_mm, created, updated) VALUES (?,?,?,?,?,?)",
                (line_id, meta["case_name"], folder, meta.get("disp_mm"), _now(), _now()))
            case_id = cur.lastrowid

        for seq, s in enumerate(meta["supports"]):
            self.cx.execute(
                "INSERT INTO supports (case_id, node, fn_codes, seq) VALUES (?,?,'',?) "
                "ON CONFLICT(case_id, node) DO UPDATE SET seq=excluded.seq",
                (case_id, int(s["node"]), seq))
        self._prune(case_id, "supports", [int(s["node"]) for s in meta["supports"]])

        for seq, lp in enumerate(meta["lift_points"]):
            self.cx.execute(
                "INSERT INTO lift_points (case_id, node, support_node, distance_mm, disp_mm, seq) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(case_id, node) DO UPDATE SET "
                "support_node=excluded.support_node, distance_mm=excluded.distance_mm, "
                "disp_mm=excluded.disp_mm, seq=excluded.seq",
                (case_id, int(lp["node"]), lp.get("support_node"), lp.get("distance_mm"),
                 lp.get("disp_mm", meta.get("disp_mm")), seq))
        self._prune(case_id, "lift_points", [int(lp["node"]) for lp in meta["lift_points"]])
        self.cx.commit()
        return case_id

    def _prune(self, case_id: int, table: str, keep: List[int]) -> None:
        if not keep:
            return
        marks = ",".join("?" * len(keep))
        self.cx.execute(f"DELETE FROM {table} WHERE case_id=? AND node NOT IN ({marks})",
                        [case_id, *keep])

    def delete_case(self, case_id: int) -> None:
        self.cx.execute("DELETE FROM lift_cases WHERE id=?", (case_id,))
        self.cx.commit()

    def ingest_sidecars(self, wo_id: int, line_root: str) -> Dict[str, int]:
        """
        Read every *_liftmeta.json under <line_root>/00_CII/.liftdoc and upsert
        the cases - the same ingest the app runs on open, callable on demand so
        a freshly generated case appears without reopening. Idempotent.
        Returns {'added', 'updated', 'failed'}.
        """
        import lift_meta
        import line_layout
        added = updated = failed = 0
        for path in line_layout.find_sidecars(line_root):
            try:
                meta = lift_meta.read_sidecar(path)
            except Exception:
                failed += 1
                continue
            line_id = self.get_or_create_line(wo_id, meta["line"], line_root)
            existed = self.find_case(line_id, meta["case_name"]) is not None
            self.upsert_case_from_meta(wo_id, meta, line_root)
            if existed:
                updated += 1
            else:
                added += 1
        return {"added": added, "updated": updated, "failed": failed}

    # -- children ---------------------------------------------------------
    def supports_for(self, case_id: int) -> List[sqlite3.Row]:
        return self.cx.execute("SELECT * FROM supports WHERE case_id=? ORDER BY seq, node",
                               (case_id,)).fetchall()

    def lifts_for(self, case_id: int) -> List[sqlite3.Row]:
        return self.cx.execute("SELECT * FROM lift_points WHERE case_id=? ORDER BY seq, node",
                               (case_id,)).fetchall()

    # -- user writes ------------------------------------------------------
    def set_support_fn(self, support_id: int, fn_codes: str) -> None:
        self.cx.execute("UPDATE supports SET fn_codes=? WHERE id=?", (fn_codes, support_id))
        self.cx.commit()

    def set_lift_force(self, lift_id: int, force_n: Optional[float]) -> None:
        self.cx.execute("UPDATE lift_points SET force_n=? WHERE id=?", (force_n, lift_id))
        self.cx.commit()

    def set_screenshot(self, case_id: int, rel_path: Optional[str]) -> None:
        self.cx.execute("UPDATE lift_cases SET screenshot=?, updated=? WHERE id=?",
                        (rel_path, _now(), case_id))
        self.cx.commit()

    def set_verdict(self, case_id: int, verdict: str, reason: str) -> None:
        self.cx.execute("UPDATE lift_cases SET verdict=?, verdict_reason=?, updated=? WHERE id=?",
                        (verdict, reason, _now(), case_id))
        self.cx.commit()

    def set_force_include(self, case_id: int, include: bool) -> None:
        self.cx.execute("UPDATE lift_cases SET force_include=?, updated=? WHERE id=?",
                        (1 if include else 0, _now(), case_id))
        self.cx.commit()

    def set_individual_forces(self, case_id: int, individual: bool) -> None:
        self.cx.execute("UPDATE lift_cases SET individual_forces=?, updated=? WHERE id=?",
                        (1 if individual else 0, _now(), case_id))
        self.cx.commit()

    def set_note_override(self, case_id: int, text: Optional[str]) -> None:
        self.cx.execute("UPDATE lift_cases SET note_override=?, updated=? WHERE id=?",
                        (text, _now(), case_id))
        self.cx.commit()

    def set_layout(self, case_id: int, layout_json: Optional[str]) -> None:
        self.cx.execute("UPDATE lift_cases SET layout_json=?, updated=? WHERE id=?",
                        (layout_json, _now(), case_id))
        self.cx.commit()

    def get_layout(self, case_id: int) -> Optional[str]:
        r = self.cx.execute("SELECT layout_json FROM lift_cases WHERE id=?", (case_id,)).fetchone()
        return r["layout_json"] if r else None

    def set_sheet_no(self, case_id: int, sheet_no: Optional[int]) -> None:
        self.cx.execute("UPDATE lift_cases SET sheet_no=?, updated=? WHERE id=?",
                        (sheet_no, _now(), case_id))
        self.cx.commit()

    # -- admin: hard delete + backup -------------------------------------
    # Permanent removal. ON DELETE CASCADE (foreign_keys=ON) takes care of
    # isos, cases, supports and lift_points. Only db-managed file copies are
    # removed when delete_files=True; external job folders are not.
    def _line_files(self, line_id: int) -> List[str]:
        """Absolute paths of db-managed files (iso copies + screenshots)."""
        out: List[str] = []
        for r in self.cx.execute("SELECT src_pdf FROM line_isos WHERE line_id=?",
                                 (line_id,)).fetchall():
            p = self.abs(r["src_pdf"])
            if p:
                out.append(p)
        for r in self.cx.execute("SELECT screenshot FROM lift_cases WHERE line_id=?",
                                 (line_id,)).fetchall():
            p = self.abs(r["screenshot"])
            if p:
                out.append(p)
        return out

    @staticmethod
    def _remove_files(paths: List[str]) -> int:
        n = 0
        for p in paths:
            try:
                os.remove(p)
                n += 1
            except OSError:
                pass
        return n

    def _prune_line_dirs(self, line_no: str) -> None:
        """Remove now-empty per-line iso/image dirs. os.rmdir only succeeds on
        an empty dir, so a line_no shared by another work order is left alone."""
        for sub in ("isos", "images"):
            d = os.path.join(self.dir, sub, _safe(line_no))
            try:
                os.rmdir(d)
            except OSError:
                pass

    def purge_line(self, line_id: int, delete_files: bool = False) -> Dict[str, int]:
        """Permanently delete a line and everything under it."""
        ln = self.get_line(line_id)
        if not ln:
            return {"lines": 0, "isos": 0, "cases": 0, "files": 0}
        isos = self.cx.execute("SELECT COUNT(*) n FROM line_isos WHERE line_id=?",
                               (line_id,)).fetchone()["n"]
        cases = self.cx.execute("SELECT COUNT(*) n FROM lift_cases WHERE line_id=?",
                                (line_id,)).fetchone()["n"]
        files = self._line_files(line_id) if delete_files else []
        self.cx.execute("DELETE FROM lines WHERE id=?", (line_id,))
        self.cx.commit()
        nfiles = self._remove_files(files) if delete_files else 0
        if delete_files:
            self._prune_line_dirs(ln["line_no"])
        return {"lines": 1, "isos": isos, "cases": cases, "files": nfiles}

    def purge_wo(self, wo_id: int, delete_files: bool = False) -> Dict[str, int]:
        """Permanently delete a work order and every line/iso/case under it."""
        wo = self.get_wo(wo_id)
        if not wo:
            return {"work_orders": 0, "lines": 0, "isos": 0, "cases": 0, "files": 0}
        line_rows = self.cx.execute("SELECT id, line_no FROM lines WHERE wo_id=?",
                                    (wo_id,)).fetchall()
        isos = cases = 0
        files: List[str] = []
        for lr in line_rows:
            isos += self.cx.execute("SELECT COUNT(*) n FROM line_isos WHERE line_id=?",
                                    (lr["id"],)).fetchone()["n"]
            cases += self.cx.execute("SELECT COUNT(*) n FROM lift_cases WHERE line_id=?",
                                     (lr["id"],)).fetchone()["n"]
            if delete_files:
                files += self._line_files(lr["id"])
        self.cx.execute("DELETE FROM work_orders WHERE id=?", (wo_id,))
        self.cx.commit()
        nfiles = self._remove_files(files) if delete_files else 0
        if delete_files:
            for lr in line_rows:
                self._prune_line_dirs(lr["line_no"])
        return {"work_orders": 1, "lines": len(line_rows),
                "isos": isos, "cases": cases, "files": nfiles}

    def backup(self, dest: Optional[str] = None) -> str:
        """Copy the SQLite file to a timestamped sidecar and return its path."""
        if dest is None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = f"{self.path}.bak-{stamp}"
        self.cx.commit()
        shutil.copy2(self.path, dest)
        return dest
