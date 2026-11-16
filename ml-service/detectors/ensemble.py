"""Late-fusion ensemble over independently trained detectors (different granularities, histories, windows).

Use this when sources cannot be aligned into one model (hourly stations vs. daily grids, a
per-city fine-tuned model vs. the national model, different training histories). Use the
``msnet`` architecture instead when the sources are aligned and daily.

Each member keeps its own calibration. Scores are compared as the ratio to the member's own
threshold, so members with different score units are commensurable (1.0 = at threshold).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

from detectors.base import AnomalyDetector
from detectors.rainfall_ae import RainfallAEDetector
from detectors.scoring import api_score


class EnsembleDetector(AnomalyDetector):
    def __init__(self, members: Sequence[Tuple[str, RainfallAEDetector, float]]):
        """``members``: (name, detector, weight). Weights are normalized."""
        if not members:
            raise ValueError("EnsembleDetector needs at least one member")
        self.members = list(members)
        total = sum(w for _, _, w in members)
        self.weights = {name: w / total for name, _, w in members}

    def detect_detailed(self, data: Any, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Same ``context`` as the members; each member uses the entries it was trained with and
        masks the rest. Returns the weighted ``scores`` (1.0 = threshold), ``flags``, ``votes``
        (how many members flag each point) and per-member ``member_scores``."""
        per = {name: det.detect_detailed(data, context) for name, det, _ in self.members}
        ratio = {name: np.maximum(r["scores"], 0.0) / max(abs(det.threshold), 1e-6)
                 for (name, det, _), r in zip(self.members, per.values())}
        scores = sum(self.weights[n] * ratio[n] for n in ratio)
        return {
            "scores": scores,
            "flags": scores >= 1.0,
            "votes": np.sum([r["flags"] for r in per.values()], axis=0),
            "member_scores": ratio,
        }

    def detect(self, data: Any, context: Optional[Dict[str, Any]] = None) -> np.ndarray:
        x = np.asarray(data, dtype=np.float64)
        if x.ndim == 2 and x.shape[1] > 1:
            if context:
                raise ValueError("context is only supported for a single series")
            raw = np.max([self.detect_detailed(x[:, j])["scores"] for j in range(x.shape[1])], axis=0)
        else:
            raw = self.detect_detailed(x.ravel(), context)["scores"]
        return api_score(raw, 1.0)
