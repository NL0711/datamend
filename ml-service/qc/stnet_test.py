"""The STNet test pass: final numbers for the STNet candidate chosen on validation, next to the old daily fusions and the untrained baselines.

STATUS: new, unit-tested on a generated world only; nothing has run on real RF25. SYNTHETIC faults, not real QC labels.

Same discipline as the cross-scale pass (``qc.crossscale_test``), all enforced before anything is scored:

  * the old daily components are NOT required: if the daily test pass was done their fusions are reported next to STNet, otherwise only the STNet
    candidate and the untrained baselines are scored (the untrained baselines are scored here when missing). An unfinished daily lock stops the pass;
  * the choice must have been made on validation (``stnet_choice.json``, written once by ``python -m qc choose-stnet``) and name the STNet candidate
    (if the rule kept the old daily pipeline there is nothing to score here);
  * the budgets must be fixed (``fusion_budgets.json``);
  * this pass has its own lock ``stnet_test.lock.json``. A finished lock makes any further run refuse (the test years are single use); an unfinished
    one can be resumed.

Nothing is fitted or tuned here: the frozen fusion and the frozen regional tables are applied as they are, and the STNet checkpoint is only run.
Scored and reported, all named in the choice file beforehand: the chosen candidate, the old daily fusions, the untrained baselines, for the test years
and the stress years (1901-1950, evaluation only), for ``seen`` and ``unseen`` clients, at the two fixed budgets.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Dict, Sequence

from qc.baselines import UNTRAINED, run_untrained
from qc.benchmark import check_benchmark
from qc.crossscale_test import comparison_rows
from qc.evaluate import evaluate_component, score_store
from qc.fusion_eval import load_budgets
from qc.runs import git_commit, read_json, write_json
from qc.stnet import score_checkpoint
from qc.stnet_arch import apply_calibration, apply_candidate, choice_path, load_candidate
from qc.testscore import lock_path as daily_lock_path, run_root

GROUPS = ("seen", "unseen")


def lock_path(p) -> Path:
    return run_root(p) / "stnet_test.lock.json"


def report_dir(p) -> Path:
    return run_root(p) / "test"


def preflight(p, splits: Sequence[str], resume: bool = False) -> Dict:
    dl = daily_lock_path(p)
    if dl.is_file() and read_json(dl).get("status") != "done":
        raise RuntimeError(f"an unfinished daily test pass exists ({dl}); finish it (`python -m qc test-score --resume`) or remove it with the owner's "
                           "agreement before this pass. (No daily test pass at all is fine: the old components are not part of this pass.)")
    cp = choice_path(p)
    if not cp.is_file():
        raise RuntimeError(f"the STNet choice has not been made ({cp}); run `python -m qc stnet-fuse` and `python -m qc choose-stnet` on validation "
                           "and commit the choice before any test year is scored")
    choice = read_json(cp)
    if choice["chosen"]["architecture"] != "stnet":
        raise RuntimeError(f"the validation rule kept the old daily pipeline ({choice['reason']}); there is no STNet candidate to score on test years")
    budgets = load_budgets(p)
    lp = lock_path(p)
    if "test" in splits and lp.is_file():
        lock = read_json(lp)
        if lock.get("status") == "done":
            raise RuntimeError(f"the STNet test pass was already done ({lock.get('finished')}); the test years are single use. Results are in "
                               f"{report_dir(p)}. To start over the owner must delete {lp} and say so in the protocol.")
        if not resume:
            raise RuntimeError(f"an unfinished STNet test pass exists ({lp}); continue it with resume=True")
    check_benchmark(p)
    return {"choice": choice, "budgets": budgets}


def names_to_score(choice: Dict, available=None) -> Dict[str, str]:
    """Label -> stored score name: the chosen candidate, the old daily fusions the rule compared against IF their test scores exist (a reference read
    from a committed file has none and is not scored), and the untrained baselines."""
    out = {"chosen STNet candidate": choice["chosen"]["component"]}
    for n, r in choice["rows"].items():
        if "candidate" not in r and not r.get("from_file") and (available is None or available(n)):
            out[f"old daily: {n}"] = n
    for n in UNTRAINED:
        out[f"untrained: {n}"] = n
    return out


def run_stnet_test(p, splits: Sequence[str] = ("test", "stress"), resume: bool = False) -> Dict:
    pre = preflight(p, splits, resume)
    choice, budgets_doc = pre["choice"], pre["budgets"]
    final, review = float(budgets_doc["final_per_1000"]), float(budgets_doc["review_per_1000"])
    now = lambda: datetime.datetime.now().isoformat(timespec="seconds")
    if "test" in splits:
        write_json(lock_path(p), {"status": "started", "started": now(), "commit": git_commit(), "choice_commit": choice.get("commit"),
                                  "component": choice["chosen"]["component"], "splits": list(splits)})
    seed, prefix = int(choice["seed"]), choice["prefix"]
    store = score_store(p)
    score_checkpoint(p, prefix, seed, tuple(splits), ("fault",))
    fit = load_candidate(p, seed)                                           # frozen: never refitted here
    apply_candidate(p, fit, tuple(splits), store)
    if choice["chosen"]["calibrated"]:
        apply_calibration(p, seed, tuple(splits), store)
    run_untrained(p, tuple(splits))                                         # the untrained baselines on these years (skips what is already scored)
    first = p.split.years[splits[0]][0]
    names = names_to_score(choice, lambda n: store.has(n, splits[0], first))
    results: Dict[str, Dict[str, Dict]] = {}
    for split in splits:
        results[split] = {label: evaluate_component(p, comp, split, [final, review], GROUPS, store, pinned=True) for label, comp in names.items()}
    report = {"label": "SYNTHETIC faults", "splits": list(splits), "budgets": {"final": final, "review": review}, "chosen": choice["chosen"],
              "choice_commit": choice.get("commit"), "choice_rule": choice.get("rule"), "benchmark_hash": check_benchmark(p)["hash"],
              "components": names, "results": results}
    report["rows"] = comparison_rows(report)
    out = report_dir(p)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stnet_test_report.json").write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")
    (out / "stnet_test_report.md").write_text(format_report(report), encoding="utf-8")
    if "test" in splits:
        lock = read_json(lock_path(p))
        lock.update({"status": "done", "finished": now()})
        write_json(lock_path(p), lock)
    return report


def format_report(report: Dict) -> str:
    fmt = lambda v: "n/a" if v is None else f"{v:.3f}"
    ch = report["chosen"]
    lines = ["# STNet test pass", "",
             f"{report['label']}. Chosen: `{ch['component']}` (variant {ch.get('variant')}, calibrated {ch.get('calibrated')}; choice made at commit "
             f"{report.get('choice_commit')}). Budgets fixed before the pass: final {report['budgets']['final']:g}, review {report['budgets']['review']:g} "
             f"false alarms per 1,000 clean cell-days. Benchmark hash {report['benchmark_hash']}. Only the chosen candidate, the old daily fusions and "
             "the untrained baselines were scored on these years.", ""]
    for split in report["splits"]:
        for group in GROUPS:
            sel = [r for r in report["rows"] if r["split"] == split and r["group"] == group]
            if not sel:
                continue
            lines += [f"## {split}, {group} clients", "",
                      "| score | budget per 1,000 | recall | event recall | false per 1,000 clean | protected extremes flagged | PR-AUC |",
                      "|---|---|---|---|---|---|---|"]
            for r in sel:
                lines.append(f"| {r['architecture']} | {r['budget_per_1000']:g} | {fmt(r['recall'])} | {fmt(r['event_recall'])} | "
                             f"{fmt(r['false_per_1000_clean'])} | {fmt(r['protected_flagged'])} | {fmt(r['pr_auc'])} |")
            lines.append("")
    return "\n".join(lines) + "\n"
