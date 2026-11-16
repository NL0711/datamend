"""Test-only detector so harness/plumbing tests do not depend on a trained model."""

import numpy as np

from detectors.base import AnomalyDetector


class ZScoreDetector(AnomalyDetector):
    """Per-row max robust z-score across columns, squashed into [0, 1]."""

    def detect(self, data):
        x = np.asarray(data, dtype=float)
        if x.ndim == 1:
            x = x.reshape(-1, 1)
        med = np.median(x, axis=0)
        mad = np.median(np.abs(x - med), axis=0) * 1.4826 + 1e-9
        return np.clip(np.max(np.abs(x - med) / mad, axis=1) / 8.0, 0.0, 1.0)
