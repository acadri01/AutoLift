"""
lift_meta.py
------------
Sidecar handshake between create_lift_case.exe (producer) and
lift_documenter.exe (consumer).

The generator writes  <case>_liftmeta.json  next to the generated _L[n].C2.
The documenter ingests every *_liftmeta.json it finds in the calling folder.

Schema v1
---------
{
  "schema": 1,
  "line": "P-1234-A1B",              # folder name at generation time
  "case_name": "46-P-1234_L3",       # stem of the generated .C2 (no extension)
  "generated": "2026-07-17T09:12:00",
  "disp_mm": 10.0,                   # nominal imposed lift
  "supports": [                      # restraint nodes being unloaded, in run order
      {"node": 340},
      {"node": 430}
  ],
  "lift_points": [                   # always 2 - the outer pair
      {"node": 325, "support_node": 340, "distance_mm": 900.0, "disp_mm": 10.0},
      {"node": 475, "support_node": 430, "distance_mm": 750.0, "disp_mm": 10.0}
  ]
}
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

SCHEMA_VERSION = 1
SIDECAR_SUFFIX = "_liftmeta.json"


# --------------------------------------------------------------------------
# Producer side - call this from lift_case_builder.py after the .C2 is written
# --------------------------------------------------------------------------
def write_sidecar(
    out_dir: str,
    line: str,
    case_name: str,
    disp_mm: float,
    supports: List[int],
    lift_points: List[Dict[str, Any]],
) -> str:
    """
    lift_points: [{"node": int, "support_node": int, "distance_mm": float,
                   "disp_mm": float}, ...]
    Returns the path written.
    """
    payload = {
        "schema": SCHEMA_VERSION,
        "line": line,
        "case_name": case_name,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "disp_mm": float(disp_mm),
        "supports": [{"node": int(n)} for n in supports],
        "lift_points": [
            {
                "node": int(lp["node"]),
                "support_node": (
                    int(lp["support_node"]) if lp.get("support_node") is not None else None
                ),
                "distance_mm": float(lp["distance_mm"]),
                "disp_mm": float(lp.get("disp_mm", disp_mm)),
            }
            for lp in lift_points
        ],
    }

    path = os.path.join(out_dir, case_name + SIDECAR_SUFFIX)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


# --------------------------------------------------------------------------
# Consumer side
# --------------------------------------------------------------------------
def find_sidecars(folder: str) -> List[str]:
    """All *_liftmeta.json in folder, sorted by name."""
    if not os.path.isdir(folder):
        return []
    return sorted(
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(SIDECAR_SUFFIX.lower())
    )


def read_sidecar(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if data.get("schema") != SCHEMA_VERSION:
        raise ValueError(
            f"{os.path.basename(path)}: schema {data.get('schema')} "
            f"(expected {SCHEMA_VERSION})"
        )

    for key in ("line", "case_name", "supports", "lift_points"):
        if key not in data:
            raise ValueError(f"{os.path.basename(path)}: missing '{key}'")

    return data
