"""Data-QC checks on a cell's recent hourly series, and the comparison across the cells of one location.

METHOD "rules+statistics v0": untrained checks (physical range, step, stuck run), applied to
hourly values, plus a buddy check across the cells of the location. This is NOT the trained gradient-boosted or neural experts;
their scores arrive through scores.py when saved scores exist. The constants below are rule settings, not fitted values.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

METHOD = "rules+statistics v0"
PHYSICAL = {"temperature": (-60.0, 65.0), "humidity": (0.0, 100.0), "pressure": (450.0, 1090.0)}
STEP_FLOOR = {"temperature": 0.3, "humidity": 2.0, "pressure": 0.2}      # smallest hour-to-hour spread treated as noise (degC, %, hPa)
STEP_K = 10.0                                                            # flag a jump this many robust spreads above the typical one
STUCK_HOURS = 6                                                          # identical consecutive hourly values
MAX_MISSING = 0.2
BUDDY_DIFF_Z = 3.0                                                       # a cell this many z away from the median of the others
MIN_BUDDIES = 2                                                          # needs at least this many other cells


def _clean(values: Sequence[float]) -> np.ndarray:
    return np.array([float("nan") if v is None else v for v in values], dtype=float)


def check_series(variable: str, values: Sequence[float], times: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """Findings for one variable of one cell. Each: {"check", "detail"}. Rainfall has no checks here (zeros are normal)."""
    if variable not in PHYSICAL:
        return []
    x = _clean(values)
    findings: List[Dict[str, Any]] = []
    t = list(times) if times is not None else [str(i) for i in range(len(x))]
    if x.size == 0:
        return [{"check": "missing", "detail": "no values"}]
    miss = float(np.mean(~np.isfinite(x)))
    if miss > MAX_MISSING:
        findings.append({"check": "missing", "detail": f"{miss:.0%} of the hourly values are missing"})
    lo, hi = PHYSICAL[variable]
    bad = np.nonzero(np.isfinite(x) & ((x < lo) | (x > hi)))[0]
    if bad.size:
        findings.append({"check": "range", "detail": f"{bad.size} value(s) outside {lo} to {hi} (first at {t[bad[0]]}: {x[bad[0]]:.2f})"})
    ok = np.isfinite(x)
    d = np.diff(x)
    dv = d[np.isfinite(d)]
    if dv.size >= 10:
        spread = max(1.4826 * float(np.median(np.abs(dv - np.median(dv)))), STEP_FLOOR[variable])
        j = int(np.nanargmax(np.abs(d)))
        if abs(d[j]) > STEP_K * spread:
            findings.append({"check": "step", "detail": f"jump of {d[j]:+.2f} between {t[j]} and {t[j + 1]} "
                                                        f"({abs(d[j]) / spread:.0f} times the usual hourly change)"})
    run, best, best_end = 1, 1, 0
    for i in range(1, x.size):
        run = run + 1 if (ok[i] and ok[i - 1] and x[i] == x[i - 1]) else 1
        if run > best:
            best, best_end = run, i
    if best >= STUCK_HOURS:
        findings.append({"check": "stuck", "detail": f"{best} identical consecutive hourly values ending {t[best_end]} ({x[best_end]:.2f})"})
    return findings


def buddy_check(z_by_cell: Dict[str, Dict[str, Optional[float]]]) -> Dict[str, List[Dict[str, Any]]]:
    """Per cell id, the variables whose z-score differs from the median z of the OTHER cells by at least BUDDY_DIFF_Z.
    Returns {} entries for cells with nothing to report; the check is skipped when there are fewer than MIN_BUDDIES other cells."""
    out: Dict[str, List[Dict[str, Any]]] = {c: [] for c in z_by_cell}
    for cell, zs in z_by_cell.items():
        for v, z in zs.items():
            if z is None:
                continue
            others = [o[v] for c, o in z_by_cell.items() if c != cell and o.get(v) is not None]
            if len(others) < MIN_BUDDIES:
                continue
            med = float(np.median(others))
            if abs(z - med) >= BUDDY_DIFF_Z:
                out[cell].append({"check": "neighbours", "detail": f"{v}: z {z:+.1f} here against a median of {med:+.1f} in the other {len(others)} cells"})
    return out


def classify(strength: int, hard_findings: List[Dict[str, Any]], buddy_findings: List[Dict[str, Any]],
             coherent_others: int, n_others: int) -> Dict[str, Any]:
    """One label per cell.

    strength: 0/1/2 weather anomaly of the cell (anomaly.anomaly_strength). coherent_others: how many OTHER cells also have a
    weather anomaly of at least 1 (comparing only cells with a usable value)."""
    reasons: List[str] = []
    if hard_findings:
        reasons += [f"{f['check']}: {f['detail']}" for f in hard_findings]
        return {"label": "possible_data_fault", "reasons": reasons}
    if buddy_findings:
        reasons += [f["detail"] for f in buddy_findings]
        return {"label": "possible_data_fault", "reasons": reasons}
    if strength == 0:
        return {"label": "consistent", "reasons": ["no unusual weather and no data-quality findings"]}
    if n_others >= MIN_BUDDIES and coherent_others * 2 >= n_others:
        return {"label": "genuine_event_likely",
                "reasons": [f"unusual weather in this cell and in {coherent_others} of {n_others} other cells together"]}
    if n_others < MIN_BUDDIES:
        return {"label": "uncertain", "reasons": [f"unusual weather, but only {n_others} other cell(s) to compare with"]}
    return {"label": "uncertain", "reasons": [f"unusual weather in this cell; only {coherent_others} of {n_others} other cells agree"]}
