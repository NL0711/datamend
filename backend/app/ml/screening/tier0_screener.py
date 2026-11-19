"""
backend/app/ml/tier0_screener.py
DataMend — In-Memory Tier 0 Deterministic Screening Module.

Executes sub-millisecond physical plausibility and integrity validation at the ingestion boundary:
1. Physical allowable range verification (WMO-No. 8 boundaries).
2. Frozen-value / stuck-sensor zero-variance detection over rolling buffers.
3. Single-step delta rate-of-change spike detection.
4. Null / NaN dropout detection.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Tier0Result:
    """Result emitted by the Tier 0 deterministic screening check."""
    status: str  # "PASS", "SUSPICIOUS", "REJECTED"
    flag: str    # "PASS", "OUT_OF_RANGE", "FROZEN_SENSOR", "STEP_SPIKE", "NULL_DROPOUT"
    violated_param: Optional[str] = None
    reason: Optional[str] = None
    telemetry: Dict[str, Optional[float]] = field(default_factory=dict)


class Tier0Screener:
    """
    In-memory, sub-millisecond screening engine for incoming AWS observations.
    Maintains a small bounded rolling history per station to detect persistence and step anomalies.
    """

    PHYSICAL_LIMITS: Dict[str, Tuple[float, float]] = {
        "temperature": (-10.0, 60.0),
        "pressure": (870.0, 1085.0),
        "humidity": (0.0, 100.0),
    }

    STEP_LIMITS: Dict[str, float] = {
        "temperature": 8.0,   # °C per interval
        "pressure": 6.0,      # hPa per interval
        "humidity": 25.0,     # % per interval
    }

    FROZEN_WINDOW_SIZE: int = 6
    FROZEN_VARIANCE_EPSILON: float = 1e-4

    def __init__(self, window_size: int = 6) -> None:
        self.window_size = window_size
        # station_id -> param_name -> deque of recent values
        self._history: Dict[str, Dict[str, Deque[float]]] = {}

    def _get_history(self, station_id: str, param: str) -> Deque[float]:
        if station_id not in self._history:
            self._history[station_id] = {
                "temperature": deque(maxlen=self.window_size),
                "pressure": deque(maxlen=self.window_size),
                "humidity": deque(maxlen=self.window_size),
            }
        return self._history[station_id][param]

    def reset_station(self, station_id: str) -> None:
        """Clears rolling buffers for a specific station."""
        self._history.pop(station_id, None)

    def screen(self, station_id: str, reading: Dict[str, Any], altitude_m: float = 0.0) -> Tier0Result:
        """
        Screens a single observation record in-memory.

        Parameters
        ----------
        station_id : str
            Unique AWS station identifier.
        reading : dict
            Dictionary containing 'temperature', 'pressure', 'humidity'.
        altitude_m : float, optional
            Station elevation in meters above sea level (default: 0.0).
        """
        temp = reading.get("temperature")
        press = reading.get("pressure")
        hum = reading.get("humidity")

        norm_telemetry = {
            "temperature": float(temp) if temp is not None and not (isinstance(temp, float) and math.isnan(temp)) else None,
            "pressure": float(press) if press is not None and not (isinstance(press, float) and math.isnan(press)) else None,
            "humidity": float(hum) if hum is not None and not (isinstance(hum, float) and math.isnan(hum)) else None,
        }

        # Check 1: Null / NaN Dropout
        for param, val in norm_telemetry.items():
            if val is None:
                return Tier0Result(
                    status="REJECTED",
                    flag="NULL_DROPOUT",
                    violated_param=param,
                    reason=f"Missing or NaN reading detected for {param}.",
                    telemetry=norm_telemetry,
                )

        # Check 2: Physical Range Boundaries
        for param, (low, high) in self.PHYSICAL_LIMITS.items():
            val = norm_telemetry[param]
            assert val is not None
            actual_low = low
            if param == "pressure" and altitude_m > 500:
                actual_low = max(500.0, 870.0 - 0.1 * altitude_m)
            if val < actual_low or val > high:
                return Tier0Result(
                    status="REJECTED",
                    flag="OUT_OF_RANGE",
                    violated_param=param,
                    reason=f"{param.capitalize()} {val} outside physically allowable range [{actual_low}, {high}].",
                    telemetry=norm_telemetry,
                )

        # Check 3: Step Delta Spike & Frozen Variance
        for param, val in norm_telemetry.items():
            assert val is not None
            hist = self._get_history(station_id, param)

            # Check single-step spike against immediately preceding reading
            if len(hist) >= 1:
                last_val = hist[-1]
                delta = abs(val - last_val)
                limit = self.STEP_LIMITS[param]
                if delta > limit:
                    hist.append(val)
                    return Tier0Result(
                        status="SUSPICIOUS",
                        flag="STEP_SPIKE",
                        violated_param=param,
                        reason=f"{param.capitalize()} single-step change of {round(delta, 2)} exceeds limit {limit}.",
                        telemetry=norm_telemetry,
                    )

            # Check frozen / stuck sensor (zero variance over window)
            if len(hist) >= (self.window_size - 1):
                sample = list(hist) + [val]
                mean_val = sum(sample) / len(sample)
                variance = sum((x - mean_val) ** 2 for x in sample) / len(sample)
                if variance < self.FROZEN_VARIANCE_EPSILON:
                    hist.append(val)
                    return Tier0Result(
                        status="SUSPICIOUS",
                        flag="FROZEN_SENSOR",
                        violated_param=param,
                        reason=f"{param.capitalize()} values frozen across {len(sample)} consecutive readings (variance={variance:.2e}).",
                        telemetry=norm_telemetry,
                    )

            hist.append(val)

        return Tier0Result(
            status="PASS",
            flag="PASS",
            reason="Observation satisfies all Tier 0 deterministic boundaries.",
            telemetry=norm_telemetry,
        )


# Global singleton screener instance
tier0_screener = Tier0Screener()
