"""Hyper-parameter sweeps over one prepared dataset. Selection uses *validation* years only."""

from __future__ import annotations

import itertools
import json
import random
from pathlib import Path
from typing import Dict, List, Optional

from training.pipeline import prepare, train_prepared
from training.presets import make_config


def sweep(
    data_dir: str | Path,
    out_root: str | Path,
    grid: Dict[str, list],
    base: str = "base",
    epochs: int = 5,
    trials: Optional[int] = None,
    seed: int = 0,
    max_train_years: Optional[int] = None,
    log=print,
) -> List[dict]:
    """Grid (or random subset of ``trials``) over ``grid`` = {config_field: [values]}.

    Each trial is saved under ``out_root/trial_NNN`` and logged to ``results.jsonl``;
    ``best.json`` points at the trial with the highest validation PR-AUC. Test metrics are
    recorded but never used to choose.
    """
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    keys = list(grid)
    combos = list(itertools.product(*grid.values()))
    if trials and trials < len(combos):
        combos = random.Random(seed).sample(combos, trials)
    # coarse_blocks fix the prepared data, so they cannot be swept (train_prepared checks this)
    prep = prepare(data_dir, max_train_years=max_train_years, coarse_blocks=make_config(base).coarse_blocks, log=log)
    rows: List[dict] = []
    for i, combo in enumerate(combos):
        overrides = dict(zip(keys, combo))
        log(f"--- trial {i + 1}/{len(combos)}: {overrides}")
        res = train_prepared(prep, make_config(base, **overrides), epochs, out_root / f"trial_{i:03d}", log=log)
        row = {"trial": i, "overrides": overrides,
               "val_pr_auc": res["val"]["primary"]["pr_auc"], "val_roc_auc": res["val"]["primary"]["roc_auc"],
               "test_pr_auc": res["test"]["primary"]["pr_auc"], "test_roc_auc": res["test"]["primary"]["roc_auc"]}
        rows.append(row)
        with open(out_root / "results.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
    best = max(rows, key=lambda r: r["val_pr_auc"])
    (out_root / "best.json").write_text(json.dumps(best, indent=2))
    log(f"best trial: {best}")
    return rows
