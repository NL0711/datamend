"""Per (station, variable) flag threshold from that station's own CLEAN reconstruction errors.

Clean = the checks' verdict for the reading was OK and the model did not flag it. The threshold is the empirical quantile ``1 - budget`` of
EARLIER clean errors only (the caller reads it before adding the current error). Budget and minimum count are config values, ``assumed``.
Until enough clean errors exist there is no threshold and nothing is flagged.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Deque, Dict, Optional, Tuple

MAX_CLEAN = 5000


class ThresholdStore:
    def __init__(self, budget: float = 0.001, min_clean: int = 1000, max_clean: int = MAX_CLEAN) -> None:
        self.budget = budget
        self.min_clean = min_clean
        self.max_clean = max_clean
        self._errors: Dict[Tuple[str, str], Deque[float]] = {}

    def count(self, station_id: str, variable: str) -> int:
        return len(self._errors.get((station_id, variable), ()))

    def add_clean(self, station_id: str, variable: str, error: float) -> None:
        self._errors.setdefault((station_id, variable), deque(maxlen=self.max_clean)).append(float(error))

    def threshold(self, station_id: str, variable: str) -> Optional[float]:
        errs = self._errors.get((station_id, variable))
        if not errs or len(errs) < max(1, self.min_clean):
            return None
        ordered = sorted(errs)
        idx = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * (1.0 - self.budget)) - 1))
        return ordered[idx]

    def reason(self, station_id: str, variable: str) -> str:
        return f"threshold not set: need {self.min_clean} clean scores, have {self.count(station_id, variable)}"
