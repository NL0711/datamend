"""
backend/app/health/tracker.py
DataMend — Tier 3.5: Sensor Health & Predictive Maintenance Tracker.

Synthesizes:
1. akshitbuilds/agent4/degradation_tracker.py:
   - Recent anomaly rate (last 10 events) vs baseline anomaly rate (prior 30 events).
   - Trend slope via linear fit across history.
   - Frozen-streak persistence and escalation.
2. datamend/ml/tier5_health.py:
   - Dynamic Sensor Health Index (SHI in [0, 100]) with EMA smoothing (alpha=0.10).
   - Multi-component penalty formulation: anomaly rate, frozen rate, drift score, dropouts, and severity.
   - Remaining Useful Life (RUL in hours/days) linear projection to failure threshold (SHI < 50).
   - Health status (EXCELLENT, GOOD, DEGRADED, POOR, CRITICAL) and actionable maintenance advisories.
3. Ashwina-Pal/datamend/health.py:
   - Per-sensor channel tracking (Temperature, Pressure, Humidity) alongside station aggregate.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ChannelHealthState:
    """Degradation tracking state for a specific sensor channel."""
    channel: str
    recent_history: deque = field(default_factory=lambda: deque(maxlen=200))
    current_shi: float = 100.0
    status: str = "EXCELLENT"
    degradation_risk: str = "STABLE"
    recent_anomaly_rate: float = 0.0
    baseline_anomaly_rate: float = 0.0
    trend_slope: float = 0.0
    frozen_streak: int = 0
    hours_to_failure: Optional[float] = None
    recommended_action: str = "Nominal operation. No maintenance required."


@dataclass
class StationHealthSnapshot:
    """Consolidated predictive health diagnostic for an AWS station."""
    station_id: str
    timestamp: datetime
    overall_health_score: float
    health_status: str
    degradation_risk: str
    anomaly_rate_30d: float
    drift_score: float
    data_quality_score: float
    estimated_hours_to_failure: Optional[float]
    recommended_action: str
    channel_health: Dict[str, Dict[str, Any]]


class PredictiveHealthTracker:
    """
    Tracks micro-failures and calibration drift over rolling observation windows
    to forecast sensor end-of-life before complete hardware breakdown.
    """

    RECENT_WINDOW = 10
    BASELINE_WINDOW = 30
    EMA_ALPHA = 0.10

    def __init__(self) -> None:
        # station_id -> channel_name -> ChannelHealthState
        self._stations: Dict[str, Dict[str, ChannelHealthState]] = defaultdict(dict)
        self._shi_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=288))

    def _get_channel_state(self, station_id: str, channel: str) -> ChannelHealthState:
        station_dict = self._stations[station_id]
        if channel not in station_dict:
            station_dict[channel] = ChannelHealthState(channel=channel)
        return station_dict[channel]

    def record_reading(
        self,
        station_id: str,
        timestamp: datetime,
        predicted_class: str,
        anomaly_score: float,
        is_fault: bool,
        primary_channel: str = "temperature_c",
        residual_val: float = 0.0,
    ) -> StationHealthSnapshot:
        """
        Updates sensor state with incoming diagnostic tick and emits updated health forecast.
        """
        # Exclude genuine meteorological events from hardware penalties
        is_hw_fault = is_fault and (predicted_class != "GENUINE_WEATHER_EVENT")
        is_frozen = (predicted_class == "FROZEN_SENSOR")
        is_dropout = (predicted_class == "COMMUNICATION_DROPOUT")
        is_drift = (predicted_class == "CALIBRATION_DRIFT")

        channels = ["temperature_c", "pressure_hpa", "humidity_pct"]

        for ch in channels:
            state = self._get_channel_state(station_id, ch)
            affects_this_ch = (ch == primary_channel) or (predicted_class in ("POWER_FLUCTUATION", "COMMUNICATION_DROPOUT"))

            fault_flag = is_hw_fault and affects_this_ch
            frozen_flag = is_frozen and affects_this_ch

            if frozen_flag:
                state.frozen_streak += 1
            else:
                state.frozen_streak = 0

            state.recent_history.append((timestamp, fault_flag, predicted_class, state.frozen_streak, residual_val))

            # Evaluate channel health
            self._update_channel_metrics(state, is_drift, affects_this_ch, residual_val)

        # Aggregate station-level overall health
        return self._build_station_snapshot(station_id, timestamp)

    def _update_channel_metrics(
        self,
        state: ChannelHealthState,
        is_drift: bool,
        affects_this_ch: bool,
        residual_val: float,
    ) -> None:
        hist = list(state.recent_history)
        n = len(hist)
        if n == 0:
            return

        flags = np.array([1.0 if h[1] else 0.0 for h in hist], dtype=float)

        # Recent anomaly rate (last 10) vs baseline rate (prior 30)
        recent_slice = flags[-self.RECENT_WINDOW:]
        recent_rate = float(recent_slice.mean()) if recent_slice.size else 0.0

        baseline_slice = flags[-(self.RECENT_WINDOW + self.BASELINE_WINDOW):-self.RECENT_WINDOW]
        baseline_rate = float(baseline_slice.mean()) if baseline_slice.size else recent_rate

        state.recent_anomaly_rate = round(recent_rate, 4)
        state.baseline_anomaly_rate = round(baseline_rate, 4)

        # Polyfit trend slope over binned history
        bin_size = max(1, len(flags) // 8)
        bins = [flags[i:i + bin_size].mean() for i in range(0, len(flags), bin_size)]
        if len(bins) >= 2:
            x = np.arange(len(bins))
            state.trend_slope = round(float(np.polyfit(x, bins, 1)[0]), 4)
        else:
            state.trend_slope = 0.0

        # Compute multi-penalty score
        drift_penalty = min(1.0, abs(residual_val) / 5.0) if (is_drift and affects_this_ch) else 0.0
        frozen_penalty = min(1.0, state.frozen_streak / 6.0)

        total_penalty = np.clip(
            0.40 * recent_rate + 0.30 * frozen_penalty + 0.20 * drift_penalty + 0.10 * max(0.0, state.trend_slope),
            0.0, 1.0
        )
        raw_shi = 100.0 * (1.0 - total_penalty)

        # EMA smoothing
        state.current_shi = round(
            float(np.clip(self.EMA_ALPHA * raw_shi + (1.0 - self.EMA_ALPHA) * state.current_shi, 0.0, 100.0)), 2
        )

        # Health status mapping
        if state.current_shi >= 85.0:
            status = "EXCELLENT"
        elif state.current_shi >= 70.0:
            status = "GOOD"
        elif state.current_shi >= 50.0:
            status = "DEGRADED"
        elif state.current_shi >= 25.0:
            status = "POOR"
        else:
            status = "CRITICAL"
        state.status = status

        # Degradation risk & RUL estimation
        if state.frozen_streak >= 6 or state.current_shi < 35.0:
            risk = "MAINTENANCE_REQUIRED"
            hours_to_fail = 0.0
        elif recent_rate - baseline_rate >= 0.20 and state.trend_slope > 0.01:
            risk = "HIGH_RISK"
            # Estimate hours to SHI < 50
            steps_to_50 = max(1.0, (state.current_shi - 50.0) / max(0.05, state.trend_slope * 10.0))
            hours_to_fail = round(float(steps_to_50 * 0.25), 1)  # 15-min intervals = 0.25h
        elif recent_rate - baseline_rate >= 0.10 or state.current_shi < 70.0:
            risk = "DEGRADING"
            hours_to_fail = round(float(max(24.0, (state.current_shi - 50.0) / 0.1)), 1)
        else:
            risk = "STABLE"
            hours_to_fail = None

        state.degradation_risk = risk
        state.hours_to_failure = hours_to_fail

        # Actionable maintenance advisories
        ch_name = state.channel.replace("_c", "").replace("_hpa", "").replace("_pct", "").capitalize()
        if status == "CRITICAL" or state.frozen_streak >= 6:
            state.recommended_action = f"Immediate field intervention: {ch_name} sensor stuck or failing. Replace sensor module."
        elif risk in ("HIGH_RISK", "MAINTENANCE_REQUIRED"):
            state.recommended_action = f"Schedule urgent maintenance: {ch_name} sensor degrading rapidly (RUL ~{hours_to_fail or 24:.0f}h)."
        elif status == "DEGRADED":
            state.recommended_action = f"Plan recalibration check: {ch_name} sensor exhibits elevated baseline variance or drift."
        else:
            state.recommended_action = f"{ch_name} sensor operating within nominal WMO precision tolerances."

    def _build_station_snapshot(self, station_id: str, timestamp: datetime) -> StationHealthSnapshot:
        station_dict = self._stations[station_id]
        channel_shis = [s.current_shi for s in station_dict.values()]
        # Overall station health is governed by its degraded sensors
        overall_shi = round(float(min(channel_shis)), 2) if channel_shis else 100.0

        # Track rolling station SHI for degradation slope
        self._shi_history[station_id].append(overall_shi)

        channel_statuses = [s.status for s in station_dict.values()]
        if "CRITICAL" in channel_statuses or overall_shi < 25.0:
            overall_status = "CRITICAL"
        elif "POOR" in channel_statuses or overall_shi < 50.0:
            overall_status = "POOR"
        elif "DEGRADED" in channel_statuses or overall_shi < 70.0:
            overall_status = "DEGRADED"
        elif "GOOD" in channel_statuses or overall_shi < 85.0:
            overall_status = "GOOD"
        else:
            overall_status = "EXCELLENT"

        # Overall risk takes worst channel risk
        risks = [s.degradation_risk for s in station_dict.values()]
        if "MAINTENANCE_REQUIRED" in risks:
            overall_risk = "MAINTENANCE_REQUIRED"
        elif "HIGH_RISK" in risks:
            overall_risk = "HIGH_RISK"
        elif "DEGRADING" in risks:
            overall_risk = "DEGRADING"
        else:
            overall_risk = "STABLE"

        # Minimum RUL across degraded channels
        ruls = [s.hours_to_failure for s in station_dict.values() if s.hours_to_failure is not None]
        min_rul = min(ruls) if ruls else None

        # Most critical recommendation
        rec = "All Automatic Weather Station sensors nominal. No maintenance required."
        for s in station_dict.values():
            if s.status in ("CRITICAL", "DEGRADED"):
                rec = s.recommended_action
                break

        # Max anomaly rate
        anom_rates = [s.recent_anomaly_rate for s in station_dict.values()]
        max_anom_rate = max(anom_rates) if anom_rates else 0.0

        channel_dict = {
            ch: {
                "health_score": s.current_shi,
                "status": s.status,
                "degradation_risk": s.degradation_risk,
                "recent_anomaly_rate": s.recent_anomaly_rate,
                "trend_slope": s.trend_slope,
                "frozen_streak": s.frozen_streak,
                "hours_to_failure": s.hours_to_failure,
                "recommended_action": s.recommended_action,
            }
            for ch, s in station_dict.items()
        }

        return StationHealthSnapshot(
            station_id=station_id,
            timestamp=timestamp,
            overall_health_score=overall_shi,
            health_status=overall_status,
            degradation_risk=overall_risk,
            anomaly_rate_30d=round(max_anom_rate, 4),
            drift_score=round(max(0.0, 1.0 - (overall_shi / 100.0)), 4),
            data_quality_score=round(overall_shi, 2),
            estimated_hours_to_failure=min_rul,
            recommended_action=rec,
            channel_health=channel_dict,
        )


# Global singleton instance
predictive_health_tracker = PredictiveHealthTracker()
