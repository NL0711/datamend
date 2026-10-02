"""
backend/app/ml/tier2_point_ml.py
Tier 2: Point ML Anomaly Detector using Scikit-Learn Isolation Forest.

Calibrates raw decision function into normalized anomaly score S_point in [0, 1]
via logistic sigmoid mapping.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)


class IsolationForestPointDetector:
    """
    Tier 2 Point Anomaly Detector based on Isolation Forest with calibrated scoring.
    """

    def __init__(
        self,
        n_estimators: int = 100,
        contamination: float = 0.01,
        random_state: int = 42,
        kappa: float = 15.0,
        tau: float = -0.05,
        feature_names: Optional[List[str]] = None,
    ):
        self.n_estimators = n_estimators
        self.contamination = contamination
        self.random_state = random_state
        self.kappa = kappa
        self.tau = tau
        self.feature_names = feature_names or [
            "temperature", "pressure", "humidity",
            "temp_delta", "press_delta", "humid_delta",
            "temp_roll_std", "press_roll_std", "humid_roll_std"
        ]
        self.model: Optional[IsolationForest] = None
        self.background_sample: Optional[np.ndarray] = None
        self.is_fitted: bool = False

    def fit(self, X: np.ndarray) -> "IsolationForestPointDetector":
        """Fit Isolation Forest on scaled training feature matrix."""
        if X.ndim != 2:
            raise ValueError(f"Expected 2D array for fitting, got shape {X.shape}")

        self.model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.model.fit(X)
        self.is_fitted = True

        # Extract background sample for SHAP (up to 100 samples)
        n_bg = min(100, len(X))
        rng = np.random.default_rng(self.random_state)
        idx = rng.choice(len(X), n_bg, replace=False)
        self.background_sample = X[idx]

        logger.info("Fitted Isolation Forest point detector on %d samples.", len(X))
        return self

    def _calibrate_scores(self, raw_decision: np.ndarray) -> np.ndarray:
        """
        Map decision_function to [0, 1] using logistic sigmoid.
        Decision function > 0 is inlier (normal) -> low anomaly score.
        Decision function < 0 is outlier (anomaly) -> high anomaly score.
        """
        # S = 1 / (1 + exp(kappa * (decision_function - tau)))
        exponent = np.clip(self.kappa * (raw_decision - self.tau), -50.0, 50.0)
        calibrated = 1.0 / (1.0 + np.exp(exponent))
        return np.clip(calibrated, 0.0, 1.0)

    def predict_score(self, X: np.ndarray) -> Union[float, np.ndarray]:
        """
        Predict continuous calibrated anomaly score in [0, 1].
        Accepts 1D vector (returns float) or 2D batch array (returns ndarray).
        """
        if self.model is None or not self.is_fitted:
            # Fallback for uninitialized model: heuristic based on vector norm
            if X.ndim == 1:
                norm = float(np.linalg.norm(X))
                return float(np.clip(norm / 15.0, 0.0, 1.0))
            norms = np.linalg.norm(X, axis=1)
            return np.clip(norms / 15.0, 0.0, 1.0)

        is_single = (X.ndim == 1)
        X_2d = X.reshape(1, -1) if is_single else X

        raw_scores = self.model.decision_function(X_2d)
        calibrated = self._calibrate_scores(raw_scores)

        if is_single:
            return float(calibrated[0])
        return calibrated

    def predict_score_single(self, z: np.ndarray) -> float:
        """Score single observation feature vector."""
        res = self.predict_score(z)
        return float(res)

    def save(self, filepath: Union[str, Path]) -> None:
        """Persist fitted Isolation Forest model to disk."""
        if self.model is None or not self.is_fitted:
            raise RuntimeError("Cannot save unfitted IsolationForestPointDetector.")

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "version": "1.0.0",
            "model": self.model,
            "feature_names": self.feature_names,
            "background_sample": self.background_sample,
            "kappa": self.kappa,
            "tau": self.tau,
            "n_estimators": self.n_estimators,
            "contamination": self.contamination,
        }
        joblib.dump(artifact, path)
        logger.info("Saved Isolation Forest artifact to %s", path)

    def load(self, filepath: Union[str, Path]) -> "IsolationForestPointDetector":
        """Load fitted model artifact from disk."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Model artifact not found at {path}")

        artifact = joblib.load(path)
        self.model = artifact["model"]
        self.feature_names = artifact.get("feature_names", self.feature_names)
        self.background_sample = artifact.get("background_sample")
        self.kappa = artifact.get("kappa", self.kappa)
        self.tau = artifact.get("tau", self.tau)
        self.n_estimators = artifact.get("n_estimators", self.n_estimators)
        self.contamination = artifact.get("contamination", self.contamination)
        self.is_fitted = True
        return self


# Backward-compatible aliases
PointAnomalyDetector = IsolationForestPointDetector
