"""Regional output: for each IMD sub-division and homogeneous region, how much of it is suspect, day by day, with a monthly roll-up.

STATUS: new, unit-tested on a generated world only; nothing has run on real RF25. The scores are those of the FROZEN benchmark: the faults in them
are SYNTHETIC injections, so every share here is a share of a synthetic benchmark, not a statement about real rainfall data. The output carries the
injected-fault share beside the flagged share so the two can be compared.

Read-only: it only reads stored scores and writes files; it scores nothing. Test and stress years are written only after the daily test pass is
finished (its lock says done).

For each unit and each day: the area-weighted share of scored cells flagged at the REVIEW and at the FINAL budget, the number of flagged cells, the
largest connected cluster (8-neighbour, inside the unit) of final-flagged cells, the injected-fault share (truth of the benchmark), and the part of the
fused score (daily, monthly, ...) that drove most final flags, when the fusion stored its drivers. IMD's departure-from-normal bands are not used and
their category names are not reused: this is data quality, not weather.
"""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from scipy import ndimage

from qc.benchmark import check_benchmark, load_bench_year
from qc.crossscale_run import driver_name
from qc.evaluate import score_store, thresholds_for
from qc.regions import RegionMap, cell_weights
from qc.runs import read_json
from qc.scoring import ScoreStore
from qc.testscore import lock_path as daily_lock_path

LABEL = "SYNTHETIC faults injected into the frozen benchmark; not real rainfall data quality"


def largest_cluster(flag_grid: np.ndarray) -> int:
    """Size of the largest 8-connected group of True cells in an (H, W) boolean grid; 0 if none."""
    lab, n = ndimage.label(flag_grid, structure=np.ones((3, 3)))
    return int(np.bincount(lab.ravel())[1:].max()) if n else 0


def unit_day_series(score: np.ndarray, thr_review: float, thr_final: float, rmap: RegionMap, weights: np.ndarray, grid,
                    truth: Optional[np.ndarray] = None, driver: Optional[np.ndarray] = None, n_scales: int = 0) -> Dict[int, Dict[str, np.ndarray]]:
    """Per unit id: arrays over the T days of one year."""
    scored = np.isfinite(score)
    final = scored & (np.nan_to_num(score, nan=-np.inf) > thr_final)
    review = scored & (np.nan_to_num(score, nan=-np.inf) > thr_review)
    T = score.shape[0]
    out: Dict[int, Dict[str, np.ndarray]] = {}
    for rid in sorted(rmap.names):
        sel = rmap.cell_region == rid
        w = weights[sel]
        sc = scored[:, sel]
        den = (sc * w[None, :]).sum(axis=1)
        safe = np.where(den > 0, den, 1.0)

        def share(m):
            return np.where(den > 0, ((m[:, sel] & sc) * w[None, :]).sum(axis=1) / safe, np.nan)

        cells_idx = np.nonzero(sel)[0]
        cluster = np.zeros(T, int)
        fin_sel = final[:, sel]
        for t in np.nonzero(fin_sel.any(axis=1))[0]:
            g = np.zeros(grid.shape, bool)
            g[grid.rows[cells_idx[fin_sel[t]]], grid.cols[cells_idx[fin_sel[t]]]] = True
            cluster[t] = largest_cluster(g)
        drv = np.full(T, -1, int)
        if driver is not None and n_scales:
            d = driver[:, sel]
            for t in np.nonzero(fin_sel.any(axis=1))[0]:
                m = fin_sel[t] & (d[t] >= 0)
                if m.any():
                    drv[t] = int(np.bincount(d[t][m].astype(int), minlength=n_scales).argmax())
        out[rid] = {"review_share": share(review), "final_share": share(final),
                    "review_cells": (review[:, sel] & sc).sum(axis=1), "final_cells": (fin_sel & sc).sum(axis=1),
                    "largest_final_cluster": cluster, "driver": drv,
                    "injected_fault_share": share(truth) if truth is not None else np.full(T, np.nan)}
    return out


def _driver_names(info: Optional[Dict]) -> List[str]:
    return list(info["parts"]) if info and info.get("parts") else []


def build_regional_output(p, component: str, split: str, level_maps: Dict[str, RegionMap], out_dir: Path, budgets: Dict,
                          store: Optional[ScoreStore] = None, choice: Optional[Dict] = None, map_provenance: Optional[Dict] = None) -> Dict[str, Path]:
    """Write ``regional_<split>.json`` and ``regional_<split>.csv`` into ``out_dir`` for the unit levels in ``level_maps`` (label -> map).

    ``budgets`` holds ``final_per_1000`` and ``review_per_1000``. Test and stress years need the daily test pass to be finished."""
    if split not in ("val", "test", "stress"):
        raise ValueError("split must be val, test or stress")
    if split != "val":
        dl = daily_lock_path(p)
        if not dl.is_file() or read_json(dl).get("status") != "done":
            raise RuntimeError(f"regional output for {split} years is written only after the daily test pass is finished ({dl}); it reads scores, it does not make them")
    store = store or score_store(p)
    bench = check_benchmark(p, require_pinned=False)
    thr = thresholds_for(p, component, [float(budgets["final_per_1000"]), float(budgets["review_per_1000"])], store)
    thr_final, thr_review = thr[float(budgets["final_per_1000"])], thr[float(budgets["review_per_1000"])]
    weights = cell_weights(p.grid)
    years = list(p.split.years[split])
    info = (choice or {}).get("fusion_info")
    names = _driver_names(info) if (choice and choice.get("chosen", {}).get("component") == component) else []
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: List[Dict] = []
    units_json: List[Dict] = []
    for level, rmap in level_maps.items():
        per_year: Dict[int, Dict[int, Dict[str, np.ndarray]]] = {}
        for y in years:
            score = store.load(component, split, y)
            by = load_bench_year(p, split, y)
            drv = store.load(driver_name(component), split, y) if names and store.has(driver_name(component), split, y) else None
            per_year[y] = unit_day_series(score, thr_review, thr_final, rmap, weights, p.grid, by.faults.labels(), drv, len(names))
            dates = np.datetime64(f"{y}-01-01") + np.arange(score.shape[0])
            for rid, s in per_year[y].items():
                for t in range(score.shape[0]):
                    rows.append({"level": level, "unit_id": rid, "unit": rmap.names[rid], "date": str(dates[t]),
                                 "review_share": s["review_share"][t], "final_share": s["final_share"][t], "review_cells": int(s["review_cells"][t]),
                                 "final_cells": int(s["final_cells"][t]), "largest_final_cluster": int(s["largest_final_cluster"][t]),
                                 "injected_fault_share": s["injected_fault_share"][t],
                                 "driver": (names[int(s["driver"][t])] if names and s["driver"][t] >= 0 else ("daily" if not names and s["final_cells"][t] else ""))})
        for rid in sorted(rmap.names):
            months = []
            for y in years:
                s = per_year[y][rid]
                T = len(s["final_cells"])
                mon = (np.datetime64(f"{y}-01-01") + np.arange(T)).astype("datetime64[M]")
                for m in np.unique(mon):
                    k = mon == m
                    fin, rev = s["final_share"][k], s["review_share"][k]
                    months.append({"month": str(m), "final_share_mean": _nm(fin), "final_share_max": _nx(fin), "review_share_mean": _nm(rev),
                                   "review_share_max": _nx(rev), "final_cell_days": int(s["final_cells"][k].sum()),
                                   "review_cell_days": int(s["review_cells"][k].sum()), "days_with_final_flag": int((s["final_cells"][k] > 0).sum()),
                                   "largest_final_cluster": int(s["largest_final_cluster"][k].max()), "injected_fault_share_mean": _nm(s["injected_fault_share"][k])})
            units_json.append({"level": level, "unit_id": rid, "unit": rmap.names[rid], "cells": int((rmap.cell_region == rid).sum()), "monthly": months})
    prov = {"label": LABEL, "run": str(p.cfg.name), "split": split, "years": [years[0], years[-1]], "component": component,
            "budgets": {k: budgets[k] for k in ("final_per_1000", "review_per_1000") if k in budgets},
            "budgets_apply_to": budgets.get("applies_to"), "thresholds": {"final": float(thr_final), "review": float(thr_review)},
            "benchmark_hash": bench["hash"], "architecture_choice_commit": (choice or {}).get("commit"),
            "unit_levels": {k: m.label for k, m in level_maps.items()}, "map_provenance": map_provenance, "drivers": names,
            "written": datetime.date.today().isoformat(),
            "meaning": "data quality of a synthetic benchmark, not rainfall or weather; IMD departure-from-normal bands are not used"}
    jpath, cpath = out_dir / f"regional_{split}.json", out_dir / f"regional_{split}.csv"
    jpath.write_text(json.dumps({"provenance": prov, "units": units_json}, indent=1, default=float), encoding="utf-8")
    fields = ["level", "unit_id", "unit", "date", "review_share", "final_share", "review_cells", "final_cells", "largest_final_cluster",
              "injected_fault_share", "driver"]
    with open(cpath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if isinstance(v, float) and np.isnan(v) else v) for k, v in r.items()})
    return {"json": jpath, "csv": cpath}


def _nm(a: np.ndarray) -> Optional[float]:
    return None if not np.isfinite(a).any() else float(np.nanmean(a))


def _nx(a: np.ndarray) -> Optional[float]:
    return None if not np.isfinite(a).any() else float(np.nanmax(a))
