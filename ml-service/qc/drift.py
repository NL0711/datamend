"""Drift check: an untrained, causal CUSUM of the residual from the neighbours, built for slow ramps (21 to 60 days).

Per cell and day: residual of log1p(rain) from the median of the neighbours outside the hidden disc, divided by a
robust spread of the block's wet-day residuals and clipped to plus or minus ``clip`` (the clip limits one day's weight
inside this score only; no input of any other component is clipped). A two-sided leaky CUSUM runs over the history
days and the scored year, updated only on days when the cell or its neighbours are wet. Score = the larger sum.

The rule for judging it is in docs/qc-evaluation-protocol.md ("Drift check (CUSUM)"), written before any run.
SYNTHETIC faults only; nothing here says anything about real sensor drift.
"""

from __future__ import annotations

import json
import logging
import warnings
from typing import Dict

import numpy as np

from qc import paths
from qc.evaluate import compute_scores, evaluate_component, score_store
from qc.neighbours import gather, ring_index
from qc.paired import compare, year_table
from qc.prepare import Prepared
from qc.scoring import Block

log = logging.getLogger(__name__)

COMPONENT = "drift_cusum"
CLIP = 3.0
REFERENCE_K = 0.5
LEAK = 0.97
WET_MM = 0.3
SPREAD_FLOOR = 0.1
MAD_TO_SIGMA = 1.4826

RULE = {"event_recall_min": 0.40, "event_recall_gain": 0.10, "pr_auc_gain": 0.05, "false_per_1000_max": 2.0, "protected_flag_max": 0.02}


def drift_score(block: Block, ring: np.ndarray, clip: float = CLIP, k: float = REFERENCE_K, leak: float = LEAK,
                wet_mm: float = WET_MM, floor: float = SPREAD_FLOOR, chunk: int = 60, spread: float = None) -> np.ndarray:
    """(T, n_land) float32, higher = more likely a slow ramp; NaN where the scored day is missing.

    The CUSUM itself only reads day t and earlier. The spread that scales the residuals is, unless ``spread`` is given,
    the robust spread of all wet-day residuals of the block (history days and the scored year), so it is taken from the
    block's own year, faults included (about 1% of cell-days)."""
    obs = block.obs
    z = np.log1p(np.clip(obs, 0, None))                                       # NaN stays NaN
    resid = np.full(z.shape, np.nan, np.float32)
    nbmed = np.full(z.shape, np.nan, np.float32)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for s in range(0, z.shape[0], chunk):
            nbmed[s:s + chunk] = np.nanmedian(gather(z[s:s + chunk], ring), axis=2)
    resid = z - nbmed
    wet_cut = np.log1p(wet_mm)
    informative = np.isfinite(resid) & ((z > wet_cut) | (nbmed > wet_cut))
    if spread is None:
        spread = max(MAD_TO_SIGMA * float(np.median(np.abs(resid[informative]))), floor) if informative.any() else floor
    u = np.where(informative, np.clip(resid / spread, -clip, clip), 0.0).astype(np.float32)
    s_pos = np.zeros(u.shape[1], np.float32)
    s_neg = np.zeros(u.shape[1], np.float32)
    out = np.zeros(u.shape, np.float32)
    for t in range(u.shape[0]):
        on = informative[t]
        s_pos = np.where(on, np.maximum(0.0, leak * s_pos + u[t] - k), s_pos)
        s_neg = np.where(on, np.maximum(0.0, leak * s_neg - u[t] - k), s_neg)
        out[t] = np.maximum(s_pos, s_neg)
    score = out[block.pad:]
    return np.where(np.isfinite(block.target), score, np.nan).astype(np.float32)


def _drift_row(table_result: Dict, metric: str) -> Dict:
    """The compare() row for drift; an empty row (nothing measured, rule not met) if the benchmark has no drift events."""
    kind = table_result["kinds"].get("drift")
    return kind[metric] if kind else {"a": None, "b": None, "diff": None}


def rule_verdict(ev_drift: Dict, pr_drift: Dict, false_per_1000: float, protected_share: float, rule: Dict = RULE) -> Dict:
    """``ev_drift`` / ``pr_drift`` are the compare() rows (a = STNet fault head, b = drift_cusum)."""
    checks = {
        "event_recall_at_least_min": ev_drift["b"] is not None and ev_drift["b"] >= rule["event_recall_min"],
        "event_recall_gain_over_stnet": ev_drift["diff"] is not None and ev_drift["diff"] >= rule["event_recall_gain"],
        "pr_auc_gain_over_stnet": pr_drift["diff"] is not None and pr_drift["diff"] >= rule["pr_auc_gain"],
        "false_alerts_within_limit": false_per_1000 is not None and false_per_1000 <= rule["false_per_1000_max"],
        "protected_extremes_within_limit": protected_share is not None and protected_share <= rule["protected_flag_max"],
    }
    met = all(checks.values())
    return {"met": met, "checks": checks, "rule": rule,
            "verdict": ("rule met: drift_cusum is a candidate evidence channel for drift on SYNTHETIC ramps" if met else
                        "rule NOT met: no gain from this check; drift stays a documented gap"),
            "caveats": ["SYNTHETIC faults (our own ramp generator), validation years only, one seed",
                        "the numbers in the rule are decisions, not measured noise levels",
                        "whole-year resampling with regions fixed: with 5 years the interval undercovers, read it as a rough guide"]}


def to_markdown(res: Dict, verdict: Dict, other: Dict) -> str:
    L = [f"# drift_cusum against {res['a']}, validation years {res['years'][0]}-{res['years'][-1]}, budget {res['budget']} false alerts per 1,000 clean cell-days", "",
         "SYNTHETIC faults, validation years only. Difference = drift_cusum minus the STNet fault head.", "", "Interval: " + res["interval"], "",
         "| kind | events | metric | STNet | drift_cusum | diff | interval of the diff | years drift_cusum better / compared |", "|---|---|---|---|---|---|---|---|"]
    for kind, row in res["kinds"].items():
        for m in ("event_recall", "recall", "pr_auc_mean_over_years"):
            x = row[m]
            f = lambda v: "n/a" if v is None else format(v, ".3f")
            ci = "n/a" if x["diff_ci"] is None else f"[{x['diff_ci'][0]:+.3f}, {x['diff_ci'][1]:+.3f}]"
            L.append(f"| {kind} | {row['events_b']} | {m} | {f(x['a'])} | {f(x['b'])} | {'n/a' if x['diff'] is None else format(x['diff'], '+.3f')} | {ci} | {x['years_b_better']} / {x['years_compared']} |")
    fa = "n/a" if other["false_per_1000"] is None else f"{other['false_per_1000']:.2f}"
    pe = "n/a (none in the data)" if other["protected_share"] is None else f"{other['protected_share']:.4f}"
    L += ["", f"False alerts per 1,000 clean cell-days: drift_cusum {fa}. Protected extremes flagged (share of cell-days): {pe}.",
          f"Drift detection delay in days after the ramp starts (events flagged): median {other.get('delay_median')}, 90th percentile {other.get('delay_p90')}.", "",
          "## Decision rule (fixed before the run)", "", f"- {verdict['verdict']}"]
    L += [f"- {name}: {'yes' if ok else 'NO'}" for name, ok in verdict["checks"].items()]
    L += [f"- rule numbers: {json.dumps(verdict['rule'])}", "- caveats: " + "; ".join(verdict["caveats"])]
    return "\n".join(L) + "\n"


def run_drift_check(p: Prepared, seed: int, base: str = "stnet", budget: float = 1.0, overwrite: bool = False) -> Dict:
    """Score ``drift_cusum`` on the validation and clean threshold years, compare with the STNet fault head of ``base``, write json and markdown."""
    c = p.cfg.components
    ring = ring_index(p.grid, c.hidden_radius, c.slow.ring_outer)
    store = score_store(p)
    compute_scores(p, COMPONENT, lambda b: drift_score(b, ring), ["val"], store, overwrite)
    a = year_table(p, f"{base}_fault_s{seed}", budget, store)
    b = year_table(p, COMPONENT, budget, store)
    res = compare(a, b, int(p.cfg.seed))
    res["a"], res["b"] = a["component"], b["component"]
    ev = evaluate_component(p, COMPONENT, "val", [budget], ("seen",), store, pinned=False)
    block = ev["groups"]["seen"]["by_budget"][str(float(budget))]
    drift_block = block.get("by_kind", {}).get("drift", {})
    share = block["protected_extremes"]["flagged_share_of_cell_days"]
    false_rate = block["false_alerts"]["per_1000_clean"]
    other = {"false_per_1000": None if false_rate is None else float(false_rate),
             "protected_share": None if share is None else float(share),           # None: no protected extreme in the data, the rule cannot be met
             "delay_median": drift_block.get("delay_days_median"), "delay_p90": drift_block.get("delay_days_p90")}
    verdict = rule_verdict(_drift_row(res, "event_recall"), _drift_row(res, "pr_auc_mean_over_years"), other["false_per_1000"], other["protected_share"])
    out_dir = paths.out_dir(p.cfg) / str(p.cfg.name) / "drift"
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = {"compare": res, "verdict": verdict, "drift_cusum": other, "params": {"clip": CLIP, "k": REFERENCE_K, "leak": LEAK, "wet_mm": WET_MM, "floor": SPREAD_FLOOR}}
    (out_dir / f"drift_check_s{seed}.json").write_text(json.dumps(doc, indent=1, default=float), encoding="utf-8")
    (out_dir / f"drift_check_s{seed}.md").write_text(to_markdown(res, verdict, other), encoding="utf-8")
    return doc
