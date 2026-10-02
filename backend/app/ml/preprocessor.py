"""
backend/app/ml/preprocessor.py
Feature Engineering, Normalization Scaler, and Rolling Window Sequence Generator.

Generates 9 continuous features:
[temperature, pressure, humidity, temp_delta, press_delta, humid_delta, temp_roll_std, press_roll_std, humid_roll_std]
Normalizes via StandardScaler and creates sliding sequences for temporal models.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


FEATURE_NAMES = [
    "temperature",
    "pressure",
    "humidity",
    "temp_delta",
    "press_delta",
    "humid_delta",
    "temp_roll_std",
    "press_roll_std",
    "humid_roll_std",
]

CORE_FEATURE_NAMES = ["temperature", "pressure", "humidity"]


def calculate_magnus_dew_point(temperature: float, humidity: float) -> float:
    """Calculates dew-point temperature (°C) via Magnus-Tetens formula."""
    t = max(float(temperature), -240.0)
    rh = np.clip(float(humidity), 0.01, 104.0)
    gamma = (17.67 * t) / (t + 243.5) + np.log(rh / 100.0)
    denom = 17.67 - gamma
    if abs(denom) < 1e-6:
        return t
    return float((243.5 * gamma) / denom)


@dataclass
class PreprocessorResult:
    """Output container for a single streaming step transformation."""
    station_id: str
    timestamp: Any
    scaled_vector: np.ndarray  # Shape: (9,)
    raw_feature_dict: Dict[str, float]
    sequence_tensor: np.ndarray  # Shape: (30, 3)
    recent_temperatures: List[float]
    recent_pressures: List[float]
    recent_humidities: List[float]
    buffer_length: int
    is_warm: bool


@dataclass
class StationBuffer:
    """FIFO observation buffer for a single AWS station."""
    station_id: str
    maxlen: int = 288
    timestamps: deque = field(default_factory=lambda: deque(maxlen=288))
    temperatures: deque = field(default_factory=lambda: deque(maxlen=288))
    pressures: deque = field(default_factory=lambda: deque(maxlen=288))
    humidities: deque = field(default_factory=lambda: deque(maxlen=288))

    def append(self, timestamp: Any, temperature: float, pressure: float, humidity: float) -> None:
        self.timestamps.append(timestamp)
        self.temperatures.append(float(temperature))
        self.pressures.append(float(pressure))
        self.humidities.append(float(humidity))

    def __len__(self) -> int:
        return len(self.temperatures)


class DataPreprocessor:
    """Feature engineering, standard scaling, and streaming sequence buffering engine."""

    def __init__(
        self,
        window_size: int = 30,
        rolling_std_window: int = 6,
        feature_names: Optional[List[str]] = None,
    ):
        self.window_size = window_size
        self.rolling_std_window = rolling_std_window
        self.feature_names = feature_names or list(FEATURE_NAMES)
        self.scaler: StandardScaler = StandardScaler()
        self.is_fitted: bool = False
        self.stations: Dict[str, StationBuffer] = {}

        # Default baselines before fit
        self.baseline_means: Dict[str, float] = {
            "temperature": 22.0,
            "pressure": 1013.25,
            "humidity": 55.0,
        }

    def get_or_create_station(self, station_id: str) -> StationBuffer:
        if station_id not in self.stations:
            self.stations[station_id] = StationBuffer(station_id=station_id, maxlen=288)
        return self.stations[station_id]

    def reset_station(self, station_id: str) -> None:
        if station_id in self.stations:
            del self.stations[station_id]

    def compute_feature_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all 9 continuous features across a historical DataFrame."""
        out = df.copy()
        for col in CORE_FEATURE_NAMES:
            if col not in out.columns:
                raise ValueError(f"Required column '{col}' missing from DataFrame.")

        out["temp_delta"] = out["temperature"].diff().fillna(0.0)
        out["press_delta"] = out["pressure"].diff().fillna(0.0)
        out["humid_delta"] = out["humidity"].diff().fillna(0.0)

        # Compatibility aliases
        out["delta_temp"] = out["temp_delta"]
        out["delta_pressure"] = out["press_delta"]
        out["delta_humidity"] = out["humid_delta"]

        out["temp_roll_std"] = out["temperature"].rolling(self.rolling_std_window, min_periods=1).std().fillna(0.0)
        out["press_roll_std"] = out["pressure"].rolling(self.rolling_std_window, min_periods=1).std().fillna(0.0)
        out["humid_roll_std"] = out["humidity"].rolling(self.rolling_std_window, min_periods=1).std().fillna(0.0)

        # Dew point
        out["dew_point"] = [
            calculate_magnus_dew_point(t, rh)
            for t, rh in zip(out["temperature"], out["humidity"])
        ]

        if "timestamp" in out.columns:
            try:
                dt = pd.to_datetime(out["timestamp"])
                hours = dt.dt.hour + dt.dt.minute / 60.0
                out["sin_hour"] = np.sin(2 * np.pi * hours / 24.0)
                out["cos_hour"] = np.cos(2 * np.pi * hours / 24.0)
            except Exception:
                out["sin_hour"] = 0.0
                out["cos_hour"] = 1.0

        return out

    def fit(self, df: pd.DataFrame) -> "DataPreprocessor":
        """Fit StandardScaler on clean training data features."""
        df_feat = self.compute_feature_dataframe(df)
        X = df_feat[self.feature_names].dropna().to_numpy(dtype=np.float64)
        if len(X) == 0:
            raise ValueError("No valid rows available to fit StandardScaler.")

        self.scaler.fit(X)
        self.is_fitted = True

        for col in CORE_FEATURE_NAMES:
            if col in df.columns:
                self.baseline_means[col] = float(df[col].mean())

        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """Transform DataFrame into normalized 9D feature matrix."""
        df_feat = self.compute_feature_dataframe(df)
        X = df_feat[self.feature_names].to_numpy(dtype=np.float64)
        if self.is_fitted:
            return self.scaler.transform(X)
        return X

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        return self.fit(df).transform(df)

    def create_sequences(self, arr: np.ndarray, window_size: Optional[int] = None) -> np.ndarray:
        """
        Generate sliding sequence array of shape (N - W + 1, W, D).
        """
        w = window_size or self.window_size
        if len(arr) < w:
            return np.empty((0, w, arr.shape[1] if arr.ndim > 1 else 1), dtype=np.float32)

        seqs = []
        for i in range(len(arr) - w + 1):
            seqs.append(arr[i : i + w])
        return np.array(seqs, dtype=np.float32)

    def update(
        self,
        station_id: str,
        timestamp: Any,
        temperature: float,
        pressure: float,
        humidity: float,
    ) -> PreprocessorResult:
        """
        Ingest single real-time observation, update station buffer, compute 9D features,
        and generate scaled feature vector and sequence tensor.
        """
        buf = self.get_or_create_station(station_id)
        buf.append(timestamp, temperature, pressure, humidity)

        # 1. Compute delta features
        n = len(buf)
        if n >= 2:
            dt = float(temperature - buf.temperatures[-2])
            dp = float(pressure - buf.pressures[-2])
            drh = float(humidity - buf.humidities[-2])
        else:
            dt = 0.0
            dp = 0.0
            drh = 0.0

        # 2. Compute rolling standard deviations (last rolling_std_window steps)
        k = min(n, self.rolling_std_window)
        recent_t = list(buf.temperatures)[-k:]
        recent_p = list(buf.pressures)[-k:]
        recent_rh = list(buf.humidities)[-k:]

        if k > 1:
            std_t = float(np.std(recent_t))
            std_p = float(np.std(recent_p))
            std_rh = float(np.std(recent_rh))
        elif self.is_fitted and hasattr(self.scaler, "mean_") and len(self.scaler.mean_) >= 9:
            std_t = float(self.scaler.mean_[6])
            std_p = float(self.scaler.mean_[7])
            std_rh = float(self.scaler.mean_[8])
        else:
            std_t = 0.0
            std_p = 0.0
            std_rh = 0.0

        td = calculate_magnus_dew_point(temperature, humidity)

        raw_dict: Dict[str, float] = {
            "temperature": float(temperature),
            "pressure": float(pressure),
            "humidity": float(humidity),
            "temp_delta": dt,
            "press_delta": dp,
            "humid_delta": drh,
            "delta_temp": dt,
            "delta_pressure": dp,
            "delta_humidity": drh,
            "temp_roll_std": std_t,
            "press_roll_std": std_p,
            "humid_roll_std": std_rh,
            "dew_point": td,
        }

        # 3. Assemble 9D raw vector
        raw_vec = np.array([raw_dict[feat] for feat in self.feature_names], dtype=np.float64)

        if self.is_fitted:
            scaled_vec = self.scaler.transform(raw_vec.reshape(1, -1))[0]
        else:
            scaled_vec = raw_vec.copy()

        # 4. Generate 30-step sequence tensor for core features (T, P, RH)
        # Scaled using the first 3 components of scaler
        w = self.window_size
        seq_core = np.zeros((w, 3), dtype=np.float32)

        if n >= w:
            seq_t = list(buf.temperatures)[-w:]
            seq_p = list(buf.pressures)[-w:]
            seq_rh = list(buf.humidities)[-w:]
            raw_3d = np.column_stack([seq_t, seq_p, seq_rh])
            if self.is_fitted:
                # Use means and scales of the first 3 core features
                mean_3d = self.scaler.mean_[:3]
                scale_3d = self.scaler.scale_[:3]
                seq_core = ((raw_3d - mean_3d) / (scale_3d + 1e-8)).astype(np.float32)
            else:
                seq_core = raw_3d.astype(np.float32)
            is_warm = True
        else:
            # Cold start: Pad existing observations at the end
            if n > 0:
                raw_3d = np.column_stack([list(buf.temperatures), list(buf.pressures), list(buf.humidities)])
                if self.is_fitted:
                    mean_3d = self.scaler.mean_[:3]
                    scale_3d = self.scaler.scale_[:3]
                    scaled_existing = ((raw_3d - mean_3d) / (scale_3d + 1e-8)).astype(np.float32)
                else:
                    scaled_existing = raw_3d.astype(np.float32)
                seq_core[-n:] = scaled_existing
            is_warm = False

        return PreprocessorResult(
            station_id=station_id,
            timestamp=timestamp,
            scaled_vector=scaled_vec,
            raw_feature_dict=raw_dict,
            sequence_tensor=seq_core,
            recent_temperatures=list(buf.temperatures),
            recent_pressures=list(buf.pressures),
            recent_humidities=list(buf.humidities),
            buffer_length=n,
            is_warm=is_warm,
        )

    def save(self, filepath: Union[str, Path]) -> None:
        """Persist scaler and configuration to disk."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "version": "1.0.0",
            "scaler": self.scaler,
            "feature_names": self.feature_names,
            "window_size": self.window_size,
            "rolling_std_window": self.rolling_std_window,
            "is_fitted": self.is_fitted,
            "baseline_means": self.baseline_means,
        }
        joblib.dump(artifact, path)

    def load(self, filepath: Union[str, Path]) -> "DataPreprocessor":
        """Load scaler artifact from disk."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Preprocessor artifact not found at {path}")
        artifact = joblib.load(path)
        self.scaler = artifact["scaler"]
        self.feature_names = artifact.get("feature_names", list(FEATURE_NAMES))
        self.window_size = artifact.get("window_size", 30)
        self.rolling_std_window = artifact.get("rolling_std_window", 6)
        self.is_fitted = artifact.get("is_fitted", True)
        self.baseline_means = artifact.get("baseline_means", self.baseline_means)
        return self


# Backward-compatible alias
Preprocessor = DataPreprocessor
