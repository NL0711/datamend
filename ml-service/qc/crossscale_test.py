"""The cross-scale test pass: final numbers for the architecture chosen on validation, next to the daily-only baseline.

STATUS: new, unit-tested on a generated world only; nothing has run on real RF25. SYNTHETIC faults, not real QC labels.

It extends the single-use daily test pass (``qc.testscore``). The rules, all enforced here before anything is scored:

  * the daily test pass must be FINISHED (its lock says done), so the daily component and the untrained baselines already have test and stress scores;
  * the architecture must have been chosen on validation (``architecture_choice.json``, written once by ``python -m qc choose-architecture``), together with
    the standardising references and the learned weights of the chosen fusion, which are applied as they are: nothing is refitted on a test year;
  * the budgets must be fixed (``fusion_budgets.json``);
  * this pass has its own lock, ``cross_scale_test.lock.json``. A finished lock makes any further run refuse to start (the test years are single use); an
    unfinished one can be resumed, and scores already written are kept.

What is scored and reported, all named in the choice file beforehand: the chosen architecture, the daily-only baseline and the untrained baselines
(rules, slow, neighbour_baseline), for the test years and the stress years (1901-1950, evaluation only), for the ``seen`` and ``unseen`` clients, at
the two fixed budgets. No other candidate is scored on a test year.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from qc.baselines import UNTRAINED
from qc.benchmark import check_benchmark
from qc.crossscale_run import compute_scale_scores, fuse_frozen
from qc.evaluate import evaluate_component, score_store, summary_row
from qc.fusion_eval import load_budgets
from qc.period_benchmark import check_period_benchmark
from qc.runs import git_commit, read_json, write_json
from qc.testscore import lock_path as daily_lock_path, run_root

GROUPS = ("seen", "unseen")


def lock_path(p) -> Path:
    return run_root(p) / "cross_scale_test.lock.json"


def choice_path(p) -> Path:
    return run_root(p) / "scales" / "architecture_choice.json"


def report_dir(p) -> Path:
    return run_root(p) / "test"


def preflight(p, splits: Sequence[str], resume: bool = False) -> Dict:
    """Everything that must hold before a test or stress year is scored. Raises RuntimeError saying what to do."""
    dl = daily_lock_path(p)
    if not dl.is_file() or read_json(dl).get("status") != "done":
        raise RuntimeError(f"the daily test pass is not finished ({dl}); run `python -m qc test-score` first. The cross-scale pass builds on its scores.")
    cp = choice_path(p)
    if not cp.is_file():
        raise RuntimeError(f"the architecture has not been chosen ({cp}); run `python -m qc cross-scale` and `python -m qc choose-architecture` on validation "
                           "and commit the choice before any test year is scored")
    choice = read_json(cp)
    budgets = load_budgets(p)                                           # raises if the budgets are not fixed
    lp = lock_path(p)
    if "test" in splits and lp.is_file():
        lock = read_json(lp)
        if lock.get("status") == "done":
            raise RuntimeError(f"the cross-scale test pass was already done ({lock.get('finished')}); the test years are single use. "
                               f"Results are in {report_dir(p)}. To start over the owner must delete {lp} and say so in the protocol.")
        if not resume:
            raise RuntimeError(f"an unfinished cross-scale test pass exists ({lp}); continue it with resume=True")
    check_benchmark(p)
    if choice["chosen"]["fusion"] != "daily":
        if not choice.get("fusion_info"):
            raise RuntimeError("the choice file has no frozen fusion information; choose the architecture again on validation")
        manifest = check_period_benchmark(p)
        missing = [s for s in splits if s not in manifest.get("split_hashes", {})]
        if missing:
            raise RuntimeError(f"the period benchmark has not been built for {missing}; run `python -m qc period-benchmark --splits {' '.join(missing)}`")
    return {"choice": choice, "budgets": budgets}


def names_to_score(choice: Dict) -> Dict[str, str]:
    """Label -> stored component name. The daily-only baseline and the untrained baselines are always included."""
    out = {"chosen architecture": choice["chosen"]["component"], "daily only": choice["daily"]}
    for n in UNTRAINED:
        out[f"untrained: {n}"] = n
    seen, uniq = set(), {}
    for k, v in out.items():
        if v not in seen:
            seen.add(v)
            uniq[k] = v
    return uniq


def run_cross_scale_test(p, splits: Sequence[str] = ("test", "stress"), resume: bool = False, seed: int = 0) -> Dict:
    pre = preflight(p, splits, resume)
    choice, budgets_doc = pre["choice"], pre["budgets"]
    final, review = float(budgets_doc["final_per_1000"]), float(budgets_doc["review_per_1000"])
    now = lambda: datetime.datetime.now().isoformat(timespec="seconds")
    if "test" in splits:
        write_json(lock_path(p), {"status": "started", "started": now(), "commit": git_commit(), "choice_commit": choice.get("commit"),
                                  "component": choice["chosen"]["component"], "splits": list(splits)})
    store = score_store(p)
    chosen = choice["chosen"]
    if chosen["fusion"] != "daily":
        info = choice["fusion_info"]
        for scale, scorer in chosen["scorers"].items():
            compute_scale_scores(p, scale, scorer, seed=seed, store=store, splits=tuple(splits))
        for split in splits:
            fuse_frozen(p, info, split, store)
    names = names_to_score(choice)
    results: Dict[str, Dict[str, Dict]] = {}
    for split in splits:
        results[split] = {}
        for label, comp in names.items():
            results[split][label] = evaluate_component(p, comp, split, [final, review], GROUPS, store, pinned=True)
    report = {"label": "SYNTHETIC faults", "splits": list(splits), "budgets": {"final": final, "review": review},
              "chosen": chosen, "choice_commit": choice.get("commit"), "choice_rule": choice.get("rule"),
              "benchmark_hash": check_benchmark(p)["hash"], "components": names, "results": results}
    rows = comparison_rows(report)
    report["rows"] = rows
    out = report_dir(p)
    out.mkdir(parents=True, exist_ok=True)
    (out / "cross_scale_test_report.json").write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")
    (out / "cross_scale_test_report.md").write_text(format_report(report), encoding="utf-8")
    if "test" in splits:
        lock = read_json(lock_path(p))
        lock.update({"status": "done", "finished": now()})
        write_json(lock_path(p), lock)
    return report


def comparison_rows(report: Dict) -> List[Dict]:
    rows = []
    for split, by_label in report["results"].items():
        for label, res in by_label.items():
            for group in GROUPS:
                if group not in res["groups"]:
                    continue
                for b in (report["budgets"]["final"], report["budgets"]["review"]):
                    r = summary_row(res, group, b)
                    rows.append({"split": split, "group": group, "budget_per_1000": float(b), "architecture": label,
                                 "component": report["components"][label], "recall": r["recall"], "event_recall": r["event_recall"],
                                 "false_per_1000_clean": r["false_per_1000"], "protected_flagged": r["protected_flagged"], "pr_auc": r["pr_auc"]})
    return rows


def format_report(report: Dict) -> str:
    fmt = lambda v: "n/a" if v is None else f"{v:.3f}"
    ch = report["chosen"]
    scales = " + ".join(ch["scales"]) if ch["scales"] else "none (daily only)"
    lines = ["# Cross-scale test pass", "",
             f"{report['label']}. Chosen architecture: daily plus {scales}, fusion `{ch['fusion']}`, component `{ch['component']}` "
             f"(choice made at commit {report.get('choice_commit')}). Budgets fixed before the pass: final {report['budgets']['final']:g}, review "
             f"{report['budgets']['review']:g} false alarms per 1,000 clean cell-days. Benchmark hash {report['benchmark_hash']}. "
             "Only the chosen architecture, the daily-only baseline and the untrained baselines were scored on these years.", ""]
    for split in report["splits"]:
        for group in GROUPS:
            sel = [r for r in report["rows"] if r["split"] == split and r["group"] == group]
            if not sel:
                continue
            lines += [f"## {split}, {group} clients", "",
                      "| architecture | budget per 1,000 | recall | event recall | false per 1,000 clean | protected extremes flagged | PR-AUC |",
                      "|---|---|---|---|---|---|---|"]
            for r in sel:
                lines.append(f"| {r['architecture']} | {r['budget_per_1000']:g} | {fmt(r['recall'])} | {fmt(r['event_recall'])} | "
                             f"{fmt(r['false_per_1000_clean'])} | {fmt(r['protected_flagged'])} | {fmt(r['pr_auc'])} |")
            lines.append("")
    return "\n".join(lines) + "\n"
