"""Gate 3: the untrained scores (rules, slow, neighbour-average baseline) and their validation metrics."""

from __future__ import annotations

import logging
from typing import Dict, Sequence

from qc import paths
from qc.evaluate import compute_scores, evaluate_component, score_store
from qc.neighbours import ring_index
from qc.prepare import Prepared
from qc.runs import RunDir, write_json
from qc.splits import audit_split
from qc.untrained import SlowReference, fit_slow_reference, neighbour_score, rules_score, slow_score

log = logging.getLogger(__name__)
UNTRAINED = ("rules", "slow", "neighbour_baseline")


def slow_reference(p: Prepared) -> SlowReference:
    """Fitted once on training years and cached next to the split manifest."""
    path = paths.work_dir(p.cfg) / "splits" / f"slow_reference_{p.manifest['hash']}.npz"
    windows = [int(w) for w in p.cfg.components.slow.windows]
    if path.is_file():
        ref = SlowReference.load(path)
        if list(ref.years) == p.split.years["train"] and list(ref.windows) == windows:
            return ref
    series, year, doy = p.series(p.split.years["train"])
    ref = fit_slow_reference(series, year, doy, p.split, windows)
    ref.save(path)
    return ref


def score_functions(p: Prepared) -> Dict:
    c = p.cfg.components
    audit_split(p.split, reach_cells=int(max(c.slow.ring_outer, c.neighbour_baseline.radius)))
    slow_ring = ring_index(p.grid, c.hidden_radius, c.slow.ring_outer)
    nb_ring = ring_index(p.grid, c.hidden_radius, c.neighbour_baseline.radius)
    ref = slow_reference(p)
    return {
        "rules": lambda b: rules_score(b, p.stats),
        "slow": lambda b: slow_score(b, ref, slow_ring),
        "neighbour_baseline": lambda b: neighbour_score(b, nb_ring),
    }


def run_untrained(p: Prepared, splits: Sequence[str] = ("val",), overwrite: bool = False, pinned: bool = True) -> Dict:
    run = RunDir(paths.out_dir(p.cfg) / str(p.cfg.name), "untrained")
    run.start(p.cfg, int(p.cfg.seed), {"split_manifest_hash": p.manifest["hash"], "components": list(UNTRAINED)})
    store = score_store(p)
    fns = score_functions(p)
    results = {}
    for name in UNTRAINED:
        compute_scores(p, name, fns[name], splits, store, overwrite)
        for split in splits:
            groups = ("seen",) if split == "val" else ("seen", "unseen")
            res = evaluate_component(p, name, split, p.cfg.evaluation.budgets, groups, store, pinned)
            write_json(run.file("metrics", f"{name}_{split}.json"), res)
            results[(name, split)] = res
    return results
