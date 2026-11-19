"""Which components does the fusion actually need? A validation-only ablation.

For each subset of components the fusion is fitted on the ``fusion_fit`` years and scored on the held-out threshold years, exactly as
in the main fusion step, and compared at the final false-alarm budget. It reads only validation scores and benchmark years (never test
or stress), writes its fused scores to a separate store (``<run>/ablation/scores``) so the main fusion is untouched, and changes
nothing that a later test pass depends on. Results are synthetic-fault validation numbers, not evidence about real faults.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from qc import paths
from qc.context import CONTEXT, context_functions
from qc.evaluate import compute_scores_many, evaluate_component, score_store, summary_row
from qc.fusion import fit_fusion, load_features
from qc.fusion_eval import holdout_years
from qc.prepare import Prepared
from qc.scoring import ScoreStore

log = logging.getLogger(__name__)

VARIANTS = ("logistic", "boosted")
FULL = ("rules", "slow", "spatial", "temporal")
SUBSETS: List[Sequence[str]] = [
    FULL,
    ("slow", "spatial", "temporal"),                       # without rules
    ("rules", "spatial", "temporal"),                      # without slow
    ("rules", "slow", "temporal"),                         # without spatial
    ("rules", "slow", "spatial"),                          # without temporal
    ("rules",), ("rules", "slow"), ("rules", "spatial"), ("rules", "slow", "spatial", "temporal", "neighbour_baseline"),
    ("rules", "slow", "spatial", "neighbour_baseline"),   # neighbour average instead of temporal
    ("rules", "slow", "spatial", "temporal", "neighbour_baseline", "plain_gru"),
    ("rules", "slow", "spatial", "temporal", "nbr_wet", "nbr_heavy"),                  # + event-coherence context (qc.context)
    ("rules", "slow", "spatial", "temporal", "neighbour_baseline", "nbr_wet", "nbr_heavy"),
    ("rules", "nbr_wet", "nbr_heavy"),
]
# Neighbour-residual evidence for zeroed, scale and drift faults (qc.residual). Run with `ablate --residual-only`; the first row is the
# unchanged four-component fusion, for comparison inside the same table.
RESIDUAL_SUBSETS: List[Sequence[str]] = [
    FULL,
    FULL + ("nbr_surprise",),
    FULL + ("nbr_surprise", "drift_cusum"),
    FULL + ("nbr_surprise", "drift_cusum", "nbr_wet", "nbr_heavy"),
    ("rules", "slow", "nbr_surprise", "drift_cusum"),      # no trained model at all
    ("rules", "nbr_surprise", "drift_cusum"),
]


def label(subset: Sequence[str]) -> str:
    return "+".join(subset)


def ablation_store(p: Prepared) -> ScoreStore:
    return ScoreStore(paths.out_dir(p.cfg) / str(p.cfg.name) / "ablation" / "scores")


def run_ablation(p: Prepared, seed: int, budget: float = 1.0, subsets: Optional[Sequence[Sequence[str]]] = None) -> List[Dict]:
    main, store = score_store(p), ablation_store(p)
    rows: List[Dict] = []
    if any(c in CONTEXT for sub in (subsets or SUBSETS) for c in sub):
        compute_scores_many(p, context_functions(p), ("val",), main)       # cheap, CPU, validation years and clean threshold years only
    from qc.residual import RESIDUAL, residual_functions
    if any(c in RESIDUAL for sub in (subsets or SUBSETS) for c in sub):
        compute_scores_many(p, residual_functions(p), ("val",), main)      # same: validation years and clean threshold years only
    for subset in (subsets or SUBSETS):
        names = _names(seed, subset)
        missing = [n for n in names if not main.has(n, "val", p.split.years["fusion_fit"][0])]
        if missing:
            rows.append({"components": label(subset), "variant": None, "note": f"NOT RUN: missing validation scores for {missing}"})
            continue
        fit = fit_fusion(p, seed, main, base=subset)
        for tag, year in [("val", y) for y in holdout_years(p)] + [("clean", y) for y in p.split.years["threshold"]]:
            feats = load_features(main, fit.names, tag, year)
            for v in VARIANTS:
                store.save(f"abl_{v}_{label(subset)}_s{seed}", tag, year, fit.score(v, feats, p.cell_client))
        for v in VARIANTS:
            res = evaluate_component(p, f"abl_{v}_{label(subset)}_s{seed}", "val", [budget], ("seen",), store, True, holdout_years(p))
            row = summary_row(res, "seen", budget)
            row.update({"components": label(subset), "variant": v, "n_components": len(subset)})
            rows.append(row)
            log.info("ablation %s %s: pr_auc %.3f recall %s", label(subset), v, row["pr_auc"], row["recall"])
    return rows


def _names(seed: int, subset: Sequence[str]) -> List[str]:
    from qc.fusion import component_names
    return component_names(seed, subset)


def format_rows(rows: Sequence[Dict]) -> str:
    def f(x, pct=False):
        return "n/a" if x is None else (f"{100 * x:.1f}%" if pct else f"{x:.3f}")
    out = [f"{'components':<62} {'variant':<9} PR-AUC  recall  ev.rec  FA/1000 prot.flag"]
    for r in rows:
        if r.get("variant") is None:
            out.append(f"{r['components']:<62} {r['note']}")
            continue
        out.append(f"{r['components']:<62} {r['variant']:<9} {f(r['pr_auc'])}  {f(r['recall'], True):>6} {f(r['event_recall'], True):>7} "
                   f"{r['false_per_1000']:>7.3f} {f(r['protected_flagged'], True):>9}")
    return "\n".join(out)
