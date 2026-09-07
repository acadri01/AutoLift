"""
cloud_geom.py
-------------
Revision-cloud geometry: a closed polygon rendered as a chain of even,
outward-bulging semicircular scallops. Shared by the PDF renderer and the
canvas so they draw identically. Returns a dense closed point list that
approximates the arc chain smoothly.
"""

from __future__ import annotations

import math
from typing import List, Tuple

Pt = Tuple[float, float]

# Target arc chord length in points. Smaller = more, tighter scallops with
# clearer inflection points between them.
SCALLOP_CHORD = 13.0
# points sampled per semicircle bump (higher = smoother)
STEPS = 10
# bump depth as a fraction of the scallop chord (0.5 = true semicircle)
DEPTH = 0.5


def _signed_area(pts: List[Pt]) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def _bump(p1: Pt, p2: Pt, outward: int) -> List[Pt]:
    """
    A semicircular bump from p1 to p2, bulging to one side (outward=+1/-1).
    Returns STEPS points (excluding p1, including p2).
    """
    x1, y1 = p1
    x2, y2 = p2
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    dx, dy = x2 - x1, y2 - y1
    chord = math.hypot(dx, dy)
    if chord < 1e-9:
        return [p2]
    # unit normal
    nx, ny = -dy / chord, dx / chord
    r = chord / 2.0
    depth = r  # semicircle
    # arc centre is the chord midpoint; sweep 180 deg on the outward side
    ux, uy = dx / chord, dy / chord    # unit along chord
    out: List[Pt] = []
    for k in range(1, STEPS + 1):
        t = math.pi * k / STEPS        # 0..pi
        # position along chord (cos) + bulge along normal (sin)
        along = -math.cos(t) * r       # -r..+r  -> p1..p2
        bulge = math.sin(t) * depth * outward
        px = mx + ux * along + nx * bulge
        py = my + uy * along + ny * bulge
        out.append((px, py))
    return out


def scallops(pts: List[Pt], bulge: float = 0.0) -> List[Pt]:
    """
    Closed clouded outline as a dense point list (first point repeated at
    end). `bulge` is accepted for signature compatibility but ignored - the
    scallop size is governed by SCALLOP_CHORD for even bumps.
    <3 vertices -> raw points.
    """
    if len(pts) < 3:
        return list(pts)

    # outward = away from polygon interior. CCW winding -> interior on left,
    # so bumps should go right (outward = -1); flip for CW.
    outward = -1 if _signed_area(pts) > 0 else 1

    poly: List[Pt] = [pts[0]]
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        m = max(1, int(round(seg / SCALLOP_CHORD)))
        for j in range(m):
            p1 = (a[0] + (b[0] - a[0]) * j / m, a[1] + (b[1] - a[1]) * j / m)
            p2 = (a[0] + (b[0] - a[0]) * (j + 1) / m, a[1] + (b[1] - a[1]) * (j + 1) / m)
            poly.extend(_bump(p1, p2, outward))
    return poly
