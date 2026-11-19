"""
backend/app/ml/tier5_health.py
Tier 5: Dynamic Sensor Health Index (SHI) and Degradation Prediction Engine.

Calculates rolling 24-hour health score SHI in [0, 100], applies EMA damping,
estimates daily degradation slope (dSHI/dt), and recommends operator maintenance actions.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


class HealthStatus(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    POOR = "POOR"
    CRITICAL = "CRITICAL"


class DegradationRisk(str, Enum):
    STABLE = "STABLE"
    DEGRADING = "DEGRADING"
    HIGH_RISK = "HIGH_RISK"
    MAINTENANCE_REQUIRED = "MAINTENANCE_REQUIRED"


@dataclass
class HealthRecord:
    timestamp: Any
    is_anomaly: bool
    is_frozen: bool
    is_missing: bool
    temperature: float
    fused_score: float
    fault_type: str


@dataclass
class StationHealthState:
    station_id: str
    window_size: int = 288
    ema_alpha: float = 0.10
    baseline_temp_mean: float = 22.0
    history: deque = field(default_factory=lambda: deque(maxlen=288))
    shi_history: deque = field(default_factory=lambda: deque(maxlen=288))
    current_shi: float = 100.0
    status: HealthStatus = HealthStatus.EXCELLENT
    dominant_fault: str = "NONE"
    degradation_risk: DegradationRisk = DegradationRisk.STABLE
    estimated_hours_to_failure: Optional[float] = None
    recommended_action: str = "All sensor parameters nominal. No maintenance required."


class SensorHealthEngine:
    """Dynamic Sensor Health Index (SHI) and degradation trend tracking engine."""

    def __init__(
        self,
        window_size: int = 288,
        ema_alpha: float = 0.10,
        baseline_temp_mean: float = 22.0,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.window_size = window_size
        self.ema_alpha = ema_alpha
        self.baseline_temp_mean = baseline_temp_mean
        self.weights = weights or {
            "w_A": 0.30,  # Anomaly rate
            "w_F": 0.25,  # Frozen rate
            "w_D": 0.20,  # Drift score
            "w_Q": 0.15,  # Missing rate
            "w_S": 0.10,  # Severity load
        }
        self.stations: Dict[str, StationHealthState] = {}

    def get_or_create_station(self, station_id: str) -> StationHealthState:
        if station_id not in self.stations:
            self.stations[station_id] = StationHealthState(
                station_id=station_id,
                window_size=self.window_size,
                ema_alpha=self.ema_alpha,
                baseline_temp_mean=self.baseline_temp_mean,
            )
        return self.stations[station_id]

    def reset_station(self, station_id: str) -> None:
        if station_id in self.stations:
            del self.stations[station_id]

    def update(
        self,
        station_id: str,
        timestamp: Any,
        is_anomaly: bool,
        is_frozen: bool,
        is_missing: bool,
        temperature: float,
        fused_score: float,
        fault_type: str,
    ) -> Tuple[float, HealthStatus, str, DegradationRisk, Optional[float]]:
        """
        Ingest step, update rolling health window, and compute dynamic SHI.
        """
        state = self.get_or_create_station(station_id)

        # Note: If genuine meteorological extreme, do not count as hardware fault
        is_hw_fault = is_anomaly and (fault_type != "METEOROLOGICAL_EXTREME")

        record = HealthRecord(
            timestamp=timestamp,
            is_anomaly=is_hw_fault,
            is_frozen=is_frozen or (fault_type == "FROZEN"),
            is_missing=is_missing or (fault_type == "DROPOUT"),
            temperature=temperature,
            fused_score=fused_score if is_hw_fault else (0.05 if fault_type == "METEOROLOGICAL_EXTREME" else fused_score),
            fault_type=fault_type,
        )
        state.history.append(record)

        n = len(state.history)
        if n == 0:
            return 100.0, HealthStatus.EXCELLENT, state.recommended_action, DegradationRisk.STABLE, None

        # Calculate penalty components
        anom_count = sum(1 for r in state.history if r.is_anomaly or (r.fused_score >= 0.50 and r.fault_type != "METEOROLOGICAL_EXTREME"))
        frozen_count = sum(1 for r in state.history if r.is_frozen or r.fault_type == "FROZEN")
        missing_count = sum(1 for r in state.history if r.is_missing)
        sev_sum = sum(r.fused_score for r in state.history if r.is_anomaly or r.fused_score >= 0.25)

        valid_temps = [r.temperature for r in state.history if not r.is_missing and not np.isnan(r.temperature)]
        temp_mean = float(np.mean(valid_temps)) if valid_temps else state.baseline_temp_mean

        # If baseline was not explicitly set per station, calibrate from the first 10 steps
        if len(state.history) <= 10 and valid_temps:
            state.baseline_temp_mean = temp_mean

        r_anomaly = anom_count / n
        r_frozen = frozen_count / n
        r_missing = missing_count / n
        s_sev = sev_sum / n
        # Thermal drift penalty applies if there is a systematic shift
        s_drift = float(np.clip(abs(temp_mean - state.baseline_temp_mean) / 5.0, 0.0, 1.0)) if n >= 15 else 0.0

        total_penalty = (
            self.weights["w_A"] * r_anomaly
            + self.weights["w_F"] * r_frozen
            + self.weights["w_D"] * s_drift
            + self.weights["w_Q"] * r_missing
            + self.weights["w_S"] * s_sev
        )
        total_penalty = float(np.clip(total_penalty, 0.0, 1.0))
        raw_shi = 100.0 * (1.0 - total_penalty)

        # EMA smoothing
        if len(state.shi_history) == 0:
            shi = raw_shi
        else:
            shi = self.ema_alpha * raw_shi + (1.0 - self.ema_alpha) * state.current_shi

        shi = float(np.clip(shi, 0.0, 100.0))
        state.current_shi = shi
        state.shi_history.append(shi)

        # Status mapping
        if shi >= 90.0:
            status = HealthStatus.EXCELLENT
        elif shi >= 75.0:
            status = HealthStatus.GOOD
        elif shi >= 50.0:
            status = HealthStatus.DEGRADED
        elif shi >= 25.0:
            status = HealthStatus.POOR
        else:
            status = HealthStatus.CRITICAL
        state.status = status

        # Recommendation synthesis with root-cause specificity
        if status == HealthStatus.EXCELLENT:
            rec = "All sensor parameters within nominal WMO operating thresholds. No maintenance needed."
        elif (r_frozen > 0.05) or (fault_type == "FROZEN"):
            rec = "Inspect sensor probe for mechanical lock, ice accumulation, or stuck ADC register."
        elif (r_missing > 0.05) or (fault_type == "DROPOUT"):
            rec = "Inspect AWS telemetry link, antenna, power supply, and battery voltage levels."
        elif (s_drift > 0.10) or (fault_type == "DRIFT"):
            rec = f"Perform laboratory recalibration; baseline thermal drift of {abs(temp_mean - state.baseline_temp_mean):.1f}°C detected."
        elif r_anomaly > 0.05:
            rec = "Check sensor cable shielding, grounding integrity, and surge protection against electrical noise."
        else:
            rec = "Schedule routine field inspection and sensor diagnostic check."
        state.recommended_action = rec

        # Degradation trend prediction
        risk, hours_to_fail = self._predict_degradation(state)
        state.degradation_risk = risk
        state.estimated_hours_to_failure = hours_to_fail

        return shi, status, rec, risk, hours_to_fail

    def _predict_degradation(self, state: StationHealthState) -> Tuple[DegradationRisk, Optional[float]]:
        if len(state.shi_history) < 24:
            return DegradationRisk.STABLE, None

        y = np.array(list(state.shi_history)[-72:])  # Last up to 6 hours
        x = np.arange(len(y))

        # Linear slope (points per step)
        try:
            slope, _ = np.polyfit(x, y, 1)
        except Exception:
            slope = 0.0

        slope_per_day = slope * 288.0  # Points per 24 hours

        hours_to_fail: Optional[float] = None
        if slope < -1e-4 and state.current_shi > 50.0:
            steps_to_50 = (50.0 - state.current_shi) / slope
            hours_to_fail = max(0.0, float(steps_to_50 * 5.0 / 60.0))

        if state.current_shi < 25.0 or (hours_to_fail is not None and hours_to_fail < 24.0):
            risk = DegradationRisk.MAINTENANCE_REQUIRED
        elif state.current_shi < 50.0 or slope_per_day < -5.0:
            risk = DegradationRisk.HIGH_RISK
        elif slope_per_day < -0.5:
            risk = DegradationRisk.DEGRADING
        else:
            risk = DegradationRisk.STABLE

        return risk, hours_to_fail
