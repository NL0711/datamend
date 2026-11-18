"""Bridge check for a live daily rainfall product against RF25 (array level).

STATUS: new, unit-tested on generated arrays only. NOT IMPLEMENTED: reading the IMD/NCMRWF merged-grid binary file (the page offers a
binary file with a control file and a 241 x 281 map grid; its layout is not documented in the repo) and any download. This module
works on arrays that someone has already read, aligned to the RF25 cells and to the same dates. Spec: qc-multires-pipeline-spec.md s7.

What it does: pick the day lag (-1, 0, +1) between the product's day and RF25's day by correlating area-weighted all-cell daily means;
measure agreement at that lag (rain / no-rain at a threshold: hit rate, false alarm ratio, equitable threat score, Peirce skill score;
mean bias and percentage RMSE; correlation); compare the distribution of the daily models' scores on the product with RF25's (the model
shift); and apply an acceptance rule. USE VALIDATION YEARS ONLY (never 2018-2025). The merged product is tuned with IMD gauges, so
agreement with RF25 is partly built in: say so wherever a result is shown.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

RAIN_MM = 0.5


@dataclass(frozen=True)
class AcceptanceRule:
    """Pass/fail limits, frozen before any data is looked at (``bridge:`` in base.yaml; log in docs/qc-evaluation-protocol.md).
    The defaults here are the owner's confirmed values of 2026-11-18, but ``confirmed_by_owner`` stays False until the config says so.

    Pass/fail uses ``primary_rain_mm``; the thresholds in ``report_rain_mm`` are reported without pass/fail. The correlation limit is
    on the cell-level pooled correlation; the area-mean correlation is reported beside it. A model shift outside ``p99_ratio_band`` is a
    WARNING (recalibrate the standardisation reference on the product's clean days), not a failure. ``allowed_years`` are the only
    years the check may use; test years are never allowed."""
    min_pss: float = 0.5
    max_far: float = 0.5
    max_abs_bias_pct: float = 20.0
    max_pct_rmse: float = 150.0
    min_corr: float = 0.8
    p99_ratio_band: tuple = (0.8, 1.25)
    primary_rain_mm: float = 0.5
    report_rain_mm: tuple = (2.5,)
    allowed_years: tuple = (2016, 2017)
    confirmed_by_owner: bool = False


def rule_from_dict(d: Dict) -> AcceptanceRule:
    """Build the rule from the ``bridge`` section of the config (a plain dict)."""
    known = set(AcceptanceRule.__dataclass_fields__)
    extra = set(d) - known - {"frozen_on"}
    if extra:
        raise ValueError(f"unknown bridge settings {sorted(extra)}")
    kw = {k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items() if k in known}
    return AcceptanceRule(**kw)


def read_imd_merged_binary(*args, **kwargs):
    raise NotImplementedError("reading the IMD/NCMRWF merged-grid binary is not implemented: the file layout (control file, 241 x 281 "
                              "grid) has to be obtained from IMD first")


def _shift(x: np.ndarray, lag: int) -> np.ndarray:
    """Product day t+lag aligned with reference day t (the ends are trimmed so that both have the same length)."""
    if lag == 0:
        return x
    return x[lag:] if lag > 0 else x[:lag]


def _trim_ref(ref: np.ndarray, lag: int) -> np.ndarray:
    if lag == 0:
        return ref
    return ref[:-lag] if lag > 0 else ref[-lag:]


def pick_lag(product: np.ndarray, ref: np.ndarray, weights: np.ndarray, lags: Sequence[int] = (-1, 0, 1)) -> Dict:
    """``product``, ``ref`` are (T, n) mm on the same cells and dates. Correlation of the area-weighted daily means at each lag."""
    if product.shape != ref.shape:
        raise ValueError("product and ref must have the same shape")
    w = weights / weights.sum()

    def daily_mean(a):
        m = np.isfinite(a)
        return (np.where(m, a, 0.0) * w[None, :]).sum(axis=1) / np.maximum((m * w[None, :]).sum(axis=1), 1e-12)

    pm, rm = daily_mean(product), daily_mean(ref)
    corr = {}
    for lag in lags:
        a, b = _shift(pm, lag), _trim_ref(rm, lag)
        corr[int(lag)] = float(np.corrcoef(a, b)[0, 1]) if a.size > 2 and a.std() > 0 and b.std() > 0 else None
    scored = {k: v for k, v in corr.items() if v is not None}
    return {"correlation_by_lag": corr, "best_lag": max(scored, key=scored.get) if scored else None,
            "note": "the lag is chosen on validation years and then frozen"}


def agreement(product: np.ndarray, ref: np.ndarray, rain_mm: float = RAIN_MM) -> Dict:
    m = np.isfinite(product) & np.isfinite(ref)
    p, r = product[m], ref[m]
    if p.size == 0:
        raise ValueError("no cells with both values")
    pr, rr = p >= rain_mm, r >= rain_mm
    hits, miss, fal, cn = int((pr & rr).sum()), int((~pr & rr).sum()), int((pr & ~rr).sum()), int((~pr & ~rr).sum())
    n = p.size
    pod = hits / (hits + miss) if hits + miss else None
    far = fal / (hits + fal) if hits + fal else None
    pofd = fal / (fal + cn) if fal + cn else None
    hits_rand = (hits + miss) * (hits + fal) / n
    denom = hits + miss + fal - hits_rand
    ets = (hits - hits_rand) / denom if denom else None
    mean_r = float(r.mean())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        corr = float(np.corrcoef(p, r)[0, 1]) if p.std() > 0 and r.std() > 0 else None
    return {"pod": pod, "far": far, "ets": ets, "pss": None if pod is None or pofd is None else pod - pofd,
            "bias_pct": None if mean_r == 0 else float(100 * (p.mean() - mean_r) / mean_r),
            "pct_rmse": None if mean_r == 0 else float(100 * np.sqrt(((p - r) ** 2).mean()) / mean_r),
            "correlation": corr, "rain_mm": rain_mm, "n": int(n)}


def model_shift(score_ref: np.ndarray, score_product: np.ndarray, rule: AcceptanceRule = AcceptanceRule(),
                quantiles: Sequence[float] = (50, 90, 99, 99.9)) -> Dict:
    """Do the daily models score the product like RF25? Quantile ratios of the score distributions and the KS distance."""
    a = np.asarray(score_ref, float)
    b = np.asarray(score_product, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if a.size < 100 or b.size < 100:
        raise ValueError("need at least 100 finite scores on each side")
    qa, qb = np.percentile(a, quantiles), np.percentile(b, quantiles)
    ratio = {f"p{q:g}": (float(y / x) if x > 0 else None) for q, x, y in zip(quantiles, qa, qb)}
    grid = np.sort(np.concatenate([a, b]))
    cdf = lambda x: np.searchsorted(np.sort(x), grid, side="right") / x.size
    ks = float(np.abs(cdf(a) - cdf(b)).max())
    p99 = ratio.get("p99")
    lo, hi = rule.p99_ratio_band
    return {"quantile_ratio_product_over_rf25": ratio, "ks": ks, "shifted": p99 is None or not (lo <= p99 <= hi),
            "note": "a shifted product cannot be scored by the RF25-trained daily models without recalibration"}


def decide(report: Dict, rule: AcceptanceRule) -> Dict:
    fails: List[str] = []
    warns: List[str] = []
    ag = report["agreement"]
    checks = [("pss", ag["pss"], lambda v: v >= rule.min_pss, f"PSS below {rule.min_pss}"),
              ("far", ag["far"], lambda v: v <= rule.max_far, f"false alarm ratio above {rule.max_far}"),
              ("bias_pct", ag["bias_pct"], lambda v: abs(v) <= rule.max_abs_bias_pct, f"|bias| above {rule.max_abs_bias_pct}%"),
              ("pct_rmse", ag["pct_rmse"], lambda v: v <= rule.max_pct_rmse, f"percentage RMSE above {rule.max_pct_rmse}%"),
              ("correlation", ag["correlation"], lambda v: v >= rule.min_corr, f"correlation below {rule.min_corr}")]
    for key, val, ok, msg in checks:
        if val is None:
            fails.append(f"{key} could not be computed")
        elif not ok(val):
            fails.append(msg)
    if report.get("model_shift", {}).get("shifted"):
        warns.append("the daily models score the product differently from RF25 (p99 ratio outside the band): recalibrate the "
                     "standardisation reference on the product's clean days before using it")
    return {"passed": not fails, "failures": fails, "warnings": warns, "rule_confirmed_by_owner": rule.confirmed_by_owner,
            "caveat": "the product is tuned with IMD gauges, so agreement with RF25 is partly built in"}


def run_bridge(product: np.ndarray, ref: np.ndarray, weights: np.ndarray, rule: AcceptanceRule, years: Sequence[int],
               score_ref: Optional[np.ndarray] = None, score_product: Optional[np.ndarray] = None,
               lags: Sequence[int] = (-1, 0, 1), frozen_lag: Optional[int] = None) -> Dict:
    """Validation years only: ``years`` are the years the arrays cover and must all be in ``rule.allowed_years``. With ``frozen_lag``
    given the lag is not searched again."""
    if not rule.confirmed_by_owner:
        raise PermissionError("the acceptance rule has not been confirmed by the owner; confirm or change it before the bridge check "
                              "is run")
    bad = sorted(set(int(y) for y in years) - set(rule.allowed_years))
    if bad:
        raise ValueError(f"years {bad} are not allowed for the bridge check (allowed: {list(rule.allowed_years)}; test years are never used)")
    lag = pick_lag(product, ref, weights, lags)
    use = frozen_lag if frozen_lag is not None else lag["best_lag"]
    if use is None:
        raise ValueError("no lag could be scored")
    p_s, r_s = _shift(product, use), _trim_ref(ref, use)
    ag = agreement(p_s, r_s, rule.primary_rain_mm)
    rep = {"lag": lag, "lag_used": int(use), "agreement": ag,
           "agreement_reported_only": {f"{t:g}": agreement(p_s, r_s, t) for t in rule.report_rain_mm},
           "area_mean_correlation_reported_only": lag["correlation_by_lag"].get(int(use)), "years": [int(y) for y in years]}
    if score_ref is not None and score_product is not None:
        rep["model_shift"] = model_shift(score_ref, score_product, rule)
    rep["decision"] = decide(rep, rule)
    return rep
