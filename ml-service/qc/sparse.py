"""Gauges as a sparse grid: put rain gauges into the RF25 frame and score them with a trained network (STNet), and measure what sparsity costs.

STATUS: BUILT and unit-tested on generated arrays; NOT RUN on RF25 or on real gauges. Nothing here says the scores are good.

STNet was trained on a full 0.25 degree field with a few held-out areas set to NaN. A handful of gauges is far sparser than anything it saw, so
a gauge score from this module is NOT VALIDATED until ``sparse-check`` (below) has been run on the validation years and its result recorded.
The export says so in its notes, and the scores are the raw fault-head softplus (not standardised, not calibrated, no flag threshold).

Three parts:
  * ``cell_of`` / ``gauges_to_obs``: each gauge goes to the grid cell that CONTAINS it (a cell is its centre plus or minus half a step). Two
    gauges in one cell are averaged for that day (and listed in the report); a gauge outside the grid, on a sea cell, without coordinates or
    without data is rejected with its reason. Cells without a gauge stay NaN, which the network reads as "not valid".
  * ``score_gauges``: the one pass from a gauge file to a score export (the score function is passed in, so this part needs no torch).
  * ``sparse_functions`` / ``sparse_check``: the experiment. The same network is scored on the validation benchmark with all but K land
    cells hidden, at several K, against the full field, with the usual false-alarm budgets (thresholds re-fixed on clean days seen the same
    sparse way). The answer is a table of recall and false alarms against K, SYNTHETIC faults, validation years only.
"""
from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from qc.grid import Grid
from qc.scoring import Block

MIN_STEP = 1e-6
NOTES = ("sparse gauge input: only the cells holding a gauge are valid, the rest of the grid is NaN. NOT VALIDATED on sparse input until the "
         "sparse-check result is recorded; raw softplus of the fault logit, not standardised, not calibrated, no threshold. SYNTHETIC-tier.")


@dataclass(frozen=True)
class Gauge:
    station: str
    lat: Optional[float]
    lon: Optional[float]
    days: Mapping[str, Optional[float]]         # ISO date -> mm of that rain day (None or NaN: no data)


@dataclass(frozen=True)
class CellHit:
    row: int
    col: int
    land_index: int                              # index into the land-cell axis (n_land)
    offset_deg: Tuple[float, float]              # gauge minus cell centre (lat, lon)


def _step(axis: np.ndarray) -> float:
    d = np.abs(np.diff(axis.astype(np.float64)))
    return float(np.median(d)) if d.size else 0.0


def _axis_index(axis: np.ndarray, v: float) -> Optional[int]:
    """The index of the cell whose centre is within half a step of ``v``, or None when ``v`` lies outside the axis."""
    step = _step(axis)
    if step < MIN_STEP:
        return None
    j = int(np.argmin(np.abs(axis.astype(np.float64) - v)))
    return j if abs(float(axis[j]) - v) <= step / 2 + 1e-9 else None


def land_index_map(grid: Grid) -> np.ndarray:
    m = np.full(grid.shape, -1, dtype=np.int64)
    m[grid.rows, grid.cols] = np.arange(grid.n_land)
    return m


def cell_of(grid: Grid, lat: Optional[float], lon: Optional[float], index_map: Optional[np.ndarray] = None) -> Tuple[Optional[CellHit], Optional[str]]:
    """The grid cell containing a point, or the reason there is none. A point exactly on a cell edge goes to the lower index."""
    if lat is None or lon is None or not (math.isfinite(lat) and math.isfinite(lon)):
        return None, "no coordinates"
    r, c = _axis_index(grid.lat, lat), _axis_index(grid.lon, lon)
    if r is None or c is None:
        return None, "outside the grid"
    idx = (index_map if index_map is not None else land_index_map(grid))[r, c]
    if idx < 0:
        return None, "on a sea cell (not land in the grid)"
    return CellHit(r, c, int(idx), (round(lat - float(grid.lat[r]), 4), round(lon - float(grid.lon[c]), 4))), None


def date_range(first: str, last: str) -> List[str]:
    a, b = date.fromisoformat(first), date.fromisoformat(last)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def gauges_to_obs(grid: Grid, gauges: Sequence[Gauge], periods: Sequence[str]) -> Tuple[np.ndarray, Dict[str, Any]]:
    """(len(periods), n_land) mm, NaN in every cell without a gauge or on a day without data, plus the placement report."""
    obs = np.full((len(periods), grid.n_land), np.nan, dtype=np.float32)
    pos = {p: i for i, p in enumerate(periods)}
    imap = land_index_map(grid)
    members: Dict[int, List[str]] = {}
    rejected: Dict[str, str] = {}
    placed: Dict[str, Dict[str, Any]] = {}
    sums = np.zeros_like(obs, dtype=np.float64)
    counts = np.zeros(obs.shape, dtype=np.int32)
    for g in gauges:
        hit, why = cell_of(grid, g.lat, g.lon, imap)
        if hit is None:
            rejected[g.station] = why or "unplaced"
            continue
        n_days = 0
        for day, mm in g.days.items():
            i = pos.get(day[:10])
            if i is None or mm is None or not math.isfinite(mm) or mm < 0:
                continue
            sums[i, hit.land_index] += mm
            counts[i, hit.land_index] += 1
            n_days += 1
        if n_days == 0:
            rejected[g.station] = "no usable day inside the period"
            continue
        members.setdefault(hit.land_index, []).append(g.station)
        placed[g.station] = {"row": hit.row, "col": hit.col, "land_index": hit.land_index, "offset_deg": list(hit.offset_deg), "days": n_days}
    ok = counts > 0
    obs[ok] = (sums[ok] / counts[ok]).astype(np.float32)
    shared = {int(k): v for k, v in members.items() if len(v) > 1}
    report = {"stations": len(gauges), "placed": len(placed), "cells": len(members), "shared_cells": shared, "rejected": rejected, "placements": placed,
              "rule": "each gauge goes to the cell that contains it; gauges sharing a cell are averaged per day; other cells stay NaN"}
    return obs, report


def doy0(periods: Sequence[str]) -> np.ndarray:
    """0-based day of year per row (leap years included), as the network's calendar input expects."""
    return np.array([date.fromisoformat(p).timetuple().tm_yday - 1 for p in periods], dtype=np.int16)


def parse_gauge_file(text: str) -> List[Gauge]:
    """The gauge file: ``{"gauges": [{"station", "lat", "lon", "days": {"YYYY-MM-DD": mm}}]}`` (written by GET /api/validation/gauges)."""
    try:
        data = json.loads(text)
        raw = data["gauges"]
    except (ValueError, KeyError, TypeError):
        raise ValueError('not a gauge file: expected {"gauges": [...]}')
    out = []
    for g in raw:
        if not isinstance(g, dict) or not g.get("station") or not isinstance(g.get("days"), dict):
            raise ValueError("every gauge needs a station and a days object")
        out.append(Gauge(str(g["station"]), g.get("lat"), g.get("lon"), g["days"]))
    return out


def withhold_short_history(scores: np.ndarray, valid: np.ndarray, min_days: int) -> Tuple[np.ndarray, int]:
    """NaN every score of a cell on a day when the cell had fewer than ``min_days`` observed days of its own before that day. ``valid`` is the
    (T, n) mask of days with a reading. Returns the scores and how many were withheld. A day with a short memory is not scored rather than scored weakly."""
    if min_days <= 0:
        return scores, 0
    prior = np.cumsum(valid, axis=0) - valid                     # own observed days strictly before each day
    cut = (prior < min_days) & np.isfinite(scores)
    out = scores.copy()
    out[cut] = np.nan
    return out, int(cut.sum())


def score_gauges(grid: Grid, gauges: Sequence[Gauge], score_fn: Callable[[Block], np.ndarray], history_days: int,
                 min_history_days: int = 0) -> Dict[str, Any]:
    """Score every day of the gauge file. ``score_fn`` maps a Block to (T, n_land) scores with NaN where the target is not finite, which is how
    only the gauge cells keep a score. History before the first day is empty (NaN), so the memory is short early on: with
    ``min_history_days`` a cell's scores are withheld until it has that many observed days of its own (a file cannot add history that was
    never recorded; the feed history starts when polling started)."""
    days = sorted({d[:10] for g in gauges for d, mm in g.days.items() if mm is not None})
    if not days:
        raise ValueError("the gauge file has no rain day")
    pre = [(date.fromisoformat(days[0]) - timedelta(days=history_days - i)).isoformat() for i in range(history_days)]
    periods = date_range(days[0], days[-1])                                   # every day, gaps stay NaN
    obs, report = gauges_to_obs(grid, gauges, pre + periods)
    if report["placed"] == 0:
        raise ValueError("no gauge could be placed on the grid: " + json.dumps(report["rejected"]))
    block = Block(date.fromisoformat(periods[0]).year, "live", obs, history_days, doy0(pre + periods), None)
    scores = np.asarray(score_fn(block), dtype=np.float32)
    scores, withheld = withhold_short_history(scores, np.isfinite(block.target), min_history_days)
    keep = np.nonzero(np.isfinite(scores).any(axis=0))[0]
    if keep.size == 0:
        raise ValueError("no gauge cell has a score: the network gave none, or every day is inside the first %d days of history" % min_history_days
                         if min_history_days else "the network gave no finite score for any gauge cell")
    report["min_history_days"], report["withheld_scores"] = min_history_days, withheld
    return {"periods": periods, "land_index": keep, "lat": grid.lat[grid.rows[keep]], "lon": grid.lon[grid.cols[keep]], "scores": scores[:, keep], "report": report}


# the experiment -----------------------------------------------------------------------------------------------------------------------

def sparse_keep(grid: Grid, n_cells: int, seed: int) -> np.ndarray:
    """A boolean (H, W) mask of ``n_cells`` land cells drawn at random without replacement (same seed, same cells). Random is the easy case:
    real gauges cluster in cities; say so wherever a result is shown."""
    if n_cells <= 0 or n_cells > grid.n_land:
        raise ValueError(f"n_cells must be between 1 and {grid.n_land}")
    rng = np.random.default_rng(seed)
    pick = rng.choice(grid.n_land, size=n_cells, replace=False)
    keep = np.zeros(grid.shape, dtype=bool)
    keep[grid.rows[pick], grid.cols[pick]] = True
    return keep


def sparse_functions(fns: Mapping[str, Callable[[Block], np.ndarray]], grid: Grid, n_cells: int, seed: int, only: str) -> Dict[str, Callable[[Block], np.ndarray]]:
    """The score function ``only`` evaluated with all but ``n_cells`` land cells hidden, stored under ``<only with _sparse<K>>``. The block's
    own copy is masked (the original is read-only for other scorers); scores outside the kept cells come out NaN because their target is NaN."""
    if only not in fns:
        raise KeyError(f"no score function {only!r}")
    keep = grid.to_series(sparse_keep(grid, n_cells, seed))
    base = fns[only]

    def wrapped(block: Block) -> np.ndarray:
        obs = block.obs.copy()
        obs[:, ~keep] = np.nan
        return base(dataclasses.replace(block, obs=obs))

    head, _, tail = only.rpartition("_s")
    return {f"{head}_sparse{n_cells}_s{tail}": wrapped}


def sparse_check(p, fns: Mapping[str, Callable[[Block], np.ndarray]], only: str, cells: Sequence[int], seed: int, out_dir: Path,
                 budgets: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    """Score the validation years at each K, evaluate with the usual budgets and write ``sparse_check_s<seed>.json`` and ``.md``.
    Needs a prepared config (RF25 present) and a finished STNet run; validation years only."""
    from qc.evaluate import compute_scores_many, evaluate_component, score_store
    from qc.runs import write_json

    budgets = list(budgets or p.cfg.evaluation.budgets)
    store = score_store(p)
    rows: List[Dict[str, Any]] = []
    for k in [None, *cells]:
        if k is None:
            name, label = only, "full field"
            compute_scores_many(p, {only: fns[only]}, ("val",), store, False)
        else:
            sf = sparse_functions(fns, p.grid, int(k), seed, only)
            name, label = next(iter(sf)), f"{k} cells"
            compute_scores_many(p, sf, ("val",), store, False)
        m = evaluate_component(p, name, "val", budgets, ("seen",), store, pinned=True)
        rows.append({"cells": k, "label": label, "component": name, "metrics": m})
    result = {"seed": seed, "cells": [None, *cells], "budgets_per_1000": budgets, "label_tier": "SYNTHETIC faults, validation years only",
              "caveats": ["cells are drawn at random: real gauges cluster, so this is the easy case",
                          "the threshold at each K is fixed on clean days seen the same sparse way (the same rule as the full field)"],
              "rows": rows}
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / f"sparse_check_s{seed}.json", result)
    (out_dir / f"sparse_check_s{seed}.md").write_text(to_markdown(result), encoding="utf-8")
    return result


def _metric(m: Dict[str, Any], budget: float) -> Tuple[Optional[float], Optional[float]]:
    """(recall, event recall) at the budget, read defensively from an ``evaluate_component`` result; None where the layout differs."""
    try:
        g = m["groups"]["seen"]
        at = g.get("budgets", g).get(str(budget)) or g.get("budgets", g).get(budget)
        return at.get("recall"), at.get("event_recall")
    except (KeyError, AttributeError, TypeError):
        return None, None


def to_markdown(result: Dict[str, Any]) -> str:
    b = result["budgets_per_1000"][0]
    lines = [f"# STNet fault head on sparse input, validation years, seed {result['seed']}", "", f"{result['label_tier']}. "
             + " ".join(result["caveats"]), "", f"| input | recall at {b} false alerts per 1,000 clean cell-days | event recall |", "|---|---|---|"]
    for r in result["rows"]:
        rec, ev = _metric(r["metrics"], b)
        lines.append(f"| {r['label']} | {'n/a' if rec is None else f'{rec:.3f}'} | {'n/a' if ev is None else f'{ev:.3f}'} |")
    lines += ["", "Full metrics per row are in the JSON file beside this one."]
    return "\n".join(lines) + "\n"
