"""Point-wise, threshold-free evaluation on injected anomalies (no point-adjust F1)."""

from __future__ import annotations

from typing import Dict

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from training.calibration import Calibration
from training.injection import KINDS
from training.sampler import WindowSampler
from training.trainer import LocalTrainer


def _auc(y: np.ndarray, s: np.ndarray) -> Dict[str, float]:
    if not y.any() or y.all():
        return {"roc_auc": float("nan"), "pr_auc": float("nan")}
    return {"roc_auc": float(roc_auc_score(y, s)), "pr_auc": float(average_precision_score(y, s))}


def evaluate(trainer: LocalTrainer, test: WindowSampler, cal: Calibration, n: int = 4096, seed: int = 0) -> Dict:
    """Score a half-corrupted test set. Reports every score stream, the fused primary score,
    a no-model baseline (disagreement with climatology + neighbours), and per-kind ROC-AUC with a
    ``seen`` flag (False = that anomaly kind was held out of training)."""
    test.rng = np.random.default_rng(seed)
    b = test.batch(n, inject_rate=0.5)
    streams = trainer.score(b)
    fused = cal.fuse(streams)
    tf = trainer.transform
    x, nbr, clim = (tf.forward(a) for a in (b.x_mm[..., 0], b.x_mm[..., 1], b.aux_mm[..., 1]))
    baseline = np.abs(x - clim) + np.abs(x - nbr)

    y = b.labels.ravel()
    scores = {"fused": fused, **streams, "baseline": baseline}
    pred = fused.ravel() >= cal.threshold
    rand = np.random.default_rng(seed + 1).random(y.size)
    out = {
        "prevalence": float(y.mean()),
        "random_pr_auc": float(average_precision_score(y, rand)) if y.any() else float("nan"),
        "scores": {k: _auc(y, v.ravel()) for k, v in scores.items()},
        "primary": {
            **_auc(y, fused.ravel()),
            "precision": float((pred & y).sum() / max(pred.sum(), 1)),
            "recall": float((pred & y).sum() / max(y.sum(), 1)),
            "threshold": cal.threshold,
        },
        "per_kind_roc_auc": {},
    }
    if trainer.config.arch == "msnet":
        # Graceful degradation: score the same windows with sources removed, one at a time and all.
        names, k = [sp.name for sp in test.specs], len(test.specs)
        variants = {"all": [True] * k, "none": [False] * k,
                    **{f"drop:{nm}": [j != i for j in range(k)] for i, nm in enumerate(names)}}
        out["source_ablation"] = {
            tag: _auc(y, cal.fuse(trainer.score(b.with_sources(keep))).ravel()) for tag, keep in variants.items()}
    if trainer.config.arch == "scalenet" and not trainer.config.single_scale and len(trainer.config.scales) > 1:
        # Per-scale contribution: mask one aggregation scale at a time out of the scale fusion.
        out["scale_ablation"] = {
            "all": _auc(y, fused.ravel()),
            **{f"drop_scale:{sc}": _auc(y, cal.fuse(trainer.score(b, drop_scales=[i])).ravel())
               for i, sc in enumerate(trainer.config.scales)}}
        out["scale_attention_mean"] = dict(zip(map(str, trainer.config.scales),
                                               trainer.scale_attention(b).mean((0, 1)).tolist()))
    seen = set(trainer.config.train_kinds or KINDS)
    clean = b.kind == -1
    for k, name in enumerate(KINDS):
        rows = clean | (b.kind == k)
        if (b.kind == k).sum() >= 5:
            r = _auc(b.labels[rows].ravel(), fused[rows].ravel())["roc_auc"]
            if not np.isnan(r):
                out["per_kind_roc_auc"][name] = {"roc_auc": r, "seen": name in seen}
    return out
