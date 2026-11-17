"""Scoring and evaluation shared by every component, baseline and fused score.

Scores live in ``<out>/<name>/scores/<component>/``:
  ``<split>_<year>.npy``   scores on the frozen benchmark (corrupted) year
  ``clean_<year>.npy``     scores on the uncorrupted year (threshold years only), for false-alarm thresholds

Thresholds are always set on clean threshold years over the cells of training clients, never on test data.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from qc import paths
from qc.benchmark import check_benchmark, load_bench_year
from qc.extremes import find_extremes
from qc.metrics import YearScores, budget_thresholds, clean_reference, evaluate, pr_auc
from qc.prepare import Prepared
from qc.scoring import Block, ScoreStore, make_block
from qc.splits import BUFFER, HELDOUT, TRAIN

log = logging.getLogger(__name__)
ScoreFn = Callable[[Block], np.ndarray]


def score_store(p: Prepared) -> ScoreStore:
    return ScoreStore(paths.out_dir(p.cfg) / str(p.cfg.name) / "scores")


def group_cells(p: Prepared, group: str) -> np.ndarray:
    """(n_land,) bool. ``seen`` = cells of training clients (buffer included); ``unseen`` = held-out clients."""
    if group == "seen":
        return (p.cell_role == TRAIN) | (p.cell_role == BUFFER)
    if group == "unseen":
        return p.cell_role == HELDOUT
    raise ValueError(f"unknown group {group!r}")


def compute_scores(p: Prepared, component: str, fn: ScoreFn, splits: Sequence[str], store: Optional[ScoreStore] = None,
                   overwrite: bool = False) -> None:
    """Score every year of ``splits`` (benchmark version) and the clean threshold years. Skips what exists."""
    store = store or score_store(p)
    pad = int(p.cfg.components.history_days)
    jobs = [(s, y, s) for s in splits for y in p.split.years[s]] + [("clean", y, None) for y in p.split.years["threshold"]]
    for tag, year, split in jobs:
        if store.has(component, tag, year) and not overwrite:
            continue
        score = fn(make_block(p, year, split, pad))
        store.save(component, tag, year, score)
        log.info("%s: scored %s %d", component, tag, year)


def thresholds_for(p: Prepared, component: str, budgets: Sequence[float], store: Optional[ScoreStore] = None) -> Dict[float, float]:
    store = store or score_store(p)
    cells = group_cells(p, "seen")
    ref = []
    for y in p.split.years["threshold"]:
        ex = find_extremes(p.store.year(y), p.stats.heavy_mm, p.grid, p.cfg.extremes.min_cells)
        ref.append(clean_reference(store.load(component, "clean", y), ex.protected, ex.ambiguous, cells))
    return budget_thresholds(np.concatenate(ref), budgets)


def load_years(p: Prepared, component: str, split: str, years: Optional[Sequence[int]] = None,
               store: Optional[ScoreStore] = None) -> List[YearScores]:
    store = store or score_store(p)
    return [YearScores(load_bench_year(p, split, y), store.load(component, split, y)) for y in (years or p.split.years[split])]


def evaluate_component(p: Prepared, component: str, split: str, budgets: Sequence[float], groups: Sequence[str] = ("seen",),
                       store: Optional[ScoreStore] = None, pinned: bool = True, years: Optional[Sequence[int]] = None) -> Dict:
    """Metrics for one component on one split. ``pinned=False`` allows an unpinned benchmark (validation only).
    ``years`` limits the evaluation to some benchmark years of the split (e.g. the years a fusion was not fitted on)."""
    bench = check_benchmark(p, require_pinned=pinned)
    thr = thresholds_for(p, component, budgets, store)
    years = load_years(p, component, split, years, store)
    out: Dict = {"component": component, "split": split, "years": [years[0].bench.year, years[-1].bench.year],
                 "label_tier": "synthetic faults", "benchmark_hash": bench["hash"],
                 "thresholds_from": {"years": p.split.years["threshold"], "cells": "training clients, clean data"},
                 "groups": {}}
    for g in groups:
        cells = group_cells(p, g)
        if not cells.any():
            continue
        out["groups"][g] = {
            "pr_auc": pr_auc(years, cells),
            "by_budget": {str(b): evaluate(years, cells, t, p.grid, p.cell_client, int(p.cfg.evaluation.bootstrap), int(p.cfg.seed))
                          for b, t in thr.items()},
        }
    return out


def summary_row(result: Dict, group: str, budget: float) -> Dict:
    """The handful of numbers shown in tables."""
    g = result["groups"][group]
    r = g["by_budget"][str(float(budget))]
    return {"component": result["component"], "pr_auc": g["pr_auc"], "recall": r["faults"].get("recall"),
            "event_recall": r["faults"].get("event_recall"), "false_per_1000": r["false_alerts"]["per_1000_clean"],
            "protected_flagged": r["protected_extremes"]["flagged_share_of_cell_days"],
            "iou": r["faults"].get("footprint_iou")}
