"""Paired comparison of stored score components on the validation years, with whole-year resampling.

Question it answers: does component B (for example the STNet whose long memory was trained longer) detect more of a fault kind than component A
(the main run) at the same false-alarm budget, and is that difference larger than the year-to-year spread?

Why whole years and not events: events inside one year share the weather and are not independent, so resampling events gives intervals that are
far too narrow (``docs/research/bootstrap-unit-check.md``, generated-data simulation: event-level coverage 14-62% of a nominal 95%; whole years with
regions fixed 84-90%). The validation period has 5 years, the smallest number this repository allows an interval for
(``qc.metrics.MIN_YEARS_FOR_CI``), and with so few years the interval still undercovers: read it as a rough guide, not a guarantee.

What is resampled: years, jointly for A and B (a paired bootstrap, so the weather of a year is the same on both sides). With up to 6 years every
resample is enumerated (5 years: 5^5 = 3,125, no random numbers); with more years 2,000 random ones. Regions are fixed.
What is reported per fault kind: event recall, cell-day recall, and the PR-AUC of that kind against clean cell-days (the mean over years of
the yearly value, because a pooled PR-AUC cannot be resampled by year at a reasonable cost), each with the difference B - A, its interval, the
difference in every single year and in how many years B is better. False alerts per 1,000 clean cell-days are reported for A and B.
Thresholds are the false-alarm budget thresholds of the validation protocol (clean threshold years, training clients). Everything is on
SYNTHETIC faults and validation years; test and stress years are never read. A difference is not a statement about real faults."""
from __future__ import annotations

import itertools
import json
import warnings
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.metrics import average_precision_score

from qc import paths
from qc.evaluate import group_cells, load_years, score_store, thresholds_for
from qc.metrics import MIN_YEARS_FOR_CI, YearScores, evaluate
from qc.prepare import Prepared

EXACT_LIMIT = 50_000            # enumerate every resample when years ** years is at most this
N_RANDOM = 2000
NO_WORSE_TOLERANCE = 0.1        # assumed: an arm's realised false alerts per 1,000 clean cell-days may exceed the baseline's by this much and still be "no worse"
RULE_MIN_GAIN = 0.05            # the decision rule written in the notebook before the run (a decision, not a measured noise level)
UNDERCOVERAGE = ("whole-year resampling with regions fixed: with 5 to 8 years the interval undercovers (84-90% for a nominal 95% in the "
                 "simulation of docs/research/bootstrap-unit-check.md); read it as a rough guide")


def _ap_kind(ys: YearScores, cells: np.ndarray, kind: str) -> Optional[float]:
    """PR-AUC of the cell-days of one fault kind against clean cell-days. Cell-days of OTHER kinds are left out (they are neither the target nor clean)."""
    f = ys.bench.faults
    lab = f.labels()
    if kind == "all":
        mk = lab
    else:
        mk = np.zeros(lab.shape, bool)
        if f.t.size:
            ek = np.array([e["kind"] for e in f.events])
            sel = ek[f.event] == kind
            mk[f.t[sel], f.cell[sel]] = True
    keep = np.isfinite(ys.score) & ~ys.bench.extremes.ambiguous & cells[None, :] & ~(lab & ~mk)
    if ys.bench.excluded is not None:
        keep &= ~ys.bench.excluded
    y = mk[keep]
    return float(average_precision_score(y, ys.score[keep])) if y.any() and not y.all() else None


def year_table(p: Prepared, component: str, budget: float, store=None, years: Optional[Sequence[int]] = None) -> Dict:
    """Per validation year and fault kind: events, flagged events, fault cell-days, flagged cell-days, PR-AUC; and the false alerts of the year."""
    store = store or score_store(p)
    thr = thresholds_for(p, component, [budget], store)[float(budget)]
    cells = group_cells(p, "seen")
    ys_all = load_years(p, component, "val", list(years) if years else None, store)
    kinds = sorted({e["kind"] for ys in ys_all for e in ys.bench.faults.events})
    counts = {k: np.zeros((len(ys_all), 4)) for k in ["all"] + kinds}           # events, flagged events, cell-days, flagged cell-days
    ap = {k: np.full(len(ys_all), np.nan) for k in ["all"] + kinds}
    clean = np.zeros((len(ys_all), 2))                                          # clean cell-days, false alerts
    for i, ys in enumerate(ys_all):
        r = evaluate([ys], cells, thr, p.grid, p.cell_client, 0, int(p.cfg.seed))
        blocks = {"all": r["faults"], **r.get("by_kind", {})}
        for k, b in blocks.items():
            if k in counts and b.get("events"):
                counts[k][i] = [b["events"], round(b["event_recall"] * b["events"]), b["cell_days"], round((b["recall"] or 0.0) * b["cell_days"])]
        for k in counts:
            v = _ap_kind(ys, cells, k)
            if v is not None:
                ap[k][i] = v
        clean[i] = [r["false_alerts"]["clean_cell_days"], r["false_alerts"]["false_alerts"]]
    return {"component": component, "budget": float(budget), "threshold": float(thr), "years": [y.bench.year for y in ys_all],
            "counts": counts, "ap": ap, "clean": clean}


def _resamples(n_years: int, rng: np.random.Generator) -> Tuple[np.ndarray, str]:
    if n_years ** n_years <= EXACT_LIMIT:
        return np.array(list(itertools.product(range(n_years), repeat=n_years))), f"every one of the {n_years}^{n_years} = {n_years ** n_years:,} resamples of the years"
    return rng.integers(0, n_years, size=(N_RANDOM, n_years)), f"{N_RANDOM:,} random resamples of the {n_years} years"


def _ratio(num: np.ndarray, den: np.ndarray, idx: np.ndarray) -> np.ndarray:
    d, n = den[idx].sum(axis=1), num[idx].sum(axis=1)
    return np.where(d > 0, n / np.where(d > 0, d, 1.0), np.nan)


def _macro(vals: np.ndarray, idx: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)                  # a resample whose years all lack the kind is NaN, not an error
        return np.nanmean(vals[idx], axis=1)


def _interval(x: np.ndarray) -> Optional[List[float]]:
    x = x[np.isfinite(x)]
    return [float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))] if x.size else None


def _metric(name: str, a: Dict, b: Dict, kind: str, idx: np.ndarray, ci: bool) -> Dict:
    ca, cb = a["counts"][kind], b["counts"][kind]
    if name == "event_recall":
        va, vb = (ca[:, 1], ca[:, 0]), (cb[:, 1], cb[:, 0])
    elif name == "recall":
        va, vb = (ca[:, 3], ca[:, 2]), (cb[:, 3], cb[:, 2])
    elif name == "pr_auc_mean_over_years":
        va, vb = a["ap"][kind], b["ap"][kind]
    else:
        raise ValueError(name)

    def per_year(v):
        return v if isinstance(v, np.ndarray) else np.where(v[1] > 0, v[0] / np.where(v[1] > 0, v[1], 1.0), np.nan)

    def pooled(v):
        if isinstance(v, np.ndarray):
            return float(np.nanmean(v)) if np.isfinite(v).any() else None
        return float(v[0].sum() / v[1].sum()) if v[1].sum() > 0 else None

    ya, yb = per_year(va), per_year(vb)
    pa, pb = pooled(va), pooled(vb)
    diff_year = yb - ya
    out = {"a": pa, "b": pb, "diff": None if pa is None or pb is None else pb - pa,
           "diff_by_year": [None if not np.isfinite(d) else float(d) for d in diff_year],
           "years_b_better": int(np.nansum(diff_year > 0)), "years_a_better": int(np.nansum(diff_year < 0)), "years_compared": int(np.isfinite(diff_year).sum())}
    if ci:
        sa = _macro(va, idx) if isinstance(va, np.ndarray) else _ratio(va[0], va[1], idx)
        sb = _macro(vb, idx) if isinstance(vb, np.ndarray) else _ratio(vb[0], vb[1], idx)
        out["diff_ci"] = _interval(sb - sa)
    else:
        out["diff_ci"] = None
    return out


def compare(a: Dict, b: Dict, seed: int = 0) -> Dict:
    """``a`` and ``b`` are :func:`year_table` results on the same years. Returns the paired comparison for every kind present in both."""
    if a["years"] != b["years"]:
        raise ValueError(f"the two components were not scored on the same years: {a['years']} against {b['years']}")
    n = len(a["years"])
    ci = n >= MIN_YEARS_FOR_CI
    idx, how = _resamples(n, np.random.default_rng(seed)) if ci else (np.zeros((0, n), int), "none")
    kinds = [k for k in a["counts"] if k in b["counts"]]
    out = {"years": a["years"], "budget": a["budget"], "interval": ("95% percentile interval of the difference B - A over " + how + "; " + UNDERCOVERAGE) if ci else
           f"no interval: fewer than {MIN_YEARS_FOR_CI} years", "kinds": {}}
    for k in kinds:
        row = {"events_a": int(a["counts"][k][:, 0].sum()), "events_b": int(b["counts"][k][:, 0].sum())}
        for m in ("event_recall", "recall", "pr_auc_mean_over_years"):
            row[m] = _metric(m, a, b, k, idx, ci)
        out["kinds"][k] = row
    ca, cb = a["clean"], b["clean"]
    fa = 1000.0 * ca[:, 1].sum() / ca[:, 0].sum() if ca[:, 0].sum() else None
    fb = 1000.0 * cb[:, 1].sum() / cb[:, 0].sum() if cb[:, 0].sum() else None
    fd = None
    if ci and fa is not None and fb is not None:
        fd = _interval(1000.0 * (_ratio(cb[:, 1], cb[:, 0], idx) - _ratio(ca[:, 1], ca[:, 0], idx)))
    out["false_alerts_per_1000_clean"] = {"a": fa, "b": fb, "diff": None if fa is None or fb is None else fb - fa, "diff_ci": fd,
                                          "per_year_a": [1000.0 * x[1] / x[0] if x[0] else None for x in ca], "per_year_b": [1000.0 * x[1] / x[0] if x[0] else None for x in cb]}
    return out


def drift_rule(result: Dict, hypothesis: str = "drift", controls: Sequence[str] = ("scale", "zeroed")) -> Dict:
    """The decision rule fixed before the run (see the notebook): the hypothesis kind improves by at least RULE_MIN_GAIN in PR-AUC and in event recall,
    with false alerts no worse. The controls should not move by RULE_MIN_GAIN or more. Says whether the rule is met on the point estimates and
    whether the interval of each gain excludes zero (a rough guide with 5 years)."""
    kinds = result["kinds"]
    if hypothesis not in kinds:
        return {"hypothesis": hypothesis, "verdict": f"no {hypothesis} events in the validation years: the rule cannot be applied"}
    h = kinds[hypothesis]
    gains = {m: h[m]["diff"] for m in ("pr_auc_mean_over_years", "event_recall")}
    fa = result["false_alerts_per_1000_clean"]
    no_worse = fa["a"] is not None and fa["b"] is not None and fa["b"] <= fa["a"] + NO_WORSE_TOLERANCE
    point = all(g is not None and g >= RULE_MIN_GAIN for g in gains.values()) and no_worse
    excludes = all(h[m]["diff_ci"] is not None and h[m]["diff_ci"][0] > 0 for m in gains)
    ctrl = {c: {m: kinds[c][m]["diff"] for m in ("pr_auc_mean_over_years", "event_recall")} for c in controls if c in kinds}
    ctrl_moved = [c for c, v in ctrl.items() if any(x is not None and abs(x) >= RULE_MIN_GAIN for x in v.values())]
    return {"hypothesis": hypothesis, "min_gain": RULE_MIN_GAIN, "gains": gains, "false_alerts_no_worse": bool(no_worse), "rule_met_on_point_estimates": bool(point),
            "gain_intervals_exclude_zero": bool(excludes), "controls": ctrl, "controls_that_moved": ctrl_moved,
            "verdict": ("rule met on the point estimates" if point else "rule NOT met: report no gain on this encoder, not that long memory is useless") +
                       ("; both gain intervals exclude zero (rough guide)" if point and excludes else "; the intervals do not both exclude zero" if point else "") +
                       ("; CONTROLS MOVED (" + ", ".join(ctrl_moved) + "): the cause is not memory alone" if ctrl_moved else ""),
            "caveats": ["SYNTHETIC faults, validation years only, one seed", "the 0.05 gain is a decision, not a measured noise level", UNDERCOVERAGE]}


def _f(x, nd=3) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def _ci(x) -> str:
    return "n/a" if not x else f"[{x[0]:+.3f}, {x[1]:+.3f}]"


def to_markdown(name_a: str, name_b: str, result: Dict, rule: Optional[Dict] = None) -> str:
    L = [f"# {name_b} against {name_a}, validation years {result['years'][0]}-{result['years'][-1]}, budget {result['budget']} false alerts per 1,000 clean cell-days", "",
         "SYNTHETIC faults, validation years only, one seed. Difference = B minus A; B = " + name_b + ", A = " + name_a + ".", "", "Interval: " + result["interval"], "",
         "| kind | events (A / B) | metric | A | B | diff | interval of the diff | years B better / compared |", "|---|---|---|---|---|---|---|---|"]
    for k, row in result["kinds"].items():
        for m in ("event_recall", "recall", "pr_auc_mean_over_years"):
            x = row[m]
            L.append(f"| {k} | {row['events_a']} / {row['events_b']} | {m} | {_f(x['a'])} | {_f(x['b'])} | {'n/a' if x['diff'] is None else format(x['diff'], '+.3f')} | "
                     f"{_ci(x['diff_ci'])} | {x['years_b_better']} / {x['years_compared']} |")
    fa = result["false_alerts_per_1000_clean"]
    L += ["", f"False alerts per 1,000 clean cell-days: A {_f(fa['a'], 2)}, B {_f(fa['b'], 2)}, diff {'n/a' if fa['diff'] is None else format(fa['diff'], '+.2f')}, interval of the diff "
          f"{_ci(fa['diff_ci'])}."]
    if rule:
        L += ["", "## Decision rule (fixed before the run)", "", f"- {rule['verdict']}", f"- gains: {json.dumps(rule.get('gains'))}", f"- controls: {json.dumps(rule.get('controls'))}",
              "- caveats: " + "; ".join(rule.get("caveats", []))]
    return "\n".join(L) + "\n"


def run_paired(p: Prepared, base: str, others: Sequence[str], seed: int, budget: float = 1.0, suffix: str = "fault", hypothesis: str = "drift",
               controls: Sequence[str] = ("scale", "zeroed")) -> Dict[str, Dict]:
    """Compare every prefix in ``others`` with ``base`` (all stored as ``<prefix>_<suffix>_s<seed>``); writes json and markdown next to the run."""
    store = score_store(p)
    out_dir = paths.out_dir(p.cfg) / str(p.cfg.name) / "paired"
    out_dir.mkdir(parents=True, exist_ok=True)
    a = year_table(p, f"{base}_{suffix}_s{seed}", budget, store)
    results = {}
    for o in others:
        b = year_table(p, f"{o}_{suffix}_s{seed}", budget, store)
        res = compare(a, b, int(p.cfg.seed))
        rule = drift_rule(res, hypothesis, controls)
        res["rule"], res["a"], res["b"] = rule, a["component"], b["component"]
        stem = f"paired_{base}_vs_{o}_s{seed}"
        (out_dir / f"{stem}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        (out_dir / f"{stem}.md").write_text(to_markdown(base, o, res, rule), encoding="utf-8")
        results[o] = res
    return results
