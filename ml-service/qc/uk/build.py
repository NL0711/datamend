"""UK study build, in two steps that mirror the India build.

``build_grid`` (before ``prepare``)   MIDAS station files -> gridded CORRECTED series written as RF25-format NetCDF
    files (so the whole QC pipeline reads them unchanged), plus the gridded ORIGINAL series and the labelled and
    excluded masks, kept beside them for the second step.
``build_uk_benchmark`` (after ``prepare``)   the "benchmark" for the validation and test years: the faults are
    the real hand corrections. The scored series is the ORIGINAL gridded series (what the QC system would have
    seen); the clean series is the corrected one.

Only manual corrections after a failed neighbour check are labelled errors. Other changes are excluded
cell-days (not scored, not clean) and counted. Protected-extreme and ambiguous masks are computed on the
corrected series by the same rule as for India; a labelled cell-day is never also protected or ambiguous.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from pathlib import Path
from typing import Dict, List

import numpy as np
import xarray as xr
from scipy.ndimage import label

from qc import paths
from qc.benchmark import _digest, _year_file, bench_dir
from qc.config import year_range
from qc.extremes import find_extremes
from qc.grid import ContractError
from qc.prepare import Prepared
from qc.runs import write_json
from qc.uk.gridding import UKGridSpec, grid_year, neighbour_table, station_matrices
from qc.uk.midas import load_midas

log = logging.getLogger(__name__)
FILL = -999.0
CAVEATS = [
    "UK MIDAS real-label study, a separate study: never pooled with the India (RF25) results.",
    "Subset: only the downloaded counties, and only station-years where QC changed a record have an original (qc-version-0) file.",
    "Circularity: the labels are hand corrections made after a failed neighbour check; the spatial component and the "
    "neighbour baseline are partly scored against the rule that produced the labels.",
    "Originals overwritten by station correction messages are not kept, so errors are undercounted; "
    "automatic estimates, split multi-day totals and flag-only changes are excluded, not labelled.",
    "Station values are gridded by inverse-distance weighting, so one bad gauge marks every cell it fed.",
]


def spec_from_config(cfg) -> UKGridSpec:
    u, g = cfg.uk, cfg.grid
    return UKGridSpec(float(g.lat0), float(g.lon0), float(g.step), int(g.n_lat), int(g.n_lon),
                      float(u.search_radius_km), int(u.max_gauges), float(u.power))


def study_years(cfg) -> List[int]:
    ys = set()
    for k in ("train", "val", "test"):
        ys |= set(year_range(cfg.years[k]))
    return sorted(ys)


def labels_dir(cfg) -> Path:
    return paths.work_dir(cfg) / "labels"


def _write_year(path: Path, year: int, field: np.ndarray, spec: UKGridSpec) -> None:
    days = np.datetime64(f"{year}-01-01") + np.arange(field.shape[0])
    out = np.where(np.isfinite(field), field, FILL).astype("float64")
    xr.Dataset({"RAINFALL": (("TIME", "LATITUDE", "LONGITUDE"), out, {"units": "mm"})},
               coords={"TIME": days, "LATITUDE": spec.lat, "LONGITUDE": spec.lon}
               ).to_netcdf(path, engine="scipy", encoding={"RAINFALL": {"_FillValue": FILL}})


def build_grid(cfg, midas_dir: Path = None) -> Dict:
    spec = spec_from_config(cfg)
    years = study_years(cfg)
    midas_dir = Path(midas_dir or cfg.uk.midas_dir)
    sd = load_midas(midas_dir, list(cfg.uk.counties), years)
    log.info("read %d stations; changes: %s", len(sd.ids), sd.counts)
    idx, dist = neighbour_table(spec, sd.lat, sd.lon)
    out_grid, out_lab = paths.work_dir(cfg) / "grid", labels_dir(cfg)
    out_grid.mkdir(parents=True, exist_ok=True)
    out_lab.mkdir(parents=True, exist_ok=True)
    H, W = spec.n_lat, spec.n_lon
    ever = np.ones(H * W, bool)
    per_year = {}
    for y in years:
        g = grid_year(station_matrices(sd, y), idx, dist, spec)
        ever &= np.isfinite(g["corrected"]).any(axis=0)           # a cell must have data in every study year
        per_year[y] = g
    if not ever.any():
        raise ContractError("no grid cell has data in every study year; widen the region or the search radius")
    land = ever.reshape(H, W)
    counts: Counter = Counter()
    for y, g in per_year.items():
        corr = np.where(land.ravel()[None, :], g["corrected"], np.nan).reshape(-1, H, W)
        _write_year(out_grid / f"RF25_ind{y}_rfp25.nc", y, corr, spec)
        live = land.ravel()[None, :]
        np.savez_compressed(out_lab / f"uk_{y}.npz", original=np.where(live, g["original"], np.nan).astype(np.float32),
                            labelled=np.packbits(g["labelled"] & live), excluded=np.packbits(g["excluded"] & live),
                            shape=np.array(g["labelled"].shape))
        counts["cell_days"] += int((np.isfinite(g["corrected"]) & live).sum())
        counts["labelled_cell_days"] += int((g["labelled"] & live).sum())
        counts["excluded_cell_days"] += int((g["excluded"] & live).sum())
    summary = {"stations": len(sd.ids), "land_cells": int(land.sum()), "grid": [H, W], "years": [years[0], years[-1]],
               "record_changes": sd.counts, "cell_days": dict(counts), "subset_note": sd.subset_note,
               "choices": {"step_deg": spec.step, "search_radius_km": spec.radius_km, "max_gauges": spec.max_gauges,
                           "power": spec.power, "counties": list(cfg.uk.counties)}}
    write_json(paths.work_dir(cfg) / "uk_build_summary.json", summary)
    return summary


def _events(labelled: np.ndarray, orig: np.ndarray, grid) -> Dict:
    """Group labelled cell-days into events: connected in space (8-neighbour) and across consecutive days."""
    field = grid.to_field(labelled, fill=False)
    lab, n = label(field, structure=np.ones((3, 3, 3), bool))
    t, r, c = np.nonzero(lab)
    ids = lab[t, r, c]
    cell_of = np.full(grid.shape, -1, np.int32)
    cell_of[grid.rows, grid.cols] = np.arange(grid.n_land)
    cell = cell_of[r, c]
    order = np.argsort(ids, kind="stable")
    t, r, c, ids, cell = t[order], r[order], c[order], ids[order], cell[order]
    starts = np.r_[0, np.nonzero(np.diff(ids))[0] + 1] if ids.size else np.zeros(0, int)
    events = []
    for a, b in zip(starts, np.r_[starts[1:], ids.size]):
        rr, cc, tt = r[a:b], c[a:b], t[a:b]
        mr, mc = rr.mean(), cc.mean()
        d = np.hypot(rr - mr, cc - mc)
        centre = int(cell[a:b][np.argmin(d)])
        extent = float(d.max())
        events.append({"kind": "manual_correction", "bases": ["manual_correction"], "strength": 1.0,
                       "radius": 0.0 if (np.unique(cell[a:b]).size == 1) else max(1.5, extent),
                       "centre": centre, "start": int(tt.min()), "duration": int(tt.max() - tt.min() + 1), "n_changed": int(b - a)})
    return {"t": t.astype(np.int32), "cell": cell.astype(np.int32), "event": (np.cumsum(np.r_[0, np.diff(ids) != 0]) if ids.size else ids).astype(np.int32),
            "events": events}


def build_uk_benchmark(p: Prepared, overwrite: bool = False) -> Dict:
    cfg = p.cfg
    out = bench_dir(cfg)
    if (out / "manifest.json").is_file() and not overwrite:
        raise ContractError(f"{out} already holds a frozen UK benchmark; pass --overwrite to replace it")
    out.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    h.update(p.manifest["hash"].encode())
    summary: Dict[str, Dict] = {}
    for split in ("val", "test"):
        tot: Counter = Counter()
        ev_kinds = 0
        for year in p.split.years[split]:
            f = np.load(labels_dir(cfg) / f"uk_{year}.npz")
            shape = tuple(int(v) for v in f["shape"])
            n = shape[0] * shape[1]
            unpack = lambda a: np.unpackbits(a)[:n].reshape(shape).astype(bool)
            full_orig = f["original"]
            sel = p.grid.rows * p.grid.shape[1] + p.grid.cols
            orig = full_orig[:, sel]
            labelled, excluded = unpack(f["labelled"])[:, sel], unpack(f["excluded"])[:, sel]
            clean = p.store.year(year)
            if clean.shape != orig.shape:
                raise ContractError(f"labels for {year} have shape {orig.shape}, the grid file has {clean.shape}")
            ex = find_extremes(clean, p.stats.heavy_mm, p.grid, int(cfg.extremes.min_cells))
            protected, ambiguous = ex.protected & ~labelled, ex.ambiguous & ~labelled
            ev = _events(labelled, orig, p.grid)
            value = orig[ev["t"], ev["cell"]]
            unseen = np.zeros(len(ev["events"]), bool)
            np.savez_compressed(
                _year_file(cfg, split, year), t=ev["t"], cell=ev["cell"], value=value.astype(np.float32),
                weight=np.ones(ev["t"].size, np.float32), event=ev["event"], shape=np.array(labelled.shape),
                protected=np.packbits(protected), ambiguous=np.packbits(ambiguous), excluded=np.packbits(excluded),
                group=ex.group, unseen_setting=unseen, counts=np.array([ex.n_protected_events, ex.n_small_groups]),
                ev_kind=np.array([e["kind"] for e in ev["events"]]), ev_bases=np.array(["+".join(e["bases"]) for e in ev["events"]]),
                ev_strength=np.array([e["strength"] for e in ev["events"]], np.float32),
                ev_radius=np.array([e["radius"] for e in ev["events"]], np.float32),
                ev_centre=np.array([e["centre"] for e in ev["events"]], np.int32),
                ev_start=np.array([e["start"] for e in ev["events"]], np.int32),
                ev_duration=np.array([e["duration"] for e in ev["events"]], np.int32),
                ev_n=np.array([e["n_changed"] for e in ev["events"]], np.int32))
            _digest(h, ev["t"], ev["cell"], value, ev["event"], np.packbits(protected), np.packbits(ambiguous), np.packbits(excluded))
            tot["cell_days"] += int(np.isfinite(clean).sum())
            tot["labelled_cell_days"] += int(labelled.sum())
            tot["labelled_events"] += len(ev["events"])
            tot["excluded_cell_days"] += int(excluded.sum())
            tot["protected_cell_days"] += int(protected.sum())
            tot["ambiguous_cell_days"] += int(ambiguous.sum())
        summary[split] = dict(tot, years=[p.split.years[split][0], p.split.years[split][-1]])
    manifest = {"name": str(cfg.benchmark.name), "hash": h.hexdigest()[:16], "split_manifest_hash": p.manifest["hash"],
                "config": cfg.to_dict()["uk"], "extremes": cfg.to_dict()["extremes"], "splits": ["val", "test"],
                "label_tier": "real corrections (UK MIDAS): original versus hand-corrected after a failed neighbour check",
                "tier_short": "real corrections (UK)", "caveats": CAVEATS, "summary": summary}
    write_json(out / "manifest.json", manifest)
    return manifest
