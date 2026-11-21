"""Rolling windows for the Keras reconstruction scorer: per (station, variable) the last 288 values at the source's native cadence.

No resampling and no filling: a missing or non-finite value empties that variable's window, so a window never spans a gap. A full window is
scaled with a trailing z-score of its own 288 values (``assumed``: the model's training mean and standard deviation are not shipped).
"""
from __future__ import annotations

import math
from collections import deque
from typing import Deque, Dict, List, Optional, Sequence, Tuple

WINDOW = 288
STD_FLOOR = 1e-6
VARIABLES = ("temperature", "pressure", "humidity")
SCALING = "trailing z-score (assumed)"
MAX_STATIONS = 5000


def finite(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def zscore(values: Sequence[float]) -> List[float]:
    n = len(values)
    mean = sum(values) / n
    std = math.sqrt(sum((x - mean) ** 2 for x in values) / n)
    std = max(std, STD_FLOOR)
    return [(x - mean) / std for x in values]


class WindowStore:
    def __init__(self, size: int = WINDOW) -> None:
        self.size = size
        self._buf: Dict[Tuple[str, str], Deque[float]] = {}
        self._seen: Dict[str, None] = {}      # insertion ordered, bounded

    def __contains__(self, station_id: str) -> bool:
        return station_id in self._seen

    def _mark(self, station_id: str) -> None:
        self._seen[station_id] = None
        while len(self._seen) > MAX_STATIONS:
            old = next(iter(self._seen))
            del self._seen[old]
            for v in VARIABLES:
                self._buf.pop((old, v), None)

    def push(self, station_id: str, variable: str, value: Optional[float]) -> int:
        """Add a value (a missing or non-finite one resets the window); return how many readings the window now holds."""
        buf = self._buf.setdefault((station_id, variable), deque(maxlen=self.size))
        if finite(value):
            buf.append(float(value))      # type: ignore[arg-type]
        else:
            buf.clear()
        return len(buf)

    def count(self, station_id: str, variable: str) -> int:
        return len(self._buf.get((station_id, variable), ()))

    def seed(self, station_id: str, rows: Sequence[Dict[str, Optional[float]]]) -> None:
        """First sight of a station: replay its stored earlier readings, oldest first (a gap in them resets the window like a live gap)."""
        self._mark(station_id)
        for row in rows:
            for v in VARIABLES:
                self.push(station_id, v, row.get(v))

    def mark(self, station_id: str) -> None:
        self._mark(station_id)

    def scaled(self, station_id: str, variable: str) -> Optional[List[float]]:
        buf = self._buf.get((station_id, variable))
        if buf is None or len(buf) < self.size:
            return None
        return zscore(list(buf))

    def warmup_reason(self, station_id: str, variable: str) -> str:
        return f"not run: need {self.size} readings, have {self.count(station_id, variable)}"
