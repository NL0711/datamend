"""IMD's 36 meteorological sub-divisions and 4 homogeneous regions from IMD's own boundary file, plus the acceptance checks.

STATUS: written against IMD's file https://mausam.imd.gov.in/imd_latest/contents/district_shapefiles/sd_boundary_rainfall.json (36 features,
properties ``name``, ``region_cod``, ``uorder``; last modified 28 Aug 2024). The file states no coordinate system and no licence: it is
treated as degrees (WGS84), which ``acceptance_known_points`` checks, and it is fetched by ``scripts/fetch_imd_regions.py`` and NOT
committed. Do not publish maps derived from it until IMD's terms are known.

Decisions (owner, 2026-11-18): a cell goes to the sub-division holding the largest share of its area (``regions.assign_by_area_share``);
the 4 homogeneous regions are the unions of sub-divisions given by the file's own ``region_cod`` attribute (``regions.derive_regions``).
IMD's four regions in this file are CENTRAL INDIA, EAST AND NORTH EAST INDIA, NORTH WEST INDIA and SOUTH PENINSULA.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

import numpy as np
from matplotlib.path import Path as MplPath

from qc.grid import Grid
from qc.regions import RegionMap, assign_by_area_share, derive_regions

# Known places and the sub-division IMD's file should put them in. Used as an acceptance test of the file and the cell assignment.
KNOWN_POINTS: Tuple[Tuple[str, float, float, str], ...] = (
    ("Mumbai", 19.08, 72.88, "KONKAN & GOA"),
    ("Delhi", 28.61, 77.21, "HAR. CHD & DELHI"),
    ("Chennai", 13.08, 80.27, "TN PUDU and KKL"),
    ("Kolkata", 22.57, 88.36, "GANGETIC WEST BENGAL"),
    ("Bengaluru", 12.97, 77.59, "S. I. KARNATAKA"),
    ("Jaipur", 26.91, 75.79, "EAST RAJASTHAN"),
    ("Guwahati", 26.14, 91.74, "ASSAM & MEGHALAYA"),
    ("Thiruvananthapuram", 8.52, 76.94, "KERALA & MAHE"),
    ("Hyderabad", 17.38, 78.48, "TELANGANA"),
    ("Patna", 25.59, 85.14, "BIHAR"),
)


def load_features(path: Path) -> List[Dict]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    feats = d.get("features")
    if not feats:
        raise ValueError(f"{path} has no features")
    out = []
    for f in feats:
        p = f["properties"]
        for need in ("name", "region_cod", "uorder"):
            if need not in p:
                raise ValueError(f"feature without {need!r}: {p}")
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]] if g["type"] == "Polygon" else None
        if polys is None:
            raise ValueError(f"unsupported geometry {g['type']}")
        out.append({"id": int(p["uorder"]), "name": str(p["name"]).strip(), "region": str(p["region_cod"]).strip(), "polygons": polys})
    ids = [f["id"] for f in out]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate sub-division ids (uorder)")
    return out


def make_locator(features: Sequence[Dict]) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
    """``locate(lon, lat)`` -> sub-division id per point (0 outside every polygon). Holes are honoured; overlaps go to the lower id."""
    parts = []
    for f in sorted(features, key=lambda f: f["id"]):
        for poly in f["polygons"]:
            outer = np.asarray(poly[0], float)[:, :2]
            holes = [MplPath(np.asarray(h, float)[:, :2]) for h in poly[1:]]
            parts.append((f["id"], MplPath(outer), holes, outer.min(axis=0), outer.max(axis=0)))

    def locate(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        pts = np.column_stack([lon, lat])
        out = np.zeros(len(lon), int)
        for fid, outer, holes, lo, hi in parts:
            cand = (out == 0) & (lon >= lo[0]) & (lon <= hi[0]) & (lat >= lo[1]) & (lat <= hi[1])
            if not cand.any():
                continue
            idx = np.nonzero(cand)[0]
            inside = outer.contains_points(pts[idx])
            for h in holes:
                inside &= ~h.contains_points(pts[idx])
            out[idx[inside]] = fid
        return out

    return locate


def build_imd_maps(grid: Grid, path: Path, sub: int = 7) -> Tuple[RegionMap, RegionMap]:
    """(sub-division map, homogeneous-region map) on ``grid``."""
    feats = load_features(path)
    names = {f["id"]: f["name"] for f in feats}
    sub_map = assign_by_area_share(grid, make_locator(feats), names, sub=sub, label="IMD meteorological sub-divisions (IMD file, area-share assignment)")
    reg_names = sorted({f["region"] for f in feats})
    rid = {n: i + 1 for i, n in enumerate(reg_names)}
    comp: Dict[int, List[int]] = {i: [] for i in rid.values()}
    for f in feats:
        comp[rid[f["region"]]].append(f["id"])
    region_map = derive_regions(sub_map, comp, {i: n for n, i in rid.items()})
    return sub_map, region_map


DEFAULT_ANCHORS = ("ASSAM & MEGHALAYA", "KONKAN & GOA")      # north-east (wettest) and west-central (Mumbai): the held-out clients


def nested_client_map(old_map: np.ndarray, grid: Grid, path: Path, k: int = 8, anchors: Sequence[str] = DEFAULT_ANCHORS,
                      sub: int = 7) -> Tuple[np.ndarray, Dict]:
    """New client map in which every client is a union of WHOLE IMD sub-divisions (decided 2026-11-18, before any run). ``old_map`` (H, W)
    supplies the land mask and the starting partition (the k-means blobs). Land cells that fall in no sub-division polygon take the
    sub-division of the nearest cell that has one. Returns (map (H, W) int8, report)."""
    from qc.clients import nest_in_subdivisions, order_clients

    sub_map, _ = build_imd_maps(grid, path, sub=sub)
    sid = sub_map.cell_region.copy()
    assigned = np.nonzero(sid > 0)[0]
    fallback = np.nonzero(sid == 0)[0]
    for i in fallback:
        d = np.hypot(grid.rows[assigned] - grid.rows[i], grid.cols[assigned] - grid.cols[i])
        sid[i] = sid[assigned[d.argmin()]]
    by_name = {n: i for i, n in sub_map.names.items()}
    missing = [a for a in anchors if a not in by_name]
    if missing:
        raise ValueError(f"anchor sub-divisions {missing} are not in the boundary file")
    anchor_ids = [by_name[a] for a in anchors]
    base = old_map[grid.rows, grid.cols].astype(np.int64)
    lab = nest_in_subdivisions(grid.rows, grid.cols, sid, base, k, anchor_ids)
    lab = order_clients(lab, grid.lat[grid.rows], grid.lon[grid.cols], k)
    out = np.zeros(grid.shape, np.int8)
    out[grid.rows, grid.cols] = lab
    clients = {int(c): sorted({sub_map.names[int(s)] for s in np.unique(sid[lab == c])}) for c in range(1, k + 1)}
    report = {"k": k, "cells_per_client": {int(c): int((lab == c).sum()) for c in range(1, k + 1)}, "clients": clients,
              "anchors": {a: int(lab[np.nonzero(sid == by_name[a])[0][0]]) for a in anchors},
              "cells_assigned_to_nearest_sub_division": int(fallback.size)}
    return out, report


def acceptance_known_points(grid: Grid, path: Path, sub_map: RegionMap, points: Sequence = KNOWN_POINTS) -> Dict:
    """Two checks of the boundary file and the assignment (decided 2026-11-18, both must pass before any regional output is shown):
    polygon level (the point is in the expected sub-division of the file) and cell level (the grid cell holding the point was assigned to it)."""
    feats = load_features(path)
    by_name = {f["name"]: f["id"] for f in feats}
    locate = make_locator(feats)
    rows = []
    for place, lat, lon, expected in points:
        eid = by_name.get(expected)
        poly_id = int(locate(np.array([lon]), np.array([lat]))[0])
        r = int(np.argmin(np.abs(grid.lat - lat)))
        c = int(np.argmin(np.abs(grid.lon - lon)))
        hit = np.nonzero((grid.rows == r) & (grid.cols == c))[0]
        cell_id = int(sub_map.cell_region[hit[0]]) if hit.size else None
        rows.append({"place": place, "expected": expected, "polygon_ok": eid is not None and poly_id == eid,
                     "cell_ok": eid is not None and cell_id == eid, "cell_on_land_grid": bool(hit.size)})
    testable = [r for r in rows if r["cell_on_land_grid"]]            # a coastal place whose cell is sea in RF25 cannot be tested at cell level
    return {"points": rows, "n": len(rows), "polygon_ok": sum(r["polygon_ok"] for r in rows),
            "cell_testable": len(testable), "cell_ok": sum(r["cell_ok"] for r in testable),
            "passed": all(r["polygon_ok"] for r in rows) and all(r["cell_ok"] for r in testable)}
