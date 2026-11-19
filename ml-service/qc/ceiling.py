"""Ceiling check: where is the recall lost, and how much of it could any detector get on this benchmark?

For stored scores of a component, at one false-alarm budget, split the fault cell-days of the held-out validation years by
  * how much the value changed (|corrupted - clean|, mm),
  * the footprint weight (local strength of the fault at that cell; 1 at the centre),
  * the fault kind, separately for centre cells and for "strong" cell-days (change >= STRONG_MM and weight >= STRONG_WEIGHT),
and report the recall of each group. Three readings:
  * Many fault cell-days with a tiny change or a small weight: the benchmark labels cells no detector could see, so a high
    overall recall is not reachable and the fair target is the recall on strong cell-days.
  * Strong cell-days of a kind are also missed: the evidence is missing (a model or feature problem), not the label.
  * A kind is caught at centre cells but not at fringe cells: the footprint, not the detector, caps its recall.
Validation years only (the threshold years, which the fusion was not fitted on). Test and stress years are never read.
Everything is SYNTHETIC faults; it says nothing about real data quality. The thresholds are the same budget thresholds as in the
validation curves (from clean threshold years)."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from qc import paths
from qc.evaluate import group_cells, load_years, score_store, thresholds_for
from qc.fusion_eval import holdout_years
from qc.prepare import Prepared

STRONG_MM = 5.0
STRONG_WEIGHT = 0.5
CHANGE_BINS = [(0.0, 0.1), (0.1, 1.0), (1.0, 5.0), (5.0, 20.0), (20.0, 100.0), (100.0, np.inf)]
WEIGHT_BINS = [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0001)]


def _recall(flag: np.ndarray, mask: np.ndarray) -> Dict:
    n = int(mask.sum())
    return {"n": n, "recall": (float(flag[mask].mean()) if n else None)}


def fault_table(p: Prepared, component: str, budget: float, store=None, years: Optional[Sequence[int]] = None) -> Dict:
    """One row per fault cell-day of the held-out validation years, as column arrays, plus the flag at ``budget``."""
    store = store or score_store(p)
    thr = thresholds_for(p, component, [budget], store)[float(budget)]
    cells = group_cells(p, "seen")
    cols: Dict[str, List[np.ndarray]] = {k: [] for k in ("change", "weight", "kind", "centre", "flag")}
    for ys in load_years(p, component, "val", list(years) if years else holdout_years(p), store):
        fs, clean = ys.bench.faults, ys.bench.clean
        keep = cells[fs.cell]
        t, c = fs.t[keep], fs.cell[keep]
        score = np.nan_to_num(ys.score[t, c], nan=-np.inf)
        ev = fs.event[keep]
        events = fs.events
        cols["change"].append(np.abs(fs.value[keep] - clean[t, c]))
        cols["weight"].append(fs.weight[keep])
        cols["kind"].append(np.array([events[e]["kind"] for e in ev]))
        cols["centre"].append(np.array([events[e]["centre"] == cell for e, cell in zip(ev, c)], bool))
        cols["flag"].append(score > thr)
    if not cols["flag"]:
        raise ValueError("no fault cell-days to analyse")
    return {k: np.concatenate(v) for k, v in cols.items()} | {"threshold": thr}


def analyse(tab: Dict, budget: float) -> Dict:
    flag, change, weight, kind, centre = tab["flag"], tab["change"], tab["weight"], tab["kind"], tab["centre"]
    allm = np.ones(flag.size, bool)
    strong = (change >= STRONG_MM) & (weight >= STRONG_WEIGHT)
    out: Dict = {
        "budget_per_1000": float(budget), "threshold": float(tab["threshold"]),
        "overall": _recall(flag, allm), "strong": _recall(flag, strong),
        "share_of_fault_cell_days": {"change_under_1mm": float((change < 1.0).mean()), "weight_under_0.5": float((weight < 0.5).mean()),
                                     "strong": float(strong.mean())},
        "by_change_mm": {f"{lo:g}-{hi:g}": _recall(flag, (change >= lo) & (change < hi)) for lo, hi in CHANGE_BINS},
        "by_weight": {f"{lo:g}-{min(hi, 1.0):g}": _recall(flag, (weight >= lo) & (weight < hi)) for lo, hi in WEIGHT_BINS},
        "by_kind": {},
    }
    for k in sorted(set(kind.tolist())):
        m = kind == k
        out["by_kind"][k] = {"all": _recall(flag, m), "centre_cells": _recall(flag, m & centre), "strong": _recall(flag, m & strong),
                             "change_under_1mm_share": float((change[m] < 1.0).mean())}
    return out


def markdown(component: str, res: Dict) -> str:
    f = lambda d: "-" if d["recall"] is None else f"{d['recall']:.3f} (n={d['n']})"
    o = [f"### Ceiling check: {component}", "",
         f"SYNTHETIC faults, held-out validation years only. Budget {res['budget_per_1000']:g} false alerts per 1,000 clean cell-days "
         f"(threshold {res['threshold']:.3f}). Strong = change >= {STRONG_MM:g} mm and footprint weight >= {STRONG_WEIGHT:g}.", "",
         f"Overall recall {f(res['overall'])}; recall on strong cell-days {f(res['strong'])}.",
         f"Share of fault cell-days: change under 1 mm {res['share_of_fault_cell_days']['change_under_1mm']:.1%}, "
         f"weight under 0.5 {res['share_of_fault_cell_days']['weight_under_0.5']:.1%}, strong {res['share_of_fault_cell_days']['strong']:.1%}.", "",
         "| change (mm) | recall |", "|---|---|"]
    o += [f"| {k} | {f(v)} |" for k, v in res["by_change_mm"].items()]
    o += ["", "| footprint weight | recall |", "|---|---|"] + [f"| {k} | {f(v)} |" for k, v in res["by_weight"].items()]
    o += ["", "| kind | all | centre cells | strong | share under 1 mm |", "|---|---|---|---|---|"]
    o += [f"| {k} | {f(v['all'])} | {f(v['centre_cells'])} | {f(v['strong'])} | {v['change_under_1mm_share']:.1%} |"
          for k, v in res["by_kind"].items()]
    return "\n".join(o) + "\n"


def run_ceiling(p: Prepared, components: Sequence[str], budget: float = 1.0, store=None) -> Dict[str, Dict]:
    """Analyse each stored component; write <run>/ceiling/ceiling_<component>.{json,md} and ceiling.md (all in one)."""
    import json
    out_dir = paths.out_dir(p.cfg) / str(p.cfg.name) / "ceiling"
    out_dir.mkdir(parents=True, exist_ok=True)
    results, md = {}, []
    for name in components:
        res = analyse(fault_table(p, name, budget, store), budget)
        res["component"] = name
        results[name] = res
        (out_dir / f"ceiling_{name}.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
        md.append(markdown(name, res))
    (out_dir / "ceiling.md").write_text("\n".join(md), encoding="utf-8")
    return results
