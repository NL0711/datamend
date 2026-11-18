"""Regional output: how much of each region is suspect, per period.

STATUS: new, unit-tested on generated arrays only. The IMD boundary file for the 36 meteorological sub-divisions and the 4
homogeneous regions is NOT in the repository and has not been sourced: ``load_region_map`` reads it from a CSV you provide
(columns ``region_id,name,row,col``, one line per land cell) and refuses to run without it. Until then ``region_map_from_clients``
gives the 8 client regions as a clearly labelled STAND-IN, not IMD units.

What is reported is DATA QUALITY (the area-weighted share of cells whose fused score is flagged), not rainfall. IMD's departure-
from-normal bands may be shown beside it for weather context but are not mixed in and their category names are not reused.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from qc.grid import Grid


@dataclass
class RegionMap:
    label: str
    cell_region: np.ndarray      # (n_land,) int; 0 = not in any region
    names: Dict[int, str]


def cell_weights(grid: Grid) -> np.ndarray:
    """Area weight of each land cell: cos(latitude)."""
    return np.cos(np.deg2rad(grid.lat[grid.rows])).astype(np.float64)


def region_map_from_clients(cell_client: np.ndarray) -> RegionMap:
    ids = sorted(int(c) for c in np.unique(cell_client) if int(c) > 0)
    return RegionMap("8 client regions (a stand-in; NOT IMD sub-divisions)", np.asarray(cell_client, int),
                     {i: f"client {i}" for i in ids})


def load_region_map(path: Path, grid: Grid, label: str = "IMD regions") -> RegionMap:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"region file {path} not found. The IMD sub-division and homogeneous-region boundaries are not in the "
                                "repository: provide a CSV with columns region_id,name,row,col (one line per land cell).")
    index = np.full(grid.shape, -1, np.int64)
    index[grid.rows, grid.cols] = np.arange(grid.n_land)
    cell_region = np.zeros(grid.n_land, int)
    names: Dict[int, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        need = {"region_id", "name", "row", "col"}
        if not rd.fieldnames or not need <= set(rd.fieldnames):
            raise ValueError(f"{path} needs the columns {sorted(need)}; found {rd.fieldnames}")
        for line in rd:
            r, c, rid = int(line["row"]), int(line["col"]), int(line["region_id"])
            if not (0 <= r < grid.shape[0] and 0 <= c < grid.shape[1]) or index[r, c] < 0:
                raise ValueError(f"cell ({r}, {c}) in {path} is not a land cell of this grid")
            if rid <= 0:
                raise ValueError("region_id must be positive")
            if cell_region[index[r, c]] not in (0, rid):
                raise ValueError(f"cell ({r}, {c}) is assigned to two regions")
            cell_region[index[r, c]] = rid
            names[rid] = line["name"]
    return RegionMap(label, cell_region, names)


def assign_by_area_share(grid: Grid, locate: Callable[[np.ndarray, np.ndarray], np.ndarray], names: Dict[int, str],
                         sub: int = 7, label: str = "IMD sub-divisions") -> RegionMap:
    """One cell, one region: each land cell goes to the region that holds the largest share of its area (decided 2026-11-18).

    ``locate(lon, lat)`` returns, for arrays of points, the positive region id each point lies in (0 = in none), so any polygon library
    can be plugged in. A cell is sampled on a ``sub`` x ``sub`` set of points; ties go to the lower id; a cell whose points all fall in no
    region stays unassigned (0), for example sea or islands. The cell size is taken from the grid's own spacing."""
    if sub < 1:
        raise ValueError("sub must be at least 1")
    dlat = float(abs(grid.lat[1] - grid.lat[0])) if grid.lat.size > 1 else 0.25
    dlon = float(abs(grid.lon[1] - grid.lon[0])) if grid.lon.size > 1 else 0.25
    off = (np.arange(sub) + 0.5) / sub - 0.5
    clat = grid.lat[grid.rows][:, None, None] + off[None, :, None] * dlat
    clon = grid.lon[grid.cols][:, None, None] + off[None, None, :] * dlon
    clat, clon = np.broadcast_arrays(clat, clon)
    ids = np.asarray(locate(clon.ravel(), clat.ravel())).reshape(grid.n_land, sub * sub).astype(int)
    unknown = sorted(set(np.unique(ids)) - {0} - set(names))
    if unknown:
        raise ValueError(f"locate returned region ids {unknown} that are not in names")
    out = np.zeros(grid.n_land, int)
    ids_sorted = sorted(names)
    counts = np.stack([(ids == i).sum(axis=1) for i in ids_sorted], axis=1)
    has = counts.max(axis=1) > 0
    out[has] = np.array(ids_sorted)[counts[has].argmax(axis=1)]
    return RegionMap(label, out, dict(names))


def derive_regions(base: RegionMap, composition: Dict[int, Sequence[int]], names: Dict[int, str],
                   label: str = "IMD homogeneous regions (unions of sub-divisions)") -> RegionMap:
    """Regions built as unions of the regions of ``base`` (decided 2026-11-18: the 4 homogeneous regions are derived from the 36
    sub-divisions, so the two always agree). ``composition[new_id]`` lists the base ids it contains; a base id may be used once."""
    used = [i for ids in composition.values() for i in ids]
    if len(used) != len(set(used)):
        raise ValueError("a sub-division is listed in more than one region")
    missing = sorted(set(used) - set(base.names))
    if missing:
        raise ValueError(f"composition names ids {missing} that are not in the base regions")
    if set(composition) != set(names):
        raise ValueError("composition and names must have the same region ids")
    out = np.zeros_like(base.cell_region)
    for new_id, ids in composition.items():
        out[np.isin(base.cell_region, list(ids))] = new_id
    return RegionMap(label, out, dict(names))


def regional_summary(review: np.ndarray, final: np.ndarray, scored: np.ndarray, rmap: RegionMap, weights: np.ndarray,
                     driver: Optional[np.ndarray] = None, scale_names: Sequence[str] = ()) -> List[Dict]:
    """``review``, ``final``, ``scored`` are (X, n) bool over X periods or days; ``driver`` is (X, n) int8 index into ``scale_names``.
    Per region: area-weighted share of scored cells flagged (max and mean over X), the count of flagged cell-periods and the scale
    that drove most final flags (else most review flags)."""
    if not (review.shape == final.shape == scored.shape):
        raise ValueError("review, final and scored must have the same shape")
    out = []
    for rid, name in sorted(rmap.names.items()):
        sel = rmap.cell_region == rid
        w = weights[sel]
        sc = scored[:, sel]
        den = (sc * w[None, :]).sum(axis=1)

        def share(flag):
            num = ((flag[:, sel] & sc) * w[None, :]).sum(axis=1)
            return np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)

        sr, sf = share(review), share(final)
        none_r, none_f = bool(np.isnan(sr).all()), bool(np.isnan(sf).all())
        row = {"region_id": rid, "name": name, "cells": int(sel.sum()),
               "review_share_max": None if none_r else float(np.nanmax(sr)),
               "review_share_mean": None if none_r else float(np.nanmean(sr)),
               "final_share_max": None if none_f else float(np.nanmax(sf)),
               "final_share_mean": None if none_f else float(np.nanmean(sf)),
               "review_cell_periods": int((review[:, sel] & sc).sum()), "final_cell_periods": int((final[:, sel] & sc).sum()),
               "strongest_scale": None}
        if driver is not None and scale_names:
            for flag in (final, review):
                m = flag[:, sel] & sc & (driver[:, sel] >= 0)
                if m.any():
                    counts = np.bincount(driver[:, sel][m].astype(int), minlength=len(scale_names))
                    row["strongest_scale"] = scale_names[int(counts.argmax())]
                    break
        out.append(row)
    return out
