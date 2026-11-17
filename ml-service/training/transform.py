"""Rainfall <-> model-space transform: log1p(mm) / scale, with scale fit on train data only."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RainfallTransform:
    scale: float  # log1p of the training wet-day quantile; maps typical heavy rain to ~1

    @classmethod
    def fit(cls, mm: np.ndarray, wet_quantile: float = 99.9) -> "RainfallTransform":
        wet = mm[np.isfinite(mm) & (mm > 0.1)]
        if wet.size == 0:
            raise ValueError("No wet values to fit the transform on")
        return cls(scale=float(np.log1p(np.percentile(wet, wet_quantile))))

    def forward(self, mm: np.ndarray) -> np.ndarray:
        """Negative inputs are clipped to 0; the rule engine owns sign errors."""
        return np.log1p(np.clip(mm, 0, None)) / self.scale

    def inverse(self, z: np.ndarray) -> np.ndarray:
        return np.expm1(np.asarray(z) * self.scale)

    def to_dict(self) -> dict:
        return {"scale": self.scale}

    @classmethod
    def from_dict(cls, d: dict) -> "RainfallTransform":
        return cls(scale=float(d["scale"]))
