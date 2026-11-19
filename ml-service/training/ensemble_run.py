"""Train the member models, build the label-free fusion pipeline, and evaluate (all seeds reported).

Per seed: train lstm_baseline / RainNet / multi-scale (and ablation members), fit branch normalizers on clean
**training-year** windows, calibrate the threshold on clean **validation-year** windows, then evaluate on test
windows with injected anomalies. Fusion variants (each rule, each leave-one-branch-out, each branch alone) reuse
cached branch scores, so ablating fusion needs no retraining.

Nothing here is a result: it only produces them when run on the training machine.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from ensemble.branches import RuleBranch, StatBranch, TrainerBranch
from ensemble.fusion import RULES, calibrate_threshold
from ensemble.pipeline import FusionConfig, FusionPipeline
from evaluation.rainfall_metrics import (ablation_variants, breakdown, region_labels, run_seeds, season_labels,
                                         window_metrics)
from training import artifact
from training.evaluate import evaluate
from training.injection import KINDS
from training.leakage import assert_no_leakage
from training.pipeline import Member, fit_member, make_sampler, prepare
from training.presets import ENSEMBLE_PRESETS, make_config

log = logging.getLogger(__name__)
HEADLINE = ("pr_auc", "random_pr_auc", "aff_f1", "event_f1", "f1", "fpr_clean")


def _branches(members: Dict[str, Member], cfgs: Dict[str, object], prep, seed: int) -> list:
    """rule + stat + one branch per model stream. The supervised head is a single branch (from the multi-scale
    model if present), never a stacking meta-model."""
    br: list = [RuleBranch()]
    if prep.stat_baseline is not None:
        br.append(StatBranch(prep.stat_baseline))
    head_from = "scalenet" if "scalenet" in members else next((n for n, c in cfgs.items() if c.arch != "lstm_ae"), None)
    for name, m in members.items():
        art = artifact.Artifact(m.trainer, m.cal, {"member": name})
        arch = cfgs[name].arch
        if arch == "lstm_ae":
            br.append(TrainerBranch("lstm_baseline", art, "recon", "rank", name))
            continue
        label = {"rainnet": "rainnet", "scalenet": "multiscale", "msnet": "msnet"}[arch]
        br.append(TrainerBranch(label, art, "nll", "likelihood", name))
        if name == head_from:
            br.append(TrainerBranch("supervised_head", art, "head", "rank", name))
    return br


def _concat(parts: List[Dict[str, np.ndarray]]) -> Dict[str, np.ndarray]:
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def _flat(m: dict) -> dict:
    return {k: v for k, v in m.items() if isinstance(v, (int, float))}


def run_ensemble(
    data_dir: str | Path,
    out_dir: str | Path,
    preset: str = "smoke",
    fusion: str = "mean_rank",
    scales: Optional[Sequence[int]] = None,
    single_scale: bool = False,
    seeds: Sequence[int] = (0,),
    epochs: int = 1,
    max_train_years: Optional[int] = None,
    elevation: Optional[str] = None,
    use_stations: bool = False,
    threshold_method: str = "fpr",
    target_fpr: float = 0.01,
    owa_orness: float = 0.7,
    holdout: Optional[Sequence[str]] = None,
    log=print,
) -> dict:
    spec = ENSEMBLE_PRESETS[preset]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    common = {"use_elevation": elevation is not None, "use_stations": use_stations}
    if holdout:
        common["train_kinds"] = [k for k in KINDS if k not in set(holdout)]
    prep = prepare(data_dir, max_train_years=max_train_years, elevation_path=elevation, build_stat=True, log=log)
    details: Dict[int, dict] = {}

    def one_seed(seed: int) -> dict:
        names = list(spec["members"])
        cfgs = {n: make_config(n, **spec["size"], **common, seed=seed) for n in names + spec["ablation"]}
        window = max(c.window for c in cfgs.values())
        patch = max([c.patch for c in cfgs.values() if c.arch == "scalenet"] or [0])
        for n, c in cfgs.items():           # one common window/patch so a single Batch feeds every member
            c.window = window
            if c.arch == "scalenet":
                c.patch = patch
                if scales and not c.single_scale:
                    c.scales = list(scales)
                if single_scale and n == "scalenet":
                    c.single_scale = True
        fitted = {n: fit_member(prep, c, epochs, log) for n, c in cfgs.items()}
        d: dict = {"members": {n: evaluate(m.trainer, m.test_s, m.cal, spec["eval_windows"], seed=0)
                               for n, m in fitted.items()}}
        fused_members = {n: fitted[n] for n in names}
        pipe = FusionPipeline(_branches(fused_members, cfgs, prep, seed),
                              FusionConfig(fusion, owa_orness, threshold_method, target_fpr))

        ref_cfg = next(c for n, c in cfgs.items() if c.arch == "scalenet") if patch else cfgs[names[0]]
        sampler = lambda years, off: make_sampler(prep, ref_cfg, years, seed + off, patch=patch)
        cal_s, val_s, test_s = sampler(prep.split.train, 100), sampler(prep.split.val, 101), sampler(prep.split.test, 102)
        prep.provenance.update(rank_reference=list(prep.split.train), threshold=list(prep.split.val))
        assert_no_leakage(prep.provenance, prep.split)

        n = spec["cal_batch_size"]
        pipe.fit_normalizers([cal_s.batch(n, 0.0) for _ in range(spec["cal_batches"])])        # TRAIN years, clean
        val_batches = [val_s.batch(n, 0.0) for _ in range(spec["cal_batches"])]               # VAL years, clean
        pipe.fit_threshold(val_batches)

        tb = test_s.batch(spec["eval_windows"], inject_rate=0.5)
        t_ranks, t_probs = pipe.normalized(tb)
        v_norm = [pipe.normalized(b) for b in val_batches]
        v_ranks, v_probs = _concat([r for r, _ in v_norm]), _concat([p for _, p in v_norm])
        v_valid = np.concatenate([b.valid for b in val_batches])
        y = tb.labels

        def metrics_for(rule: str, drop=(), only=None) -> dict:
            vr = {k: v for k, v in v_ranks.items() if (only is None or k == only)}
            vp = {k: v for k, v in v_probs.items() if (only is None or k == only)}
            tr = {k: v for k, v in t_ranks.items() if (only is None or k == only)}
            tp = {k: v for k, v in t_probs.items() if (only is None or k == only)}
            cal = calibrate_threshold(pipe.fuse_normalized(vr, vp, rule, drop), v_valid, threshold_method, target_fpr)
            fused = pipe.fuse_normalized(tr, tp, rule, drop)
            m = window_metrics(y, fused, fused >= cal["threshold"], seed=seed)
            m["threshold"], m["val_achieved_fpr"] = cal["threshold"], cal["achieved_fpr"]
            return m

        active = list(t_ranks)
        d["fusion_variants"] = [
            {**v, "metrics": metrics_for(v["rule"], (v["drop_branch"],) if v["drop_branch"] else ())}
            for v in ablation_variants(active, RULES, ("multi_scale",))]
        d["branch_alone"] = {b: metrics_for("mean_rank", only=b) for b in active}
        main = metrics_for(fusion)
        d["main"] = main
        fused = pipe.fuse_normalized(t_ranks, t_probs, fusion)
        pred = fused >= main["threshold"]
        kind_names = np.array(["clean"] + list(KINDS), dtype=object)[tb.kind + 1]
        d["by_kind"] = breakdown(y, fused, pred, kind_names, seed)
        d["held_out_kinds"] = [k for k in KINDS if holdout and k in holdout]
        d["by_season"] = breakdown(y, fused, pred, season_labels(tb.doy), seed)
        d["by_region"] = breakdown(y, fused, pred, region_labels(tb.static[:, 0, 2]), seed)
        pipe.save(out / f"seed_{seed}")
        details[seed] = d
        return {k: main[k] for k in HEADLINE}

    result = run_seeds(one_seed, list(seeds))      # every seed reported; there is no best-of-N selection
    result["details"] = {str(k): v for k, v in details.items()}
    result["provenance"] = {k: v for k, v in prep.provenance.items()}
    (out / "results.json").write_text(json.dumps(result, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    return result
