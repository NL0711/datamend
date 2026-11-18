"""Per-scale selection: train every candidate, score the synthetic period benchmark on VALIDATION years, keep the simplest
candidate that is not clearly worse than the best, and write the evidence for the protocol log.

STATUS: new, unit-tested on generated arrays and a generated world; nothing has run on real RF25. All numbers are on SYNTHETIC
faults and must be labelled so. Spec: docs/qc-multires-pipeline-spec.md section 5.

Rules implemented here:

* thresholds come from clean periods of the threshold years (false-alarm budgets per 1,000 clean periods), never from faults;
* recall (period level and event level) is measured on the corrupted periods of all validation years, so it is out of sample for
  the threshold; false alarms are reported on the validation years that were NOT used for the thresholds (out of sample) and,
  separately, on all of them (partly in sample);
* confidence intervals resample whole years with the regions fixed (``qc.metrics.year_bootstrap_ci``) and are None for fewer
  than 5 years;
* selection: among candidates whose false-alarm rate at the budget is within ``max_false_ratio`` times the budget (when it can
  be measured), take the simplest whose mean recall at the budget is within ``slack_se`` standard errors of the best. The standard
  error is the spread of per-year recall divided by the square root of the number of years (a simple choice of this project).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
from sklearn.metrics import average_precision_score

from qc.metrics import MIN_YEARS_FOR_CI, budget_thresholds, year_bootstrap_ci
from qc.period_benchmark import PeriodYear
from qc.resolution import Periods
from qc.scale_scorers import CANDIDATES, ScaleContext, make_scorer

DEFAULT_BUDGETS = (1.0, 5.0)
MAX_FALSE_RATIO = 3.0
SLACK_SE = 1.0


def _runs(fault: np.ndarray) -> np.ndarray:
    """(P, n) bool -> (P, n) int run ids: consecutive faulty periods of one cell share an id; 0 = no fault."""
    P, n = fault.shape
    ids = np.zeros((P, n), np.int64)
    cur = np.zeros(n, np.int64)
    nxt = 0
    for p in range(P):
        starts = fault[p] & (cur == 0)
        k = int(starts.sum())
        cur = np.where(starts, nxt + np.cumsum(starts), cur)
        nxt += k
        cur = np.where(fault[p], cur, 0)
        ids[p] = cur
    return ids


def evaluate_scores(scores: Dict[int, np.ndarray], years: Dict[int, PeriodYear], threshold_years: Sequence[int],
                    budgets: Sequence[float] = DEFAULT_BUDGETS, rng: Optional[np.random.Generator] = None,
                    n_boot: int = 200) -> Dict:
    """Metrics of one scorer on the period benchmark. ``scores[y]`` is (P, n) for each year in ``years``."""
    rng = rng or np.random.default_rng(0)
    ys = sorted(years)
    thr_years = [y for y in threshold_years if y in years]
    if not thr_years:
        raise ValueError("none of the threshold years is in the benchmark years")
    clean_ref = np.concatenate([scores[y][years[y].clean_mask & np.isfinite(scores[y])] for y in thr_years])
    if clean_ref.size < 100:
        raise ValueError(f"only {clean_ref.size} clean scored periods in the threshold years; cannot set a budget threshold")
    thresholds = budget_thresholds(clean_ref, list(budgets))
    oos = [y for y in ys if y not in thr_years]
    res: Dict = {"years": ys, "threshold_years": thr_years, "out_of_sample_years": oos, "budgets": {}}
    pos_s, neg_s = [], []
    for y in ys:
        s, py = scores[y], years[y]
        fin = np.isfinite(s)
        pos_s.append(s[py.fault & fin])
        neg_s.append(s[py.clean_mask & fin])
    pos, neg = np.concatenate(pos_s), np.concatenate(neg_s)
    res["pr_auc"] = (float(average_precision_score(np.r_[np.ones(pos.size), np.zeros(neg.size)], np.r_[pos, neg]))
                     if pos.size and neg.size else None)
    res["fault_periods"] = int(pos.size)
    res["scored_fault_share"] = float(pos.size / max(sum(int(years[y].fault.sum()) for y in ys), 1))
    for b in budgets:
        thr = thresholds[float(b)]
        n_f, f_f, n_e, f_e, c_n, c_f = [], [], [], [], [], []
        for y in ys:
            s, py = scores[y], years[y]
            fin = np.isfinite(s)
            flag = fin & (np.nan_to_num(s, nan=-np.inf) > thr)
            fm = py.fault & fin
            n_f.append(fm.sum())
            f_f.append((flag & fm).sum())
            runs = _runs(py.fault & fin)
            nr = int(runs.max())
            n_e.append(nr)
            hit = np.unique(runs[flag & (runs > 0)])
            f_e.append(hit.size)
            cm = py.clean_mask & fin
            c_n.append(cm.sum())
            c_f.append((flag & cm).sum())
        n_f, f_f, n_e, f_e, c_n, c_f = (np.array(a, float) for a in (n_f, f_f, n_e, f_e, c_n, c_f))
        o = np.array([y in oos for y in ys])
        yr_rec = np.where(n_f > 0, f_f / np.maximum(n_f, 1), np.nan)
        res["budgets"][str(b)] = {
            "threshold": float(thr),
            "recall": float(f_f.sum() / n_f.sum()) if n_f.sum() else None,
            "recall_ci": year_bootstrap_ci(f_f, n_f, rng, n_boot),
            "recall_by_year": [None if np.isnan(v) else float(v) for v in yr_rec],
            "event_recall": float(f_e.sum() / n_e.sum()) if n_e.sum() else None,
            "event_recall_ci": year_bootstrap_ci(f_e, n_e, rng, n_boot),
            "false_per_1000_out_of_sample": float(1000 * c_f[o].sum() / c_n[o].sum()) if o.any() and c_n[o].sum() else None,
            "false_per_1000_out_of_sample_ci": (None if o.sum() < MIN_YEARS_FOR_CI else
                                                [1000 * v for v in (year_bootstrap_ci(c_f[o], c_n[o], rng, n_boot) or [np.nan, np.nan])]),
            "false_per_1000_all_years": float(1000 * c_f.sum() / c_n.sum()) if c_n.sum() else None,
            "ci_unit": f"whole years ({len(ys)}); regions fixed; none below {MIN_YEARS_FOR_CI} years",
        }
    return res


def _mean(vals: Sequence[Optional[float]]) -> Optional[float]:
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return float(np.mean(v)) if v else None


def aggregate_seeds(per_seed: List[Dict]) -> Dict:
    """Mean over seeds of the headline numbers; the full per-seed results are kept alongside."""
    out = {"seeds": len(per_seed), "pr_auc": _mean([r["pr_auc"] for r in per_seed]), "budgets": {}}
    for b in per_seed[0]["budgets"]:
        rows = [r["budgets"][b] for r in per_seed]
        by_year = np.array([[np.nan if v is None else v for v in r["recall_by_year"]] for r in rows], float)
        yr = np.nanmean(by_year, axis=0) if np.isfinite(by_year).any() else np.full(by_year.shape[1], np.nan)
        finite = yr[np.isfinite(yr)]
        se = float(np.std(finite, ddof=1) / np.sqrt(finite.size)) if finite.size > 1 else 0.0
        out["budgets"][b] = {"recall": _mean([r["recall"] for r in rows]), "recall_se": se,
                             "recall_range_over_seeds": [min(r["recall"] for r in rows), max(r["recall"] for r in rows)],
                             "recall_ci_seed0": rows[0]["recall_ci"], "event_recall": _mean([r["event_recall"] for r in rows]),
                             "false_per_1000_out_of_sample": _mean([r["false_per_1000_out_of_sample"] for r in rows]),
                             "false_per_1000_all_years": _mean([r["false_per_1000_all_years"] for r in rows]),
                             "ci_unit": rows[0]["ci_unit"]}
    return out


def select_simplest(results: Dict[str, Dict], complexity: Dict[str, int], budget: str,
                    slack_se: float = SLACK_SE, max_false_ratio: float = MAX_FALSE_RATIO) -> Dict:
    """Pick one candidate for ``budget`` (the key of ``budgets``, for example "1.0")."""
    ok = {}
    for name, r in results.items():
        row = r["budgets"][budget]
        fa = row["false_per_1000_out_of_sample"]
        if row["recall"] is None:
            continue
        if fa is not None and fa > max_false_ratio * float(budget):
            continue
        ok[name] = row
    if not ok:
        return {"chosen": None, "reason": "no candidate had a measurable recall within the false-alarm guard"}
    best = max(ok, key=lambda k: ok[k]["recall"])
    floor = ok[best]["recall"] - slack_se * ok[best]["recall_se"]
    near = [k for k in ok if ok[k]["recall"] >= floor]
    chosen = sorted(near, key=lambda k: (complexity[k], -ok[k]["recall"]))[0]
    return {"chosen": chosen, "best": best, "budget": budget, "floor": float(floor), "within_floor": sorted(near),
            "reason": (f"simplest candidate with recall >= {floor:.3f} (best {best} at {ok[best]['recall']:.3f} minus "
                       f"{slack_se} standard error)")}


def run_selection(names: Sequence[str], train: Dict[int, Periods], ctx: ScaleContext, years: Dict[int, PeriodYear],
                  threshold_years: Sequence[int], budgets: Sequence[float] = DEFAULT_BUDGETS, seeds: Sequence[int] = (0, 1, 2),
                  n_boot: int = 200, seed: int = 0, select_on: Optional[str] = None) -> Dict:
    """Fit and score every candidate in ``names``. ``train`` holds training years only; ``years`` the benchmark years."""
    unknown = [n for n in names if n not in CANDIDATES]
    if unknown:
        raise KeyError(f"unknown scorers {unknown}; choose from {sorted(CANDIDATES)}")
    ys = sorted(years)
    corrupted = {y: years[y].corrupted for y in ys}
    results: Dict[str, Dict] = {}
    detail: Dict[str, List[Dict]] = {}
    for name in names:
        use = (seeds[0],) if CANDIDATES[name].complexity <= 1 else tuple(seeds)       # untrained baselines do not depend on a seed
        per_seed = []
        for sd in use:
            sc = make_scorer(name).fit(train, ctx, seed=int(sd))
            scores = {y: sc.score(corrupted[y], corrupted.get(y - 1), ctx) for y in ys}
            per_seed.append(evaluate_scores(scores, years, threshold_years, budgets, np.random.default_rng([seed, int(sd)]), n_boot))
        results[name] = aggregate_seeds(per_seed)
        detail[name] = per_seed
    complexity = {n: CANDIDATES[n].complexity for n in names}
    key = select_on or str(budgets[0])
    sel = select_simplest(results, complexity, key)
    return {"scale": ctx.scale, "label": "SYNTHETIC faults, validation years only", "budgets": [float(b) for b in budgets],
            "years": ys, "threshold_years": list(threshold_years), "candidates": results, "selection": sel,
            "per_seed": detail}


def selection_markdown(result: Dict) -> str:
    """A table for docs/qc-evaluation-protocol.md. Commit it before any test year is scored."""
    b0, b1 = (str(float(b)) for b in result["budgets"][:2]) if len(result["budgets"]) > 1 else (str(float(result["budgets"][0])),) * 2
    lines = [f"### Scale selection: {result['scale']}", "",
             f"{result['label']}. Validation years {result['years'][0]}-{result['years'][-1]}; thresholds from "
             f"{result['threshold_years']}. Intervals resample whole years (none below {MIN_YEARS_FOR_CI}).", "",
             f"| candidate | complexity | recall at {b0} | recall at {b1} | false per 1,000 (out of sample) at {b0} | event recall at {b0} | PR-AUC | seeds |",
             "|---|---|---|---|---|---|---|---|"]
    fmt = lambda v: "n/a" if v is None else f"{v:.3f}"
    for n, r in result["candidates"].items():
        x, y = r["budgets"][b0], r["budgets"][b1]
        lines.append(f"| {n} | {CANDIDATES[n].complexity} | {fmt(x['recall'])} | {fmt(y['recall'])} | "
                     f"{fmt(x['false_per_1000_out_of_sample'])} | {fmt(x['event_recall'])} | {fmt(r['pr_auc'])} | {r['seeds']} |")
    sel = result["selection"]
    lines += ["", f"Chosen: **{sel['chosen']}**. {sel['reason']}."]
    return "\n".join(lines) + "\n"


def write_selection(out_dir: Path, result: Dict) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"selection_{result['scale']}.json").write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")
    md = out_dir / f"selection_{result['scale']}.md"
    md.write_text(selection_markdown(result), encoding="utf-8")
    return md


def load_training_periods(p, scale: str) -> tuple:
    """(train periods by year, ScaleStats, ScaleContext) for a Prepared ``p``; training years only, held-out cells never read."""
    from qc.resolution import aggregate, fit_scale_stats
    from qc.scale_scorers import make_context
    from qc.splits import BUFFER, TRAIN

    years = list(p.split.years["train"])
    per = {y: aggregate(p.store.year(y), y, scale) for y in years}
    stats = fit_scale_stats(per, years, p.split, p.cell_client, scale)
    ctx = make_context(p.grid, p.cell_client, stats, hidden_radius=float(p.cfg.components.hidden_radius),
                       target_ok=p.cell_role == TRAIN, read_ok=(p.cell_role == TRAIN) | (p.cell_role == BUFFER))
    return per, stats, ctx


def run_for_prepared(p, scale: str, names: Sequence[str], out_dir: Path, budgets: Sequence[float] = DEFAULT_BUDGETS,
                     seeds: Optional[Sequence[int]] = None, n_boot: Optional[int] = None) -> Dict:
    """Selection for one scale on the validation split of the period benchmark of ``p``. Writes JSON and a markdown table."""
    from qc.benchmark import bench_dir
    from qc.period_benchmark import check_period_benchmark, load_period_year, period_dir

    check_period_benchmark(p)
    train, _, ctx = load_training_periods(p, scale)
    root = period_dir(bench_dir(p.cfg))
    years = {y: load_period_year(root, scale, "val", y) for y in p.split.years["val"]}
    seeds = tuple(p.cfg.train.seeds) if seeds is None else tuple(seeds)
    n_boot = int(p.cfg.evaluation.bootstrap) if n_boot is None else int(n_boot)
    result = run_selection(names, train, ctx, years, p.split.years["threshold"], budgets, seeds, n_boot, int(p.cfg.seed))
    write_selection(out_dir, result)
    return result
