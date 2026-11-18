"""Wire cross-scale fusion to the score store and evaluate it like any other component.

STATUS: new, unit-tested on a generated world only; nothing has run on real RF25. All numbers are on SYNTHETIC faults, validation years only.
Spec: docs/qc-multires-pipeline-spec.md section 6.

How it fits: every score lives in the ScoreStore as a (days, n_land) array under a component name, for the corrupted benchmark year
(``val``) and for the clean threshold years (``clean``). This module

  1. ``compute_scale_scores``: fits a chosen period scorer (``qc.scale_scorers``) on TRAINING years, scores the corrupted validation periods
     and the clean threshold-year periods, aligns each period score to days (``crossscale.align_to_days``) and stores it as
     ``scale_<scale>_<scorer>``;
  2. ``fuse_cross_scale``: standardises each part (the daily component and the scale components) by the 99.9th percentile of its CLEAN
     threshold-year scores over clean cell-days, combines them with the fixed rule (max or noisy-OR) and the coherent-extreme discount, and
     stores the result as one more component, ``xscale_<mode>_daily+<scales>``;
  3. ``compare_cross_scale``: evaluates the daily score alone and every combination with the SAME machinery as the daily components
     (budget thresholds from clean threshold years, recall, false alarms per 1,000 clean cell-days, protected extremes flagged), so the
     answer to "does adding a scale help?" is a table, not an assumption.

The daily fusion is itself fitted on the fusion-fit years, so the comparison is made on the held-out threshold years only (``holdout_years``),
2 years in the real config: no interval is reported (fewer than 5 years), and the thresholds come from the clean version of the same years,
as in the existing validation curves. The test and stress years are never scored here.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from qc.benchmark import bench_dir, check_benchmark, load_bench_year
from qc.crossscale import align_to_days, fit_nonneg_logistic, fuse_scales, learned_features, reference
from qc.evaluate import evaluate_component, group_cells, score_store, summary_row
from qc.extremes import find_extremes
from qc.fusion_eval import holdout_years
from qc.metrics import clean_reference
from qc.period_benchmark import check_period_benchmark, load_period_year, period_dir
from qc.resolution import days_in_year
from qc.scale_scorers import make_scorer
from qc.scale_select import load_training_periods
from qc.scoring import ScoreStore

SCALES = ("monthly", "seasonal", "yearly")


def scale_component(scale: str, scorer: str) -> str:
    return f"scale_{scale}_{scorer}"


def compute_scale_scores(p, scale: str, scorer_name: str, seed: int = 0, store: Optional[ScoreStore] = None,
                         overwrite: bool = False, splits: Sequence[str] = ("val",)) -> str:
    """Fit ``scorer_name`` on the training years and store its day-aligned scores for the benchmark years of each split in ``splits`` (by default
    only ``val``, which also stores the clean threshold years used for thresholds and references). Test and stress years are scored only when
    asked for, by the cross-scale test pass. Needs the daily benchmark and the period benchmark (``qc benchmark`` and ``qc period-benchmark``)."""
    if scale not in SCALES:
        raise ValueError(f"scale must be one of {SCALES}")
    bad = [s for s in splits if s not in ("val", "test", "stress")]
    if bad:
        raise ValueError(f"unknown splits {bad}")
    store = store or score_store(p)
    name = scale_component(scale, scorer_name)
    todo = [(split, y) for split in splits for y in p.split.years[split] if overwrite or not store.has(name, split, y)]
    todo_clean = [y for y in p.split.years["threshold"] if "val" in splits and (overwrite or not store.has(name, "clean", y))]
    if not todo and not todo_clean:
        return name
    check_benchmark(p, require_pinned=False)
    check_period_benchmark(p)
    train, _, ctx = load_training_periods(p, scale)
    scorer = make_scorer(scorer_name).fit(train, ctx, seed=int(seed))
    root = period_dir(bench_dir(p.cfg))
    loaded = {split: {y: load_period_year(root, scale, split, y) for y in p.split.years[split]} for split in splits}
    for split, y in todo:
        years = loaded[split]
        s = scorer.score(years[y].corrupted, years[y - 1].corrupted if (y - 1) in years else None, ctx)
        store.save(name, split, y, align_to_days(s, y, scale, days_in_year(y)))
    for y in todo_clean:
        years = loaded["val"]
        s = scorer.score(years[y].clean, years[y - 1].clean if (y - 1) in years else None, ctx)
        store.save(name, "clean", y, align_to_days(s, y, scale, days_in_year(y)))
    return name


def driver_name(component: str) -> str:
    """Score-store name of the array holding, for each cell-day of a fused component, the index of the part that drove it (-1 none)."""
    return f"{component}__driver"


def xscale_name(mode: str, scales: Sequence[str]) -> str:
    return f"xscale_{mode}_" + "+".join(["daily"] + list(scales))


def fit_learned_weights(p, parts: Dict[str, str], refs: Dict[str, float], store: ScoreStore, seed: int = 0,
                        neg_per_pos: int = 20) -> Dict:
    """Non-negative logistic weights for the learned fusion, fitted on the SYNTHETIC faults of the fusion-fit years only (never the held-out
    threshold years). Rows: every faulty cell-day and a seeded sample of ``neg_per_pos`` clean cell-days per faulty one, over the cells of
    training clients. Features: log1p of each part's standardised ratio, a missing part counting as 0."""
    fit_years = [y for y in p.split.years["fusion_fit"] if y not in p.split.years["threshold"]]
    if not fit_years:
        raise ValueError("no fusion-fit year is outside the threshold years; the learned fusion would be fitted on its own evaluation years")
    cells = group_cells(p, "seen")
    rng = np.random.default_rng([int(p.cfg.seed), int(seed), 77])
    xs, ys = [], []
    for y in fit_years:
        by = load_bench_year(p, "val", y)
        lab = by.faults.labels()
        arrays = [store.load(comp, "val", y) for comp in parts.values()]
        ratios = np.stack([a / refs[k] for a, k in zip(arrays, parts)], axis=0)
        anyv = np.isfinite(ratios).any(axis=0) & cells[None, :]
        feat = np.nan_to_num(learned_features(ratios), nan=0.0)
        pos = anyv & lab
        neg = anyv & ~lab & ~by.extremes.protected & ~by.extremes.ambiguous
        pi = np.nonzero(pos.ravel())[0]
        ni = np.nonzero(neg.ravel())[0]
        ni = rng.choice(ni, size=min(ni.size, max(neg_per_pos * pi.size, 1000)), replace=False) if ni.size else ni
        flat = feat.reshape(feat.shape[0], -1)
        xs += [flat[:, pi].T, flat[:, ni].T]
        ys += [np.ones(pi.size), np.zeros(ni.size)]
    x, yv = np.concatenate(xs), np.concatenate(ys)
    w, b = fit_nonneg_logistic(x, yv)
    return {"weights": [float(v) for v in w], "intercept": b, "fit_years": fit_years, "rows": int(yv.size),
            "positive_rows": int(yv.sum()), "parts": list(parts)}


def fuse_cross_scale(p, daily: str, scales: Dict[str, str], mode: str = "max", factor: float = 0.5,
                     store: Optional[ScoreStore] = None, overwrite: bool = False, seed: int = 0) -> Dict:
    """``scales`` maps a scale to the scorer name whose scores ``compute_scale_scores`` stored. Returns the new component name, the
    standardising references and, per part, the share of flagged-region cell-days it drove. ``mode="learned"`` fits non-negative logistic
    weights on the fusion-fit years first (``fit_learned_weights``)."""
    store = store or score_store(p)
    parts = {"daily": daily, **{s: scale_component(s, sc) for s, sc in scales.items()}}
    name = xscale_name(mode, list(scales))
    thr_years = list(p.split.years["threshold"])
    val_years = list(p.split.years["val"])
    cells = group_cells(p, "seen")
    ext_clean = {y: find_extremes(p.store.year(y), p.stats.heavy_mm, p.grid, p.cfg.extremes.min_cells) for y in thr_years}
    refs = {}
    for part, comp in parts.items():
        vals = np.concatenate([clean_reference(store.load(comp, "clean", y), ext_clean[y].protected, ext_clean[y].ambiguous, cells)
                               for y in thr_years])
        refs[part] = reference(vals)
    learned = fit_learned_weights(p, parts, refs, store, seed) if mode == "learned" else None
    jobs = [("val", y) for y in val_years] + [("clean", y) for y in thr_years]
    driver_counts = np.zeros(len(parts))
    for tag, y in jobs:
        if not overwrite and store.has(name, tag, y):
            continue
        loaded = {part: store.load(comp, tag, y) for part, comp in parts.items()}
        shapes = {a.shape for a in loaded.values()}
        if len(shapes) != 1:
            raise ValueError(f"scores of year {y} ({tag}) have different shapes: {sorted(shapes)}")
        protected = load_bench_year(p, "val", y).extremes.protected if tag == "val" else ext_clean[y].protected
        f = fuse_scales(loaded, refs, mode, protected=protected, protected_factor=factor,
                        weights=learned["weights"] if learned else None)
        store.save(name, tag, y, f.score)
        store.save(driver_name(name), tag, y, f.driver.astype(np.float32))
        if tag == "val":
            ok = f.driver >= 0
            driver_counts += np.bincount(f.driver[ok].astype(int), minlength=len(parts))
    total = driver_counts.sum()
    return {"name": name, "parts": parts, "references": refs, "mode": mode, "protected_factor": factor, "learned": learned,
            "driver_share": {k: (float(v / total) if total else None) for k, v in zip(parts, driver_counts)}}


def fuse_frozen(p, info: Dict, split: str, store: Optional[ScoreStore] = None, overwrite: bool = False) -> List[int]:
    """Apply an ALREADY FROZEN fusion (``info`` from ``fuse_cross_scale``: parts, references, mode, factor, learned weights) to every year of
    ``split`` and store it under ``info['name']``. Nothing is refitted or re-referenced, so a test or stress year cannot change the fusion.
    The parts must already be stored for that split. Returns the years written."""
    store = store or score_store(p)
    parts, refs, mode = info["parts"], info["references"], info["mode"]
    weights = info["learned"]["weights"] if info.get("learned") else None
    done = []
    for y in p.split.years[split]:
        if not overwrite and store.has(info["name"], split, y):
            continue
        loaded = {part: store.load(comp, split, y) for part, comp in parts.items()}
        protected = load_bench_year(p, split, y).extremes.protected
        f = fuse_scales(loaded, refs, mode, protected=protected, protected_factor=float(info["protected_factor"]), weights=weights)
        store.save(info["name"], split, y, f.score)
        store.save(driver_name(info["name"]), split, y, f.driver.astype(np.float32))
        done.append(int(y))
    return done


def compare_cross_scale(p, daily: str, scales: Dict[str, str], budgets: Sequence[float], mode: str = "max", factor: float = 0.5,
                        store: Optional[ScoreStore] = None, overwrite: bool = False) -> Dict:
    """Daily alone against every combination of the given scales, on the held-out threshold years."""
    store = store or score_store(p)
    check_benchmark(p, require_pinned=False)
    years = holdout_years(p)
    rows: List[Dict] = []
    fused_info: Dict[str, Dict] = {}

    def row_for(label: str, comp: str, used: Sequence[str], fusion: str):
        res = evaluate_component(p, comp, "val", budgets, ("seen",), store, pinned=False, years=years)
        for b in budgets:
            r = summary_row(res, "seen", b)
            rows.append({"combination": label, "scales": list(used), "fusion": fusion, "component": comp,
                         "budget_per_1000": float(b), "recall": r["recall"], "event_recall": r["event_recall"],
                         "false_per_1000_clean": r["false_per_1000"], "protected_flagged": r["protected_flagged"], "pr_auc": r["pr_auc"]})

    row_for("daily only", daily, [], "daily")
    keys = list(scales)
    for k in range(1, len(keys) + 1):
        for combo in combinations(keys, k):
            sub = {s: scales[s] for s in combo}
            for fusion_mode, tag in ((mode, "fixed"), ("learned", "learned")):
                info = fuse_cross_scale(p, daily, sub, fusion_mode, factor, store, overwrite)
                fused_info[info["name"]] = info
                row_for("daily + " + " + ".join(combo) + (" (learned)" if tag == "learned" else ""), info["name"], combo, tag)
    return {"label": "SYNTHETIC faults, held-out threshold years only", "evaluation_years": years, "mode": mode,
            "daily": daily, "scorers": dict(scales),
            "protected_factor": factor, "budgets": [float(b) for b in budgets], "rows": rows, "fusions": fused_info,
            "caveats": ["the daily fusion is fitted on the fusion-fit years, so only the threshold years are held out",
                        "thresholds come from the clean version of the same years (as in the existing validation curves)",
                        f"{len(years)} evaluation years: no confidence interval (fewer than 5 years)"]}


def decide_architecture(result: Dict, final_budget: float = 1.0, min_recall_gain: float = 0.02) -> Dict:
    """Apply the frozen rule of docs/qc-evaluation-protocol.md to a ``compare_cross_scale`` result and return the choice.

    A combination replaces ``daily only`` only if at the final budget its recall is at least ``min_recall_gain`` higher, its false alarms per
    1,000 clean cell-days do not exceed the budget, and its share of flagged protected extremes is not higher. A learned fusion must in
    addition pass the same test against the fixed-rule row of the same scales. Among qualifiers the simplest wins (fewest scales, fixed
    before learned), then the higher recall; if none qualifies the choice is daily only."""
    at = [r for r in result["rows"] if abs(r["budget_per_1000"] - final_budget) < 1e-9]
    if not at:
        raise ValueError(f"the table has no rows at the final budget {final_budget}")
    base = next(r for r in at if r["fusion"] == "daily")

    def val(r, k, default=0.0):
        return default if r[k] is None else float(r[k])

    def passes(r, ref):
        return (val(r, "recall", -1.0) >= val(ref, "recall", 0.0) + min_recall_gain - 1e-12
                and val(r, "false_per_1000_clean") <= final_budget + 1e-12
                and val(r, "protected_flagged") <= val(ref, "protected_flagged") + 1e-12)

    qual = []
    notes = []
    for r in at:
        if r["fusion"] == "daily":
            continue
        ok = passes(r, base)
        if ok and r["fusion"] == "learned":
            twin = next((t for t in at if t["fusion"] == "fixed" and sorted(t["scales"]) == sorted(r["scales"])), None)
            ok = twin is not None and passes(r, twin)
            if not ok:
                notes.append(f"{r['combination']} beats daily only but not its fixed-rule twin by {min_recall_gain}")
        if ok:
            qual.append(r)
    if not qual:
        return {"chosen": {"scales": [], "fusion": "daily", "component": base["component"], "scorers": {}},
                "reason": f"no combination raised recall by {min_recall_gain} within the guards: daily only", "notes": notes,
                "rule": {"final_budget": final_budget, "min_recall_gain": min_recall_gain}}
    qual.sort(key=lambda r: (len(r["scales"]), r["fusion"] == "learned", -val(r, "recall")))
    c = qual[0]
    return {"chosen": {"scales": list(c["scales"]), "fusion": c["fusion"], "component": c["component"],
                       "scorers": {s: result["scorers"][s] for s in c["scales"]}},
            "reason": f"simplest qualifying combination: {c['combination']} (recall {val(c, 'recall'):.3f} against {val(base, 'recall'):.3f} for daily only)",
            "qualifying": [r["combination"] for r in qual], "notes": notes,
            "rule": {"final_budget": final_budget, "min_recall_gain": min_recall_gain}}


def comparison_markdown(result: Dict) -> str:
    fmt = lambda v: "n/a" if v is None else f"{v:.3f}"
    lines = ["### Cross-scale fusion (validation, " + result["label"] + ")", "",
             f"Evaluation years {result['evaluation_years']}; fixed `{result['mode']}` rule; coherent-extreme factor {result['protected_factor']}. "
             + " ".join(result["caveats"]), "",
             "| combination | budget per 1,000 | recall | event recall | false per 1,000 clean | protected extremes flagged | PR-AUC |",
             "|---|---|---|---|---|---|---|"]
    for r in result["rows"]:
        lines.append(f"| {r['combination']} | {r['budget_per_1000']:g} | {fmt(r['recall'])} | {fmt(r['event_recall'])} | "
                     f"{fmt(r['false_per_1000_clean'])} | {fmt(r['protected_flagged'])} | {fmt(r['pr_auc'])} |")
    return "\n".join(lines) + "\n"


def write_comparison(out_dir: Path, result: Dict) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cross_scale_validation.json").write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")
    md = out_dir / "cross_scale_validation.md"
    md.write_text(comparison_markdown(result), encoding="utf-8")
    return md
