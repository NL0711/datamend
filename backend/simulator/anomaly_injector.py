"""
SkyGuard AI — Anomaly Injector Engine.

Programmatically injects 8 ground-truth labeled anomaly patterns into AWS telemetry time series:
- SPIKE: Instantaneous transient impulse
- DRIFT: Progressive linear calibration offset
- FROZEN: Sensor stuck repeating constant value (zero variance)
- DROPOUT: Signal loss resulting in NaN, zero, or sentinel values
- NOISE_BURST: High-frequency variance noise surge
- MULTIVARIATE_INCONSISTENCY: Physical thermodynamic decoupling
- METEOROLOGICAL_EXTREME: Genuine convective squall (is_fault=False)
- DATA_CORRUPTION: Malformed framing, string tokens, non-numerics
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


class AnomalyType(str, Enum):
    NORMAL = "NORMAL"
    SPIKE = "SPIKE"
    DRIFT = "DRIFT"
    FROZEN = "FROZEN"
    DROPOUT = "DROPOUT"
    NOISE_BURST = "NOISE_BURST"
    MULTIVARIATE_INCONSISTENCY = "MULTIVARIATE_INCONSISTENCY"
    METEOROLOGICAL_EXTREME = "METEOROLOGICAL_EXTREME"
    DATA_CORRUPTION = "DATA_CORRUPTION"


class Severity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


SEVERITY_ORDER: Dict[str, int] = {
    Severity.NONE.value: 0,
    Severity.LOW.value: 1,
    Severity.MEDIUM.value: 2,
    Severity.HIGH.value: 3,
    Severity.CRITICAL.value: 4,
}


def _ensure_ground_truth_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure ground-truth tracking columns and clean baseline copies exist."""
    df = df.copy()
    if "clean_temperature" not in df.columns and "temperature" in df.columns:
        df["clean_temperature"] = df["temperature"].copy()
    if "clean_pressure" not in df.columns and "pressure" in df.columns:
        df["clean_pressure"] = df["pressure"].copy()
    if "clean_humidity" not in df.columns and "humidity" in df.columns:
        df["clean_humidity"] = df["humidity"].copy()

    if "is_anomaly" not in df.columns:
        df["is_anomaly"] = False
    if "anomaly_type" not in df.columns:
        df["anomaly_type"] = AnomalyType.NORMAL.value
    if "severity" not in df.columns:
        df["severity"] = Severity.NONE.value
    if "is_fault" not in df.columns:
        df["is_fault"] = False
    if "affected_params" not in df.columns:
        df["affected_params"] = "none"
    if "anomaly_metadata" not in df.columns:
        df["anomaly_metadata"] = "{}"

    return df


def _escalate_severity(current: str, new: str) -> str:
    """Return the higher severity level between current and new."""
    c_level = SEVERITY_ORDER.get(str(current), 0)
    n_level = SEVERITY_ORDER.get(str(new), 0)
    return new if n_level > c_level else current


def inject_spike(
    df: pd.DataFrame,
    target_column: Union[str, List[str]],
    start_idx: int,
    duration: int = 1,
    magnitude: Optional[float] = None,
    decay: bool = False,
    severity: Optional[str] = None,
    random_seed: Optional[int] = None,
) -> pd.DataFrame:
    """Inject sudden transient step change in single or multiple observations."""
    df = _ensure_ground_truth_columns(df)
    n = len(df)
    if start_idx < 0 or start_idx >= n:
        raise IndexError(f"start_idx {start_idx} out of range [0, {n-1}]")

    end_idx = min(start_idx + duration, n)
    cols = [target_column] if isinstance(target_column, str) else target_column
    rng = np.random.RandomState(random_seed) if random_seed is not None else np.random.RandomState(42)

    for col in cols:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in DataFrame.")

        if magnitude is None:
            if col == "temperature":
                mag = float(rng.choice([15.0, 25.0, -12.0, 30.0]))
            elif col == "pressure":
                mag = float(rng.choice([20.0, -35.0, 45.0]))
            elif col == "humidity":
                mag = float(rng.choice([40.0, -50.0, 60.0]))
            else:
                mag = 20.0
        else:
            mag = float(magnitude)

        k = end_idx - start_idx
        for step_i, idx in enumerate(range(start_idx, end_idx)):
            pulse = np.exp(-step_i / (k / 2.0)) if (decay and k > 1) else 1.0
            df.loc[idx, col] = float(df.loc[idx, col]) + mag * pulse

    sev = severity or (Severity.CRITICAL.value if abs(mag) > 20.0 else Severity.HIGH.value)

    for idx in range(start_idx, end_idx):
        df.loc[idx, "is_anomaly"] = True
        df.loc[idx, "anomaly_type"] = AnomalyType.SPIKE.value
        df.loc[idx, "severity"] = _escalate_severity(str(df.loc[idx, "severity"]), sev)
        df.loc[idx, "is_fault"] = True
        df.loc[idx, "affected_params"] = ",".join(cols)
        df.loc[idx, "anomaly_metadata"] = json.dumps({
            "type": "SPIKE",
            "magnitude": mag,
            "duration": duration,
            "target": cols,
        })

    return df


def inject_drift(
    df: pd.DataFrame,
    target_column: str,
    start_idx: int,
    duration: int = 72,
    max_drift: float = 8.0,
    drift_rate: Optional[float] = None,
    slope: Optional[float] = None,
    exponent: float = 1.0,
    persistent: bool = False,
    severity: Optional[str] = None,
    random_seed: Optional[int] = None,
) -> pd.DataFrame:
    """Inject progressive linear calibration offset over an extended duration."""
    df = _ensure_ground_truth_columns(df)
    n = len(df)
    if start_idx < 0 or start_idx >= n:
        raise IndexError(f"start_idx {start_idx} out of range [0, {n-1}]")

    end_idx = min(start_idx + duration, n)
    if target_column not in df.columns:
        raise ValueError(f"Column '{target_column}' not found.")

    drift_span = end_idx - start_idx
    if drift_rate is not None:
        target_max_drift = drift_rate * drift_span
    elif slope is not None:
        target_max_drift = slope * max(1, drift_span - 1)
    else:
        target_max_drift = max_drift

    for step_i, idx in enumerate(range(start_idx, end_idx)):
        progress = ((step_i + 1) / max(1, drift_span)) ** exponent
        offset = target_max_drift * progress
        df.loc[idx, target_column] = float(df.loc[idx, target_column]) + offset

        if abs(offset) < 0.33 * abs(target_max_drift):
            step_sev = Severity.LOW.value
        elif abs(offset) < 0.66 * abs(target_max_drift):
            step_sev = Severity.MEDIUM.value
        else:
            step_sev = Severity.HIGH.value

        df.loc[idx, "is_anomaly"] = True
        df.loc[idx, "anomaly_type"] = AnomalyType.DRIFT.value
        df.loc[idx, "severity"] = severity or _escalate_severity(str(df.loc[idx, "severity"]), step_sev)
        df.loc[idx, "is_fault"] = True
        df.loc[idx, "affected_params"] = target_column
        df.loc[idx, "anomaly_metadata"] = json.dumps({
            "type": "DRIFT",
            "current_offset": round(offset, 3),
            "max_drift": target_max_drift,
            "duration": duration,
        })

    if persistent and end_idx < n:
        for idx in range(end_idx, n):
            df.loc[idx, target_column] = float(df.loc[idx, target_column]) + target_max_drift
            df.loc[idx, "is_anomaly"] = True
            df.loc[idx, "anomaly_type"] = AnomalyType.DRIFT.value
            df.loc[idx, "severity"] = severity or _escalate_severity(str(df.loc[idx, "severity"]), Severity.HIGH.value)
            df.loc[idx, "is_fault"] = True
            df.loc[idx, "affected_params"] = target_column

    return df


def inject_frozen(
    df: pd.DataFrame,
    target_column: Union[str, List[str]],
    start_idx: int,
    duration: int = 24,
    stuck_value: Optional[float] = None,
    severity: Optional[str] = None,
    random_seed: Optional[int] = None,
) -> pd.DataFrame:
    """Inject sensor values stuck/repeating with zero variance over K steps."""
    df = _ensure_ground_truth_columns(df)
    n = len(df)
    if start_idx < 0 or start_idx >= n:
        raise IndexError(f"start_idx {start_idx} out of range [0, {n-1}]")

    end_idx = min(start_idx + duration, n)
    cols = [target_column] if isinstance(target_column, str) else target_column

    for col in cols:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found.")
        val = stuck_value if stuck_value is not None else float(df.loc[start_idx, col])
        df.loc[start_idx:end_idx - 1, col] = val

    for step_i, idx in enumerate(range(start_idx, end_idx)):
        step_sev = Severity.LOW.value if step_i < 5 else (Severity.MEDIUM.value if step_i < 12 else Severity.HIGH.value)
        df.loc[idx, "is_anomaly"] = True
        df.loc[idx, "anomaly_type"] = AnomalyType.FROZEN.value
        df.loc[idx, "severity"] = severity or _escalate_severity(str(df.loc[idx, "severity"]), step_sev)
        df.loc[idx, "is_fault"] = True
        df.loc[idx, "affected_params"] = ",".join(cols)
        df.loc[idx, "anomaly_metadata"] = json.dumps({
            "type": "FROZEN",
            "stuck_value": val,
            "duration": duration,
        })

    return df


def inject_dropout(
    df: pd.DataFrame,
    target_column: Union[str, List[str]],
    start_idx: int,
    duration: int = 12,
    fill_mode: str = "nan",
    drop_probability: float = 1.0,
    severity: str = Severity.CRITICAL.value,
    random_seed: Optional[int] = None,
) -> pd.DataFrame:
    """Inject abrupt null/zero values representing signal loss."""
    df = _ensure_ground_truth_columns(df)
    n = len(df)
    if start_idx < 0 or start_idx >= n:
        raise IndexError(f"start_idx {start_idx} out of range [0, {n-1}]")

    VALID_FILL_MODES = ["nan", "zero", "sentinel_neg999", "null"]
    if fill_mode not in VALID_FILL_MODES:
        raise ValueError(f"Unsupported fill_mode '{fill_mode}'. Valid modes: {VALID_FILL_MODES}")

    end_idx = min(start_idx + duration, n)
    cols = ["temperature", "pressure", "humidity"] if target_column == "all" else (
        [target_column] if isinstance(target_column, str) else target_column
    )
    for col in cols:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in DataFrame.")

    rng = np.random.RandomState(random_seed) if random_seed is not None else np.random.RandomState(42)

    for idx in range(start_idx, end_idx):
        if rng.uniform(0, 1) <= drop_probability:
            for col in cols:
                if fill_mode == "nan":
                    df.loc[idx, col] = np.nan
                elif fill_mode == "zero":
                    df.loc[idx, col] = 0.0
                elif fill_mode == "sentinel_neg999":
                    df.loc[idx, col] = -999.0
                elif fill_mode == "null":
                    df.loc[idx, col] = None

            df.loc[idx, "is_anomaly"] = True
            df.loc[idx, "anomaly_type"] = AnomalyType.DROPOUT.value
            df.loc[idx, "severity"] = _escalate_severity(str(df.loc[idx, "severity"]), severity)
            df.loc[idx, "is_fault"] = True
            df.loc[idx, "affected_params"] = ",".join(cols)
            df.loc[idx, "anomaly_metadata"] = json.dumps({
                "type": "DROPOUT",
                "fill_mode": fill_mode,
                "drop_prob": drop_probability,
            })

    return df


def inject_noise_burst(
    df: pd.DataFrame,
    target_column: Union[str, List[str]],
    start_idx: int,
    duration: int = 36,
    noise_factor: float = 8.0,
    noise_type: str = "gaussian",
    severity: str = Severity.MEDIUM.value,
    random_seed: Optional[int] = None,
) -> pd.DataFrame:
    """Inject high-frequency variance noise burst."""
    df = _ensure_ground_truth_columns(df)
    n = len(df)
    if start_idx < 0 or start_idx >= n:
        raise IndexError(f"start_idx {start_idx} out of range [0, {n-1}]")

    VALID_NOISE_TYPES = ["gaussian", "uniform"]
    if noise_type not in VALID_NOISE_TYPES:
        raise ValueError(f"Unsupported noise_type '{noise_type}'. Valid types: {VALID_NOISE_TYPES}")

    end_idx = min(start_idx + duration, n)
    cols = [target_column] if isinstance(target_column, str) else target_column
    for col in cols:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in DataFrame.")

    rng = np.random.RandomState(random_seed) if random_seed is not None else np.random.RandomState(42)

    for col in cols:
        nominal_std = {"temperature": 0.35, "pressure": 0.15, "humidity": 1.2}.get(col, 1.0)
        burst_std = nominal_std * noise_factor

        span = end_idx - start_idx
        if noise_type == "gaussian":
            noise = rng.normal(0, burst_std, size=span)
        else:
            noise = rng.uniform(-np.sqrt(3) * burst_std, np.sqrt(3) * burst_std, size=span)

        df.loc[start_idx:end_idx - 1, col] = df.loc[start_idx:end_idx - 1, col].astype(float) + noise

    for idx in range(start_idx, end_idx):
        df.loc[idx, "is_anomaly"] = True
        df.loc[idx, "anomaly_type"] = AnomalyType.NOISE_BURST.value
        df.loc[idx, "severity"] = _escalate_severity(str(df.loc[idx, "severity"]), severity)
        df.loc[idx, "is_fault"] = True
        df.loc[idx, "affected_params"] = ",".join(cols)
        df.loc[idx, "anomaly_metadata"] = json.dumps({
            "type": "NOISE_BURST",
            "noise_factor": noise_factor,
            "duration": duration,
        })

    return df


def inject_multivariate_inconsistency(
    df: pd.DataFrame,
    start_idx: int,
    duration: int = 24,
    mode: str = "thermodynamic_inversion",
    temp_shift: float = 14.0,
    rh_shift: float = 40.0,
    pressure_shift: float = 0.0,
    severity: str = Severity.HIGH.value,
    random_seed: Optional[int] = None,
) -> pd.DataFrame:
    """Inject physical decoupling where T increases while RH also increases sharply violating physics."""
    df = _ensure_ground_truth_columns(df)
    n = len(df)
    if start_idx < 0 or start_idx >= n:
        raise IndexError(f"start_idx {start_idx} out of range [0, {n-1}]")

    VALID_MODES = ["thermodynamic_inversion", "unphysical_supersaturation", "barometric_decoupling"]
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported multivariate mode '{mode}'. Valid modes: {VALID_MODES}")

    end_idx = min(start_idx + duration, n)

    if mode == "thermodynamic_inversion":
        df.loc[start_idx:end_idx - 1, "temperature"] = df.loc[start_idx:end_idx - 1, "temperature"].astype(float) + temp_shift
        df.loc[start_idx:end_idx - 1, "humidity"] = np.clip(
            df.loc[start_idx:end_idx - 1, "humidity"].astype(float) + rh_shift, 5.0, 100.0
        )
    elif mode == "unphysical_supersaturation":
        df.loc[start_idx:end_idx - 1, "temperature"] = 42.0
        df.loc[start_idx:end_idx - 1, "humidity"] = 100.0
    elif mode == "barometric_decoupling":
        p_shift = pressure_shift if pressure_shift != 0.0 else -18.0
        df.loc[start_idx:end_idx - 1, "pressure"] = df.loc[start_idx:end_idx - 1, "pressure"].astype(float) + p_shift

    for idx in range(start_idx, end_idx):
        df.loc[idx, "is_anomaly"] = True
        df.loc[idx, "anomaly_type"] = AnomalyType.MULTIVARIATE_INCONSISTENCY.value
        df.loc[idx, "severity"] = _escalate_severity(str(df.loc[idx, "severity"]), severity)
        df.loc[idx, "is_fault"] = True
        df.loc[idx, "affected_params"] = "temperature,humidity" if mode != "barometric_decoupling" else "pressure"
        df.loc[idx, "anomaly_metadata"] = json.dumps({
            "type": "MULTIVARIATE_INCONSISTENCY",
            "mode": mode,
            "temp_shift": temp_shift,
            "rh_shift": rh_shift,
        })

    return df


def inject_meteorological_extreme(
    df: pd.DataFrame,
    start_idx: int,
    duration: int = 12,
    temp_drop: float = -8.0,
    pressure_drop: float = -5.0,
    rh_surge: float = 35.0,
    severity: str = Severity.HIGH.value,
    random_seed: Optional[int] = None,
) -> pd.DataFrame:
    """Inject genuine severe weather event with physically consistent multi-variable dynamics (is_fault=False)."""
    df = _ensure_ground_truth_columns(df)
    n = len(df)
    if start_idx < 0 or start_idx >= n:
        raise IndexError(f"start_idx {start_idx} out of range [0, {n-1}]")

    end_idx = min(start_idx + duration, n)
    span = end_idx - start_idx

    t_ramp = np.linspace(0, temp_drop, span)
    p_ramp = np.linspace(0, pressure_drop, span)
    rh_ramp = np.linspace(0, rh_surge, span)

    df.loc[start_idx:end_idx - 1, "temperature"] = df.loc[start_idx:end_idx - 1, "temperature"].astype(float) + t_ramp
    df.loc[start_idx:end_idx - 1, "pressure"] = df.loc[start_idx:end_idx - 1, "pressure"].astype(float) + p_ramp
    df.loc[start_idx:end_idx - 1, "humidity"] = np.clip(
        df.loc[start_idx:end_idx - 1, "humidity"].astype(float) + rh_ramp, 5.0, 100.0
    )

    for idx in range(start_idx, end_idx):
        df.loc[idx, "is_anomaly"] = True
        df.loc[idx, "anomaly_type"] = AnomalyType.METEOROLOGICAL_EXTREME.value
        df.loc[idx, "severity"] = _escalate_severity(str(df.loc[idx, "severity"]), severity)
        df.loc[idx, "is_fault"] = False  # Crucial differentiation!
        df.loc[idx, "affected_params"] = "temperature,pressure,humidity"
        df.loc[idx, "anomaly_metadata"] = json.dumps({
            "type": "METEOROLOGICAL_EXTREME",
            "temp_drop": temp_drop,
            "pressure_drop": pressure_drop,
        })

    return df


def inject_data_corruption(
    df: pd.DataFrame,
    target_column: Union[str, List[str]],
    start_idx: int,
    duration: int = 3,
    corruption_mode: str = "string_err",
    severity: str = Severity.CRITICAL.value,
    random_seed: Optional[int] = None,
) -> pd.DataFrame:
    """Inject malformed or corrupted telemetry observations."""
    df = _ensure_ground_truth_columns(df)
    n = len(df)
    if start_idx < 0 or start_idx >= n:
        raise IndexError(f"start_idx {start_idx} out of range [0, {n-1}]")

    VALID_CORRUPTION_MODES = ["string_err", "out_of_bounds", "duplicate_timestamp"]
    if corruption_mode not in VALID_CORRUPTION_MODES:
        raise ValueError(f"Unsupported corruption_mode '{corruption_mode}'. Valid modes: {VALID_CORRUPTION_MODES}")

    end_idx = min(start_idx + duration, n)
    cols = [target_column] if isinstance(target_column, str) else target_column
    for col in cols:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in DataFrame.")

    if corruption_mode == "string_err":
        for col in cols:
            df[col] = df[col].astype(object)

    for col in cols:
        for idx in range(start_idx, end_idx):
            if corruption_mode == "string_err":
                df.loc[idx, col] = "$ERR_COMM_TIMEOUT#"
            elif corruption_mode == "out_of_bounds":
                df.loc[idx, col] = 9999.0
            elif corruption_mode == "duplicate_timestamp" and idx > 0:
                df.loc[idx, "timestamp"] = df.loc[idx - 1, "timestamp"]

    for idx in range(start_idx, end_idx):
        df.loc[idx, "is_anomaly"] = True
        df.loc[idx, "anomaly_type"] = AnomalyType.DATA_CORRUPTION.value
        df.loc[idx, "severity"] = _escalate_severity(str(df.loc[idx, "severity"]), severity)
        df.loc[idx, "is_fault"] = True
        df.loc[idx, "affected_params"] = ",".join(cols)
        df.loc[idx, "anomaly_metadata"] = json.dumps({
            "type": "DATA_CORRUPTION",
            "corruption_mode": corruption_mode,
        })

    return df


class AnomalyInjector:
    """Fluent chaining builder and runner for injecting anomalies into weather datasets."""

    def __init__(self, df: Optional[pd.DataFrame] = None) -> None:
        self._df = _ensure_ground_truth_columns(df) if df is not None else None

    @classmethod
    def wrap_clean(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Wrap a clean dataframe with standard ground-truth columns."""
        return _ensure_ground_truth_columns(df)

    def set_dataframe(self, df: pd.DataFrame) -> "AnomalyInjector":
        self._df = _ensure_ground_truth_columns(df)
        return self

    def get_dataframe(self) -> pd.DataFrame:
        if self._df is None:
            raise ValueError("No DataFrame set in AnomalyInjector.")
        return self._df

    def apply(self) -> pd.DataFrame:
        return self.get_dataframe()

    def inject_spike(self, **kwargs) -> "AnomalyInjector":
        if self._df is None:
            raise ValueError("No DataFrame set in AnomalyInjector.")
        self._df = inject_spike(self._df, **kwargs)
        return self

    def add_spike(self, **kwargs) -> "AnomalyInjector":
        return self.inject_spike(**kwargs)

    def inject_drift(self, **kwargs) -> "AnomalyInjector":
        if self._df is None:
            raise ValueError("No DataFrame set in AnomalyInjector.")
        self._df = inject_drift(self._df, **kwargs)
        return self

    def add_drift(self, **kwargs) -> "AnomalyInjector":
        return self.inject_drift(**kwargs)

    def inject_frozen(self, **kwargs) -> "AnomalyInjector":
        if self._df is None:
            raise ValueError("No DataFrame set in AnomalyInjector.")
        self._df = inject_frozen(self._df, **kwargs)
        return self

    def add_frozen(self, **kwargs) -> "AnomalyInjector":
        return self.inject_frozen(**kwargs)

    def inject_dropout(self, **kwargs) -> "AnomalyInjector":
        if self._df is None:
            raise ValueError("No DataFrame set in AnomalyInjector.")
        self._df = inject_dropout(self._df, **kwargs)
        return self

    def add_dropout(self, **kwargs) -> "AnomalyInjector":
        return self.inject_dropout(**kwargs)

    def inject_noise_burst(self, **kwargs) -> "AnomalyInjector":
        if self._df is None:
            raise ValueError("No DataFrame set in AnomalyInjector.")
        self._df = inject_noise_burst(self._df, **kwargs)
        return self

    def add_noise_burst(self, **kwargs) -> "AnomalyInjector":
        return self.inject_noise_burst(**kwargs)

    def inject_multivariate_inconsistency(self, **kwargs) -> "AnomalyInjector":
        if self._df is None:
            raise ValueError("No DataFrame set in AnomalyInjector.")
        self._df = inject_multivariate_inconsistency(self._df, **kwargs)
        return self

    def add_multivariate_inconsistency(self, **kwargs) -> "AnomalyInjector":
        return self.inject_multivariate_inconsistency(**kwargs)

    def inject_meteorological_extreme(self, **kwargs) -> "AnomalyInjector":
        if self._df is None:
            raise ValueError("No DataFrame set in AnomalyInjector.")
        self._df = inject_meteorological_extreme(self._df, **kwargs)
        return self

    def add_meteorological_extreme(self, **kwargs) -> "AnomalyInjector":
        return self.inject_meteorological_extreme(**kwargs)

    def inject_data_corruption(self, **kwargs) -> "AnomalyInjector":
        if self._df is None:
            raise ValueError("No DataFrame set in AnomalyInjector.")
        self._df = inject_data_corruption(self._df, **kwargs)
        return self

    def add_data_corruption(self, **kwargs) -> "AnomalyInjector":
        return self.inject_data_corruption(**kwargs)

