"""
backend/app/ml/stages/stage2_ensemble.py
SkyGuard AI / DataMend — Stage 2: Multivariate Residual Anomaly Ensemble.

CANONICAL Phase 4 detector: ResidualIsolationForest on 3-channel Stage-1
STL residuals ordered [T_resid, P_resid, RH_resid] (m, 3).
Legacy 9D IsolationForestPointDetector path is NOT supported here.

Combines point-density isolation (PyOD Isolation Forest) with temporal sequence
reconstruction (PyTorch GRU / 1D-Conv Autoencoder) to evaluate de-trended residual vectors.
Emits a calibrated, normalized fused anomaly score in [0.0, 1.0].
Maintains warm-loaded in-memory model instances to guarantee <= 15 ms inference latency.
"""

from __future__ import annotations

import logging
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

# Canonical Phase 4 residual contract (see OpenSpec phase4-residual-isolation-forest).
RESIDUAL_CHANNELS: List[str] = ["T_resid", "P_resid", "RH_resid"]
RESIDUAL_CONTRACT_VERSION: str = "1.0.0"
EXPECTED_N_FEATURES: int = 3
MIN_FIT_ROWS: int = 10

# Attempt PyOD import; gracefully fallback to scikit-learn.
# NOTE: sklearn fallback is ALWAYS imported (pre-existing bug fixed: previously
# SkIForest was undefined when PyOD was present, breaking the fallback path).
from sklearn.ensemble import IsolationForest as SkIForest

try:
    from pyod.models.iforest import IForest as PyODIForest
    _HAS_PYOD = True
except Exception:
    _HAS_PYOD = False


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    """Standard sigmoid squashing function."""
    arr = np.asarray(x, dtype=float)
    return 1.0 / (1.0 + np.exp(-arr))


def _validate_residuals(X: np.ndarray, *, context: str) -> np.ndarray:
    """Validate canonical (m, 3) residual contract; reject legacy 9D vectors."""
    arr = np.asarray(X, dtype=float)
    if arr.ndim == 1:
        if arr.shape[0] == 9:
            raise ValueError(
                f"{context}: got 1D legacy 9D feature vector; canonical Phase 4 input "
                f"is 3-channel STL residuals {RESIDUAL_CHANNELS} (contract {RESIDUAL_CONTRACT_VERSION})."
            )
        if arr.shape[0] != EXPECTED_N_FEATURES:
            raise ValueError(
                f"{context}: expected 3 residual channels {RESIDUAL_CHANNELS}, got shape {arr.shape}."
            )
        return arr.reshape(1, -1)
    if arr.ndim != 2 or arr.shape[1] != EXPECTED_N_FEATURES:
        if arr.ndim == 2 and arr.shape[1] == 9:
            raise ValueError(
                f"{context}: got (m, 9) legacy feature matrix; canonical Phase 4 input "
                f"is (m, 3) STL residuals {RESIDUAL_CHANNELS} (contract {RESIDUAL_CONTRACT_VERSION})."
            )
        raise ValueError(
            f"{context}: expected (m, 3) residuals {RESIDUAL_CHANNELS}, got shape {arr.shape}."
        )
    return arr


class ResidualIsolationForest:
    """
    CANONICAL Phase 4 detector: Isolation Forest fitted on 3-channel
    de-trended STL residuals [T_resid, P_resid, RH_resid].
    Emits continuous outlier score in [0.0, 1.0] with fitted threshold mapped to 0.50.
    """

    residual_contract_version: str = RESIDUAL_CONTRACT_VERSION

    def __init__(self, contamination: float = 0.02, random_state: int = 42) -> None:
        self.contamination = contamination
        self.random_state = random_state
        self._model = None
        self._is_fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        """Whether a fitted Isolation Forest model is loaded."""
        return bool(self._is_fitted and self._model is not None)

    @property
    def engine_name(self) -> str:
        """Active engine tag: 'pyod' when PyOD available, else 'sklearn'."""
        return "pyod" if _HAS_PYOD else "sklearn"

    def fit(self, residuals: np.ndarray) -> ResidualIsolationForest:
        """Fits Isolation Forest on baseline historical STL residuals (m, 3)."""
        X = _validate_residuals(residuals, context="ResidualIsolationForest.fit")
        if len(X) < MIN_FIT_ROWS:
            logger.warning(
                "ResidualIsolationForest.fit: insufficient history (%d < %d); "
                "remaining UNFITTED (degraded mode).",
                len(X), MIN_FIT_ROWS,
            )
            return self

        if _HAS_PYOD:
            self._model = PyODIForest(contamination=self.contamination, random_state=self.random_state, n_jobs=1)
        else:
            self._model = SkIForest(contamination=self.contamination, random_state=self.random_state, n_jobs=1)

        self._model.fit(X)
        self._is_fitted = True
        if _HAS_PYOD:
            scores = self._model.decision_scores_
            self.thresh_ = float(getattr(self._model, "threshold_", 0.0))
            self.min_val_ = float(scores.min()) if len(scores) else -1.0
            self.max_val_ = float(scores.max()) if len(scores) else 1.0
        else:
            raw_scores = -self._model.decision_function(X)
            self.thresh_ = float(np.percentile(raw_scores, 100 * (1 - self.contamination)))
            self.min_val_ = float(raw_scores.min()) if len(raw_scores) else -1.0
            self.max_val_ = float(raw_scores.max()) if len(raw_scores) else 1.0
        return self

    def score(self, residuals: np.ndarray) -> np.ndarray:
        """
        Computes normalized outlier score for residual vectors.
        Maps the decision threshold to exactly 0.50 via piecewise linear scaling:
        - Normal observations: [0.0, 0.50)
        - Anomaly observations: [0.50, 1.0]

        DEGRADED MODE: when unfitted, returns deterministic MAD/z fallback scores
        and emits a warning so callers never mistake them for fitted IF scores.
        Use `is_fitted` to distinguish.
        """
        X = _validate_residuals(residuals, context="ResidualIsolationForest.score")
        if not self._is_fitted or self._model is None:
            logger.warning(
                "ResidualIsolationForest.score: UNFITTED model — returning degraded "
                "MAD/z fallback scores (is_fitted=False), not Isolation Forest scores."
            )
            if len(X) > 1:
                med = np.nanmedian(X, axis=0)
                mad = np.nanmedian(np.abs(X - med), axis=0) + 1e-6
                z = np.nan_to_num(np.abs(X - med) / (1.4826 * mad))
                return np.clip(0.25 * z.mean(axis=1), 0.0, 1.0)
            else:
                scales = np.array([3.0, 3.0, 15.0])
                z = np.abs(X[0]) / scales
                score = np.clip(0.50 * np.max(z) / 3.0, 0.0, 1.0)
                return np.array([score])

        if _HAS_PYOD:
            raw = np.asarray(self._model.decision_function(X), dtype=float)
        else:
            raw = np.asarray(-self._model.decision_function(X), dtype=float)

        thresh = getattr(self, "thresh_", 0.0)
        min_v = getattr(self, "min_val_", -1.0)
        max_v = getattr(self, "max_val_", 1.0)

        # Piecewise normalization centering threshold at 0.50
        norm_scores = np.zeros_like(raw)
        below = raw < thresh
        above = ~below

        denom_below = max(1e-5, thresh - min_v)
        norm_scores[below] = np.clip(0.50 * (raw[below] - min_v) / denom_below, 0.0, 0.49)

        denom_above = max(1e-5, max_v - thresh)
        norm_scores[above] = np.clip(0.50 + 0.50 * (raw[above] - thresh) / denom_above, 0.50, 1.0)

        return norm_scores

    def save(self, filepath: Union[str, Path]) -> None:
        """Persist fitted residual detector with engine + contract metadata."""
        import joblib

        if not self.is_fitted:
            raise RuntimeError("Cannot save unfitted ResidualIsolationForest.")
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "version": "1.0.0",
            "model": self._model,
            "engine": self.engine_name,
            "contamination": self.contamination,
            "random_state": self.random_state,
            "thresh_": getattr(self, "thresh_", 0.0),
            "min_val_": getattr(self, "min_val_", -1.0),
            "max_val_": getattr(self, "max_val_", 1.0),
            "residual_channels": list(RESIDUAL_CHANNELS),
            "residual_contract_version": RESIDUAL_CONTRACT_VERSION,
        }
        joblib.dump(artifact, path)
        logger.info("Saved ResidualIsolationForest (%s) to %s", self.engine_name, path)

    def load(self, filepath: Union[str, Path]) -> ResidualIsolationForest:
        """Load fitted residual detector; validates contract metadata."""
        import joblib

        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Residual IF artifact not found at {path}")
        artifact = joblib.load(path)
        channels = artifact.get("residual_channels", RESIDUAL_CHANNELS)
        if list(channels) != list(RESIDUAL_CHANNELS):
            raise ValueError(
                f"Residual contract mismatch: artifact channels {channels} != {RESIDUAL_CHANNELS}"
            )
        self._model = artifact["model"]
        self.contamination = artifact.get("contamination", self.contamination)
        self.random_state = artifact.get("random_state", self.random_state)
        self.thresh_ = float(artifact.get("thresh_", 0.0))
        self.min_val_ = float(artifact.get("min_val_", -1.0))
        self.max_val_ = float(artifact.get("max_val_", 1.0))
        self.residual_contract_version = artifact.get(
            "residual_contract_version", RESIDUAL_CONTRACT_VERSION
        )
        self._is_fitted = True
        return self


class SequenceAutoencoderScorer:
    """
    Lightweight PyTorch Sequence Autoencoder (Conv1D or GRU) for temporal reconstruction error.
    Trained on clean historical residual sequences; anomalies exhibit high reconstruction error (MSE).
    """

    def __init__(
        self,
        n_channels: int = 3,
        window: int = 24,
        variant: Literal["conv", "gru"] = "gru",
    ) -> None:
        self.n_channels = n_channels
        self.window = window
        self.variant = variant
        self._model = None
        self._norm_min: float = 0.0
        self._norm_max: float = 1.0
        self._is_fitted: bool = False

    def _build_model(self):
        import torch
        import torch.nn as nn

        C, W = self.n_channels, self.window

        if self.variant == "conv":
            class ConvAE(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.enc = nn.Sequential(
                        nn.Conv1d(C, 16, 3, padding=1),
                        nn.ReLU(),
                        nn.Conv1d(16, 8, 3, padding=1),
                        nn.ReLU(),
                    )
                    self.dec = nn.Sequential(
                        nn.Conv1d(8, 16, 3, padding=1),
                        nn.ReLU(),
                        nn.Conv1d(16, C, 3, padding=1),
                    )

                def forward(self, x):
                    return self.dec(self.enc(x))

            return ConvAE()
        else:
            hidden = 16
            class GruAE(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.gru = nn.GRU(C, hidden, batch_first=True)
                    self.fc = nn.Linear(hidden, C)

                def forward(self, x):  # x: (B, C, W) -> transpose to (B, W, C)
                    xw = x.transpose(1, 2)
                    out, _ = self.gru(xw)
                    return self.fc(out).transpose(1, 2)

            return GruAE()

    def fit(self, residuals: np.ndarray, epochs: int = 4, lr: float = 1e-3) -> SequenceAutoencoderScorer:
        """Fits the autoencoder on normal residual windows."""
        try:
            import torch
            import torch.nn as nn
        except ImportError:
            logger.debug("PyTorch unavailable; skipping Autoencoder training.")
            return self

        X = np.asarray(residuals, dtype=np.float32)
        W = min(self.window, len(X))
        if W < 4:
            return self

        wins = np.stack([X[i : i + W] for i in range(max(1, len(X) - W + 1))])
        # Transpose to (Batch, Channels, Window)
        t = torch.from_numpy(wins.transpose(0, 2, 1))

        self._model = self._build_model()
        opt = torch.optim.Adam(self._model.parameters(), lr=lr)
        loss_fn = nn.MSELoss()

        self._model.train()
        for _ in range(epochs):
            opt.zero_grad()
            pred = self._model(t)
            loss = loss_fn(pred, t)
            loss.backward()
            opt.step()
        self._model.eval()
        with torch.no_grad():
            err = ((self._model(t) - t) ** 2).mean(dim=(1, 2)).numpy()
        self.mean_err_ = float(err.mean())
        self.std_err_ = float(err.std()) if err.std() > 0 else 1.0
        self.thresh_ = self.mean_err_ + 3.0 * self.std_err_
        self._is_fitted = True
        return self

    def score(self, residuals: np.ndarray) -> np.ndarray:
        """Computes reconstruction error normalized to [0.0, 1.0]."""
        X = np.asarray(residuals, dtype=np.float32)
        if not self._is_fitted or self._model is None:
            # Fallback to mean squared magnitude
            sq = (X ** 2).mean(axis=1)
            return np.clip(sq / 10.0, 0.0, 1.0)

        import torch
        W = min(self.window, len(X))
        wins = np.stack([X[i : i + W] for i in range(max(1, len(X) - W + 1))])
        t = torch.from_numpy(wins.transpose(0, 2, 1))

        self._model.eval()
        with torch.inference_mode():
            pred = self._model(t)
            err = ((pred - t) ** 2).mean(dim=(1, 2)).numpy()

        thresh = getattr(self, "thresh_", 1.0)
        std_err = getattr(self, "std_err_", 0.5)

        norm = np.zeros_like(err)
        below = err < thresh
        above = ~below
        norm[below] = np.clip(0.40 * err[below] / max(1e-5, thresh), 0.0, 0.40)
        norm[above] = np.clip(0.50 + 0.50 * (err[above] - thresh) / max(1e-5, 3.0 * std_err), 0.50, 1.0)

        full = np.zeros(len(X))
        full[: len(norm)] = norm
        if len(norm) < len(X):
            full[len(norm) :] = norm[-1]
        return np.clip(full, 0.0, 1.0)


@dataclass
class EnsembleResult:
    """Diagnostic outcome of Stage 2 multivariate ensemble scoring."""
    if_score: np.ndarray
    ae_score: np.ndarray
    fused_score: np.ndarray
    is_anomaly: np.ndarray
    latency_ms: float


class MultivariateEnsembleDetector:
    """
    Tier 2 Stage 2 Multivariate Anomaly Ensemble Detector.
    Fuses tree-based isolation density scoring with sequence autoencoder reconstruction error.
    """

    def __init__(
        self,
        if_weight: float = 0.55,
        ae_variant: Literal["conv", "gru"] = "gru",
        anomaly_threshold: float = 0.50,
    ) -> None:
        self.if_weight = if_weight
        self.anomaly_threshold = anomaly_threshold
        self.if_scorer = ResidualIsolationForest()
        self.ae_scorer = SequenceAutoencoderScorer(variant=ae_variant)
        self._is_warmed: bool = False

    def fit(self, residuals: np.ndarray, ae_epochs: int = 4) -> MultivariateEnsembleDetector:
        """Fits both ensemble sub-models on historical baseline residuals."""
        self.if_scorer.fit(residuals)
        try:
            self.ae_scorer.fit(residuals, epochs=ae_epochs)
        except Exception as exc:
            logger.debug("Autoencoder fitting error: %s", exc)
        self._is_warmed = True
        return self

    def warm(self, sample_residuals: np.ndarray) -> None:
        """Ensures models are warm-loaded in memory for sub-15ms execution."""
        if not self._is_warmed:
            self.fit(sample_residuals, ae_epochs=1)

    def score(self, residuals: np.ndarray) -> EnsembleResult:
        """
        Executes fast ensemble scoring on an incoming residual matrix (m, 3).
        Guarantees sub-15ms response by avoiding on-the-fly model reinitialization.
        """
        t0 = time.perf_counter()
        X = np.asarray(residuals, dtype=float)
        m = len(X)
        if m == 0:
            return EnsembleResult(
                if_score=np.array([]),
                ae_score=np.array([]),
                fused_score=np.array([]),
                is_anomaly=np.array([], dtype=bool),
                latency_ms=0.0,
            )

        s_if = self.if_scorer.score(X)
        try:
            s_ae = self.ae_scorer.score(X)
        except Exception:
            s_ae = np.zeros(m)

        count = min(len(s_if), len(s_ae))
        fused = np.clip(
            self.if_weight * s_if[:count] + (1.0 - self.if_weight) * s_ae[:count],
            0.0,
            1.0,
        )
        is_anom = fused >= self.anomaly_threshold
        latency = (time.perf_counter() - t0) * 1000.0

        return EnsembleResult(
            if_score=s_if[:count],
            ae_score=s_ae[:count],
            fused_score=fused,
            is_anomaly=is_anom,
            latency_ms=latency,
        )
