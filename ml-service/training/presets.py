"""Named configs. ``smoke`` verifies wiring on CPU; ``base`` / ``large`` are for a GPU run."""

from __future__ import annotations

from typing import Any

from training.trainer import TrainConfig

PRESETS = {
    "smoke": dict(window=20, hidden=16, layers=1, attn_layers=0, steps_per_epoch=10,
                  batch_size=64, warmup_steps=5, prefetch=False),
    "lstm_baseline": dict(arch="lstm_ae", window=30, hidden=64, steps_per_epoch=200, batch_size=256),
    "scalenet": dict(arch="scalenet", scales=[1, 5, 30], patch=3, window=90),
    "scalenet_single": dict(arch="scalenet", scales=[1], single_scale=True, patch=3, window=90),
    "scalenet_large": dict(arch="scalenet", scales=[1, 5, 30], patch=5, window=90, hidden=256, layers=3,
                           attn_layers=2, heads=8, batch_size=1024, steps_per_epoch=1000, lr=1e-3, amp=True),
    "multiscale": dict(arch="msnet", coarse_blocks=[4, 8], source_dropout=0.3),
    "base": dict(),  # TrainConfig defaults: hidden 128, 2 BiLSTM + 1 attn layer, window 60
    "multiscale_large": dict(arch="msnet", coarse_blocks=[4, 8], source_dropout=0.3, window=90, hidden=256,
                             layers=3, attn_layers=2, heads=8, batch_size=1024, steps_per_epoch=1000,
                             lr=1e-3, amp=True),
    "large": dict(window=90, hidden=256, layers=3, attn_layers=2, heads=8, batch_size=1024,
                  steps_per_epoch=1000, lr=1e-3, amp=True),
    "xlarge": dict(window=120, hidden=384, layers=4, attn_layers=4, heads=8, batch_size=1024,
                   steps_per_epoch=2000, lr=7e-4, amp=True),
}


def make_config(preset: str = "base", **overrides: Any) -> TrainConfig:
    if preset not in PRESETS:
        raise KeyError(f"Unknown preset {preset!r}; choose from {sorted(PRESETS)}")
    return TrainConfig(**{**PRESETS[preset], **overrides})


# --- ensemble presets -------------------------------------------------------------------------------
# Member preset names; every member is trained on the same prepared data. ``ablation`` members are trained
# and evaluated standalone (single-scale vs multi-scale) and are NOT part of the fused ensemble.
SMOKE_SIZE = dict(window=40, hidden=16, layers=1, attn_layers=0, steps_per_epoch=4, batch_size=32,
                  warmup_steps=2, prefetch=False)

ENSEMBLE_PRESETS = {
    "smoke": dict(members=["lstm_baseline", "base", "scalenet"], ablation=["scalenet_single"], size=SMOKE_SIZE,
                  eval_windows=256, cal_batches=2, cal_batch_size=64),
    "ensemble": dict(members=["lstm_baseline", "base", "scalenet"], ablation=["scalenet_single"], size={},
                     eval_windows=4096, cal_batches=16, cal_batch_size=512),
    "ensemble_large": dict(members=["lstm_baseline", "large", "scalenet_large"], ablation=["scalenet_single"], size={},
                           eval_windows=8192, cal_batches=32, cal_batch_size=1024),
}
