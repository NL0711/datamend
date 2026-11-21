"""Score calibration: robust-standardize each stream on clean data, fuse, pick a threshold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

from training.sampler import WindowSampler


@dataclass
class Calibration:
    stats: Dict[str, Tuple[float, float]]  # stream -> (median, scale) on clean validation windows
    threshold: float                       # q-th percentile of the fused clean score

    def fuse(self, streams: Dict[str, np.ndarray]) -> np.ndarray:
        """Mean of robust z-scores across streams (clipped so one stream cannot dominate)."""
        zs = [np.clip((streams[k] - m) / s, -10, 200) for k, (m, s) in self.stats.items()]
        return np.mean(zs, axis=0)

    @classmethod
    def fit(cls, trainer, clean: WindowSampler, q: float = 99.0, n: int = 2048) -> "Calibration":
        streams = trainer.score(clean.batch(n, 0.0))
        stats = {}
        for k, v in streams.items():
            med = float(np.median(v))
            stats[k] = (med, max(float(1.4826 * np.median(np.abs(v - med))), 1e-4))
        cal = cls(stats, 0.0)
        cal.threshold = float(np.percentile(cal.fuse(streams), q))
        return cal

    def to_dict(self) -> dict:
        return {"stats": {k: list(v) for k, v in self.stats.items()}, "threshold": self.threshold}

    @classmethod
    def from_dict(cls, d: dict) -> "Calibration":
        return cls({k: (v[0], v[1]) for k, v in d["stats"].items()}, d["threshold"])
