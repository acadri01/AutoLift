"""
sheet_canvas.py
---------------
The WYSIWYG editor. A view over SheetLayout - it owns no geometry.

Canvas <-> PDF transform:
    canvas_x = pdf_x * zoom
    canvas_y = (PAGE_H - pdf_y) * zoom

Handles
    text box   : body, tip
    dimension  : a1, a2, b1, b2, label
    free line  : p1, p2, body

Mouse
    drag              move
    shift+drag        constrain a leader/line to 0/45/90 deg
    double-click box  edit text
    Delete            remove selected free item
    Ctrl+Z            undo
"""

from __future__ import annotations

import math
import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, List, Optional, Tuple

from PIL import Image, ImageTk

import catalog
import cloud_geom
import fonts
import sheet_model as M

HANDLE = 3.0            # px half-size
HIT = 6.0               # px grab radius
SEL = "#0066CC"


class SheetCanvas(ttk.Frame):
    def __init__(self, master, layout: M.SheetLayout,
                 specs: Optional[List] = None,
                 on_change: Optional[Callable[[], None]] = None,
                 backdrop: Optional[str] = None, backdrop_page: int = 0):
        super().__init__(master)
        self.layout = layout
        self.specs = specs or []
        self.on_change = on_change or (lambda: None)
        self.backdrop = backdrop            # iso PDF path, rasterised for on-screen preview only
        self.backdrop_page = backdrop_page
        self._backdrop_img = None
        self._backdrop_key = ()
        self._pal_drag: Optional[object] = None
        self._draw_cloud_pts: Optional[list] = None   # active vertex list while drawing

        self.zoom = 1.0
        self._ox = 0.0                          # pan offsets - set properly by
        self._oy = 0.0                          # fit(), but a <Configure> can
                                                # trigger redraw() first
        self._img_cache: Optional[ImageTk.PhotoImage] = None
        self._img_key: Tuple = ()
        self._undo: List[str] = []

        self._sel: Optional[Tuple] = None       # (obj, role)
        self._drag: Optional[Tuple] = None      # (obj, role, dx, dy)
        self._handles: List[Tuple] = []         # (obj, role, cx, cy)
        self._edit = None                       # in-place Text widget
        self._edit_obj = None
        self._tip = None                        # hover tooltip Toplevel
        self._tip_lbl = None

        self._build()
        self._user_view = False        # True once the user zooms/pans manually
        self.after(30, self._initial_fit)

    def _initial_fit(self, tries: int = 0) -> None:
        """
        Fit once the canvas has REAL geometry. The editor window starts
        maximized, and that settles asynchronously - fitting at the first
        after() tick sees a ~1 px canvas and lands on an absurd zoom (~4%).
        Retry briefly until the maximize has taken effect.
        """
        if ((self.cv.winfo_width() < 200 or self.cv.winfo_height() < 200)
                and tries < 40):
            self.after(50, lambda: self._initial_fit(tries + 1))
            return
        self.fit()

    # ==================================================================
    def _build(self) -> None:
        bar = ttk.Frame(self, padding=3)
        bar.pack(fill="x")
        ttk.Button(bar, text="Remove", command=self.delete_sel).pack(side="left", padx=1)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(bar, text="Draw cloud", command=self.start_cloud).pack(side="left", padx=1)
        ttk.Button(bar, text="+ vertex", command=self.add_vertex).pack(side="left", padx=1)
        ttk.Button(bar, text="- vertex", command=self.remove_vertex).pack(side="left", padx=1)
        ttk.Button(bar, text="Flip scallops", command=self.flip_cloud).pack(side="left", padx=1)
        ttk.Button(bar, text="Undo", command=self.undo).pack(side="left", padx=1)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(bar, text="Fit", command=self.fit).pack(side="left", padx=1)
        ttk.Button(bar, text="-", width=3, command=lambda: self.set_zoom(self.zoom / 1.25)).pack(side="left")
        ttk.Button(bar, text="+", width=3, command=lambda: self.set_zoom(self.zoom * 1.25)).pack(side="left")
        self.zlbl = ttk.Label(bar, text="100%", width=6)
        self.zlbl.pack(side="left", padx=4)

        split = ttk.Frame(self)
        split.pack(fill="both", expand=True)

        # ---- palette: everything the dataset knows that isn't placed yet
        pal = ttk.Frame(split)
        pal.pack(side="left", fill="y", padx=(0, 4))
        ttk.Label(pal, text="Available annotations",
                  font=("Segoe UI", 8, "bold"), padding=2).pack(anchor="w")
        self.pal = ttk.Treeview(pal, show="tree", selectmode="browse", height=24)
        self.pal.column("#0", width=232)
        self.pal.pack(fill="both", expand=True)
        ttk.Label(pal, text="Drag onto the sheet to place.\nRemove one and it comes back here.",
                  foreground="#777", font=("Segoe UI", 8), padding=2).pack(anchor="w")

        self.pal.bind("<ButtonPress-1>", self._pal_press)
        self.pal.bind("<B1-Motion>", self._pal_motion)
        self.pal.bind("<ButtonRelease-1>", self._pal_release)

        wrap = ttk.Frame(split, relief="sunken", borderwidth=1)
        wrap.pack(side="left", fill="both", expand=True)
        self.cv = tk.Canvas(wrap, bg="#8a8a8a", highlightthickness=0)
        self.cv.pack(fill="both", expand=True)

        self.cv.bind("<Configure>", self._on_configure)
        self.cv.bind("<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", self._motion)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<Double-Button-1>", self._dbl)
        self.cv.bind("<Motion>", self._hover)
        self.cv.bind("<Leave>", lambda e: self._hide_tip())
        # zoom: mouse wheel (Windows/Mac). pan: middle-drag, or right-drag.
        self.cv.bind("<MouseWheel>", self._wheel_zoom)
        self.cv.bind("<Button-4>", lambda e: self.set_zoom(self.zoom * 1.1, e.x, e.y))
        self.cv.bind("<Button-5>", lambda e: self.set_zoom(self.zoom / 1.1, e.x, e.y))
        self.cv.bind("<ButtonPress-2>", self._pan_start)
        self.cv.bind("<B2-Motion>", self._pan_move)
        self.cv.bind("<ButtonRelease-2>", self._pan_end)
        self.cv.bind("<ButtonPress-3>", self._pan_start)
        self.cv.bind("<B3-Motion>", self._pan_move)
        self.cv.bind("<ButtonRelease-3>", self._pan_end)

        top = self.winfo_toplevel()
        top.bind("<Delete>", lambda e: self.delete_sel())
        top.bind("<Control-z>", lambda e: self.undo())
        top.bind("<Escape>", lambda e: self._cancel_cloud())
        top.bind("<Return>", lambda e: self._finish_cloud())

    # ==================================================================
    # Transform  (pan offset _ox,_oy in canvas px + zoom)
    # ==================================================================
    def _pw(self) -> float:
        return getattr(self, "_page_w", M.PAGE_W)

    def _ph(self) -> float:
        return getattr(self, "_page_h", M.PAGE_H)

    def X(self, x: float) -> float:
        return x * self.zoom + self._ox

    def Y(self, y: float) -> float:
        return (self._ph() - y) * self.zoom + self._oy

    def px(self, cx: float) -> float:
        return (cx - self._ox) / self.zoom

    def py(self, cy: float) -> float:
        return self._ph() - (cy - self._oy) / self.zoom

    def _on_configure(self, e) -> None:
        """
        Canvas resized. Until the user has zoomed or panned manually, keep
        the page fitted (this is what snaps the view to full size when the
        maximized window finishes settling, or the preview toggle re-packs
        the editor). After a manual view change, just redraw.
        """
        if not getattr(self, "_user_view", False):
            self.fit()
        else:
            self.redraw()

    def fit(self) -> None:
        if not hasattr(self, "_page_w"):
            self._resolve_page()
        w = max(self.cv.winfo_width(), 50)
        h = max(self.cv.winfo_height(), 50)
        self.zoom = min(w / self._pw(), h / self._ph()) * 0.96
        # centre the page
        self._ox = (w - self._pw() * self.zoom) / 2.0
        self._oy = (h - self._ph() * self.zoom) / 2.0
        self._user_view = False
        self.zlbl.config(text=f"{self.zoom*100:.0f}%")
        self.redraw()

    def _resolve_page(self):
        # Use the LAYOUT's own page size so the editor matches export exactly.
        self._page_w = getattr(self.layout, "page_w", None) or M.PAGE_W
        self._page_h = getattr(self.layout, "page_h", None) or M.PAGE_H
        self._ox = getattr(self, "_ox", 0.0)
        self._oy = getattr(self, "_oy", 0.0)
        if self.backdrop:
            # iso pages: the backdrop PDF's mediabox is authoritative
            try:
                from pypdf import PdfReader
                b = PdfReader(self.backdrop).pages[self.backdrop_page].mediabox
                self._page_w, self._page_h = float(b.width), float(b.height)
                self.layout.page_w, self.layout.page_h = self._page_w, self._page_h
            except Exception:
                pass

    def set_zoom(self, z: float, cx: Optional[float] = None, cy: Optional[float] = None) -> None:
        """Zoom, keeping the canvas point (cx,cy) fixed. Defaults to centre."""
        if not hasattr(self, "_ox"):
            self._resolve_page()
        if cx is None:
            cx = self.cv.winfo_width() / 2.0
        if cy is None:
            cy = self.cv.winfo_height() / 2.0
        # world point under the cursor before zoom
        wx, wy = self.px(cx), self.py(cy)
        self.zoom = max(0.2, min(6.0, z))
        # solve offset so (wx,wy) still maps to (cx,cy)
        self._ox = cx - wx * self.zoom
        self._oy = cy - (self._ph() - wy) * self.zoom
        self._user_view = True
        self.zlbl.config(text=f"{self.zoom*100:.0f}%")
        self.redraw()

    def _wheel_zoom(self, e) -> None:
        factor = 1.1 if getattr(e, "delta", 0) > 0 else (1 / 1.1)
        self.set_zoom(self.zoom * factor, e.x, e.y)

    def _pan_start(self, e) -> None:
        self._pan_from = (e.x, e.y, self._ox, self._oy)
        self.cv.config(cursor="fleur")

    def _pan_move(self, e) -> None:
        if not getattr(self, "_pan_from", None):
            return
        x0, y0, ox0, oy0 = self._pan_from
        self._ox = ox0 + (e.x - x0)
        self._oy = oy0 + (e.y - y0)
        self._user_view = True
        self.redraw()

    def _pan_end(self, e) -> None:
        self._pan_from = None
        self.cv.config(cursor="")

    # ==================================================================
    # Undo
    # ==================================================================
    def push(self) -> None:
        self._undo.append(self.layout.to_json())
        del self._undo[:-40]

    def undo(self) -> None:
        if not self._undo:
            return
        restored = M.SheetLayout.from_json(self._undo.pop())
        self.layout.__dict__.update(restored.__dict__)
        self._sel = None
        self.redraw()
        self.on_change()

    # ==================================================================
    # Draw
    # ==================================================================
    def redraw(self) -> None:
        self._fill_palette()
        c = self.cv
        c.delete("all")
        self._handles = []

        c.create_rectangle(self.X(0), self.Y(self._ph()),
                           self.X(self._pw()), self.Y(0),
                           fill="white", outline="#333")
        # margin guide - dashed rectangle at the printable inset, so you can
        # see where the page edge and safe area are (matches export exactly)
        m = M.MARGIN
        c.create_rectangle(self.X(m), self.Y(self._ph() - m),
                           self.X(self._pw() - m), self.Y(m),
                           outline="#bbb", dash=(4, 3))

        self._draw_backdrop()
        self._draw_image()
        for cl in self.layout.clouds:
            self._draw_cloud(cl)
        if self._draw_cloud_pts is not None:
            self._draw_inprogress_cloud()
        for ln in self.layout.lines:
            self._draw_line(ln)
        for d in self.layout.dims:
            self._draw_dim(d)
        for b in self.layout.boxes:
            self._draw_box(b)

        for obj, role, cx, cy in self._handles:
            sel = self._sel == (id(obj), role)
            if role == "resize":
                # filled corner marker, slightly larger
                c.create_rectangle(cx - HANDLE, cy - HANDLE, cx + HANDLE, cy + HANDLE,
                                   fill="#0066CC", outline="white", width=1)
            else:
                c.create_rectangle(cx - HANDLE, cy - HANDLE, cx + HANDLE, cy + HANDLE,
                                   fill=SEL if sel else "white", outline=SEL, width=1)

    def _H(self, obj, role, x: float, y: float) -> None:
        self._handles.append((obj, role, self.X(x), self.Y(y)))

    def _draw_backdrop(self) -> None:
        if not self.backdrop:
            return
        w = max(int(round(self._pw() * self.zoom)), 1)
        h = max(int(round(self._ph() * self.zoom)), 1)
        key = (self.backdrop, self.backdrop_page, w, h)
        if key != self._backdrop_key:
            try:
                img = self._raster_pdf(self.backdrop, self.backdrop_page, w, h)
                from PIL import ImageTk
                self._backdrop_img = ImageTk.PhotoImage(img)
                self._backdrop_key = key
            except Exception:
                self._backdrop_img = None
        if self._backdrop_img:
            self.cv.create_image(self.X(0), self.Y(self._ph()),
                                 image=self._backdrop_img, anchor="nw")

    @staticmethod
    def _raster_pdf(path, page, w, h):
        """
        Rasterise one PDF page to a PIL image for the editing backdrop.
        Prefers PyMuPDF (pip 'pymupdf', no external binary). Falls back to
        pdf2image (needs poppler), then to a grey placeholder so the editor
        still works even if neither is installed.
        """
        from PIL import Image
        w, h = max(int(w), 1), max(int(h), 1)
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            pg = doc.load_page(page)
            rect = pg.rect
            zoom_x = w / rect.width if rect.width else 1.0
            zoom_y = h / rect.height if rect.height else 1.0
            pix = pg.get_pixmap(matrix=fitz.Matrix(zoom_x, zoom_y), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            doc.close()
            return img.resize((w, h), Image.LANCZOS)
        except Exception:
            pass
        try:
            from pdf2image import convert_from_path
            imgs = convert_from_path(path, first_page=page + 1, last_page=page + 1,
                                     size=(w, h))
            return imgs[0].convert("RGB")
        except Exception:
            return Image.new("RGB", (w, h), "#eeeeee")

    def _draw_image(self) -> None:
        im = self.layout.image
        if not im.path or im.w <= 0 or not os.path.isfile(im.path):
            return
        # pixel size from ZOOM only - X()/Y() include the pan offset and must
        # not be used to measure a width/height, or the image distorts.
        w = max(int(round(im.w * self.zoom)), 1)
        h = max(int(round(im.h * self.zoom)), 1)
        key = (im.path, w, h)
        if key != self._img_key:
            src = Image.open(im.path).convert("RGB")
            self._img_cache = ImageTk.PhotoImage(
                src.resize((w, h), Image.LANCZOS))
            self._img_key = key
        # top-left corner in canvas coords
        self.cv.create_image(self.X(im.x), self.Y(im.y + im.h),
                             image=self._img_cache, anchor="nw")

    def _arrow_pts(self, tip, frm) -> List[float]:
        tx, ty = self.X(tip[0]), self.Y(tip[1])
        fx, fy = self.X(frm[0]), self.Y(frm[1])
        ang = math.atan2(ty - fy, tx - fx)
        L, Hh = M.ARROW_LEN * self.zoom, M.ARROW_HALF * self.zoom
        bx, by = tx - L * math.cos(ang), ty - L * math.sin(ang)
        px, py = -math.sin(ang) * Hh, math.cos(ang) * Hh
        return [tx, ty, bx + px, by + py, bx - px, by - py]

    def _pxw(self, kind: str) -> int:
        """Editor pixel width for a markup kind: the PDF point weight scaled by
        zoom (X()/Y() map 1 pt -> `zoom` px), min 1 so it never vanishes.
        Keeps the canvas WYSIWYG with the exported PDF."""
        return max(1, int(round(M.stroke_pt(kind) * self.zoom)))

    def _draw_box(self, b: M.TextBox) -> None:
        x, y, w, h = M.box_rect(b)
        if b.tip is not None:
            a = M.box_anchor(b)
            self.cv.create_line(self.X(a[0]), self.Y(a[1]),
                                self.X(b.tip[0]), self.Y(b.tip[1]),
                                fill=M.RED, width=self._pxw("callout"))
            self.cv.create_polygon(self._arrow_pts(b.tip, a), fill=M.RED, outline=M.RED)
            self._H(b, "tip", *b.tip)

        x0, y0 = self.X(x), self.Y(y + h)
        x1, y1 = self.X(x + w), self.Y(y)
        if b.border:
            self.cv.create_rectangle(x0, y0, x1, y1, fill="white", outline=M.RED,
                                     width=self._pxw("callout"))

        size_px = max(int(round(b.size * self.zoom)), 1)
        fnt = (fonts.tk_family(), -size_px, "bold" if b.bold else "normal")
        ty = y0 + M.BOX_PAD_Y * self.zoom
        for ln in M.box_lines(b):
            if b.align == "center":
                self.cv.create_text((x0 + x1) / 2, ty, text=ln, fill=M.RED,
                                    font=fnt, anchor="n")
            else:
                self.cv.create_text(x0 + M.BOX_PAD_X * self.zoom, ty, text=ln,
                                    fill=M.RED, font=fnt, anchor="nw")
            ty += b.size * M.LINE_GAP * self.zoom

        # resize handle at bottom-right, only for the selected box (reduces clutter)
        if self._sel and self._sel[0] == id(b):
            self._H(b, "resize", x + w, y)

    def _draw_line(self, ln: M.FreeLine) -> None:
        self.cv.create_line(self.X(ln.p1[0]), self.Y(ln.p1[1]),
                            self.X(ln.p2[0]), self.Y(ln.p2[1]), fill=M.RED,
                            width=self._pxw("arrow" if ln.arrow else "line"))
        if ln.arrow:
            self.cv.create_polygon(self._arrow_pts(ln.p2, ln.p1), fill=M.RED, outline=M.RED)
        self._H(ln, "p1", *ln.p1)
        self._H(ln, "p2", *ln.p2)

    def _draw_dim(self, d: M.Dimension) -> None:
        c = self.cv
        for p, q in ((d.a1, d.a2), (d.b1, d.b2), (d.a1, d.b1)):
            c.create_line(self.X(p[0]), self.Y(p[1]), self.X(q[0]), self.Y(q[1]),
                          fill=M.RED, width=self._pxw("dimension"))
        c.create_polygon(self._arrow_pts(d.a1, d.b1), fill=M.RED, outline=M.RED)
        c.create_polygon(self._arrow_pts(d.b1, d.a1), fill=M.RED, outline=M.RED)

        for role in ("a1", "a2", "b1", "b2"):
            self._H(d, role, *getattr(d, role))

        if not d.text:
            return
        mid = ((d.a1[0] + d.b1[0]) / 2.0, (d.a1[1] + d.b1[1]) / 2.0)
        w, h = M.box_size(d.text)
        lp = d.label_pos or (mid[0] - w / 2.0, mid[1] + 5.0)
        lb = M.TextBox(kind="free", text=d.text, x=lp[0], y=lp[1], align="center")
        cx, cy = lp[0] + w / 2.0, lp[1] + h / 2.0
        if math.hypot(cx - mid[0], cy - mid[1]) > max(w, h):
            lb.tip = mid
        self._draw_box(lb)
        self._handles = [hh for hh in self._handles if hh[0] is not lb]
        self._H(d, "label", lp[0], lp[1])

    # ==================================================================
    # Hit testing
    # ==================================================================
    @staticmethod
    def _pt_seg_dist(px, py, ax, ay, bx, by) -> float:
        """Distance from point to segment, all in canvas px."""
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    def _hit(self, cx: float, cy: float):
        # 1. handles (vertices, tips, resize) take priority - fine control
        best, bd = None, HIT
        for obj, role, hx, hy in reversed(self._handles):
            dist = math.hypot(cx - hx, cy - hy)
            if dist <= bd:
                best, bd = (obj, role), dist
        if best:
            return best

        # 2. text box body -> whole-shape move (carries its leader tip)
        for b in reversed(self.layout.boxes):
            x, y, w, h = M.box_rect(b)
            if self.X(x) <= cx <= self.X(x + w) and self.Y(y + h) <= cy <= self.Y(y):
                return (b, "move")

        # 3. dimension outline -> move whole dimension
        for d in reversed(self.layout.dims):
            for p, q in ((d.a1, d.a2), (d.b1, d.b2), (d.a1, d.b1)):
                if self._pt_seg_dist(cx, cy, self.X(p[0]), self.Y(p[1]),
                                     self.X(q[0]), self.Y(q[1])) <= HIT:
                    return (d, "move")

        # 4. free line -> move
        for ln in reversed(self.layout.lines):
            if self._pt_seg_dist(cx, cy, self.X(ln.p1[0]), self.Y(ln.p1[1]),
                                 self.X(ln.p2[0]), self.Y(ln.p2[1])) <= HIT:
                return (ln, "move")

        # 5. cloud outline -> move
        for cl in reversed(self.layout.clouds):
            n = len(cl.pts)
            for i in range(n):
                a = cl.pts[i]; b = cl.pts[(i + 1) % n]
                if self._pt_seg_dist(cx, cy, self.X(a[0]), self.Y(a[1]),
                                     self.X(b[0]), self.Y(b[1])) <= HIT + 4:
                    return (cl, "move")
        return None

    def _hover(self, e) -> None:
        self.cv.config(cursor="fleur" if self._hit(e.x, e.y) else "")
        txt = self._ref_hover_text(e.x, e.y)
        if txt:
            self._show_tip(txt, e.x_root, e.y_root)
        else:
            self._hide_tip()

    def _ref_hover_text(self, cx: float, cy: float) -> Optional[str]:
        """Case name(s) behind a REFER-SHEET callout under the cursor, so you
        can confirm which case a callout points at while its box shows only the
        sheet number."""
        for b in reversed(self.layout.boxes):
            names = M.ref_targets(b.text)
            if not names:
                continue
            x, y, w, h = M.box_rect(b)
            if self.X(x) <= cx <= self.X(x + w) and self.Y(y + h) <= cy <= self.Y(y):
                rows = []
                for nm in names:
                    n = M.resolve_ref(nm)
                    rows.append(f"Sheet {n}:  {nm}" if n is not None
                                else f"Refers to:  {nm}")
                return "\n".join(rows)
        return None

    def _ensure_tip(self) -> None:
        if self._tip is None:
            self._tip = tk.Toplevel(self)
            self._tip.wm_overrideredirect(True)
            try:
                self._tip.attributes("-topmost", True)
            except tk.TclError:
                pass
            self._tip_lbl = tk.Label(self._tip, justify="left", bg="#ffffe0",
                                     fg="#000000", relief="solid", bd=1,
                                     font=("Segoe UI", 8), padx=4, pady=2)
            self._tip_lbl.pack()
            self._tip.withdraw()

    def _show_tip(self, text: str, rx: int, ry: int) -> None:
        self._ensure_tip()
        self._tip_lbl.config(text=text)
        self._tip.geometry(f"+{int(rx) + 14}+{int(ry) + 14}")
        self._tip.deiconify()

    def _hide_tip(self) -> None:
        if self._tip is not None:
            try:
                self._tip.withdraw()
            except tk.TclError:
                pass

    def _press(self, e) -> None:
        if self._draw_cloud_pts is not None:
            self._draw_cloud_pts.append((M.snap(self.px(e.x)), M.snap(self.py(e.y))))
            self.redraw()
            return
        hit = self._hit(e.x, e.y)
        if not hit:
            self._sel = None
            self.redraw()
            return
        obj, role = hit
        self._sel = (id(obj), role)
        self.push()
        px, py = self.px(e.x), self.py(e.y)
        if role == "move":
            # capture a snapshot of the whole shape's geometry to translate it
            self._drag = (obj, role, px, py)
            self._move_snapshot = self._snapshot(obj)
        else:
            ox, oy = self._get(obj, role)
            self._drag = (obj, role, px - ox, py - oy)
        self.redraw()

    def _motion(self, e) -> None:
        if not self._drag:
            return
        obj, role, dx, dy = self._drag
        if role == "move":
            # dx,dy hold the press-point; translate the whole shape by delta
            tx = M.snap(self.px(e.x)) - self._round(dx)
            ty = M.snap(self.py(e.y)) - self._round(dy)
            self._translate(obj, self._move_snapshot, tx, ty)
            self.redraw()
            return
        nx, ny = M.snap(self.px(e.x) - dx), M.snap(self.py(e.y) - dy)
        if e.state & 0x0001:            # shift - constrain
            nx, ny = self._constrain(obj, role, nx, ny)
        self._set(obj, role, nx, ny)
        self.redraw()

    @staticmethod
    def _round(v: float) -> float:
        return M.snap(v)

    # ---- whole-shape move -------------------------------------------
    def _snapshot(self, obj):
        """Capture original geometry so a move translates from a fixed base."""
        if isinstance(obj, M.TextBox):
            return {"x": obj.x, "y": obj.y,
                    "tip": tuple(obj.tip) if obj.tip else None}
        if isinstance(obj, M.FreeLine):
            return {"p1": tuple(obj.p1), "p2": tuple(obj.p2)}
        if isinstance(obj, M.Dimension):
            return {"a1": tuple(obj.a1), "a2": tuple(obj.a2),
                    "b1": tuple(obj.b1), "b2": tuple(obj.b2),
                    "label_pos": tuple(obj.label_pos) if obj.label_pos else None}
        if isinstance(obj, M.Cloud):
            return {"pts": [tuple(p) for p in obj.pts],
                    "label_pos": tuple(obj.label_pos) if obj.label_pos else None}
        return {}

    def _translate(self, obj, snap, tx: float, ty: float) -> None:
        """Move obj so its snapshot base shifts by (tx, ty)."""
        def sh(p):
            return (p[0] + tx, p[1] + ty) if p else None
        if isinstance(obj, M.TextBox):
            obj.x = snap["x"] + tx
            obj.y = snap["y"] + ty
            if snap["tip"]:
                obj.tip = sh(snap["tip"])
        elif isinstance(obj, M.FreeLine):
            obj.p1 = sh(snap["p1"]); obj.p2 = sh(snap["p2"])
        elif isinstance(obj, M.Dimension):
            obj.a1 = sh(snap["a1"]); obj.a2 = sh(snap["a2"])
            obj.b1 = sh(snap["b1"]); obj.b2 = sh(snap["b2"])
            if snap["label_pos"]:
                obj.label_pos = sh(snap["label_pos"])
        elif isinstance(obj, M.Cloud):
            obj.pts = [sh(p) for p in snap["pts"]]
            if snap["label_pos"]:
                obj.label_pos = sh(snap["label_pos"])

    def _release(self, e) -> None:
        if self._drag:
            self._drag = None
            self.on_change()

    def _constrain(self, obj, role, nx, ny):
        anchor = None
        if isinstance(obj, M.TextBox) and role == "tip":
            anchor = M.box_anchor(obj)
        elif isinstance(obj, M.FreeLine):
            anchor = obj.p1 if role == "p2" else obj.p2
        elif isinstance(obj, M.Dimension) and role in ("a2", "b2"):
            anchor = obj.a1 if role == "a2" else obj.b1
        if not anchor:
            return nx, ny
        dx, dy = nx - anchor[0], ny - anchor[1]
        ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
        r = math.hypot(dx, dy)
        return anchor[0] + r * math.cos(ang), anchor[1] + r * math.sin(ang)

    # ---- generic get/set on (obj, role) ------------------------------
    def _get(self, obj, role) -> Tuple[float, float]:
        if isinstance(obj, M.TextBox):
            if role == "body":
                return (obj.x, obj.y)
            if role == "resize":
                bx, by, w, h = M.box_rect(obj)
                return (bx + w, by)          # bottom-right corner, world coords
            return obj.tip
        if isinstance(obj, M.FreeLine):
            return obj.p1 if role == "p1" else obj.p2
        if isinstance(obj, M.Cloud):
            return obj.pts[role[1]]
        if isinstance(obj, M.Dimension):
            if role == "label":
                if obj.label_pos is None:
                    w, h = M.box_size(obj.text)
                    mid = ((obj.a1[0] + obj.b1[0]) / 2, (obj.a1[1] + obj.b1[1]) / 2)
                    obj.label_pos = (mid[0] - w / 2, mid[1] + 5.0)
                return obj.label_pos
            return getattr(obj, role)
        raise TypeError(obj)

    def _set(self, obj, role, x: float, y: float) -> None:
        if isinstance(obj, M.TextBox):
            if role == "body":
                obj.x, obj.y = x, y
            elif role == "resize":
                # Switch to a top-left anchor so resize grows right+down
                # predictably, keeping the visual top-left fixed.
                bx, by, _w, _h = M.box_rect(obj)
                top = by + _h
                if obj.anchor != "nw":
                    obj.x, obj.y, obj.anchor = bx, top, "nw"
                new_w = max(x - bx, 3 * M.BOX_PAD_X)
                new_h = max(top - y, obj.size * M.LINE_GAP + 2 * M.BOX_PAD_Y)
                obj.w, obj.h = new_w, new_h
            else:
                obj.tip = (x, y)
        elif isinstance(obj, M.FreeLine):
            setattr(obj, "p1" if role == "p1" else "p2", (x, y))
        elif isinstance(obj, M.Cloud):
            obj.pts[role[1]] = (x, y)
        elif isinstance(obj, M.Dimension):
            setattr(obj, "label_pos" if role == "label" else role, (x, y))

    # ==================================================================
    # Items
    # ==================================================================
    def _uid(self, prefix: str) -> str:
        n = 1
        used = ({b.box_id for b in self.layout.boxes}
                | {d.dim_id for d in self.layout.dims}
                | {l.line_id for l in self.layout.lines})
        while f"{prefix}{n}" in used:
            n += 1
        return f"{prefix}{n}"

    # ==================================================================
    # Clouds
    # ==================================================================
    def _draw_cloud(self, cl) -> None:
        if len(cl.pts) < 3:
            for i, v in enumerate(cl.pts):
                self._H(cl, ("vert", i), *v)
            return
        poly = cloud_geom.scallops(cl.pts, cl.bulge)
        flat = []
        for (px, py) in poly:
            flat += [self.X(px), self.Y(py)]
        if len(flat) >= 4:
            self.cv.create_line(*flat, fill=M.RED, width=self._pxw("cloud"),
                                smooth=True, splinesteps=6)
        for i, v in enumerate(cl.pts):
            self._H(cl, ("vert", i), *v)

    def _draw_inprogress_cloud(self) -> None:
        pts = self._draw_cloud_pts
        for i, v in enumerate(pts):
            cx, cy = self.X(v[0]), self.Y(v[1])
            self.cv.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, outline=SEL, width=1)
            if i:
                p = pts[i - 1]
                self.cv.create_line(self.X(p[0]), self.Y(p[1]), cx, cy,
                                    fill=SEL, dash=(3, 2))
        if pts:
            self.cv.create_text(10, 10, anchor="nw", fill=SEL,
                text="Cloud: click to add points, Enter/double-click to close, Esc to cancel")

    def start_cloud(self) -> None:
        self._draw_cloud_pts = []
        self._sel = None
        self.cv.config(cursor="crosshair")
        self.redraw()

    def _cancel_cloud(self) -> None:
        if self._draw_cloud_pts is not None:
            self._draw_cloud_pts = None
            self.cv.config(cursor="")
            self.redraw()

    def _finish_cloud(self) -> None:
        pts = self._draw_cloud_pts
        self._draw_cloud_pts = None
        self.cv.config(cursor="")
        if pts and len(pts) >= 3:
            self.push()
            used = catalog.placed_ids(self.layout)
            n = 1
            while f"cloud{n}" in used:
                n += 1
            self.layout.clouds.append(M.Cloud(pts=list(pts), bulge=0.16,
                                              cloud_id=f"cloud{n}"))
            self.on_change()
        self.redraw()

    def flip_cloud(self) -> None:
        """Cycle the scallop size of the selected cloud (bulge)."""
        if not self._sel:
            return
        obj = self._obj(self._sel[0])
        if isinstance(obj, M.Cloud):
            self.push()
            steps = [0.10, 0.16, 0.24, 0.32]
            try:
                i = steps.index(min(steps, key=lambda s: abs(s - obj.bulge)))
            except ValueError:
                i = 1
            obj.bulge = steps[(i + 1) % len(steps)]
            self.redraw()
            self.on_change()

    def add_vertex(self) -> None:
        """Split the longest edge of the selected cloud."""
        if not self._sel:
            return
        obj = self._obj(self._sel[0])
        if not isinstance(obj, M.Cloud) or len(obj.pts) < 2:
            return
        self.push()
        best_i, best_len = 0, -1.0
        for i in range(len(obj.pts)):
            a = obj.pts[i]; b = obj.pts[(i + 1) % len(obj.pts)]
            d = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
            if d > best_len:
                best_len, best_i = d, i
        a = obj.pts[best_i]; b = obj.pts[(best_i + 1) % len(obj.pts)]
        obj.pts.insert(best_i + 1, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
        self.redraw()
        self.on_change()

    def _obj(self, oid: int):
        for o in (*self.layout.boxes, *self.layout.dims, *self.layout.lines,
                  *self.layout.clouds):
            if id(o) == oid:
                return o
        return None

    # ==================================================================
    # Palette
    # ==================================================================
    def _fill_palette(self) -> None:
        if not hasattr(self, "pal"):
            return
        open_groups = {self.pal.item(i, "text") for i in self.pal.get_children()
                       if self.pal.item(i, "open")}
        self.pal.delete(*self.pal.get_children())
        self._pal_map = {}
        avail = catalog.unplaced(self.specs, self.layout)
        grouper = catalog.grouped_iso if self.layout.kind == "iso" else catalog.grouped
        for group, items in grouper(avail):
            gid = self.pal.insert("", "end", text=group,
                                  open=(group in open_groups) or not open_groups)
            for s in items:
                iid = self.pal.insert(gid, "end", text="   " + s.label)
                self._pal_map[iid] = s

    def _pal_press(self, e) -> None:
        iid = self.pal.identify_row(e.y)
        self._pal_drag = self._pal_map.get(iid)
        if self._pal_drag:
            self.pal.config(cursor="plus")

    def _pal_motion(self, e) -> None:
        pass  # cursor is the affordance; a ghost item would need a toplevel

    def _pal_release(self, e) -> None:
        spec, self._pal_drag = self._pal_drag, None
        self.pal.config(cursor="")
        if not spec:
            return

        # was the release over the canvas?
        rx, ry = self.winfo_pointerxy()
        cx = rx - self.cv.winfo_rootx()
        cy = ry - self.cv.winfo_rooty()
        if not (0 <= cx <= self.cv.winfo_width() and 0 <= cy <= self.cv.winfo_height()):
            return

        x, y = M.snap(self.px(cx)), M.snap(self.py(cy))
        self.place_spec(spec, x, y)

    def place_spec(self, spec, x: float, y: float) -> None:
        if spec.item_id == "__cloud":
            self.start_cloud()
            return
        item = spec.make(x, y)

        if spec.reusable:
            self._assign_uid(item, spec.item_id)

        self.push()
        if isinstance(item, M.TextBox):
            self.layout.boxes.append(item)
        elif isinstance(item, M.Dimension):
            self.layout.dims.append(item)
        elif isinstance(item, M.FreeLine):
            self.layout.lines.append(item)
        self.redraw()
        self.on_change()

        # text-bearing items: open the in-place editor straight away instead
        # of a popup dialog, so you just start typing.
        if isinstance(item, M.TextBox) and not item.text:
            self._begin_inplace(item)
        elif isinstance(item, M.Dimension) and spec.item_id == "__dim":
            if not item.text:
                item.text = "000 mm"
            self._begin_inplace(item)

    def _assign_uid(self, item, spec_id: str) -> None:
        prefix = {"__text": "free", "__label": "free", "__arrow": "arw",
                  "__line": "lin", "__dim": "udim"}.get(spec_id, "itm")
        used = catalog.placed_ids(self.layout)
        n = 1
        while f"{prefix}{n}" in used:
            n += 1
        uid = f"{prefix}{n}"
        for attr in ("box_id", "dim_id", "line_id"):
            if hasattr(item, attr):
                setattr(item, attr, uid)

    # ==================================================================
    def delete_sel(self) -> None:
        """Removing a placed item; dataset-backed items return to the palette."""
        if not self._sel:
            return
        oid = self._sel[0]
        self.push()
        for coll in (self.layout.boxes, self.layout.dims, self.layout.lines,
                     self.layout.clouds):
            for o in list(coll):
                if id(o) == oid:
                    coll.remove(o)
        self._sel = None
        self.redraw()
        self.on_change()

    def remove_vertex(self) -> None:
        if not self._sel or not isinstance(self._sel[1], tuple):
            return
        obj = self._obj(self._sel[0])
        if not isinstance(obj, M.Cloud) or len(obj.pts) <= 3:
            return
        self.push()
        del obj.pts[self._sel[1][1]]
        self._sel = None
        self.redraw()
        self.on_change()

    def _dbl(self, e) -> None:
        if self._draw_cloud_pts is not None:
            self._finish_cloud()
            return
        hit = self._hit(e.x, e.y)
        if not hit:
            return
        obj, role = hit
        if isinstance(obj, (M.TextBox, M.Dimension)):
            self._begin_inplace(obj)

    # ------------------------------------------------------------------
    # In-place text editing (no popup dialog)
    # ------------------------------------------------------------------
    def _begin_inplace(self, obj) -> None:
        """Overlay a Text widget on the canvas at the object, edit in place."""
        self._end_inplace(commit=False)
        # position: box top-left for a TextBox; label pos for a Dimension
        if isinstance(obj, M.TextBox):
            bx, by, w, h = M.box_rect(obj)
            cx, cy = self.X(bx), self.Y(by + h)
            width_px = max(int(w * self.zoom), 60)
        else:  # Dimension label
            if obj.label_pos is None:
                mid = ((obj.a1[0] + obj.b1[0]) / 2, (obj.a1[1] + obj.b1[1]) / 2)
                w, h = M.box_size(obj.text or "000 mm")
                obj.label_pos = (mid[0] - w / 2, mid[1] + 5.0)
            cx, cy = self.X(obj.label_pos[0]), self.Y(obj.label_pos[1])
            width_px = 120

        size_px = max(int(round(getattr(obj, "size", M.FONT_SIZE) * self.zoom)), 8)
        self._edit_obj = obj
        self._edit = tk.Text(self.cv, width=1, height=1, wrap="word",
                             font=(fonts.tk_family(), size_px),
                             fg=M.RED, bd=1, relief="solid", padx=2, pady=1)
        self._edit.insert("1.0", obj.text)
        self._edit.place(x=int(cx), y=int(cy),
                         width=width_px, height=max(int(size_px * 2.2), 28))
        self._edit.focus_set()
        self._edit.tag_add("sel", "1.0", "end")
        self._edit.bind("<Escape>", lambda ev: self._end_inplace(commit=False))
        # Enter commits; Shift+Enter inserts a newline
        self._edit.bind("<Return>", self._inplace_return)
        self._edit.bind("<Shift-Return>", lambda ev: None)
        self._edit.bind("<FocusOut>", lambda ev: self._end_inplace(commit=True))

    def _inplace_return(self, e):
        if e.state & 0x0001:      # shift held -> newline
            return
        self._end_inplace(commit=True)
        return "break"

    def _end_inplace(self, commit: bool) -> None:
        w = getattr(self, "_edit", None)
        if not w:
            return
        obj = self._edit_obj
        if commit:
            txt = w.get("1.0", "end-1c")
            if txt != obj.text:
                self.push()
                obj.text = txt
                self.on_change()
        try:
            w.destroy()
        except Exception:
            pass
        self._edit = None
        self._edit_obj = None
        self.redraw()
