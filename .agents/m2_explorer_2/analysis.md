# Milestone M2: Tier 3 Multivariate, Fusion Engine & Tier 4 Classifier Architectural Specification

**Agent**: `m2_explorer_2`  
**Milestone**: M2 — 5-Tier ML Pipeline Engine (Phases 7–8 of TODO.md)  
**Target Files**:
- `backend/app/ml/tier3_multivariate.py` (Thermodynamic consistency & Mahalanobis distance)
- `backend/app/ml/fusion.py` (Multi-tier fusion engine & confidence scoring)
- `backend/app/ml/tier4_classifier.py` (Fault taxonomy & front vs fault discrimination)
**Reference Specifications**: `PROJECT.md`, `ARCHITECTURE.md`, `GOAL.md`, `TODO.md`, `AGENTS.md`, `.agents/survey_spec_miner_2/report.md`

---

## 1. Executive Summary

In the SkyGuard AI 5-tier architecture, standard point outliers (Tier 2 Isolation Forest) and temporal reconstruction errors (Tier 2 Autoencoder) are insufficient on their own to detect coupled atmospheric anomalies or distinguish genuine meteorological weather fronts from sensor hardware failures. 

This document provides the complete mathematical foundations, algorithmic designs, software architectures, edge-case protections, and data contracts for:
1. **Tier 3 Multivariate Consistency Engine (`tier3_multivariate.py`)**: Evaluates thermodynamic equilibrium via the Clausius-Clapeyron Magnus-Tetens dew-point formula ($T_d \le T + 0.5^\circ\text{C}$) and statistical joint distributions via regularized Mahalanobis distance $D_M^2$ evaluated against the Chi-square CDF $F_{\chi^2(3)}(D_M^2)$, with persistence in `models/mahalanobis.joblib`.
2. **Multi-Tier Fusion Engine (`fusion.py`)**: Synthesizes evidence across all 5 tiers using a deterministic Tier 1 hard override, a calibrated convex combination ($w_1=0.25, w_{2\text{pt}}=0.20, w_{2\text{temp}}=0.25, w_3=0.30$), an inter-model concordance variance confidence metric $C_{\text{fused}} \in [0.10, 1.00]$, and standardized severity tier mapping (`NONE`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
3. **Tier 4 Fault Taxonomy Classifier (`tier4_classifier.py`)**: Maps multi-tier signals to 9 distinct fault classes (`NORMAL`, `SPIKE`, `DRIFT`, `FROZEN`, `DROPOUT`, `NOISE_BURST`, `MULTIVARIATE_INCONSISTENCY`, `DATA_CORRUPTION`, `METEOROLOGICAL_EXTREME`, `UNCERTAIN_EVENT`), specifically distinguishing genuine convective squall fronts (`is_fault=False`) from sensor hardware degradation (`is_fault=True`).

---

## 2. Tier 3: Multivariate Consistency Engine Specification (`tier3_multivariate.py`)

### 2.1 Thermodynamic Foundations & Magnus-Tetens Dew-Point Formulation

In atmospheric thermodynamics, saturation vapor pressure $e_s(T)$ is the maximum partial pressure of water vapor the atmosphere can sustain at dry-bulb temperature $T$ without condensation. It is governed by the Clausius-Clapeyron equation:
$$\frac{de_s}{dT} = \frac{L_v(T) \cdot e_s}{R_v \cdot T^2}$$

Using the Magnus-Tetens empirical approximation for meteorological operations ($T \in [-40^\circ\text{C}, +60^\circ\text{C}]$):
$$e_s(T) = a \cdot \exp\left( \frac{b \cdot T}{T + c} \right) \quad [\text{hPa}]$$
Where standard WMO constants are:
- $a = 6.112\text{ hPa}$ (saturation vapor pressure at $0^\circ\text{C}$)
- $b = 17.67$ (dimensionless empirical constant)
- $c = 243.5^\circ\text{C}$ (temperature offset parameter)

The actual ambient water vapor pressure $e$ is determined from Relative Humidity ($RH \in (0, 104\%]$):
$$e = e_s(T) \cdot \frac{\max(RH, 0.01)}{100.0}$$

By equating $e = e_s(T_d)$ and inverting for the dew-point temperature $T_d$:
$$\gamma(T, RH) = \frac{b \cdot T}{T + c} + \ln\left(\frac{\max(RH, 0.01)}{100.0}\right)$$
$$T_d(T, RH) = \frac{c \cdot \gamma(T, RH)}{b - \gamma(T, RH)} \quad [^\circ\text{C}]$$

#### Thermodynamic Physical Consistency Constraint:
Under standard physical equilibrium in free air:
$$T_d \le T + \epsilon_{\text{tol}}$$
Where $\epsilon_{\text{tol}} = 0.5^\circ\text{C}$ accounts for operational sensor calibration tolerance and slight local supersaturation ($RH \le 104\%$).

If $T_d > T + 0.5^\circ\text{C}$, the observation violates the second law of thermodynamics (unphysical supersaturation or sensor calibration failure). We define the physical discrepancy:
$$\Delta_{\text{thermo}} = \max\left(0.0, \; T_d - (T + \epsilon_{\text{tol}})\right)$$
$$S_{\text{thermo}} = \min\left(1.0, \; \frac{\Delta_{\text{thermo}}}{3.0}\right)$$
Where $\Delta_{\text{thermo}} \ge 3.0^\circ\text{C}$ results in maximal thermodynamic anomaly score $S_{\text{thermo}} = 1.0$.

---

### 2.2 Multivariate Mahalanobis Distance & Chi-Square CDF Formulation

The primary 3 meteorological variables $\mathbf{x} = [T, P, RH]^T \in \mathbb{R}^3$ exhibit strong physical cross-correlations (e.g. $T$ and $RH$ are strongly negatively correlated during diurnal heating).

Let:
- $\boldsymbol{\mu} = \mathbb{E}[\mathbf{x}] = [\mu_T, \mu_P, \mu_{RH}]^T \in \mathbb{R}^3$ (empirical mean vector on clean training data)
- $\boldsymbol{\Sigma} = \mathbb{E}[(\mathbf{x} - \boldsymbol{\mu})(\mathbf{x} - \boldsymbol{\mu})^T] \in \mathbb{R}^{3 \times 3}$ (empirical covariance matrix)

#### Regularized Inversion:
To protect against ill-conditioned or singular covariance matrices caused by constant/frozen sensor values during training:
$$\boldsymbol{\Sigma}_{\text{reg}} = \boldsymbol{\Sigma} + \lambda \mathbf{I}_3, \quad \lambda = 10^{-5}$$
$$\mathbf{V} = \boldsymbol{\Sigma}_{\text{reg}}^{-1}$$
If matrix inversion still fails due to zero determinant ($\det(\boldsymbol{\Sigma}) \le 10^{-12}$), the engine falls back gracefully to Moore-Penrose pseudo-inverse $\mathbf{V} = \text{pinv}(\boldsymbol{\Sigma})$.

#### Squared Mahalanobis Distance:
$$D_M^2(\mathbf{x}) = (\mathbf{x} - \boldsymbol{\mu})^T \mathbf{V} (\mathbf{x} - \boldsymbol{\mu})$$
$$D_M(\mathbf{x}) = \sqrt{\max(0.0, D_M^2(\mathbf{x}))}$$

#### Chi-Square Cumulative Distribution Function (CDF):
Under the null hypothesis that clean observations follow a 3-dimensional multivariate normal distribution $\mathcal{N}_3(\boldsymbol{\mu}, \boldsymbol{\Sigma})$, the squared Mahalanobis distance follows a Chi-square distribution with $k = 3$ degrees of freedom:
$$D_M^2 \sim \chi^2(3)$$

The cumulative probability (CDF) gives the statistical anomaly score $S_{\text{mahalanobis}} \in [0.0, 1.0]$:
$$S_{\text{mahalanobis}} = F_{\chi^2(3)}(D_M^2) = \frac{\gamma\left(\frac{3}{2}, \frac{D_M^2}{2}\right)}{\Gamma\left(\frac{3}{2}\right)} = \frac{1}{\sqrt{\pi}} \int_0^{D_M^2 / 2} t^{1/2} e^{-t} dt$$
Computed via `scipy.stats.chi2.cdf(D_M^2, df=3)`.

| $D_M^2$ Value | Chi-Square CDF $F_{\chi^2(3)}(D_M^2)$ | Meteorological Interpretation |
|---|---|---|
| $0.58$ | $0.10$ | Very typical observation near cluster center |
| $2.37$ | $0.50$ | Median nominal observation |
| $6.25$ | $0.90$ | Moderate atmospheric deviation |
| $7.81$ | $0.95$ | 95th percentile outlier boundary |
| $11.34$ | $0.99$ | High statistical anomaly (1% occurrence under nominal conditions) |
| $16.27$ | $0.999$ | Critical multivariate anomaly ($S_{\text{mahalanobis}} \approx 1.0$) |

---

### 2.3 Tier 3 Combined Score & Diagnostics

The combined Tier 3 score synthesizes thermodynamic and statistical deviations:
$$S_{\text{Tier3}} = \max\left( S_{\text{thermo}}, \; S_{\text{mahalanobis}} \right)$$

This formulation ensures that an explicit violation of atmospheric physics ($T_d > T + 0.5^\circ\text{C}$) triggers a high Tier 3 score immediately, while subtle joint covariance decoupling (e.g. high temperature paired with abnormally high barometric pressure) is captured by the Mahalanobis CDF.

```python
@dataclass
class Tier3Result:
    is_valid: bool
    dew_point: float
    dew_point_diff: float  # T_d - T
    thermo_violation: bool
    thermo_score: float
    mahalanobis_distance: float
    mahalanobis_sq: float
    mahalanobis_score: float  # Chi-square CDF p-value
    tier3_score: float
    diagnostics: Dict[str, Any]
```

---

### 2.4 Artifact Persistence & Training Specification

The Mahalanobis parameters are fitted on clean training baseline telemetry (`data/train_clean.csv`) and saved to `models/mahalanobis.joblib`.

#### Persisted Artifact Structure:
```python
{
    "version": "1.0.0",
    "features": ["temperature", "pressure", "humidity"],
    "mean": np.ndarray,          # shape: (3,), dtype: float64
    "covariance": np.ndarray,    # shape: (3, 3), dtype: float64
    "inv_covariance": np.ndarray,# shape: (3, 3), dtype: float64
    "df": 3,
    "regularization_lambda": 1e-5,
    "fitted_samples": int,
    "fit_timestamp": "2026-08-24T10:00:00Z",
    "stats": {
        "mean_T": float, "std_T": float,
        "mean_P": float, "std_P": float,
        "mean_RH": float, "std_RH": float,
        "corr_T_RH": float,
    }
}
```

---

### 2.5 Software Architecture & Implementation Blueprint (`tier3_multivariate.py`)

```python
"""
backend/app/ml/tier3_multivariate.py
Tier 3: Multivariate Thermodynamic Consistency & Mahalanobis Distance Engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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
    dew_point_diff: float
    thermo_violation: bool
    thermo_score: float
    mahalanobis_distance: float
    mahalanobis_sq: float
    mahalanobis_score: float
    tier3_score: float
    diagnostics: Dict[str, Any]

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
            "diagnostics": self.diagnostics,
        }


def calculate_dew_point(temperature: float, humidity: float) -> float:
    """
    Calculate dew-point temperature (°C) using Magnus-Tetens approximation.
    
    Safe guards:
    - Clamps humidity to [0.01, 100.0]% to prevent ln(0) or ln(negative).
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
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Model artifact not found at {path}")

        artifact = joblib.load(path)
        detector = cls(
            mean=artifact["mean"],
            covariance=artifact["covariance"],
            regularization_lambda=artifact.get("regularization_lambda", 1e-5),
        )
        detector.fitted_samples = artifact.get("fitted_samples", 0)
        return detector

    def evaluate_mahalanobis(
        self, temperature: float, pressure: float, humidity: float
    ) -> Tuple[float, float, float]:
        """
        Calculate Mahalanobis distance D_M, D_M^2, and Chi-square CDF p-value.
        """
        if self.mean is None or self.inv_covariance is None:
            # Fallback for uninitialized state
            return 0.0, 0.0, 0.0

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
        if any(np.isnan(v) or np.isinf(v) for v in (temperature, pressure, humidity)):
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
                diagnostics={"error": "NaN or Inf values encountered in input features"},
            )

        # 1. Thermodynamic Clausius-Clapeyron check
        is_consistent, td, diff, thermo_score = evaluate_thermodynamic_consistency(
            temperature, humidity
        )

        # 2. Mahalanobis distance & Chi-square CDF
        d_m, d_sq, mahal_score = self.evaluate_mahalanobis(temperature, pressure, humidity)

        # 3. Unified Tier 3 score
        tier3_score = max(thermo_score, mahal_score)

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
            diagnostics={
                "dew_point_c": round(td, 2),
                "is_thermodynamic_consistent": is_consistent,
                "mahalanobis_p_value": round(mahal_score, 4),
            },
        )

    def score_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Batch scoring over pandas DataFrame with vectorized acceleration."""
        results = []
        for _, row in df.iterrows():
            res = self.score_observation(
                float(row["temperature"]),
                float(row["pressure"]),
                float(row["humidity"]),
            )
            results.append(res.to_dict())
        return pd.DataFrame(results)
```

---

## 3. Multi-Tier Anomaly Fusion Engine Specification (`fusion.py`)

### 3.1 Mathematical Architecture & Convex Fusion Formulation

The anomaly fusion engine unifies evidence from deterministic quality control, point ML, temporal sequence modeling, and multivariate thermodynamics into a coherent inference decision.

#### Score Inputs:
- $S_{\text{Tier1\_hard}} \in \{0.0, 1.0\}$: Hard physics bound or data integrity failure (Range bound exceeded, NaN, zero variance frozen sensor).
- $S_{\text{Tier1\_soft}} \in [0.0, 1.0]$: Continuous rate-of-change or rolling deviation ratio.
- $S_{\text{point}} \in [0.0, 1.0]$: Tier 2 Isolation Forest normalized score.
- $S_{\text{temporal}} \in [0.0, 1.0]$: Tier 2 PyTorch Autoencoder reconstruction MSE normalized score.
- $S_{\text{Tier3}} \in [0.0, 1.0]$: Tier 3 Multivariate consistency score.

#### 1. Hard Deterministic Override:
If a fundamental physical impossibility or fatal data integrity failure is identified by Tier 1, the pipeline executes a hard override:
$$\text{If } S_{\text{Tier1\_hard}} == 1.0 \implies \begin{cases}
S_{\text{fused}} = 1.0 \\
\text{Severity} = \text{CRITICAL} \\
\text{override\_applied} = \text{True}
\end{cases}$$

#### 2. Weighted Convex Combination:
When no hard Tier 1 violation is present, the fused anomaly score is computed as a weighted linear combination:
$$S_{\text{fused}} = w_1 S_{\text{Tier1\_soft}} + w_{2\text{pt}} S_{\text{point}} + w_{2\text{temp}} S_{\text{temporal}} + w_3 S_{\text{Tier3}}$$
Where weights are strictly normalized:
$$w_1 = 0.25, \quad w_{2\text{pt}} = 0.20, \quad w_{2\text{temp}} = 0.25, \quad w_3 = 0.30 \quad \left(\sum w_i = 1.00\right)$$

$S_{\text{fused}}$ is strictly clamped to $[0.0, 1.0]$.

---

### 3.2 Model Concordance & Decision Confidence Formulation ($C_{\text{fused}}$)

Confidence represents the certainty of the system's assessment. It should be high ($C \approx 1.0$) when multiple independent models agree (whether all indicate normal or all indicate anomalous), and low ($C \le 0.50$) when models strongly conflict or when historical sequence context is insufficient (cold start).

#### Inter-Model Sample Variance:
Let the active ML and statistical tier scores be $\mathbf{s} = [S_{\text{point}}, S_{\text{temporal}}, S_{\text{Tier3}}]$ ($M = 3$ models).
$$\bar{s} = \frac{1}{M} \sum_{i=1}^M s_i$$
$$\sigma_s = \sqrt{\frac{1}{M} \sum_{i=1}^M (s_i - \bar{s})^2}$$

The maximum possible standard deviation among $M=3$ values bounded in $[0, 1]$ occurs at $[1.0, 0.0, 0.0]$, where $\sigma_{\max} = \frac{1}{\sqrt{3}} \approx 0.577$.
We define base model concordance:
$$C_{\text{concordance}} = 1.0 - \min\left(1.0, \; \sqrt{3} \cdot \sigma_s\right)$$

#### Historical Buffer Penalty:
When an AWS station cold-starts and fewer than $W = 30$ observations are buffered in memory:
$$\text{Penalty}_{\text{buffer}} = \begin{cases}
0.20 \cdot \left(1.0 - \frac{N}{30}\right) & \text{if } N < 30 \\
0.0 & \text{if } N \ge 30
\end{cases}$$

#### Total Calibrated Confidence:
$$C_{\text{fused}} = \text{clip}\left( C_{\text{concordance}} - \text{Penalty}_{\text{buffer}}, \; 0.10, \; 1.00 \right)$$
If a Tier 1 hard override occurred:
$$C_{\text{fused}} = \text{clip}\left( 1.00 - \text{Penalty}_{\text{buffer}}, \; 0.10, \; 1.00 \right)$$

---

### 3.3 Severity Tier Threshold Mapping

| Severity Level | Threshold Criterion | Operational Meaning | Action / Alert Status |
|---|---|---|---|
| `CRITICAL` | $S_{\text{Tier1\_hard}} == 1.0 \lor S_{\text{fused}} \ge 0.85$ | Fatal physical bound violation or unanimous extreme ML detection | Trigger instant operator alert; mark sensor degraded/offline |
| `HIGH` | $0.65 \le S_{\text{fused}} < 0.85$ | Significant anomaly corroborated across temporal and multivariate models | High-priority alert; schedule inspection |
| `MEDIUM` | $0.45 \le S_{\text{fused}} < 0.65$ | Moderate anomaly or single-model alert with partial agreement | Warning logged; monitor trend |
| `LOW` | $0.25 \le S_{\text{fused}} < 0.45$ | Minor statistical drift or slight rate-of-change elevation | Advisory notification |
| `NONE` | $S_{\text{fused}} < 0.25$ | Clean nominal meteorological telemetry | Normal operation |

#### Anomaly Flag Criterion:
$$\text{is\_anomaly} = (S_{\text{fused}} \ge \theta_{\text{anomaly}}) \quad (\text{default } \theta_{\text{anomaly}} = 0.45)$$

---

### 3.4 Software Architecture & Implementation Blueprint (`fusion.py`)

```python
"""
backend/app/ml/fusion.py
Multi-Tier Anomaly Score Fusion, Confidence Estimation, and Severity Engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class TierScores:
    tier1_hard_flag: bool = False
    tier1_soft_score: float = 0.0
    tier2_point_score: float = 0.0
    tier2_temporal_score: float = 0.0
    tier3_multivariate_score: float = 0.0


@dataclass
class FusionResult:
    fused_score: float
    confidence: float
    severity: Severity
    is_anomaly: bool
    tier_scores: Dict[str, float]
    override_applied: bool
    contributing_tiers: List[str]
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fused_score": round(self.fused_score, 4),
            "confidence": round(self.confidence, 4),
            "severity": self.severity.value,
            "is_anomaly": self.is_anomaly,
            "tier_scores": {k: round(v, 4) for k, v in self.tier_scores.items()},
            "override_applied": self.override_applied,
            "contributing_tiers": self.contributing_tiers,
            "diagnostics": self.diagnostics,
        }


class AnomalyFusionEngine:
    """
    Synthesizes multi-tier anomaly evidence into unified score, confidence, and severity.
    """

    def __init__(
        self,
        weight_tier1: float = 0.25,
        weight_tier2_point: float = 0.20,
        weight_tier2_temporal: float = 0.25,
        weight_tier3: float = 0.30,
        anomaly_threshold: float = 0.45,
        required_buffer_length: int = 30,
    ) -> None:
        self.w1 = weight_tier1
        self.w2_pt = weight_tier2_point
        self.w2_temp = weight_tier2_temporal
        self.w3 = weight_tier3
        self.anomaly_threshold = anomaly_threshold
        self.required_buffer_length = required_buffer_length

        # Normalize weights
        total_w = self.w1 + self.w2_pt + self.w2_temp + self.w3
        if total_w > 0:
            self.w1 /= total_w
            self.w2_pt /= total_w
            self.w2_temp /= total_w
            self.w3 /= total_w

    def compute_confidence(
        self,
        scores: List[float],
        buffer_length: int,
        override_applied: bool = False,
    ) -> float:
        """
        Calculate decision confidence based on inter-model concordance and buffer length.
        """
        # Buffer cold-start penalty
        if buffer_length < self.required_buffer_length:
            buffer_penalty = 0.20 * (1.0 - (buffer_length / self.required_buffer_length))
        else:
            buffer_penalty = 0.0

        if override_applied:
            return float(np.clip(1.0 - buffer_penalty, 0.10, 1.00))

        if not scores or len(scores) < 2:
            return float(np.clip(0.50 - buffer_penalty, 0.10, 1.00))

        arr = np.array(scores, dtype=np.float64)
        std_dev = np.std(arr)
        # Scale standard deviation so max possible spread (sqrt(3)/3) maps to zero concordance
        concordance = 1.0 - min(1.0, np.sqrt(3.0) * std_dev)
        raw_conf = concordance - buffer_penalty
        return float(np.clip(raw_conf, 0.10, 1.00))

    def map_severity(self, fused_score: float, override_applied: bool = False) -> Severity:
        """Map fused anomaly score to standardized Severity enum."""
        if override_applied or fused_score >= 0.85:
            return Severity.CRITICAL
        elif fused_score >= 0.65:
            return Severity.HIGH
        elif fused_score >= 0.45:
            return Severity.MEDIUM
        elif fused_score >= 0.25:
            return Severity.LOW
        else:
            return Severity.NONE

    def fuse(
        self,
        tier_scores: TierScores,
        buffer_length: int = 30,
    ) -> FusionResult:
        """
        Execute multi-tier evidence fusion.
        """
        # 1. Deterministic Tier 1 Hard Override
        if tier_scores.tier1_hard_flag:
            fused_score = 1.0
            override_applied = True
            severity = Severity.CRITICAL
            confidence = self.compute_confidence([], buffer_length, override_applied=True)
            contributing = ["tier1_qc"]
        else:
            override_applied = False
            # 2. Weighted Convex Combination
            fused_score = (
                self.w1 * float(np.clip(tier_scores.tier1_soft_score, 0.0, 1.0))
                + self.w2_pt * float(np.clip(tier_scores.tier2_point_score, 0.0, 1.0))
                + self.w2_temp * float(np.clip(tier_scores.tier2_temporal_score, 0.0, 1.0))
                + self.w3 * float(np.clip(tier_scores.tier3_multivariate_score, 0.0, 1.0))
            )
            fused_score = float(np.clip(fused_score, 0.0, 1.0))
            severity = self.map_severity(fused_score, override_applied=False)

            active_scores = [
                tier_scores.tier2_point_score,
                tier_scores.tier2_temporal_score,
                tier_scores.tier3_multivariate_score,
            ]
            confidence = self.compute_confidence(active_scores, buffer_length, override_applied=False)

            # Identify contributing tiers
            contributing = []
            if tier_scores.tier1_soft_score >= 0.30:
                contributing.append("tier1_qc")
            if tier_scores.tier2_point_score >= 0.40:
                contributing.append("tier2_point_ml")
            if tier_scores.tier2_temporal_score >= 0.40:
                contributing.append("tier2_temporal_ml")
            if tier_scores.tier3_multivariate_score >= 0.40:
                contributing.append("tier3_multivariate")

        is_anomaly = fused_score >= self.anomaly_threshold or override_applied

        return FusionResult(
            fused_score=fused_score,
            confidence=confidence,
            severity=severity,
            is_anomaly=is_anomaly,
            tier_scores={
                "tier1_hard": 1.0 if tier_scores.tier1_hard_flag else 0.0,
                "tier1_soft": tier_scores.tier1_soft_score,
                "tier2_point": tier_scores.tier2_point_score,
                "tier2_temporal": tier_scores.tier2_temporal_score,
                "tier3_multivariate": tier_scores.tier3_multivariate_score,
            },
            override_applied=override_applied,
            contributing_tiers=contributing,
            diagnostics={
                "buffer_length": buffer_length,
                "threshold_applied": self.anomaly_threshold,
            },
        )
```

---

## 4. Tier 4: Fault Taxonomy Classifier Specification (`tier4_classifier.py`)

### 4.1 9-Class Fault Taxonomy

The Tier 4 classifier categorizes telemetry states into 9 standardized meteorological and sensor hardware classes:

```
                                  TELEMETRY CLASSIFICATION TAXONOMY
                                                  │
                 ┌────────────────────────────────┴────────────────────────────────┐
                 │                                                                 │
                 ▼                                                                 ▼
          GENUINE SIGNALS                                                   SENSOR & DATA FAULTS
                 │                                                                 │
     ┌───────────┴───────────┐                         ┌───────────────────────────┼───────────────────────────┐
     │                       │                         │                           │                           │
     ▼                       ▼                         ▼                           ▼                           ▼
  NORMAL           METEOROLOGICAL_EXTREME            SPIKE                       DRIFT                      FROZEN
(S_fused < 0.30)   (Squall / Cold Front)         (Transient Impulse)       (Linear Bias Shift)        (Zero-Variance Stuck)
                   [is_fault = False]            [is_fault = True]         [is_fault = True]          [is_fault = True]
                                                       │                           │                           │
                                                       ▼                           ▼                           ▼
                                                    DROPOUT                   NOISE_BURST           MULTIVARIATE_INCONSISTENCY
                                               (Null / NaN / Sentinel)    (High Variance Surge)     (Decoupled Thermodynamics)
                                               [is_fault = True]          [is_fault = True]         [is_fault = True]
                                                       │                           │
                                                       ▼                           ▼
                                                DATA_CORRUPTION             UNCERTAIN_EVENT
                                            (String / Framing / Bit)     (Ambiguous Signature)
                                            [is_fault = True]            [is_fault = True]
```

---

### 4.2 Scientific Weather Front vs. Sensor Hardware Failure Discrimination

Distinguishing genuine convective atmospheric squalls from sensor failures is a core differentiator required by `AGENTS.md` and `ARCHITECTURE.md`.

#### Meteorological Physics of a Convective Cold Front / Thunderstorm Squall:
During the passage of a gust front or cold front microburst:
1. **Temperature Drop ($\Delta T_{15\text{min}}$)**: Evaporative downdraft cooling drives rapid thermal drop ($\Delta T_{15\text{min}} \le -3.0^\circ\text{C}$, often $-5^\circ\text{C}$ to $-12^\circ\text{C}$ within 15 minutes).
2. **Atmospheric Pressure Perturbation ($\Delta P_{15\text{min}}$)**: Mesoscale pressure jump (mesohigh) or thunderstorm barometric wave ($|\Delta P_{15\text{min}}| \ge 1.5\text{ hPa}$).
3. **Relative Humidity Surge ($\Delta RH_{15\text{min}}$)**: Precipitation and evaporative cooling drive humidity towards saturation ($\Delta RH_{15\text{min}} \ge +15\%$, often reaching $90\% - 100\%$).
4. **Thermodynamic Law Conserved**: Clausius-Clapeyron Magnus-Tetens dew-point consistency is strictly obeyed ($T_d \le T + 0.5^\circ\text{C}$).
5. **Physical Bounds Conserved**: All variables remain within realistic bounds ($-40 \le T \le 60$, $300 \le P \le 1100$, $0 \le RH \le 104$).

#### Sensor Hardware Failure Signatures:
1. **Isolated Spike**: Temperature jumps $+20^\circ\text{C}$ in 5 minutes while Barometric Pressure and Humidity are completely unperturbed ($\Delta P \approx 0, \Delta RH \approx 0$). In physical meteorology, a $+20^\circ\text{C}$ ambient air jump cannot occur without severe barometric or moisture shifts $\implies$ Classified as `SPIKE` (`is_fault = True`).
2. **Unphysical Supersaturation**: Temperature jumps to $45^\circ\text{C}$ while Relative Humidity is forced to $100\%$ with dry weather pressure. This yields an unphysical vapor pressure $e = 95.8\text{ hPa}$ and $T_d = 45^\circ\text{C}$ violating local thermodynamics $\implies$ Classified as `MULTIVARIATE_INCONSISTENCY` (`is_fault = True`).
3. **Sensor Freeze**: Atmospheric pressure and humidity continue diurnal oscillations while temperature reports exactly $22.450^\circ\text{C}$ for 6+ steps ($\sigma^2 < 10^{-6}$) $\implies$ Classified as `FROZEN` (`is_fault = True`).
4. **Dropout / Signal Loss**: Telemetry packet arrives with `NaN`, `None`, $0.0$, or sentinel value $-999.0$ $\implies$ Classified as `DROPOUT` (`is_fault = True`).
5. **Electrical Noise Burst**: High-frequency random jitter ($\sigma \ge 5\times$ nominal) caused by grounding loops or EMI $\implies$ Classified as `NOISE_BURST` (`is_fault = True`).
6. **Data Corruption**: Malformed ASCII token `"$ERR_COMM_TIMEOUT#"` or corrupted timestamp $\implies$ Classified as `DATA_CORRUPTION` (`is_fault = True`).

---

### 4.3 Classification Decision Tree & Hybrid Rule-ML Architecture

```text
Hierarchical Classification Pipeline:
-----------------------------------------------------------------------------------------
Input: Telemetry Record, Sliding History Buffer (N <= 30), Tier 1-3 Scores, Fusion Result

1. Check Normal Operation:
   IF fused_score < 0.30 AND NOT tier1_hard_flag:
       RETURN NORMAL (is_fault = False, confidence = 1.0 - fused_score)

2. Check Fatal Data Corruption & Dropouts (Tier 1 Hard Flags):
   IF any value is NaN / None / Sentinel (-999.0):
       RETURN DROPOUT (is_fault = True, severity = CRITICAL)
   IF value is string error / out-of-range (>60°C or < -40°C) / duplicate timestamp:
       RETURN DATA_CORRUPTION (is_fault = True, severity = CRITICAL)
   IF is_frozen (variance over last K >= 6 steps < 1e-6):
       RETURN FROZEN (is_fault = True, severity = HIGH/CRITICAL)

3. Check Front vs Hardware Disambiguation:
   Compute 15-minute window gradients (last 3 steps):
       ΔT_15m = T(t) - T(t-3)
       ΔP_15m = P(t) - P(t-3)
       ΔRH_15m = RH(t) - RH(t-3)
   
   IF Clausius-Clapeyron holds (Td <= T + 0.5°C)
      AND ΔT_15m <= -3.0°C
      AND abs(ΔP_15m) >= 1.5 hPa
      AND ΔRH_15m >= +15.0%:
       RETURN METEOROLOGICAL_EXTREME (is_fault = False, severity = MEDIUM/HIGH)

4. Check Thermodynamic Decoupling:
   IF Td > T + 0.5°C OR tier3_thermo_score >= 0.50:
       RETURN MULTIVARIATE_INCONSISTENCY (is_fault = True)

5. Check Temporal Waveform Morphology:
   IF duration <= 2 steps AND (abs(ΔT) > 5.0°C OR abs(ΔP) > 3.0 hPa OR abs(ΔRH) > 25%):
       RETURN SPIKE (is_fault = True)
   IF local rolling variance (10 steps) > 5.0 * nominal_baseline_variance:
       RETURN NOISE_BURST (is_fault = True)
   IF duration >= 12 steps AND monotonic linear slope with low variance:
       RETURN DRIFT (is_fault = True)
   IF tier3_mahalanobis_score >= 0.85:
       RETURN MULTIVARIATE_INCONSISTENCY (is_fault = True)

6. Fallback:
   RETURN UNCERTAIN_EVENT (is_fault = True, confidence = 0.50)
-----------------------------------------------------------------------------------------
```

---

### 4.4 Software Architecture & Implementation Blueprint (`tier4_classifier.py`)

```python
"""
backend/app/ml/tier4_classifier.py
Tier 4: Fault Taxonomy Classifier (Distinguishing Fronts from Sensor Hardware Faults).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from backend.app.ml.fusion import FusionResult, Severity
from backend.app.ml.tier3_multivariate import Tier3Result, calculate_dew_point

logger = logging.getLogger(__name__)


class FaultClass(str, Enum):
    NORMAL = "NORMAL"
    SPIKE = "SPIKE"
    DRIFT = "DRIFT"
    FROZEN = "FROZEN"
    DROPOUT = "DROPOUT"
    NOISE_BURST = "NOISE_BURST"
    MULTIVARIATE_INCONSISTENCY = "MULTIVARIATE_INCONSISTENCY"
    DATA_CORRUPTION = "DATA_CORRUPTION"
    METEOROLOGICAL_EXTREME = "METEOROLOGICAL_EXTREME"
    UNCERTAIN_EVENT = "UNCERTAIN_EVENT"


@dataclass
class ClassificationResult:
    fault_class: FaultClass
    is_fault: bool
    confidence: float
    reason: str
    rule_triggered: str
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fault_class": self.fault_class.value,
            "is_fault": self.is_fault,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "rule_triggered": self.rule_triggered,
            "diagnostics": self.diagnostics,
        }


class Tier4FaultClassifier:
    """
    Hybrid Deterministic & ML Rule-Based Classifier for Automatic Weather Station Faults.
    """

    def __init__(
        self,
        frozen_variance_threshold: float = 1e-6,
        frozen_window: int = 6,
        noise_burst_factor: float = 5.0,
        front_temp_drop_threshold: float = -3.0,
        front_pressure_jump_threshold: float = 1.5,
        front_humidity_surge_threshold: float = 15.0,
    ) -> None:
        self.frozen_var_thresh = frozen_variance_threshold
        self.frozen_window = frozen_window
        self.noise_burst_factor = noise_burst_factor
        self.front_temp_drop = front_temp_drop_threshold
        self.front_p_jump = front_pressure_jump_threshold
        self.front_rh_surge = front_humidity_surge_threshold

        # Nominal variance baselines for noise detection
        self.nominal_stds = {"temperature": 0.35, "pressure": 0.15, "humidity": 1.2}

    def _check_frozen(self, buffer_df: pd.DataFrame, column: str) -> bool:
        """Check if sensor readings have zero empirical variance over K steps."""
        if len(buffer_df) < self.frozen_window or column not in buffer_df.columns:
            return False
        recent = buffer_df[column].tail(self.frozen_window).to_numpy(dtype=np.float64)
        if np.any(np.isnan(recent)):
            return False
        return float(np.var(recent)) < self.frozen_var_thresh

    def _check_noise_burst(self, buffer_df: pd.DataFrame, column: str) -> bool:
        """Check if recent variance is significantly elevated above nominal level."""
        if len(buffer_df) < 10 or column not in buffer_df.columns:
            return False
        recent = buffer_df[column].tail(10).to_numpy(dtype=np.float64)
        if np.any(np.isnan(recent)):
            return False
        nominal_std = self.nominal_stds.get(column, 1.0)
        recent_std = float(np.std(recent))
        return recent_std >= (self.noise_burst_factor * nominal_std)

    def _check_drift(self, buffer_df: pd.DataFrame, column: str) -> Tuple[bool, float]:
        """Check if sensor exhibits a progressive linear calibration drift."""
        if len(buffer_df) < 15 or column not in buffer_df.columns:
            return False, 0.0
        recent = buffer_df[column].tail(24).to_numpy(dtype=np.float64)
        if np.any(np.isnan(recent)):
            return False, 0.0
        x = np.arange(len(recent))
        slope, _ = np.polyfit(x, recent, 1)
        r_matrix = np.corrcoef(x, recent)
        r_val = r_matrix[0, 1] if r_matrix.shape == (2, 2) else 0.0
        # High linearity and non-zero slope indicating steady drift
        is_drifting = abs(slope) >= 0.05 and abs(r_val) >= 0.85
        return is_drifting, float(slope)

    def classify(
        self,
        current_observation: Dict[str, Any],
        buffer_df: pd.DataFrame,
        tier3_result: Tier3Result,
        fusion_result: FusionResult,
        tier1_flag_reason: Optional[str] = None,
    ) -> ClassificationResult:
        """
        Classify telemetry event into fault taxonomy.
        """
        temp = current_observation.get("temperature")
        pres = current_observation.get("pressure")
        hum = current_observation.get("humidity")

        # 1. Check for Normal Telemetry
        if not fusion_result.is_anomaly and not fusion_result.override_applied:
            return ClassificationResult(
                fault_class=FaultClass.NORMAL,
                is_fault=False,
                confidence=float(np.clip(1.0 - fusion_result.fused_score, 0.50, 1.00)),
                reason="Telemetry within normal operational and meteorological baselines.",
                rule_triggered="RULE_NORMAL_OPERATION",
                diagnostics={"fused_score": fusion_result.fused_score},
            )

        # 2. Check for Dropouts (NaN / None / Sentinel values)
        if any(v is None or (isinstance(v, (int, float)) and (np.isnan(v) or v == -999.0)) for v in (temp, pres, hum)):
            return ClassificationResult(
                fault_class=FaultClass.DROPOUT,
                is_fault=True,
                confidence=0.99,
                reason="Sensor communication loss or missing telemetry packet (NaN/null/sentinel).",
                rule_triggered="RULE_DATA_DROPOUT",
                diagnostics={"raw_values": {"temperature": temp, "pressure": pres, "humidity": hum}},
            )

        # 3. Check for Data Corruption / Physical Range Violations
        if any(isinstance(v, str) for v in (temp, pres, hum)):
            return ClassificationResult(
                fault_class=FaultClass.DATA_CORRUPTION,
                is_fault=True,
                confidence=0.99,
                reason="Malformed non-numeric token encountered in observation payload.",
                rule_triggered="RULE_STRING_CORRUPTION",
            )

        t_val, p_val, rh_val = float(temp), float(pres), float(hum)

        if t_val < -40.0 or t_val > 60.0 or p_val < 300.0 or p_val > 1100.0 or rh_val < 0.0 or rh_val > 104.0:
            return ClassificationResult(
                fault_class=FaultClass.DATA_CORRUPTION,
                is_fault=True,
                confidence=0.98,
                reason=f"Observation outside physical limits: T={t_val}°C, P={p_val}hPa, RH={rh_val}%.",
                rule_triggered="RULE_PHYSICAL_RANGE_BOUNDS",
            )

        # 4. Check for Frozen Sensors (Zero Variance over K steps)
        for col in ["temperature", "pressure", "humidity"]:
            if self._check_frozen(buffer_df, col):
                return ClassificationResult(
                    fault_class=FaultClass.FROZEN,
                    is_fault=True,
                    confidence=0.95,
                    reason=f"Sensor '{col}' repeating identical value with zero empirical variance over >= {self.frozen_window} steps.",
                    rule_triggered=f"RULE_FROZEN_{col.upper()}",
                    diagnostics={"stuck_parameter": col},
                )

        # 5. Distinguish Meteorological Front from Sensor Faults
        if len(buffer_df) >= 3:
            t_3 = float(buffer_df["temperature"].iloc[-3])
            p_3 = float(buffer_df["pressure"].iloc[-3])
            rh_3 = float(buffer_df["humidity"].iloc[-3])

            delta_t_15 = t_val - t_3
            delta_p_15 = p_val - p_3
            delta_rh_15 = rh_val - rh_3

            # Check if thermodynamic law holds AND front dynamics match
            if (
                not tier3_result.thermo_violation
                and delta_t_15 <= self.front_temp_drop
                and abs(delta_p_15) >= self.front_p_jump
                and delta_rh_15 >= self.front_rh_surge
            ):
                return ClassificationResult(
                    fault_class=FaultClass.METEOROLOGICAL_EXTREME,
                    is_fault=False,  # Genuine atmospheric event
                    confidence=0.92,
                    reason=(
                        f"Genuine convective squall front detected: ΔT={delta_t_15:.1f}°C, "
                        f"ΔP={delta_p_15:.1f}hPa, ΔRH=+{delta_rh_15:.1f}% adhering to Clausius-Clapeyron thermodynamics."
                    ),
                    rule_triggered="RULE_METEOROLOGICAL_SQUALL_FRONT",
                    diagnostics={
                        "delta_T_15m": delta_t_15,
                        "delta_P_15m": delta_p_15,
                        "delta_RH_15m": delta_rh_15,
                        "dew_point_c": tier3_result.dew_point,
                    },
                )

        # 6. Check for Thermodynamic Multivariate Inconsistency
        if tier3_result.thermo_violation:
            return ClassificationResult(
                fault_class=FaultClass.MULTIVARIATE_INCONSISTENCY,
                is_fault=True,
                confidence=0.94,
                reason=(
                    f"Thermodynamic violation: calculated dew point ({tier3_result.dew_point:.1f}°C) "
                    f"exceeds dry bulb temperature ({t_val:.1f}°C) by {tier3_result.dew_point_diff:.1f}°C."
                ),
                rule_triggered="RULE_THERMODYNAMIC_DECOUPLING",
                diagnostics={"dew_point_diff": tier3_result.dew_point_diff},
            )

        # 7. Check for Spike Impulses (High gradient with short duration)
        if len(buffer_df) >= 2:
            prev_t = float(buffer_df["temperature"].iloc[-2])
            prev_p = float(buffer_df["pressure"].iloc[-2])
            prev_rh = float(buffer_df["humidity"].iloc[-2])

            dt = abs(t_val - prev_t)
            dp = abs(p_val - prev_p)
            drh = abs(rh_val - prev_rh)

            if dt > 5.0 or dp > 4.0 or drh > 25.0:
                affected = []
                if dt > 5.0:
                    affected.append(f"T (Δ={dt:.1f}°C)")
                if dp > 4.0:
                    affected.append(f"P (Δ={dp:.1f}hPa)")
                if drh > 25.0:
                    affected.append(f"RH (Δ={drh:.1f}%)")
                return ClassificationResult(
                    fault_class=FaultClass.SPIKE,
                    is_fault=True,
                    confidence=0.91,
                    reason=f"Transient impulse step-change detected in {', '.join(affected)} within 5 minutes.",
                    rule_triggered="RULE_TRANSIENT_SPIKE",
                    diagnostics={"deltas": {"dT": dt, "dP": dp, "dRH": drh}},
                )

        # 8. Check for Noise Bursts
        for col in ["temperature", "pressure", "humidity"]:
            if self._check_noise_burst(buffer_df, col):
                return ClassificationResult(
                    fault_class=FaultClass.NOISE_BURST,
                    is_fault=True,
                    confidence=0.88,
                    reason=f"High-frequency noise burst surge detected on parameter '{col}'.",
                    rule_triggered=f"RULE_NOISE_BURST_{col.upper()}",
                )

        # 9. Check for Progressive Linear Calibration Drift
        for col in ["temperature", "pressure", "humidity"]:
            is_drift, slope = self._check_drift(buffer_df, col)
            if is_drift:
                return ClassificationResult(
                    fault_class=FaultClass.DRIFT,
                    is_fault=True,
                    confidence=0.86,
                    reason=f"Progressive calibration drift detected on '{col}' (slope={slope:+.3f} units/step).",
                    rule_triggered=f"RULE_PROGRESSIVE_DRIFT_{col.upper()}",
                    diagnostics={"slope": slope},
                )

        # 10. Check for Statistical Mahalanobis Covariance Decoupling
        if tier3_result.mahalanobis_score >= 0.90:
            return ClassificationResult(
                fault_class=FaultClass.MULTIVARIATE_INCONSISTENCY,
                is_fault=True,
                confidence=0.85,
                reason=(
                    f"Multivariate covariance anomaly detected (Mahalanobis D_M={tier3_result.mahalanobis_distance:.2f}, "
                    f"p={tier3_result.mahalanobis_score:.4f})."
                ),
                rule_triggered="RULE_MAHALANOBIS_COVARIANCE_ANOMALY",
            )

        # 11. Fallback for Uncategorized / Ambiguous Events
        return ClassificationResult(
            fault_class=FaultClass.UNCERTAIN_EVENT,
            is_fault=True,
            confidence=0.55,
            reason="Ambiguous anomaly detected; signature does not match distinct fault patterns.",
            rule_triggered="RULE_FALLBACK_UNCERTAIN",
            diagnostics={"fused_score": fusion_result.fused_score},
        )
```

---

## 5. End-to-End Pipeline Integration & Schema Contracts

### 5.1 Pipeline Data Flow Through Tiers 3, Fusion, and 4

```
Incoming Telemetry (T, P, RH, timestamp)
   │
   ├─► Tier 1: QC Engine (Deterministic limits, ROC, missingness)
   │       └──> produces: S_tier1_hard, S_tier1_soft, flag_reason
   │
   ├─► Tier 2: Point & Temporal ML (Isolation Forest, GRU Autoencoder)
   │       └──> produces: S_point, S_temporal
   │
   ├─► Tier 3: Multivariate Engine (Dew point CC & Mahalanobis CDF)
   │       └──> produces: Tier3Result (S_thermo, S_mahal, S_tier3)
   │
   ▼
ANOMALY FUSION ENGINE (fusion.py)
   │
   │── Evaluates: Hard Tier 1 override vs Convex Combination
   │── Evaluates: Model Concordance Variance & Buffer Penalty
   │── Produces: FusionResult (fused_score, confidence, severity, is_anomaly)
   │
   ▼
TIER 4 FAULT CLASSIFIER (tier4_classifier.py)
   │
   │── Evaluates: Front vs Hardware Fault Disambiguation
   │── Evaluates: Physical Gradient, Waveform Morphology, CC Check
   │── Produces: ClassificationResult (fault_class, is_fault, reason, diagnostics)
   │
   ▼
Tier 5 (Sensor Health Index & Explainability)
   │
   │── Updates SHI (penalizes if is_fault == True; preserves if is_fault == False)
   └── Generates SHAP attribution and human-readable explanation
```

---

### 5.2 JSON Output Schema Contract (`InferenceResult`)

```json
{
  "timestamp": "2026-08-24T12:00:00Z",
  "station_id": "AWS-001",
  "temperature": 28.4,
  "pressure": 1008.7,
  "humidity": 72.1,
  "is_anomaly": true,
  "anomaly_score": 0.8245,
  "confidence": 0.9150,
  "severity": "HIGH",
  "classification": "SPIKE",
  "is_fault": true,
  "reason": "Transient impulse step-change detected in T (Δ=+24.0°C) within 5 minutes.",
  "tier_scores": {
    "tier1_hard": 0.0,
    "tier1_soft": 0.85,
    "tier2_point": 0.88,
    "tier2_temporal": 0.79,
    "tier3_multivariate": 0.74
  },
  "multivariate_diagnostics": {
    "dew_point": 22.84,
    "dew_point_diff": -5.56,
    "thermo_violation": false,
    "mahalanobis_distance": 3.82,
    "mahalanobis_p_value": 0.9850
  },
  "sensor_health": 74.2,
  "recommended_action": "Inspect temperature sensor probe for loose wiring or power glitch."
}
```

---

## 6. Unit & Integration Test Specifications

To guarantee zero regressions and verify all mathematical requirements, the following test suites must be implemented in `tests/`:

### 6.1 `tests/test_tier3_multivariate.py` ($\ge 8$ test cases)
1. `test_dew_point_magnus_tetens_accuracy`: Asserts calculated $T_d$ for standard conditions ($T=20^\circ\text{C}, RH=50\% \implies T_d \approx 9.27^\circ\text{C}$) matches empirical tables within $\pm 0.05^\circ\text{C}$.
2. `test_dew_point_physical_consistency`: Asserts that when $RH \le 100\%$, $T_d \le T$, resulting in $S_{\text{thermo}} = 0.0$.
3. `test_dew_point_supersaturation_violation`: Asserts that unphysical supersaturation ($T_d > T + 0.5^\circ\text{C}$) triggers $S_{\text{thermo}} > 0.0$ and `thermo_violation = True`.
4. `test_dew_point_negative_zero_rh_clamping`: Asserts $RH = 0.0\%$ and $RH = -5.0\%$ are clamped safely to $\epsilon = 0.01\%$ without numerical divergence.
5. `test_mahalanobis_fit_and_persistence`: Asserts `fit()`, `save()`, and `load()` persist parameters correctly and produce identical numerical distances.
6. `test_mahalanobis_distance_nominal_p_value`: Asserts typical mean observations produce $D_M^2 < 3.0$ and Chi-square CDF score $< 0.60$.
7. `test_mahalanobis_distance_anomalous_coupling`: Asserts extreme decoupled inputs ($T=50^\circ\text{C}, P=1035\text{ hPa}, RH=99\%$) produce $D_M^2 > 16.0$ and $S_{\text{mahalanobis}} > 0.99$.
8. `test_tier3_nan_inf_handling`: Asserts input containing `NaN` or `Inf` returns `is_valid = False` gracefully without raising unhandled exceptions.

### 6.2 `tests/test_fusion.py` ($\ge 8$ test cases)
1. `test_fusion_tier1_hard_override`: Asserts $S_{\text{Tier1\_hard}} == 1.0$ forces $S_{\text{fused}} = 1.0$, `severity = CRITICAL`, and `override_applied = True`.
2. `test_fusion_convex_weights_sum`: Asserts weighted sum using $w_1=0.25, w_{2\text{pt}}=0.20, w_{2\text{temp}}=0.25, w_3=0.30$ produces expected linear combination.
3. `test_fusion_confidence_model_agreement`: Asserts identical high tier scores ($[0.9, 0.9, 0.9]$) yield high confidence ($C \ge 0.95$).
4. `test_fusion_confidence_model_conflict`: Asserts conflicting tier scores ($[1.0, 0.0, 0.0]$) penalize confidence ($C \le 0.40$).
5. `test_fusion_confidence_cold_start_buffer_penalty`: Asserts buffer length $N=5 < 30$ reduces confidence by buffer penalty.
6. `test_fusion_severity_tier_thresholds`: Verifies exact threshold boundaries for `NONE` ($<0.25$), `LOW` ($0.25-0.45$), `MEDIUM` ($0.45-0.65$), `HIGH` ($0.65-0.85$), and `CRITICAL` ($\ge 0.85$).
7. `test_fusion_contributing_tiers_identification`: Asserts contributing tiers list contains only modules with active scores $\ge 0.40$.
8. `test_fusion_clamping_bounds`: Asserts inputs $< 0.0$ or $> 1.0$ are safely clamped to $[0.0, 1.0]$.

### 6.3 `tests/test_tier4_classifier.py` ($\ge 10$ test cases)
1. `test_classifier_normal_telemetry`: Asserts clean observation classifies as `NORMAL` with `is_fault = False`.
2. `test_classifier_dropout_nan_sentinel`: Asserts `NaN`, `None`, and `-999.0` classify as `DROPOUT` with `is_fault = True`.
3. `test_classifier_data_corruption_string_range`: Asserts string tokens and $T=9999^\circ\text{C}$ classify as `DATA_CORRUPTION`.
4. `test_classifier_frozen_sensor_zero_variance`: Asserts $K \ge 6$ constant readings classify as `FROZEN`.
5. `test_classifier_convective_squall_front_discrimination`: Asserts severe temperature drop, pressure jump, and RH surge adhering to Clausius-Clapeyron classify as `METEOROLOGICAL_EXTREME` with **`is_fault = False`**.
6. `test_classifier_single_variable_spike`: Asserts isolated $+20^\circ\text{C}$ temperature surge without front dynamics classifies as `SPIKE` (`is_fault = True`).
7. `test_classifier_thermodynamic_inconsistency`: Asserts Clausius-Clapeyron violation ($T_d > T + 0.5^\circ\text{C}$) classifies as `MULTIVARIATE_INCONSISTENCY`.
8. `test_classifier_noise_burst`: Asserts high-frequency jitter ($\ge 5\times$ nominal) classifies as `NOISE_BURST`.
9. `test_classifier_progressive_linear_drift`: Asserts sustained linear slope over 24 steps classifies as `DRIFT`.
10. `test_classifier_uncertain_fallback`: Asserts uncategorized mild anomalies return `UNCERTAIN_EVENT`.

---

## 7. Implementation Checklist for M2 Execution

- [x] Full mathematical formalization of Clausius-Clapeyron & Magnus-Tetens dew-point consistency.
- [x] Regularized Mahalanobis distance & Chi-square CDF statistical modeling with joblib persistence.
- [x] Multi-tier weighted convex fusion with hard deterministic override.
- [x] Inter-model sample variance concordance confidence scoring with buffer cold-start penalty.
- [x] 9-class fault taxonomy with scientific convective weather front vs sensor failure disambiguation.
- [x] Full Python code blueprints with dataclasses, type hints, and docstrings.
- [x] 26+ targeted unit test specifications covering boundary conditions and edge cases.
