"""
backend/app/ml/tier1_qc.py
Tier 1: Deterministic Quality Control & Boundary Engine.

Enforces WMO physical limits, derivative rate-of-change step limits,
persistence (frozen sensor) checks, missing values, and data integrity checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Union
import numpy as np
import pandas as pd


@dataclass
class Tier1QCConfig:
    """WMO and empirical Quality Control thresholds."""
    # Temperature (°C)
    temp_min: float = -40.0
    temp_max: float = 60.0
    temp_step_max: float = 5.0  # max change per 5-min step
    temp_rate_per_min: float = 1.0

    # Atmospheric Pressure (hPa)
    pressure_min: float = 300.0
    pressure_max: float = 1100.0
    pressure_step_max: float = 3.0
    pressure_rate_per_min: float = 0.6

    # Relative Humidity (%)
    rh_min: float = 0.0
    rh_max: float = 104.0
    rh_step_max: float = 25.0
    rh_rate_per_min: float = 5.0

    # Persistence / Frozen sensor check
    frozen_window_steps: int = 6
    frozen_var_threshold: float = 1e-6
    max_step_gap_minutes: float = 15.0


@dataclass
class Tier1QCResult:
    """Output contract for Tier 1 Quality Control analysis."""
    is_valid: bool = True
    qc_flag: bool = False  # True if violation detected
    score: float = 0.0  # 1.0 if hard failure, 0.0 if clean, or normalized ratio
    is_hard_override: bool = False
    is_frozen: bool = False
    is_missing: bool = False
    flags: Dict[str, Any] = field(default_factory=dict)
    violations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "qc_flag": self.qc_flag,
            "score": round(self.score, 4),
            "is_hard_override": self.is_hard_override,
            "is_frozen": self.is_frozen,
            "is_missing": self.is_missing,
            "flags": self.flags,
            "violations": self.violations,
            "metadata": self.metadata,
        }


class Tier1QC:
    """Deterministic Quality Control & Physical Plausibility Engine."""

    def __init__(self, config: Optional[Tier1QCConfig] = None):
        self.config = config or Tier1QCConfig()

    def evaluate(
        self,
        temperature: Optional[Union[float, int, str]] = None,
        pressure: Optional[Union[float, int, str]] = None,
        humidity: Optional[Union[float, int, str]] = None,
        temp_history: Optional[Sequence[float]] = None,
        press_history: Optional[Sequence[float]] = None,
        humid_history: Optional[Sequence[float]] = None,
        timestamp: Optional[Any] = None,
        prev_timestamp: Optional[Any] = None,
    ) -> Tier1QCResult:
        """
        Evaluate a single telemetry observation against deterministic QC rules.
        """
        flags: Dict[str, Any] = {
            "out_of_bounds": False,
            "violating_param": None,
            "rate_of_change_exceeded": False,
            "is_frozen": False,
            "missing_value": False,
            "corrupt_token": False,
            "non_monotonic_timestamp": False,
            "duplicate_timestamp": False,
        }
        violations: List[str] = []
        is_hard_override = False
        is_missing = False
        is_frozen = False
        score = 0.0

        # 1. Missingness & Sentinel Value Check
        raw_vals = {"temperature": temperature, "pressure": pressure, "humidity": humidity}
        for name, val in raw_vals.items():
            if val is None:
                is_missing = True
                flags["missing_value"] = True
                violations.append(f"Missing parameter: {name} is None")
            elif isinstance(val, (int, float)) and (np.isnan(val) or val == -999.0 or val == 9999.0):
                is_missing = True
                flags["missing_value"] = True
                violations.append(f"Sentinel or NaN value encountered in {name}: {val}")

        if is_missing:
            return Tier1QCResult(
                is_valid=False,
                qc_flag=True,
                score=1.0,
                is_hard_override=True,
                is_missing=True,
                flags=flags,
                violations=violations,
                metadata={"reason": "Missing telemetry or sentinel values"},
            )

        # 2. Corrupt String / Non-Numeric Check
        parsed_vals: Dict[str, float] = {}
        for name, val in raw_vals.items():
            if isinstance(val, str):
                try:
                    parsed_vals[name] = float(val)
                except ValueError:
                    flags["corrupt_token"] = True
                    violations.append(f"Corrupt non-numeric token in {name}: '{val}'")
            else:
                try:
                    parsed_vals[name] = float(val)  # type: ignore
                except (ValueError, TypeError):
                    flags["corrupt_token"] = True
                    violations.append(f"Invalid type in {name}: {type(val)}")

        if flags["corrupt_token"]:
            return Tier1QCResult(
                is_valid=False,
                qc_flag=True,
                score=1.0,
                is_hard_override=True,
                flags=flags,
                violations=violations,
                metadata={"reason": "Corrupt non-numeric tokens"},
            )

        t = parsed_vals["temperature"]
        p = parsed_vals["pressure"]
        rh = parsed_vals["humidity"]

        # 3. Timestamp Monotonicity & Duplication Checks
        if timestamp is not None and prev_timestamp is not None:
            try:
                t_curr = pd.to_datetime(timestamp)
                t_prev = pd.to_datetime(prev_timestamp)
                if t_curr == t_prev:
                    flags["duplicate_timestamp"] = True
                    violations.append(f"Duplicate timestamp encountered: {timestamp}")
                elif t_curr < t_prev:
                    flags["non_monotonic_timestamp"] = True
                    violations.append(f"Non-monotonic timestamp: current {timestamp} < previous {prev_timestamp}")
            except Exception:
                pass

        # 4. WMO Physical Plausibility (Range Bounds)
        if t < self.config.temp_min or t > self.config.temp_max:
            flags["out_of_bounds"] = True
            flags["violating_param"] = "temperature"
            violations.append(f"Temperature {t:.2f}°C outside WMO bounds [{self.config.temp_min}, {self.config.temp_max}]")
            is_hard_override = True

        if p < self.config.pressure_min or p > self.config.pressure_max:
            flags["out_of_bounds"] = True
            if flags["violating_param"] is None:
                flags["violating_param"] = "pressure"
            violations.append(f"Pressure {p:.2f} hPa outside WMO bounds [{self.config.pressure_min}, {self.config.pressure_max}]")
            is_hard_override = True

        if rh < self.config.rh_min or rh > self.config.rh_max:
            flags["out_of_bounds"] = True
            if flags["violating_param"] is None:
                flags["violating_param"] = "humidity"
            violations.append(f"Humidity {rh:.2f}% outside WMO bounds [{self.config.rh_min}, {self.config.rh_max}]")
            is_hard_override = True

        # 5. Rate of Change / Step Limits
        roc_violations = []
        if temp_history and len(temp_history) > 0:
            last_t = float(temp_history[-1])
            dt = abs(t - last_t)
            if dt > self.config.temp_step_max:
                flags["rate_of_change_exceeded"] = True
                if flags["violating_param"] is None:
                    flags["violating_param"] = "temperature"
                roc_violations.append(f"Temperature step change |ΔT|={dt:.2f}°C exceeds {self.config.temp_step_max}°C")

        if press_history and len(press_history) > 0:
            last_p = float(press_history[-1])
            dp = abs(p - last_p)
            if dp > self.config.pressure_step_max:
                flags["rate_of_change_exceeded"] = True
                if flags["violating_param"] is None:
                    flags["violating_param"] = "pressure"
                roc_violations.append(f"Pressure step change |ΔP|={dp:.2f}hPa exceeds {self.config.pressure_step_max}hPa")

        if humid_history and len(humid_history) > 0:
            last_rh = float(humid_history[-1])
            drh = abs(rh - last_rh)
            if drh > self.config.rh_step_max:
                flags["rate_of_change_exceeded"] = True
                if flags["violating_param"] is None:
                    flags["violating_param"] = "humidity"
                roc_violations.append(f"Humidity step change |ΔRH|={drh:.2f}% exceeds {self.config.rh_step_max}%")

        violations.extend(roc_violations)

        # 6. Persistence / Frozen Sensor Check (Variance over last K steps)
        def check_frozen_seq(curr: float, hist: Optional[Sequence[float]]) -> bool:
            if hist is None:
                return False
            seq = [float(x) for x in hist] + [curr]
            if len(seq) >= self.config.frozen_window_steps:
                recent = seq[-self.config.frozen_window_steps:]
                return float(np.var(recent)) < self.config.frozen_var_threshold
            return False

        if check_frozen_seq(t, temp_history):
            flags["is_frozen"] = True
            is_frozen = True
            is_hard_override = True
            violations.append(f"Temperature sensor frozen for >= {self.config.frozen_window_steps} consecutive steps")

        if check_frozen_seq(p, press_history):
            flags["is_frozen"] = True
            is_frozen = True
            is_hard_override = True
            violations.append(f"Pressure sensor frozen for >= {self.config.frozen_window_steps} consecutive steps")

        if check_frozen_seq(rh, humid_history):
            flags["is_frozen"] = True
            is_frozen = True
            is_hard_override = True
            violations.append(f"Humidity sensor frozen for >= {self.config.frozen_window_steps} consecutive steps")

        # Determine overall QC Flag and Score
        has_violations = len(violations) > 0 or flags["out_of_bounds"] or flags["rate_of_change_exceeded"] or is_frozen

        if is_hard_override or flags["out_of_bounds"] or flags["duplicate_timestamp"] or flags["non_monotonic_timestamp"] or is_frozen:
            score = 1.0
            is_hard_override = True
        elif flags["rate_of_change_exceeded"]:
            score = 0.85
        elif has_violations:
            score = 0.50
        else:
            score = 0.0

        return Tier1QCResult(
            is_valid=not (flags["corrupt_token"] or flags["missing_value"] or flags["duplicate_timestamp"] or flags["non_monotonic_timestamp"]),
            qc_flag=has_violations,
            score=score,
            is_hard_override=is_hard_override,
            is_frozen=is_frozen,
            is_missing=is_missing,
            flags=flags,
            violations=violations,
            metadata={
                "temperature": t,
                "pressure": p,
                "humidity": rh,
                "timestamp": str(timestamp) if timestamp is not None else None,
            },
        )

    def check_observation(
        self,
        current: Dict[str, Any],
        previous: Optional[Dict[str, Any]] = None,
        recent_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Tier1QCResult:
        """Evaluate a single dictionary record against QC rules."""
        temp_hist = [float(h["temperature"]) for h in recent_history if "temperature" in h and h["temperature"] is not None] if recent_history else None
        press_hist = [float(h["pressure"]) for h in recent_history if "pressure" in h and h["pressure"] is not None] if recent_history else None
        humid_hist = [float(h["humidity"]) for h in recent_history if "humidity" in h and h["humidity"] is not None] if recent_history else None

        if previous is not None and not temp_hist:
            if "temperature" in previous and previous["temperature"] is not None:
                temp_hist = [float(previous["temperature"])]
            if "pressure" in previous and previous["pressure"] is not None:
                press_hist = [float(previous["pressure"])]
            if "humidity" in previous and previous["humidity"] is not None:
                humid_hist = [float(previous["humidity"])]

        prev_time = previous.get("timestamp") if previous else None

        return self.evaluate(
            temperature=current.get("temperature"),
            pressure=current.get("pressure"),
            humidity=current.get("humidity"),
            temp_history=temp_hist,
            press_history=press_hist,
            humid_history=humid_hist,
            timestamp=current.get("timestamp"),
            prev_timestamp=prev_time,
        )

    def check_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Batch QC evaluation over a historical DataFrame."""
        results = []
        df_sorted = df.copy()
        if "timestamp" in df_sorted.columns:
            try:
                df_sorted["dt_parsed"] = pd.to_datetime(df_sorted["timestamp"])
                df_sorted = df_sorted.sort_values("dt_parsed").drop(columns=["dt_parsed"])
            except Exception:
                pass

        t_hist: List[float] = []
        p_hist: List[float] = []
        rh_hist: List[float] = []
        prev_ts = None

        for _, row in df_sorted.iterrows():
            curr_ts = row.get("timestamp")
            t_val = row.get("temperature")
            p_val = row.get("pressure")
            rh_val = row.get("humidity")

            res = self.evaluate(
                temperature=t_val,
                pressure=p_val,
                humidity=rh_val,
                temp_history=t_hist[-self.config.frozen_window_steps:],
                press_history=p_hist[-self.config.frozen_window_steps:],
                humid_history=rh_hist[-self.config.frozen_window_steps:],
                timestamp=curr_ts,
                prev_timestamp=prev_ts,
            )
            results.append(res.to_dict())

            if res.is_valid and not res.is_missing:
                try:
                    t_hist.append(float(t_val))
                    p_hist.append(float(p_val))
                    rh_hist.append(float(rh_val))
                except Exception:
                    pass
            prev_ts = curr_ts

        res_df = pd.DataFrame(results)
        return pd.concat([df_sorted.reset_index(drop=True), res_df], axis=1)


# Provide alias for backward/interchangeable naming
Tier1QCEngine = Tier1QC
