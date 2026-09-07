"""
sheet_model.py  (schema 2)
--------------------------
Single source of truth for a mark-up sheet.

Coordinates: PDF points, origin BOTTOM-LEFT, A4 landscape.
The tkinter editor applies zoom + y-flip; it never owns geometry.

Plain data + JSON only. No tkinter. Stored in lift_cases.layout_json.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

import fonts
import doc_config as _cfg

# Page sizes, points
A4_LAND = (841.89, 595.28)
A3_LAND = (1190.55, 841.89)

# Default for lift sheets. Isos keep their own native mediabox, so page size
# lives on the layout - these are only the defaults.
PAGE_W, PAGE_H = A3_LAND
MARGIN = 34.0

SCHEMA_VERSION = 4

RED = "#FF0000"
FONT_SIZE = 18.0
TITLE_SIZE = 24.0
LINE_GAP = 1.18
BOX_PAD_X = 5.0
BOX_PAD_Y = 4.0
# --- markup line weights (points) -----------------------------------------
# One weight per markup type. These baked-in defaults are the compiled fallback
# ("Reset to baked-in" returns here). They can be tuned live in the editor via
#   Advanced > Markup line weights...
# which persists markup_<kind>= lines into lift_doc_tool.cfg. Weights resolve at
# DRAW TIME (see stroke_pt) - never stored on a shape - so any change applies to
# every document, past and future, with no migration.
MARKUP_KINDS = ("cloud", "line", "arrow", "dimension", "callout")
STROKE_MIN, STROKE_MAX = 0.5, 6.0
_STROKE_BAKED = {
    "cloud":     1.7,
    "line":      1.7,
    "arrow":     1.7,
    "dimension": 1.7,
    "callout":   1.7,
}
STROKE = _STROKE_BAKED["line"]     # back-compat alias (was a single 0.7)

_stroke_over = None                # cache: kind -> float, cfg overrides only


def clamp_stroke(v: float) -> float:
    return max(STROKE_MIN, min(STROKE_MAX, v))


def baked_weights() -> Dict[str, float]:
    """The compiled defaults (what Reset restores)."""
    return dict(_STROKE_BAKED)


def load_stroke_overrides() -> None:
    """(Re)load markup_<kind> overrides from lift_doc_tool.cfg into memory.
    Tolerant: a missing / malformed / out-of-range value simply leaves that
    type on its baked-in default rather than raising during a render."""
    global _stroke_over
    over: Dict[str, float] = {}
    data = _cfg.load()
    for k in MARKUP_KINDS:
        raw = data.get(f"markup_{k}")
        if raw is None:
            continue
        try:
            over[k] = clamp_stroke(float(raw))
        except (TypeError, ValueError):
            pass
    _stroke_over = over


def _overrides() -> Dict[str, float]:
    if _stroke_over is None:
        load_stroke_overrides()
    return _stroke_over


def stroke_pt(kind: str) -> float:
    """Effective line weight in points for a markup kind: cfg override if set,
    else the baked-in default."""
    return _overrides().get(kind, _STROKE_BAKED.get(kind, STROKE))


def effective_weights() -> Dict[str, float]:
    return {k: stroke_pt(k) for k in MARKUP_KINDS}


ARROW_LEN = 7.0
ARROW_HALF = 2.4
GRID = 2.0               # snap


def snap(v: float) -> float:
    return round(v / GRID) * GRID


# --------------------------------------------------------------------------
@dataclass
class ImageItem:
    path: str = ""
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0

    def fit_page(self, px_w: int, px_h: int, top_reserve: float = 34.0,
                 page: Tuple[float, float] = (PAGE_W, PAGE_H)) -> None:
        pw, ph = page
        avail_w = pw - 2 * MARGIN
        avail_h = ph - 2 * MARGIN - top_reserve
        s = min(avail_w / px_w, avail_h / px_h)
        self.w, self.h = px_w * s, px_h * s
        self.x = (pw - self.w) / 2.0
        self.y = MARGIN + (avail_h - self.h) / 2.0


ANCHORS = ("sw", "se", "nw", "ne", "n", "s", "w", "e", "c")


@dataclass
class TextBox:
    """
    kind: callout | note | title | sheet | free
    border=False gives a plain unboxed label.
    tip=None gives a box with no leader.

    (x, y) is the ANCHOR POINT, not the bottom-left. `anchor` says which
    part of the box is nailed to it. This is what stops a box drifting or
    running off the page when its text grows - e.g. when a force is first
    entered and a 2-line callout becomes 3 lines.

        nw  n  ne          right-gutter callouts -> "ne"  (grow left/down)
        w   c   e          left-gutter callouts  -> "nw"  (grow right/down)
        sw  s  se          centred note/title    -> "n"   (grow both ways)
                           sheet number          -> "se"
    """
    kind: str = "callout"
    text: str = ""
    x: float = 0.0
    y: float = 0.0
    anchor: str = "sw"
    tip: Optional[Tuple[float, float]] = None
    box_id: str = ""
    border: bool = True
    align: str = "left"
    size: float = FONT_SIZE
    bold: bool = False
    w: Optional[float] = None      # explicit width - None = auto-fit to text
    h: Optional[float] = None      # explicit height - None = auto-fit to text


@dataclass
class Dimension:
    """
    Four-point dimension.

        a2 o                          o b2
           |                          |
        a1 |<─────── 900 mm ─────────>| b1

    Lines: a1-a2 and b1-b2.
    Double-headed arrow: a1 ── b1, one head on each line's a1/b1 end.
    All four points drag independently.
    """
    a1: Tuple[float, float] = (0.0, 0.0)
    a2: Tuple[float, float] = (0.0, 0.0)
    b1: Tuple[float, float] = (0.0, 0.0)
    b2: Tuple[float, float] = (0.0, 0.0)
    text: str = ""
    label_pos: Optional[Tuple[float, float]] = None
    dim_id: str = ""


@dataclass
class Cloud:
    """
    Revision cloud: a closed polygon you draw vertex by vertex, rendered as
    outward-bulging scallops (see cloud_geom.scallops).

    case_id links it to a lift case - the label then reads "REFER SHEET n"
    and renumbers itself whenever the work order is reordered. case_id=None
    means a manual remark about the enclosed supports (free text).

    `bulge` is scallop sagitta as a fraction of edge length.
    """
    pts: List[Tuple[float, float]] = field(default_factory=list)
    text: str = ""
    label_pos: Optional[Tuple[float, float]] = None
    case_id: Optional[int] = None
    cloud_id: str = ""
    bulge: float = 0.16


@dataclass
class FreeLine:
    """Plain line, or single-headed arrow when arrow=True (head at p2)."""
    p1: Tuple[float, float] = (0.0, 0.0)
    p2: Tuple[float, float] = (0.0, 0.0)
    arrow: bool = False
    line_id: str = ""


@dataclass
class SheetLayout:
    schema: int = SCHEMA_VERSION
    kind: str = "lift"                 # lift | iso
    case_name: str = ""
    line_no: str = ""
    page_w: float = PAGE_W
    page_h: float = PAGE_H
    image: ImageItem = field(default_factory=ImageItem)   # lift sheets: screenshot
    iso_pdf: str = ""                 # iso sheets: source PDF (overlaid, never rasterised)
    iso_page: int = 0
    boxes: List[TextBox] = field(default_factory=list)
    dims: List[Dimension] = field(default_factory=list)
    lines: List[FreeLine] = field(default_factory=list)
    clouds: List[Cloud] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1)

    @staticmethod
    def from_json(s: str) -> "SheetLayout":
        d: Dict[str, Any] = json.loads(s)
        if d.get("schema") != SCHEMA_VERSION:
            raise ValueError(f"layout schema {d.get('schema')} (expected {SCHEMA_VERSION})")
        lay = SheetLayout(
            schema=d["schema"],
            kind=d.get("kind", "lift"),
            case_name=d.get("case_name", ""),
            line_no=d.get("line_no", ""),
            page_w=d.get("page_w", PAGE_W),
            page_h=d.get("page_h", PAGE_H),
            image=ImageItem(**d["image"]),
            iso_pdf=d.get("iso_pdf", ""),
            iso_page=d.get("iso_page", 0),
        )
        for b in d.get("boxes", []):
            b = dict(b)
            if b.get("tip") is not None:
                b["tip"] = tuple(b["tip"])
            lay.boxes.append(TextBox(**b))
        # Normalise font sizes: only the title is TITLE_SIZE; everything else
        # is the standard FONT_SIZE. This heals layouts saved under older
        # builds that used different or inconsistent sizes.
        for b in lay.boxes:
            b.size = TITLE_SIZE if b.kind == "title" else FONT_SIZE
        for m in d.get("dims", []):
            m = dict(m)
            for k in ("a1", "a2", "b1", "b2"):
                m[k] = tuple(m[k])
            if m.get("label_pos") is not None:
                m["label_pos"] = tuple(m["label_pos"])
            lay.dims.append(Dimension(**m))
        for l in d.get("lines", []):
            l = dict(l)
            l["p1"], l["p2"] = tuple(l["p1"]), tuple(l["p2"])
            lay.lines.append(FreeLine(**l))
        for cl in d.get("clouds", []):
            cl = dict(cl)
            cl["pts"] = [tuple(v) for v in cl.get("pts", [])]
            if cl.get("label_pos") is not None:
                cl["label_pos"] = tuple(cl["label_pos"])
            lay.clouds.append(Cloud(**cl))
        lay.normalize_fonts()
        return lay

    def normalize_fonts(self) -> None:
        """
        Enforce the single-size philosophy: the title is TITLE_SIZE, every
        other text box is FONT_SIZE. Guarantees consistency even for layouts
        saved under earlier versions with mixed sizes.
        """
        for b in self.boxes:
            if b.kind == "title" or b.box_id == "title":
                b.size = TITLE_SIZE
                b.bold = True
            else:
                b.size = FONT_SIZE

    def box(self, box_id: str) -> Optional[TextBox]:
        return next((b for b in self.boxes if b.box_id == box_id), None)

    def dim(self, dim_id: str) -> Optional[Dimension]:
        return next((d for d in self.dims if d.dim_id == dim_id), None)

    def cloud(self, cloud_id: str) -> Optional[Cloud]:
        return next((c for c in self.clouds if c.cloud_id == cloud_id), None)

    def fit_backdrop(self, px_w: int, px_h: int) -> None:
        """Fit a raster screenshot to THIS layout's page."""
        self.image.fit_page(px_w, px_h, page=(self.page_w, self.page_h))


# --------------------------------------------------------------------------
# Metrics - the parity guarantee between canvas and PDF
# --------------------------------------------------------------------------
def string_width(text: str, size: float = FONT_SIZE, bold: bool = False) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return stringWidth(text, fonts.bold() if bold else fonts.regular(), size)


def wrap_lines(text: str, size: float, bold: bool, max_w: float) -> List[str]:
    """
    Wrap text to fit within max_w (inner width, pad already removed).
    Respects explicit newlines, then word-wraps each paragraph.
    """
    if max_w <= 0:
        return text.split("\n")
    out: List[str] = []
    for para in text.split("\n"):
        words = para.split(" ")
        if not words:
            out.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            trial = cur + " " + w
            if string_width(trial, size, bold) <= max_w:
                cur = trial
            else:
                out.append(cur)
                cur = w
        out.append(cur)
    return out or [""]


import re as _re
_REF_RE = _re.compile(r"@@REF:(.+?)@@")

# Optional editor-side resolver: case_name -> sheet number (or None). When set
# (the editor sets it from the current work-order plan), an unresolved
# @@REF:case@@ token previews as the FINAL 'REFER SHEET n' string, so the box
# is sized in the editor exactly as it exports. When it is not set (previews,
# and PDF render where the token is already substituted), behaviour is
# unchanged - the legacy 'REFER SHEET [case]' preview.
_REF_RESOLVER = None


def set_ref_resolver(fn) -> None:
    """fn(case_name) -> Optional[int]. Pass None to clear."""
    global _REF_RESOLVER
    _REF_RESOLVER = fn


def ref_targets(text: str) -> List[str]:
    """Case names referenced by @@REF:...@@ tokens in `text`."""
    return _REF_RE.findall(text or "")


def resolve_ref(case: str) -> Optional[int]:
    """Provisional sheet number for a case via the active resolver, or None."""
    fn = _REF_RESOLVER
    if fn is None:
        return None
    try:
        return fn(case)
    except Exception:
        return None


def display_text(b: "TextBox") -> str:
    """
    The text actually shown. In the EDITOR an unresolved @@REF:case@@ token is
    previewed so the box is sized to what will be issued:
      * resolver set + case numbered -> 'REFER SHEET n'   (exact export width)
      * resolver set + case unknown  -> 'REFER SHEET ??'  (fixed-width mask)
      * no resolver (previews / PDF) -> 'REFER SHEET [case]' (legacy preview)
    The exporter substitutes the token in the text before render, so by PDF
    time there is no token left and this function is an identity there.
    """
    def repl(m):
        case = m.group(1)
        if _REF_RESOLVER is not None:
            n = resolve_ref(case)
            return f"REFER SHEET {n}" if n is not None else "REFER SHEET ??"
        return f"REFER SHEET [{case}]"
    return _REF_RE.sub(repl, b.text)


def box_lines(b: TextBox) -> List[str]:
    """The actual display lines for a box - wrapped if it has an explicit width."""
    txt = display_text(b)
    if b.w is not None:
        return wrap_lines(txt, b.size, b.bold, b.w - 2 * BOX_PAD_X)
    return txt.split("\n") or [""]


def box_size(text: str, size: float = FONT_SIZE, bold: bool = False) -> Tuple[float, float]:
    lines = text.split("\n") or [""]
    w = max((string_width(ln, size, bold) for ln in lines), default=0.0)
    return w + 2 * BOX_PAD_X, len(lines) * size * LINE_GAP + 2 * BOX_PAD_Y


def box_rect(b: TextBox) -> Tuple[float, float, float, float]:
    """-> (bottom_left_x, bottom_left_y, w, h), resolving the anchor.

    Sizing uses the DISPLAY text (REF tokens previewed), so a refer callout
    is sized to 'REFER SHEET [case]', not the raw token. Explicit w/h win.
    """
    disp = display_text(b)
    if b.w is not None or b.h is not None:
        lines = box_lines(b)
        auto_w, auto_h = box_size(disp, b.size, b.bold)
        w = b.w if b.w is not None else auto_w
        wrapped_h = len(lines) * b.size * LINE_GAP + 2 * BOX_PAD_Y
        h = b.h if b.h is not None else wrapped_h
    else:
        w, h = box_size(disp, b.size, b.bold)

    a = b.anchor if b.anchor in ANCHORS else "sw"
    dx = {"sw": 0.0, "w": 0.0, "nw": 0.0,
          "s": -w / 2, "c": -w / 2, "n": -w / 2,
          "se": -w, "e": -w, "ne": -w}[a]
    dy = {"sw": 0.0, "s": 0.0, "se": 0.0,
          "w": -h / 2, "c": -h / 2, "e": -h / 2,
          "nw": -h, "n": -h, "ne": -h}[a]
    return b.x + dx, b.y + dy, w, h


def box_anchor(b: TextBox) -> Tuple[float, float]:
    """Where the leader leaves the box: the border point facing the tip."""
    x, y, w, h = box_rect(b)
    cx, cy = x + w / 2.0, y + h / 2.0
    if b.tip is None:
        return cx, cy
    dx, dy = b.tip[0] - cx, b.tip[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    sx = (w / 2.0) / abs(dx) if dx else float("inf")
    sy = (h / 2.0) / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


# --------------------------------------------------------------------------
# Cloud geometry - shared by the canvas and the PDF renderer so they agree
# --------------------------------------------------------------------------
def _signed_area(pts: List[Tuple[float, float]]) -> float:
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def _resample(pts: List[Tuple[float, float]], step: float) -> List[Tuple[float, float]]:
    """Walk the closed polygon, emitting points ~step apart. Each edge gets a
    whole number of scallops so no stub appears at a vertex."""
    out: List[Tuple[float, float]] = []
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1e-9:
            continue
        k = max(1, int(round(L / step)))
        for j in range(k):
            t = j / k
            out.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    return out


def cloud_arcs(c: Cloud) -> List[Tuple]:
    """
    -> [(p0, c1, c2, p3), ...] cubic bezier scallops, each an outward-bulging
    semicircle. Two beziers per scallop (a semicircle needs two quarter arcs).
    """
    if len(c.pts) < 3:
        return []

    path = _resample(c.pts, c.bulge * 2.0)
    if len(path) < 3:
        return []

    ccw = _signed_area(c.pts) > 0
    K = 0.5522847498307936          # quarter-circle bezier constant
    out = []

    for i in range(len(path)):
        p = path[i]
        q = path[(i + 1) % len(path)]
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            continue

        ux, uy = dx / L, dy / L
        nx, ny = (uy, -ux) if ccw else (-uy, ux)   # outward
        r = L / 2.0
        mx, my = (p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0
        tx, ty = mx + nx * r, my + ny * r          # apex of the semicircle

        # quarter 1: p -> apex
        out.append((p,
                    (p[0] + nx * r * K, p[1] + ny * r * K),
                    (tx - ux * r * K, ty - uy * r * K),
                    (tx, ty)))
        # quarter 2: apex -> q
        out.append(((tx, ty),
                    (tx + ux * r * K, ty + uy * r * K),
                    (q[0] + nx * r * K, q[1] + ny * r * K),
                    q))
    return out


def cloud_centroid(c: Cloud) -> Tuple[float, float]:
    if not c.pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in c.pts) / len(c.pts),
            sum(p[1] for p in c.pts) / len(c.pts))
