"""Map calibrated detector scores onto the API's [0, 1] scale."""

from __future__ import annotations

import numpy as np

_LOGIT_08 = float(np.log(0.8 / 0.2))


def api_score(score: np.ndarray, threshold: float) -> np.ndarray:
    """Monotone map to (0, 1) with ``score == threshold`` -> 0.8 (the API's default threshold).

    So a point is flagged at the default API threshold exactly when the model's own calibrated
    threshold is crossed; lowering the API threshold makes it more sensitive.
    """
    z = _LOGIT_08 + (np.asarray(score, dtype=np.float64) - threshold) / max(abs(threshold) / 4.0, 1e-6)
    return (1.0 / (1.0 + np.exp(-np.clip(z, -50, 50)))).astype(np.float64)
