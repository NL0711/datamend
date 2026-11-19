"""
backend/app/ml/tier3_multivariate.py
Tier 3: Multivariate Thermodynamic Consistency & Mahalanobis Distance Engine.

Evaluates:
1. Clausius-Clapeyron Magnus-Tetens dew-point physical consistency (T_d <= T + 0.5°C).
2. Regularized Mahalanobis distance D_M^2 against Chi-square CDF (df=3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import joblib
import numpy as np
import pandas as pd
from scipy.stats import chi2

logger = logging.getLogger(__name__)

# WMO Magnus-Tetens physical constants
MAGNUS_A = 6.112  # hPa
MAGNUS_B = 17.67
MAGNUS_C = 243.5  # °C
DEW_POINT_TOLERANCE = 0.5  # °C
THERMO_DISCREPANCY_SCALE = 3.0  # °C for score saturation


@dataclass
class Tier3Result:
    """Detailed output schema for Tier 3 Multivariate analysis."""
    is_valid: bool
    dew_point: float
    dew_point_diff: float  # T_d - T
    thermo_violation: bool
    thermo_score: float
    mahalanobis_distance: float
    mahalanobis_sq: float
    mahalanobis_score: float  # Chi-square CDF p-value
    tier3_score: float
    multivariate_score: float = 0.0  # Alias for tier3_score
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.multivariate_score == 0.0 and self.tier3_score != 0.0:
            self.multivariate_score = self.tier3_score
        if not self.metadata and self.diagnostics:
            self.metadata = dict(self.diagnostics)
            self.metadata["dew_point"] = self.dew_point
            self.metadata["thermo_violation"] = self.thermo_violation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "dew_point": round(self.dew_point, 2),
            "dew_point_diff": round(self.dew_point_diff, 2),
            "thermo_violation": self.thermo_violation,
            "thermo_score": round(self.thermo_score, 4),
            "mahalanobis_distance": round(self.mahalanobis_distance, 4),
            "mahalanobis_sq": round(self.mahalanobis_sq, 4),
            "mahalanobis_score": round(self.mahalanobis_score, 4),
            "tier3_score": round(self.tier3_score, 4),
            "multivariate_score": round(self.multivariate_score, 4),
            "diagnostics": self.diagnostics,
            "metadata": self.metadata,
        }


def calculate_dew_point(temperature: float, humidity: float) -> float:
    """
    Calculate dew-point temperature (°C) using Magnus-Tetens approximation.
    Safeguards:
    - Clamps humidity to [0.01, 104.0]% to prevent log of non-positive numbers.
    - Clamps temperature to >= -240.0°C to prevent division by zero in (T + 243.5).
    """
    t = max(float(temperature), -240.0)
    rh = np.clip(float(humidity), 0.01, 104.0)

    gamma = (MAGNUS_B * t) / (t + MAGNUS_C) + np.log(rh / 100.0)
    denom = MAGNUS_B - gamma
    if abs(denom) < 1e-6:
        return t

    td = (MAGNUS_C * gamma) / denom
    return float(td)


def evaluate_thermodynamic_consistency(
    temperature: float, humidity: float, tolerance: float = DEW_POINT_TOLERANCE
) -> Tuple[bool, float, float, float]:
    """
    Evaluate thermodynamic physical consistency (T_d <= T + tolerance).

    Returns:
        (is_consistent, dew_point, dew_point_diff, thermo_score)
    """
    td = calculate_dew_point(temperature, humidity)
    diff = td - temperature
    violation = diff > tolerance
    discrepancy = max(0.0, diff - tolerance)
    thermo_score = min(1.0, discrepancy / THERMO_DISCREPANCY_SCALE)
    return not violation, td, diff, float(thermo_score)


class Tier3MultivariateDetector:
    """
    Tier 3 Multivariate Detector combining Clausius-Clapeyron physical constraints
    and regularized Mahalanobis distance evaluated against the Chi-square CDF.
    """

    def __init__(
        self,
        mean: Optional[np.ndarray] = None,
        covariance: Optional[np.ndarray] = None,
        regularization_lambda: float = 1e-5,
    ) -> None:
        self.features = ["temperature", "pressure", "humidity"]
        self.df = 3
        self.reg_lambda = regularization_lambda
        self.mean: Optional[np.ndarray] = None
        self.covariance: Optional[np.ndarray] = None
        self.inv_covariance: Optional[np.ndarray] = None
        self.fitted_samples: int = 0

        if mean is not None and covariance is not None:
            self._set_parameters(mean, covariance)

    def _set_parameters(self, mean: np.ndarray, covariance: np.ndarray) -> None:
        self.mean = np.asarray(mean, dtype=np.float64).reshape(3,)
        self.covariance = np.asarray(covariance, dtype=np.float64).reshape(3, 3)

        # Regularize covariance matrix to prevent singularity
        cov_reg = self.covariance + self.reg_lambda * np.eye(3)
        try:
            self.inv_covariance = np.linalg.inv(cov_reg)
        except np.linalg.LinAlgError:
            logger.warning("Singular covariance matrix encountered. Using pseudo-inverse.")
            self.inv_covariance = np.linalg.pinv(cov_reg)

    def fit(self, df: pd.DataFrame) -> "Tier3MultivariateDetector":
        """Fit empirical mean vector and covariance matrix on clean baseline telemetry."""
        for feat in self.features:
            if feat not in df.columns:
                raise ValueError(f"Required feature '{feat}' not present in DataFrame.")

        clean_df = df[self.features].dropna()
        if len(clean_df) < 10:
            raise ValueError(f"Insufficient samples to fit Tier 3 Multivariate Detector (n={len(clean_df)}).")

        data = clean_df.to_numpy(dtype=np.float64)
        mean = np.mean(data, axis=0)
        covariance = np.cov(data, rowvar=False)
        self.fitted_samples = len(clean_df)
        self._set_parameters(mean, covariance)
        logger.info("Fitted Tier 3 Multivariate Detector on %d samples.", self.fitted_samples)
        return self

    def save(self, filepath: Union[str, Path]) -> None:
        """Persist fitted model parameters to joblib file."""
        if self.mean is None or self.covariance is None or self.inv_covariance is None:
            raise RuntimeError("Cannot save unfitted Tier 3 Multivariate Detector.")

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "version": "1.0.0",
            "features": self.features,
            "mean": self.mean,
            "covariance": self.covariance,
            "inv_covariance": self.inv_covariance,
            "df": self.df,
            "regularization_lambda": self.reg_lambda,
            "fitted_samples": self.fitted_samples,
        }
        joblib.dump(artifact, path)
        logger.info("Saved Tier 3 Mahalanobis artifact to %s", path)

    @classmethod
    def load(cls, filepath: Union[str, Path]) -> "Tier3MultivariateDetector":
        """Load fitted model artifact from joblib file."""
        detector = cls() if isinstance(cls, type) else cls
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Model artifact not found at {path}")

        artifact = joblib.load(path)
        cov = artifact.get("covariance", artifact.get("cov"))
        detector._set_parameters(artifact["mean"], cov)
        detector.features = artifact.get("features", detector.features)
        detector.reg_lambda = artifact.get("regularization_lambda", detector.reg_lambda)
        detector.fitted_samples = artifact.get("fitted_samples", 0)
        return detector

    @classmethod
    def load_from_file(cls, filepath: Union[str, Path]) -> "Tier3MultivariateDetector":
        return cls.load(filepath)

    def evaluate_mahalanobis(
        self, temperature: float, pressure: float, humidity: float
    ) -> Tuple[float, float, float]:
        """
        Calculate Mahalanobis distance D_M, D_M^2, and Chi-square CDF p-value.
        """
        if self.mean is None or self.inv_covariance is None:
            # Default baseline fallback if not fitted yet
            mean_default = np.array([22.0, 1013.25, 55.0])
            std_default = np.array([5.0, 10.0, 20.0])
            z = (np.array([temperature, pressure, humidity]) - mean_default) / std_default
            d_sq = float(np.sum(z ** 2))
            d_m = float(np.sqrt(d_sq))
            p_val = float(chi2.cdf(d_sq, df=self.df))
            return d_m, d_sq, p_val

        x = np.array([temperature, pressure, humidity], dtype=np.float64)
        delta = x - self.mean
        d_sq = float(np.dot(np.dot(delta, self.inv_covariance), delta))
        d_sq = max(0.0, d_sq)
        d_m = float(np.sqrt(d_sq))
        p_val = float(chi2.cdf(d_sq, df=self.df))
        return d_m, d_sq, p_val

    def score_observation(
        self, temperature: float, pressure: float, humidity: float
    ) -> Tier3Result:
        """Score a single incoming AWS observation across thermodynamic and covariance checks."""
        # Check for NaN / invalid numbers
        if any(v is None or np.isnan(v) or np.isinf(v) for v in (temperature, pressure, humidity)):
            return Tier3Result(
                is_valid=False,
                dew_point=0.0,
                dew_point_diff=0.0,
                thermo_violation=False,
                thermo_score=0.0,
                mahalanobis_distance=0.0,
                mahalanobis_sq=0.0,
                mahalanobis_score=0.0,
                tier3_score=0.0,
                multivariate_score=0.0,
                diagnostics={"error": "NaN or Inf values encountered in input features"},
                metadata={"error": "NaN or Inf values encountered"},
            )

        # 1. Thermodynamic Clausius-Clapeyron check
        is_consistent, td, diff, thermo_score = evaluate_thermodynamic_consistency(
            temperature, humidity
        )

        # 2. Mahalanobis distance & Chi-square CDF
        d_m, d_sq, p_val = self.evaluate_mahalanobis(temperature, pressure, humidity)
        # Calibrate anomaly score: normal points within 99% confidence ellipsoid (p_val < 0.99) have score = 0.0
        # Points exceeding 99th percentile scale smoothly to 1.0
        if p_val < 0.99:
            mahal_score = 0.0
        else:
            mahal_score = min(1.0, (p_val - 0.99) / 0.01)

        # 3. Unified Tier 3 score (thermodynamic Clausius-Clapeyron violation or extreme multivariate covariance distance)
        tier3_score = max(thermo_score, mahal_score)

        diag = {
            "dew_point_c": round(td, 2),
            "dew_point": round(td, 2),
            "is_thermodynamic_consistent": is_consistent,
            "thermo_violation": not is_consistent,
            "mahalanobis_distance": round(d_m, 4),
            "mahalanobis_p_value": round(mahal_score, 4),
        }

        return Tier3Result(
            is_valid=True,
            dew_point=td,
            dew_point_diff=diff,
            thermo_violation=not is_consistent,
            thermo_score=thermo_score,
            mahalanobis_distance=d_m,
            mahalanobis_sq=d_sq,
            mahalanobis_score=mahal_score,
            tier3_score=tier3_score,
            multivariate_score=tier3_score,
            diagnostics=diag,
            metadata=diag,
        )

    def evaluate(
        self, temperature: float, pressure: float, humidity: float
    ) -> Tier3Result:
        """Alias for score_observation."""
        return self.score_observation(temperature, pressure, humidity)

    def score_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Batch scoring over pandas DataFrame."""
        results = []
        for _, row in df.iterrows():
            res = self.score_observation(
                float(row["temperature"]),
                float(row["pressure"]),
                float(row["humidity"]),
            )
            results.append(res.to_dict())
        return pd.DataFrame(results)


# Backward-compatible alias
Tier3Multivariate = Tier3MultivariateDetector
