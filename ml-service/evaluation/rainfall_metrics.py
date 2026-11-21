"""Evaluation code for the rainfall anomaly ensemble. Written and unit-tested on toy arrays only.

Deliberately absent: point-adjusted F1 (it inflates scores; a random score can look strong under it).
Headline metrics: point-wise PR-AUC against a random-score baseline, affiliation-based F1, event/range
metrics, and the false-positive rate on clean data. All run in a fixed list of seeds, every run reported.

[unvalidated] ``affiliation`` is written from the published definition (Huet et al., 2022) as I understand
it and has not been cross-checked against the reference ``affiliation-metrics`` package; do that on the
training machine before quoting its numbers. The unit tests only check its defining properties.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

NAN = float("nan")

# Season bounds as (first_doy, last_doy) of a 0-based day-of-year index; configurable.
# "monsoon_onset" is a crude calendar proxy (June), NOT a per-region onset date.
DEFAULT_SEASONS: Dict[str, Tuple[int, int]] = {
    "winter": (0, 58), "pre_monsoon": (59, 151), "monsoon_onset": (152, 181),
    "monsoon": (182, 273), "post_monsoon": (274, 365),
}


# --------------------------------------------------------------------------- point-wise
def pointwise(y: np.ndarray, s: np.ndarray) -> Dict[str, float]:
    y, s = np.asarray(y, bool).ravel(), np.asarray(s, float).ravel()
    if not y.any() or y.all():
        return {"pr_auc": NAN, "roc_auc": NAN, "prevalence": float(y.mean()) if y.size else NAN}
    return {"pr_auc": float(average_precision_score(y, s)), "roc_auc": float(roc_auc_score(y, s)),
            "prevalence": float(y.mean())}


def random_baseline(y: np.ndarray, seed: int = 0) -> Dict[str, float]:
    """PR-AUC of uniform random scores (expected value ~ prevalence). Always report next to a model."""
    y = np.asarray(y, bool).ravel()
    if not y.any() or y.all():
        return {"pr_auc": NAN}
    return {"pr_auc": float(average_precision_score(y, np.random.default_rng(seed).random(y.size)))}


def threshold_metrics(y: np.ndarray, pred: np.ndarray) -> Dict[str, float]:
    y, pred = np.asarray(y, bool).ravel(), np.asarray(pred, bool).ravel()
    tp, fp, fn = int((pred & y).sum()), int((pred & ~y).sum()), int((~pred & y).sum())
    neg = int((~y).sum())
    prec = tp / (tp + fp) if tp + fp else NAN
    rec = tp / (tp + fn) if tp + fn else NAN
    f1 = 2 * prec * rec / (prec + rec) if tp else 0.0
    return {"precision": prec, "recall": rec, "f1": f1, "fpr": fp / neg if neg else NAN}


def fpr_on_clean(pred: np.ndarray, y: np.ndarray) -> float:
    """Share of anomaly-free points flagged (false-positive rate)."""
    return threshold_metrics(y, pred)["fpr"]


# --------------------------------------------------------------------------- events
def to_events(mask: np.ndarray) -> List[Tuple[int, int]]:
    """Inclusive (start, end) index pairs of consecutive True runs."""
    m = np.asarray(mask, bool).ravel()
    if not m.any():
        return []
    d = np.diff(np.concatenate([[0], m.astype(int), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1))


def event_metrics(y: np.ndarray, pred: np.ndarray, tol: int = 0) -> Dict[str, float]:
    """Range-based metrics without point adjustment. A true event counts as detected if any predicted
    point falls within ``tol`` steps of it; a predicted event is correct if it touches a true event
    within ``tol``. ``delay`` is steps from event start to the first alarm (detected events only)."""
    y, pred = np.asarray(y, bool).ravel(), np.asarray(pred, bool).ravel()
    ev, pv = to_events(y), to_events(pred)
    det_delay, hit = [], 0
    for a, b in ev:
        idx = np.flatnonzero(pred[max(a - tol, 0): b + tol + 1])
        if idx.size:
            hit += 1
            det_delay.append(max(idx[0] + max(a - tol, 0) - a, 0))
    good = sum(1 for a, b in pv if y[max(a - tol, 0): b + tol + 1].any())
    rec = hit / len(ev) if ev else NAN
    prec = good / len(pv) if pv else NAN
    f1 = 2 * prec * rec / (prec + rec) if (prec and rec and not np.isnan(prec) and not np.isnan(rec)) else 0.0
    return {"event_recall": rec, "event_precision": prec, "event_f1": f1,
            "false_alarm_events": float(len(pv) - good), "mean_delay": float(np.mean(det_delay)) if det_delay else NAN,
            "n_events": float(len(ev)), "n_predicted_events": float(len(pv))}


def affiliation(y: np.ndarray, pred: np.ndarray) -> Dict[str, float]:
    """Affiliation precision / recall / F1 (see module docstring for the caveat)."""
    y, pred = np.asarray(y, bool).ravel(), np.asarray(pred, bool).ravel()
    t_len, ev, preds = y.size, to_events(y), np.flatnonzero(pred)
    if not ev:
        return {"aff_precision": NAN, "aff_recall": NAN, "aff_f1": NAN}
    if preds.size == 0:
        return {"aff_precision": NAN, "aff_recall": 0.0, "aff_f1": 0.0}
    bounds = [0.0] + [(ev[j][1] + ev[j + 1][0]) / 2.0 for j in range(len(ev) - 1)] + [float(t_len)]
    pts = np.arange(t_len)
    precs, recs = [], []
    for j, (a, b) in enumerate(ev):
        zone = pts[(pts >= bounds[j]) & (pts < bounds[j + 1])]
        pj = preds[(preds >= bounds[j]) & (preds < bounds[j + 1])]
        if pj.size == 0:
            recs.append(0.0)
            continue
        d_zone = np.sort(np.maximum(a - zone, 0) + np.maximum(zone - b, 0))
        d_pred = np.maximum(a - pj, 0) + np.maximum(pj - b, 0)
        precs.append(float((1.0 - np.searchsorted(d_zone, d_pred, side="left") / d_zone.size).mean()))
        gt = np.arange(a, b + 1)
        d_gt = np.abs(gt[:, None] - pj[None, :]).min(axis=1)
        recs.append(float((np.abs(gt[:, None] - zone[None, :]) >= d_gt[:, None]).mean()))
    p = float(np.mean(precs)) if precs else NAN
    r = float(np.mean(recs))
    f1 = 2 * p * r / (p + r) if (precs and p + r > 0) else 0.0
    return {"aff_precision": p, "aff_recall": r, "aff_f1": f1}


# --------------------------------------------------------------------------- windows & breakdowns
def concat_windows(a: np.ndarray, gap: int) -> np.ndarray:
    """(n, W) -> one long series with ``gap`` False steps between windows (so events never join)."""
    n, w = a.shape
    out = np.zeros((n, w + gap), dtype=a.dtype)
    out[:, :w] = a
    return out.ravel()


def window_metrics(y: np.ndarray, s: np.ndarray, pred: np.ndarray, seed: int = 0, tol: int = 0) -> Dict[str, float]:
    """All headline metrics for (n, W) arrays: point-wise PR-AUC + random baseline, threshold metrics,
    event metrics and affiliation F1 on the gap-concatenated series."""
    y, s, pred = np.asarray(y, bool), np.asarray(s, float), np.asarray(pred, bool)
    gap = y.shape[1]
    yl, pl = concat_windows(y, gap), concat_windows(pred, gap)
    out = {**pointwise(y, s), **{f"random_{k}": v for k, v in random_baseline(y, seed).items()},
           **threshold_metrics(y, pred), **event_metrics(yl, pl, tol), **affiliation(yl, pl)}
    out["fpr_clean"] = out["fpr"]
    return out


def season_labels(doy: np.ndarray, seasons: Optional[Dict[str, Tuple[int, int]]] = None) -> np.ndarray:
    """(n, W) int doy -> (n, W) season names. Monsoon onset is reported separately from the monsoon."""
    seasons = seasons or DEFAULT_SEASONS
    out = np.full(doy.shape, "other", dtype=object)
    for name, (lo, hi) in seasons.items():
        out[(doy >= lo) & (doy <= hi)] = name
    return out


def region_labels(lat_norm: np.ndarray, edges: Sequence[float] = (0.33, 0.66)) -> np.ndarray:
    """(n,) normalized latitude -> south / central / north bands (no shapefile available; a stand-in)."""
    names = np.array(["south", "central", "north"], dtype=object)
    return names[np.digitize(lat_norm, edges)]


def breakdown(y: np.ndarray, s: np.ndarray, pred: np.ndarray, groups: np.ndarray, seed: int = 0) -> Dict[str, Dict[str, float]]:
    """Metrics per category. ``groups`` is (n,) (window-level: full metrics) or (n, W) (point-level:
    point-wise PR-AUC, threshold metrics and FPR only; events are not defined across scattered points)."""
    y, s, pred, groups = np.asarray(y, bool), np.asarray(s, float), np.asarray(pred, bool), np.asarray(groups)
    out = {}
    for g in np.unique(groups):
        sel = groups == g
        if groups.ndim == 1:
            out[str(g)] = window_metrics(y[sel], s[sel], pred[sel], seed)
        else:
            out[str(g)] = {**pointwise(y[sel], s[sel]), **threshold_metrics(y[sel], pred[sel]),
                           **{f"random_{k}": v for k, v in random_baseline(y[sel], seed).items()}}
    return out


# --------------------------------------------------------------------------- seeds
def _mean_std(runs: List[dict]) -> Tuple[dict, dict]:
    keys = [k for k, v in runs[0].items() if isinstance(v, (int, float))]
    arr = {k: np.array([r[k] for r in runs], float) for k in keys}
    return ({k: float(np.nanmean(v)) if np.isfinite(v).any() else NAN for k, v in arr.items()},
            {k: float(np.nanstd(v)) if np.isfinite(v).any() else NAN for k, v in arr.items()})


def run_seeds(run_fn: Callable[[int], dict], seeds: Sequence[int]) -> dict:
    """Run ``run_fn(seed)`` for every seed in the fixed list and report **all** runs plus mean/std.
    There is deliberately no best-of-N selection."""
    seeds = list(seeds)
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be a non-empty list without duplicates")
    runs = [run_fn(int(sd)) for sd in seeds]
    mean, std = _mean_std(runs)
    return {"seeds": seeds, "runs": runs, "mean": mean, "std": std}


# --------------------------------------------------------------------------- ablations
def ablation_variants(branches: Sequence[str], rules: Sequence[str], scale_modes: Sequence[str] = ("multi_scale", "single_scale")) -> List[dict]:
    """Config-driven ablation grid: each fusion rule, each leave-one-branch-out, and scale mode.
    Fusion-only variants (rule / drop-branch) re-use cached branch scores; ``scale_mode`` variants need
    their own trained model."""
    out = [{"scale_mode": m, "rule": r, "drop_branch": None} for m in scale_modes for r in rules]
    out += [{"scale_mode": scale_modes[0], "rule": r, "drop_branch": b} for r in rules for b in branches]
    return out
