"""Metric definitions for the QC benchmark (spec section 9). All labels here are synthetic faults.

Cell-day groups (they never overlap):
  fault      carries a synthetic fault
  protected  protected extreme (never corrupted); reported in its own rows
  ambiguous  isolated extreme; reported in its own row; in neither the fault nor the clean denominator
  clean      everything else with a finite score. False-alarm budgets are defined on this group only.

A flag is ``score > threshold``. Thresholds come from false-alarm budgets (false alerts per 1,000 clean
cell-days) measured on uncorrupted threshold years, see ``budget_thresholds``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
from sklearn.metrics import average_precision_score

from qc.benchmark import BenchYear
from qc.faults import FaultGenerator
from qc.grid import Grid

DELAY_KINDS = ("stuck", "repeat", "drift")
MONSOON = (151, 272)                 # 0-based day of year, 1 June to 30 September (non-leap)
SIZE_BINS = ((4, 9), (10, 29), (30, 10 ** 9))


@dataclass
class YearScores:
    bench: BenchYear
    score: np.ndarray                # (T, n_land), NaN = not scored


def radius_bin(r: float) -> str:
    return "single cell" if r == 0 else ("radius 1.5-4" if r <= 4 else "radius 4-6")


def budget_thresholds(clean_scores: np.ndarray, budgets: Sequence[float]) -> Dict[float, float]:
    """Threshold per budget so that at most ``budget`` of every 1,000 clean scores exceed it."""
    s = clean_scores[np.isfinite(clean_scores)]
    if s.size == 0:
        raise ValueError("no clean scores to set thresholds on")
    s = np.sort(s)
    out = {}
    for b in budgets:
        k = int(np.floor(float(b) / 1000.0 * s.size))          # how many clean scores may be flagged
        out[float(b)] = float(s[max(s.size - k - 1, 0)])        # flag = score > threshold: at most k (fewer with ties)
    return out


def clean_reference(score: np.ndarray, protected: np.ndarray, ambiguous: np.ndarray, cells: np.ndarray) -> np.ndarray:
    """Scores of clean cell-days of an uncorrupted year, for threshold setting."""
    keep = ~protected & ~ambiguous
    keep &= cells[None, :]
    return score[keep & np.isfinite(score)]


def _ratio(a: float, b: float) -> Optional[float]:
    return float(a) / float(b) if b else None


def _ci(values: np.ndarray) -> Optional[List[float]]:
    v = values[np.isfinite(values)]
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] if v.size else None


def pr_auc(years: List[YearScores], cells: np.ndarray) -> Optional[float]:
    """Area under the precision-recall curve. Positives: fault cell-days. Negatives: every other scored
    cell-day except ambiguous ones (protected extremes count as negatives: flagging them costs precision)."""
    ys, ss = [], []
    for y in years:
        lab = y.bench.faults.labels()
        keep = np.isfinite(y.score) & ~y.bench.extremes.ambiguous & cells[None, :]
        ys.append(lab[keep])
        ss.append(y.score[keep])
    yv, sv = np.concatenate(ys), np.concatenate(ss)
    return float(average_precision_score(yv, sv)) if yv.any() and not yv.all() else None


def evaluate(years: List[YearScores], cells: np.ndarray, threshold: float, grid: Grid, cell_client: np.ndarray,
             bootstrap: int = 200, seed: int = 0) -> Dict:
    """Every metric at one threshold, for the land cells selected by ``cells`` (n_land,) bool."""
    gen = FaultGenerator(grid)
    rng = np.random.default_rng(seed)
    ev_rows: List[Dict] = []
    per_year = []
    prot = {"cd": 0, "cd_flag": 0, "ev": 0, "ev_flag": 0}
    prot_by: Dict[str, Dict[str, List[int]]] = {"client": {}, "season": {}, "size": {}}
    amb = [0, 0]
    for y in years:
        b, f = y.bench, y.bench.faults
        T, n = y.score.shape
        flag = np.nan_to_num(y.score, nan=-np.inf) > threshold
        scored = np.isfinite(y.score) & cells[None, :]
        lab = f.labels()
        # ---- clean cell-days and false alerts
        clean = scored & ~lab & ~b.extremes.protected & ~b.extremes.ambiguous
        per_year.append((int(clean.sum()), int((flag & clean).sum())))
        # ---- faults, per event
        sel = scored[f.t, f.cell]
        E = len(f.events)
        n_cd = np.bincount(f.event[sel], minlength=E)
        fl = flag[f.t, f.cell] & sel
        n_fl = np.bincount(f.event[fl], minlength=E)
        first = np.full(E, np.iinfo(np.int32).max)
        np.minimum.at(first, f.event[fl], f.t[fl])
        for i, e in enumerate(f.events):
            if n_cd[i] == 0:
                continue                                   # the fault lies entirely outside this cell group
            row = {"kind": e["kind"], "radius_bin": radius_bin(e["radius"]), "unseen": bool(b.unseen_setting[i]),
                   "n": int(n_cd[i]), "flagged": int(n_fl[i]), "delay": None, "iou": None}
            if n_fl[i]:
                if e["kind"] in DELAY_KINDS:
                    row["delay"] = int(first[i] - e["start"])
                region, _ = gen.footprint(e["centre"], e["radius"] + 2.0)
                region = region[cells[region]]
                mine = f.event == i
                true = np.zeros((e["duration"], n), bool)
                true[f.t[mine] - e["start"], f.cell[mine]] = True
                true = true[:, region]
                got = flag[e["start"]:e["start"] + e["duration"]][:, region]
                days = true.any(axis=1)
                union = (true | got)[days].sum(axis=1)
                row["iou"] = float(((true & got)[days].sum(axis=1) / np.maximum(union, 1)).mean())
            ev_rows.append(row)
        # ---- protected and ambiguous extremes
        p_mask = b.extremes.protected & scored
        pf = p_mask & flag
        prot["cd"] += int(p_mask.sum())
        prot["cd_flag"] += int(pf.sum())
        groups = np.unique(b.extremes.group[p_mask])
        hit = np.unique(b.extremes.group[pf])
        prot["ev"] += groups.size
        prot["ev_flag"] += hit.size
        tt, cc = np.nonzero(p_mask)
        if tt.size:
            sizes = np.bincount(b.extremes.group.ravel())[b.extremes.group[tt, cc]]
            season = np.where((tt >= MONSOON[0]) & (tt <= MONSOON[1]), "monsoon (Jun-Sep)", "rest of year")
            keys = {"client": cell_client[cc].astype(str), "season": season,
                    "size": np.select([sizes <= 9, sizes <= 29], ["4-9 cells", "10-29 cells"], "30+ cells")}
            fl_cd = pf[tt, cc]
            for dim, lab_arr in keys.items():
                for k in np.unique(lab_arr):
                    m = lab_arr == k
                    acc = prot_by[dim].setdefault(str(k), [0, 0])
                    acc[0] += int(m.sum())
                    acc[1] += int(fl_cd[m].sum())
        a_mask = b.extremes.ambiguous & scored
        amb[0] += int(a_mask.sum())
        amb[1] += int((a_mask & flag).sum())

    n_arr = np.array([r["n"] for r in ev_rows], float)
    f_arr = np.array([r["flagged"] for r in ev_rows], float)

    def fault_block(idx: np.ndarray) -> Dict:
        if idx.size == 0:
            return {"events": 0}
        out = {"events": int(idx.size), "cell_days": int(n_arr[idx].sum()),
               "recall": _ratio(f_arr[idx].sum(), n_arr[idx].sum()),
               "event_recall": float((f_arr[idx] > 0).mean())}
        if bootstrap:
            draws = rng.integers(0, idx.size, size=(bootstrap, idx.size))
            pick = idx[draws]
            out["recall_ci"] = _ci(f_arr[pick].sum(axis=1) / np.maximum(n_arr[pick].sum(axis=1), 1))
            out["event_recall_ci"] = _ci((f_arr[pick] > 0).mean(axis=1))
        ious = np.array([ev_rows[i]["iou"] for i in idx if ev_rows[i]["iou"] is not None], float)
        if ious.size:
            out["footprint_iou"] = float(ious.mean())
        delays = np.array([ev_rows[i]["delay"] for i in idx if ev_rows[i]["delay"] is not None], float)
        if delays.size:
            out["delay_days_median"] = float(np.median(delays))
            out["delay_days_p90"] = float(np.percentile(delays, 90))
        delay_kind = np.array([ev_rows[i]["kind"] in DELAY_KINDS for i in idx])
        if delay_kind.any():
            out["never_detected"] = int((f_arr[idx][delay_kind] == 0).sum())
        return out

    all_idx = np.arange(len(ev_rows))
    res ={"threshold": float(threshold), "faults": fault_block(all_idx)}
    if ev_rows:
        res["by_kind"] = {k: fault_block(np.array([i for i in all_idx if ev_rows[i]["kind"] == k], int))
                          for k in sorted({r["kind"] for r in ev_rows})}
        res["by_radius"] = {k: fault_block(np.array([i for i in all_idx if ev_rows[i]["radius_bin"] == k], int))
                            for k in sorted({r["radius_bin"] for r in ev_rows})}
        res["by_setting"] = {name: fault_block(np.array([i for i in all_idx if ev_rows[i]["unseen"] == flag_], int))
                             for name, flag_ in (("seen settings", False), ("test-only settings", True))}
    n_clean = sum(c for c, _ in per_year)
    n_false = sum(f for _, f in per_year)
    rate = _ratio(1000.0 * n_false, n_clean)
    res["false_alerts"] = {"clean_cell_days": n_clean, "false_alerts": n_false, "per_1000_clean": rate,
                           "per_daily_field": None if rate is None else rate / 1000.0 * grid.n_land}
    if bootstrap and len(per_year) > 1:
        arr = np.array(per_year, float)
        pick = rng.integers(0, len(per_year), size=(bootstrap, len(per_year)))
        res["false_alerts"]["per_1000_clean_ci"] = _ci(1000.0 * arr[pick, 1].sum(axis=1) / np.maximum(arr[pick, 0].sum(axis=1), 1))
    res["protected_extremes"] = {
        "label": "plausible, unverified", "cell_days": prot["cd"], "events": prot["ev"],
        "flagged_share_of_cell_days": _ratio(prot["cd_flag"], prot["cd"]),
        "events_with_any_flag_share": _ratio(prot["ev_flag"], prot["ev"]),
        "cell_days_flagged_by": {dim: {k: {"cell_days": v[0], "flagged_share": _ratio(v[1], v[0])} for k, v in sorted(d.items())}
                                 for dim, d in prot_by.items()},
    }
    res["ambiguous_extremes"] = {"cell_days": amb[0], "flagged_share": _ratio(amb[1], amb[0])}
    return res


def calibration(prob: np.ndarray, label: np.ndarray, bins: int = 10) -> Dict:
    """Reliability table and expected calibration error of a probability against synthetic-fault labels.
    Equal-count bins, because almost all probabilities are near zero at about 1% prevalence."""
    ok = np.isfinite(prob)
    prob, label = prob[ok], label[ok].astype(float)
    edges = np.unique(np.quantile(prob, np.linspace(0, 1, bins + 1)))
    which = np.clip(np.searchsorted(edges, prob, side="right") - 1, 0, max(edges.size - 2, 0))
    rows, ece = [], 0.0
    for k in range(max(edges.size - 1, 1)):
        m = which == k
        if m.any():
            p, o = float(prob[m].mean()), float(label[m].mean())
            rows.append({"mean_predicted": p, "observed_fault_rate": o, "n": int(m.sum())})
            ece += m.mean() * abs(p - o)
    return {"expected_calibration_error": float(ece), "bins": rows,
            "note": "calibrated to the synthetic fault rate; says nothing about real error probability"}
