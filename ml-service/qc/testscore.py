"""Gate 7: the single test-scoring pass, the unseen-client and stress evaluations, and the report.

Test years (``years.test``, 2018-2025) are scored ONCE, with the budgets fixed at gate 5. Before anything is
scored this module checks that
  * the budgets are fixed (``fusion_budgets.json``) and were made for this benchmark and this split,
  * the benchmark hash is the pinned one,
  * every required model and fusion exists for every seed.
It then writes ``test_scoring.lock.json``. A finished lock makes any further test scoring refuse to start:
the test set is single use. An unfinished lock (a crashed or time-capped run) can be resumed; finished
score files are kept, so nothing is scored twice. The stress split (1901-1950, evaluation only) has no lock.

Scores for each seed: rules, slow, neighbour_baseline (untrained); spatial, temporal, plain_gru (centralized);
every federated variant whose model exists; and the fusion variants fitted at gate 5. Metrics use the clean
threshold years for thresholds, as on validation, for the groups ``seen`` and ``unseen`` clients.

Also scored when they exist: the offline comparison models (qc.offline; non-causal, configured under
``offline.artifacts``) and fusions fitted on federated components (``python -m qc fusion --on fedpers``, stored as
``fusion_<variant>@<source>``). Whatever is missing is listed in every report as NOT RUN, with the reason.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from qc import paths
from qc.baselines import UNTRAINED, score_functions
from qc.benchmark import check_benchmark, load_bench_year
from qc.evaluate import compute_scores_many, evaluate_component, group_cells, score_store, summary_row, thresholds_for
from qc.federated import COMPONENTS as FED_COMPONENTS, VARIANTS as FED_VARIANTS, federated_score_function, load_client_models, run_label
from qc.fusion import FusionFit, VARIANTS as FUSION_VARIANTS, apply_fusion, component_names, fused_name, load_features
from qc.fusion_eval import budgets_path, load_budgets
from qc.metrics import calibration
from qc.offline import ARCHS as OFFLINE_ARCHS, offline_name, offline_scorers
from qc.prepare import Prepared
from qc.runs import RunDir, git_commit, read_json, write_json
from qc.trained import COMPONENTS as CENTRAL_COMPONENTS, load_model, resolve_device, run_name, score_function

log = logging.getLogger(__name__)
FUSION_SOURCES = ("fedpers", "fedavg", "fedft")          # federated variants a fusion can be fitted on (qc.fusion.FED_SOURCES)


def run_root(p: Prepared) -> Path:
    return paths.out_dir(p.cfg) / str(p.cfg.name)


def lock_path(p: Prepared) -> Path:
    return run_root(p) / "test_scoring.lock.json"


def final_checkpoint(p: Prepared, component: str, seed: int) -> Path:
    n = run_name(component, seed)
    return run_root(p) / n / "checkpoints" / f"{n}_final.pt"


def fed_checkpoint(p: Prepared, variant: str, component: str, seed: int) -> Path:
    n = run_label(variant, component, seed, float(p.cfg.federated.prox_mu))
    return run_root(p) / n / "checkpoints" / f"{n}_final.pt"


def preflight(p: Prepared, seeds: Sequence[int], splits: Sequence[str], resume: bool = False) -> Dict:
    """Everything that must hold before a single test or stress year is scored. Raises RuntimeError with the fix."""
    budgets = load_budgets(p)                                   # raises if the budgets are not fixed
    bench = check_benchmark(p, require_pinned=True)
    if budgets.get("benchmark_hash") and str(budgets["benchmark_hash"]) != str(bench["hash"]):
        raise RuntimeError("the budgets were fixed for a different benchmark than the one being scored")
    if budgets.get("split_manifest_hash") != p.manifest["hash"]:
        raise RuntimeError("the budgets were fixed for a different split than the current one")
    missing = []
    for s in seeds:
        missing += [str(final_checkpoint(p, c, s)) for c in CENTRAL_COMPONENTS if not final_checkpoint(p, c, s).is_file()]
        if not (run_root(p) / "fusion" / "models" / f"logistic_s{s}.json").is_file():
            missing.append(f"fusion model for seed {s} (run `python -m qc fusion`)")
    if missing:
        raise RuntimeError("cannot score the test years: missing " + "; ".join(missing[:4]) + (" ..." if len(missing) > 4 else ""))
    if "test" in splits and lock_path(p).is_file():
        lock = read_json(lock_path(p))
        if lock.get("status") == "done":
            raise RuntimeError(f"the test years were already scored ({lock.get('finished')}); the test set is single use. "
                               f"Results are in {run_root(p) / 'test'}. To start over, the owner must delete {lock_path(p)} and "
                               "say so in docs/qc-evaluation-protocol.md.")
        if not resume:
            raise RuntimeError(f"an unfinished test-scoring pass exists ({lock_path(p)}); continue it with --resume")
    return budgets


def _scorers(p: Prepared, seed: int, device) -> Dict:
    """name -> score function, for everything that exists for this seed. Also returns the list of what is missing."""
    fns, missing = {}, []
    for c in CENTRAL_COMPONENTS:
        fns[run_name(c, seed)] = score_function(p, c, load_model(p, c, final_checkpoint(p, c, seed), device), device)
    for v in FED_VARIANTS:
        for c in FED_COMPONENTS:
            path = fed_checkpoint(p, v, c, seed)
            name = run_label(v, c, seed, float(p.cfg.federated.prox_mu))
            if path.is_file():
                fns[name] = federated_score_function(p, c, load_client_models(p, c, path, device), device)
            else:
                missing.append(name)
    return fns, missing


def score_all(p: Prepared, seeds: Sequence[int], splits: Sequence[str]) -> Dict:
    """Write score files for ``splits`` and return what was not run."""
    cfg, store, device = p.cfg, score_store(p), resolve_device(p.cfg)
    not_run: Dict[str, str] = {}
    compute_scores_many(p, score_functions(p), splits, store)
    for seed in seeds:
        fns, missing = _scorers(p, seed, device)
        compute_scores_many(p, fns, splits, store)
        for name in missing:
            not_run[name] = "NOT RUN: no trained model found"
        fit = FusionFit.load(run_root(p) / "fusion" / "models", seed)
        variants = FUSION_VARIANTS + (("logistic_fed",) if fit.logistic_fed is not None else ())
        apply_fusion(p, fit, splits, variants, store)
        for src in FUSION_SOURCES:
            label = f"fusion fitted on {src} components (seed {seed})"
            f = run_root(p) / "fusion" / "models" / f"logistic_{src}_s{seed}.json"
            if not f.is_file():
                not_run[label] = f"NOT RUN: no fit found (run `python -m qc fusion --on {src}`)"
                continue
            sfit = FusionFit.load(run_root(p) / "fusion" / "models", seed, src)
            if not all(store.has(n, splits[0], p.split.years[splits[0]][0]) or n in {"rules", "slow"} for n in sfit.names):
                not_run[label] = f"NOT RUN: the {src} component scores were not computed (no {src} models for seed {seed})"
                continue
            apply_fusion(p, sfit, splits, FUSION_VARIANTS + (("logistic_fed",) if sfit.logistic_fed is not None else ()), store)
    offline, why = offline_scorers(p, splits, str(device))
    not_run.update(why)
    compute_scores_many(p, offline, splits, store)
    return not_run


def evaluate_all(p: Prepared, seeds: Sequence[int], splits: Sequence[str], budgets: Dict) -> Dict[str, Dict[str, Dict]]:
    """results[split][name] = metrics for groups seen and unseen at the final and review budgets."""
    store = score_store(p)
    bs = [float(budgets["final_per_1000"]), float(budgets["review_per_1000"])]
    names = list(UNTRAINED)
    for s in seeds:
        names += [run_name(c, s) for c in CENTRAL_COMPONENTS]
        names += [run_label(v, c, s, float(p.cfg.federated.prox_mu)) for v in FED_VARIANTS for c in FED_COMPONENTS]
        names += [fused_name(v, s) for v in FUSION_VARIANTS + ("logistic_fed",)]
        names += [fused_name(v, s, src) for src in FUSION_SOURCES for v in FUSION_VARIANTS + ("logistic_fed",)]
    names += [offline_name(a) for a in OFFLINE_ARCHS]
    out: Dict = {}
    for split in splits:
        out[split] = {}
        for n in dict.fromkeys(names):
            if all(store.has(n, split, y) for y in p.split.years[split]):
                out[split][n] = evaluate_component(p, n, split, bs, ("seen", "unseen"), store, True)
    return out


# ---------------------------------------------------------------------------------------------- aggregation

def base_name(name: str) -> str:
    head, _, tail = name.rpartition("_s")
    return head if tail.isdigit() else name


def _stat(values: List[Optional[float]]) -> Optional[Dict]:
    v = [x for x in values if x is not None and np.isfinite(x)]
    return {"mean": float(np.mean(v)), "min": float(np.min(v)), "max": float(np.max(v)), "n_seeds": len(v)} if v else None


def aggregate_seeds(per_name: Dict[str, Dict], budgets: Sequence[float]) -> Dict[str, Dict]:
    """Mean and range over seeds, for each model family, group and budget. Untrained scores have one 'seed'."""
    fam: Dict[str, List[Dict]] = {}
    for n, res in per_name.items():
        fam.setdefault(base_name(n), []).append(res)
    out: Dict[str, Dict] = {}
    for f, rs in fam.items():
        out[f] = {}
        for g in rs[0]["groups"]:
            out[f][g] = {"pr_auc": _stat([r["groups"][g]["pr_auc"] for r in rs if g in r["groups"]])}
            for b in budgets:
                rows = [summary_row(r, g, b) for r in rs if g in r["groups"]]
                out[f][g][str(b)] = {k: _stat([row[k] for row in rows])
                                     for k in ("recall", "event_recall", "false_per_1000", "protected_flagged", "iou")}
    return out


def fused_calibration(p: Prepared, seed: int, split: str) -> Dict:
    store = score_store(p)
    out = {}
    for g in ("seen", "unseen"):
        cells = group_cells(p, g)
        probs, labs = [], []
        for y in p.split.years[split]:
            sc = store.load(fused_name("logistic", seed), split, y)
            b = load_bench_year(p, split, y)
            ok = np.isfinite(sc) & cells[None, :] & ~b.extremes.ambiguous
            probs.append(1.0 / (1.0 + np.exp(-sc[ok].astype(np.float64))))
            labs.append(b.faults.labels()[ok])
        out[g] = calibration(np.concatenate(probs), np.concatenate(labs))
    return out


def write_alerts(p: Prepared, seed: int, split: str, budgets: Dict, out_dir: Path) -> Path:
    """Per-alert records of the main fusion: every cell-day above the review threshold, with the four component
    scores (log1p, as the fusion sees them), the fused score and which flag it raised."""
    import pandas as pd

    store = score_store(p)
    fit = FusionFit.load(run_root(p) / "fusion" / "models", seed)
    name = fused_name("logistic", seed)
    thr = thresholds_for(p, name, [budgets["final_per_1000"], budgets["review_per_1000"]], store)
    t_final, t_review = thr[float(budgets["final_per_1000"])], thr[float(budgets["review_per_1000"])]
    frames = []
    for y in p.split.years[split]:
        fused = store.load(name, split, y)
        tt, cc = np.nonzero(np.nan_to_num(fused, nan=-np.inf) > t_review)
        feats = load_features(store, fit.names, split, y)[tt, cc]
        lab = load_bench_year(p, split, y).faults.labels()[tt, cc]
        df = pd.DataFrame({"split": split, "year": y, "day_of_year": tt.astype(np.int16), "cell": cc.astype(np.int32),
                           "lat": p.grid.lat[p.grid.rows[cc]], "lon": p.grid.lon[p.grid.cols[cc]],
                           "client": p.cell_client[cc], "fused_score": fused[tt, cc],
                           "flag": np.where(fused[tt, cc] > t_final, "final", "review"),
                           "synthetic_fault": lab})
        for i, n in enumerate(fit.names):
            df[f"score_{n}"] = np.expm1(feats[:, i])
        frames.append(df)
    out = out_dir / f"alerts_{split}_s{seed}.parquet"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_parquet(out, index=False)
    return out


# ---------------------------------------------------------------------------------------------- the pass

def run_test_scoring(p: Prepared, seeds: Optional[Sequence[int]] = None, splits: Sequence[str] = ("test", "stress"),
                     resume: bool = False) -> Dict:
    cfg = p.cfg
    seeds = list(seeds if seeds is not None else [int(s) for s in cfg.train.seeds])
    budgets = preflight(p, seeds, splits, resume)
    root = run_root(p)
    now = lambda: datetime.datetime.now().isoformat(timespec="seconds")
    if "test" in splits:
        write_json(lock_path(p), {"status": "started", "started": now(), "commit": git_commit(), "seeds": seeds,
                                  "budgets": {k: budgets[k] for k in ("final_per_1000", "review_per_1000")},
                                  "benchmark_hash": check_benchmark(p)["hash"]})
    not_run = score_all(p, seeds, splits)
    results = evaluate_all(p, seeds, splits, budgets)
    bs = [float(budgets["final_per_1000"]), float(budgets["review_per_1000"])]
    out_dir = RunDir(root, "test").path
    report: Dict = {"label_tier": "synthetic faults (no real labels exist for RF25)", "budgets": budgets, "seeds": seeds,
                    "not_run": not_run, "splits": {}}
    for split in splits:
        report["splits"][split] = {
            "years": [p.split.years[split][0], p.split.years[split][-1]],
            "by_model_family": aggregate_seeds(results[split], bs),
            "calibration_main_fusion": {str(s): fused_calibration(p, s, split) for s in seeds} if split == "test" else None,
        }
        write_json(out_dir / f"metrics_{split}.json", results[split])
        for s in seeds:
            write_alerts(p, s, split, budgets, out_dir / "alerts") if split == "test" else None
    write_json(out_dir / "test_report.json", report)
    (out_dir / "test_report.md").write_text(format_report(report), encoding="utf-8")
    if "test" in splits:
        lock = read_json(lock_path(p))
        lock.update({"status": "done", "finished": now()})
        write_json(lock_path(p), lock)
    return report


def _fmt(s: Optional[Dict], pct: bool = False) -> str:
    if not s:
        return "n/a"
    f = (lambda v: f"{100 * v:.1f}%") if pct else (lambda v: f"{v:.3f}")
    return f(s["mean"]) if s["n_seeds"] == 1 else f"{f(s['mean'])} [{f(s['min'])}-{f(s['max'])}]"


def format_report(report: Dict) -> str:
    """Markdown tables: model family x (recall, event recall, false alerts, protected extremes flagged, IoU)."""
    lines = ["# Test scoring report", "", f"Labels: {report['label_tier']}.", "",
             f"Budgets (false alerts per 1,000 clean cell-days): final {report['budgets']['final_per_1000']}, "
             f"review {report['budgets']['review_per_1000']}. Seeds: {report['seeds']}. "
             "Cells show the mean over seeds with the range in brackets.", ""]
    for split, doc in report["splits"].items():
        lines += [f"## {split} {doc['years'][0]}-{doc['years'][1]}", ""]
        for budget_key, bname in ((str(float(report["budgets"]["final_per_1000"])), "final flag"),
                                  (str(float(report["budgets"]["review_per_1000"])), "review flag")):
            for group in ("seen", "unseen"):
                lines += [f"### {bname}, {group} clients", "",
                          "| model | PR-AUC | recall | event recall | false alerts /1000 | protected flagged | footprint IoU |",
                          "|---|---|---|---|---|---|---|"]
                for fam, groups in doc["by_model_family"].items():
                    if group not in groups:
                        continue
                    g = groups[group]
                    r = g.get(budget_key, {})
                    lines.append(f"| {fam} | {_fmt(g['pr_auc'])} | {_fmt(r.get('recall'), True)} | {_fmt(r.get('event_recall'), True)} | "
                                 f"{_fmt(r.get('false_per_1000'))} | {_fmt(r.get('protected_flagged'), True)} | {_fmt(r.get('iou'))} |")
                lines.append("")
    lines += ["## Not run", ""] + [f"- {k}: {v}" for k, v in report["not_run"].items()]
    lines += ["- local-only variant on unseen clients: NOT AVAILABLE (no model exists for them; cells are left unscored).", ""]
    return "\n".join(lines)
