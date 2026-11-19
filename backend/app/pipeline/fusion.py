"""Retraining from reviewer labels: refit the weights that combine the checks (step C of the update ladder in
docs/mlops-feedback-loop-spec.md). Standalone on purpose (numpy and scipy only, no imports from the platform) so the same file runs on the
server's CPU or inside a Kaggle notebook.

What it is: a non-negative logistic regression over which checks fired on a station-day, trained on the labels of a training snapshot
(reviewed fault, false alarm, audit "ok" and "missed fault", weighted). What it is NOT: a deep model, and not the RF25 STNet; it only
learns how much to trust each check. The existing fixed-weight rule score is evaluated on the SAME later validation days as the baseline,
so the comparison is like for like.

Honesty limits stated in every result: the labels are one reviewer's judgements, the validation days are the later part of the same
snapshot (a temporal split, never random), and with few labels the numbers are not meaningful, so training refuses below a minimum.
"""
from __future__ import annotations

import json
import math
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize

CHECKS: Tuple[str, ...] = ("impossible_value", "repeated_value", "climatology_upper_tail", "neighbour_isolated_wet", "neighbour_isolated_dry", "duplicate_row")
FIXED_WEIGHTS: Dict[str, float] = {"impossible_value": 0.95, "repeated_value": 0.60, "climatology_upper_tail": 0.30,
                                   "neighbour_isolated_wet": 0.30, "neighbour_isolated_dry": 0.30, "duplicate_row": 0.30}   # the platform's rule weights
MIN_FAULT, MIN_CLEAN = 20, 100                 # labels needed to TRAIN (earlier days)
MIN_VAL_FAULT, MIN_VAL_CLEAN = 5, 20           # labels needed to JUDGE (later days); the registry gate imports these so the two cannot disagree
TRAIN_SHARE = 0.7
BUDGET_PER_1000 = 5.0


class NotEnoughLabels(ValueError):
    pass


def parse_snapshot(text: str) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _x(row: Dict[str, Any]) -> np.ndarray:
    fired = set(row.get("checks") or [])
    return np.array([1.0 if c in fired else 0.0 for c in CHECKS])


def _rule(row: Dict[str, Any]) -> float:
    p = 1.0
    for c in row.get("checks") or []:
        p *= 1.0 - FIXED_WEIGHTS.get(c, 0.0)
    return 1.0 - p


def temporal_split(rows: Sequence[Dict[str, Any]], share: float = TRAIN_SHARE) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    """Earlier days train, later days validate. Rows of the boundary day stay together, so no day is in both."""
    days = sorted({r["day"] for r in rows})
    if len(days) < 2:
        raise NotEnoughLabels("need labelled rows on at least two different days to split by time")
    cut = days[max(0, min(len(days) - 2, int(len(days) * share) - 1))]
    return [r for r in rows if r["day"] <= cut], [r for r in rows if r["day"] > cut], cut


def _fit(X: np.ndarray, y: np.ndarray, w: np.ndarray, l2: float = 1.0) -> Tuple[np.ndarray, float]:
    n, d = X.shape

    def loss(theta: np.ndarray):
        coef, b = theta[:d], theta[d]
        z = X @ coef + b
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        eps = 1e-9
        val = -np.sum(w * (y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))) / w.sum() + 0.5 * l2 * np.sum(coef ** 2) / max(n, 1)
        g = (p - y) * w / w.sum()
        return val, np.concatenate([X.T @ g + l2 * coef / max(n, 1), [g.sum()]])

    res = minimize(loss, np.zeros(d + 1), jac=True, method="L-BFGS-B", bounds=[(0, None)] * d + [(None, None)])
    return res.x[:d], float(res.x[d])


def _threshold_for_budget(scores_clean: np.ndarray, weights_clean: np.ndarray, budget_per_1000: float) -> float:
    """The lowest threshold whose weighted false-alarm rate on the TRAINING clean days stays within the budget."""
    if not len(scores_clean):
        return 1.0
    allowed = weights_clean.sum() * budget_per_1000 / 1000.0
    thr = float(scores_clean.max()) + 1e-6                 # flags no clean day at all, unless a lower value fits the budget
    for v in sorted({float(s) for s in scores_clean}, reverse=True):
        # every clean day scoring at or above v is flagged, ties included, so a tie is taken whole or not at all
        if float(weights_clean[scores_clean >= v - 1e-12].sum()) > allowed:
            break
        thr = v
    return thr


def _metrics(score: np.ndarray, rows: Sequence[Dict[str, Any]], thr: float) -> Dict[str, Any]:
    lab = np.array([r["label"] for r in rows])
    w = np.array([float(r.get("weight", 1.0)) for r in rows])
    flagged = score >= thr
    fault, clean, genuine = lab == "fault", lab == "clean", lab == "genuine_extreme"
    recall = float(w[fault & flagged].sum() / w[fault].sum()) if w[fault].sum() else None
    fa = float(w[clean & flagged].sum() / w[clean].sum() * 1000.0) if w[clean].sum() else None
    return {"recall_at_budget": recall, "false_alarms_per_1000": fa, "protected_extremes_flagged": int((genuine & flagged).sum()),
            "n_fault": int(fault.sum()), "n_clean": int(clean.sum()), "n_genuine_extreme": int(genuine.sum())}


def train(rows: Sequence[Dict[str, Any]], budget_per_1000: float = BUDGET_PER_1000, min_fault: int = MIN_FAULT, min_clean: int = MIN_CLEAN,
          snapshot_sha256: Optional[str] = None) -> Dict[str, Any]:
    """Fit on the earlier days, judge on the later days, and report the candidate and the fixed-weight baseline on the same validation rows."""
    # Rows excluded by an accepted correction are KEPT: accepting an exclude_value proposal is exactly how an impossible value is confirmed as a
    # fault, and the checks that fired on the original value are already in "checks" (mm_original semantics).
    rows = [r for r in rows if r.get("label") in ("fault", "clean", "genuine_extreme")]
    tr, va, cut = temporal_split(rows)
    trn = [r for r in tr if r["label"] in ("fault", "clean")]
    n_fault, n_clean = sum(r["label"] == "fault" for r in trn), sum(r["label"] == "clean" for r in trn)
    v_fault, v_clean = sum(r["label"] == "fault" for r in va), sum(r["label"] == "clean" for r in va)
    if n_fault < min_fault or n_clean < min_clean or v_fault < MIN_VAL_FAULT or v_clean < MIN_VAL_CLEAN:
        raise NotEnoughLabels(f"too few labels to train or judge: train {n_fault} faults and {n_clean} clean (need {min_fault} and {min_clean}), "
                              f"validation {v_fault} faults and {v_clean} clean (need {MIN_VAL_FAULT} and {MIN_VAL_CLEAN})")
    X = np.stack([_x(r) for r in trn])
    y = np.array([1.0 if r["label"] == "fault" else 0.0 for r in trn])
    w = np.array([float(r.get("weight", 1.0)) for r in trn])
    coef, bias = _fit(X, y, w)
    # Rule for a check that never fires in the training rows: it has no evidence, so its learned weight is 0 by construction, NOT because the
    # check is useless. The artifact keeps the fixed rule weight for it in "effective_rule_weights" and lists it in "never_fired_in_training".
    never_fired = [c for i, c in enumerate(CHECKS) if not X[:, i].any()]

    def cand(rs: Sequence[Dict[str, Any]]) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(np.stack([_x(r) for r in rs]) @ coef + bias, -30, 30)))

    clean_tr = [r for r in trn if r["label"] == "clean"]
    thr_c = _threshold_for_budget(cand(clean_tr), np.array([float(r.get("weight", 1.0)) for r in clean_tr]), budget_per_1000)
    thr_b = _threshold_for_budget(np.array([_rule(r) for r in clean_tr]), np.array([float(r.get("weight", 1.0)) for r in clean_tr]), budget_per_1000)
    m_c = _metrics(cand(va), va, thr_c)
    m_b = _metrics(np.array([_rule(r) for r in va]), va, thr_b)
    return {
        "kind": "label_fusion", "snapshot_sha256": snapshot_sha256, "false_alarm_budget_per_1000": budget_per_1000,
        "recall_at_budget": m_c["recall_at_budget"], "false_alarms_per_1000": m_c["false_alarms_per_1000"],
        "protected_extremes_flagged": m_c["protected_extremes_flagged"],
        "baseline": {"name": "fixed rule weights", **m_b},
        "validation": {"split": "temporal: earlier days train, later days validate", "train_until": cut, "n_fault": m_c["n_fault"],
                       "n_clean": m_c["n_clean"], "n_genuine_extreme": m_c["n_genuine_extreme"]},
        "train": {"n_fault": n_fault, "n_clean": n_clean},
        "temporal_split": True, "labels_not_ground_truth": True,
        "artifact": {"kind": "label_fusion", "checks": list(CHECKS), "weights": [float(c) for c in coef], "bias": bias, "threshold": thr_c,
                     "fixed_weights": FIXED_WEIGHTS, "never_fired_in_training": never_fired,
                     "effective_rule_weights": {c: (FIXED_WEIGHTS[c] if c in never_fired else None) for c in CHECKS},
                     "weights_note": "weights are learned logit coefficients; a check in never_fired_in_training has no learned value (0) and keeps its fixed rule weight "
                                     "(effective_rule_weights), it is not learned to be useless"},
        "note": "Weights learned from one reviewer's labels; validation is the later part of the same snapshot. Not the frozen RF25 protocol and not ground truth.",
    }


def main(argv: Sequence[str]) -> int:
    """python fusion.py snapshot.jsonl result.json [sha256]  (used inside the Kaggle notebook and by the server)."""
    text = open(argv[1], encoding="utf-8").read()
    try:
        result = train(parse_snapshot(text), snapshot_sha256=argv[3] if len(argv) > 3 else None)
        out = {"ok": True, "metrics": result}
    except NotEnoughLabels as e:
        out = {"ok": False, "error": str(e)}
    with open(argv[2], "w", encoding="utf-8") as f:
        json.dump(out, f)
    print(json.dumps(out)[:2000])
    return 0 if out["ok"] else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
