# SkyGuard AI — M2 ML Pipeline Architecture & Implementation Specifications
## Components: Tier 1 QC, Feature Preprocessor, Tier 2 Point ML, Tier 2 Temporal ML

**Author**: `m2_explorer_1`  
**Milestone**: M2 (Phases 3–6 of TODO.md)  
**Date**: 2026-08-24  
**Target Modules**:
1. `backend/app/ml/tier1_qc.py`
2. `backend/app/ml/preprocessor.py`
3. `backend/app/ml/tier2_point_ml.py`
4. `backend/app/ml/tier2_temporal_ml.py`

---

## 1. Executive Summary & System Placement

The SkyGuard AI ML pipeline is structured as a sequential and hierarchical 5-tier architecture designed for Automatic Weather Station (AWS) anomaly detection, fault classification, and sensor health estimation. Under the strict constraint of primary parameters (Temperature $T$, Atmospheric Pressure $P$, Relative Humidity $RH$), the first two tiers and the preprocessor form the foundation of the entire pipeline:

```
                  Raw AWS Telemetry (T, P, RH, timestamp, station_id)
                                          │
                                          ▼
                ┌──────────────────────────────────────────────────┐
                │ TIER 1: Deterministic Quality Control & Bounds  │
                │  - Physical WMO Limits (-40 to 60°C, 300-1100hPa)│
                │  - Derivative Step Limits (|ΔT|<=5°C, |ΔP|<=3hPa) │
                │  - Persistence / Frozen Sensor Check (K=6 steps) │
                │  - Data Completeness & Monotonicity Check        │
                └─────────────────────────┬────────────────────────┘
                                          │ Passes / Evaluates
                                          ▼
                ┌──────────────────────────────────────────────────┐
                │ PREPROCESSOR & FEATURE ENGINEERING               │
                │  - 9-Feature Vector Generation (T,P,RH,Δ,sin,cos,Td)│
                │  - Standard Scaler Normalization (scaler.joblib) │
                │  - Rolling Window Sequence Generator (W=30 steps)│
                └─────────────────────────┬────────────────────────┘
                                          │
                        ┌─────────────────┴─────────────────┐
                        ▼                                   ▼
        ┌───────────────────────────────┐   ┌───────────────────────────────┐
        │ TIER 2: Point Anomaly Model   │   │ TIER 2: Temporal Anomaly Model│
        │  - IsolationForest (n=100)    │   │  - PyTorch GRU/LSTM Autoenc   │
        │  - Scaled 9D Feature Input    │   │  - Window W=30, Latent=16     │
        │  - Calibrated S_point in [0,1]│   │  - Reconstruction MSE Score   │
        │  - isolation_forest.joblib    │   │  - autoencoder.pt             │
        └───────────────┬───────────────┘   └───────────────┬───────────────┘
                        │                                   │
                        └─────────────────┬─────────────────┘
                                          ▼
                   Downstream: Tier 3, Fusion, Tier 4 & Tier 5
```

---

## 2. Module 1: Tier 1 Deterministic Quality Control Engine (`tier1_qc.py`)

### 2.1 Theoretical & Operational Objective
Tier 1 serves as the deterministic gatekeeper. It enforces non-negotiable physical laws and WMO (World Meteorological Organization) standard quality control limits. Any hard violation at Tier 1 immediately triggers a deterministic override in the fusion engine ($S_{\text{Tier1}} = 1.0, \text{Severity} = \text{CRITICAL}$), bypassing or overriding soft statistical models.

### 2.2 Mathematical Formulations & Quality Checks

#### 1. Physical Plausibility (WMO Range Bounds)
Every parameter must reside strictly within physically possible meteorological bounds for surface stations:
- **Temperature ($T$)**:
  $$-40.0^\circ\text{C} \le T \le +60.0^\circ\text{C}$$
  If $T < -40.0$ or $T > 60.0 \implies \text{flag } \texttt{range\_temp\_violation} = \text{True}$.
- **Atmospheric Pressure ($P$)**:
  $$300.0\text{ hPa} \le P \le 1100.0\text{ hPa}$$
  If $P < 300.0$ or $P > 1100.0 \implies \text{flag } \texttt{range\_pressure\_violation} = \text{True}$.
- **Relative Humidity ($RH$)**:
  $$0.0\% \le RH \le 104.0\%$$
  *(Note: Standard WMO surface stations allow up to $104\%$ for instrument tolerance/supersaturation in fog; anything $> 104.0\%$ or $< 0.0\%$ violates physical limits).*
  If $RH < 0.0$ or $RH > 104.0 \implies \text{flag } \texttt{range\_humidity\_violation} = \text{True}$.

#### 2. Rate of Change / Derivative Step-Limits
For consecutive observations separated by sampling interval $\Delta t$ (default $\Delta t = 5\text{ minutes}$):
- **Temperature Rate of Change**:
  $$|\Delta T| = |T_t - T_{t-1}| \le 5.0^\circ\text{C} \quad (1.0^\circ\text{C}/\text{min})$$
- **Pressure Rate of Change**:
  $$|\Delta P| = |P_t - P_{t-1}| \le 3.0\text{ hPa} \quad (0.6\text{ hPa}/\text{min})$$
- **Humidity Rate of Change**:
  $$|\Delta RH| = |RH_t - RH_{t-1}| \le 25.0\% \quad (5.0\%/\text{min})$$
If $\Delta t \ne 5\text{ min}$, derivative limits scale dynamically: $|\Delta x| \le \text{rate\_per\_min} \times \Delta t$.

#### 3. Persistence & Frozen Sensor Check
A sensor is declared stuck/frozen if its empirical variance over a rolling window of $K = 6$ consecutive steps ($30\text{ minutes}$) collapses to zero:
$$\text{Var}(x_{t-K+1:t}) = \frac{1}{K} \sum_{i=0}^{K-1} (x_{t-i} - \bar{x})^2 < 10^{-6} \implies \text{flag } \texttt{frozen\_sensor} = \text{True}$$
- Applies independently to $T, P, RH$.
- If time difference between consecutive observations exceeds $15\text{ minutes}$ (e.g. station offline gap), the persistence buffer is reset to avoid false positives.

#### 4. Completeness, Format & Monotonicity Checks
- **Missing / Null Check**: Detects `NaN`, `None`, empty strings `""`, or sentinel values ($-999.0, 9999.0$).
- **Corrupt Token Check**: Non-numeric string payloads, bit-flip characters, or malformed formats.
- **Timestamp Monotonicity & Duplication**:
  - $t_i = t_{i-1} \implies \text{flag } \texttt{duplicate\_timestamp} = \text{True}$.
  - $t_i < t_{i-1} \implies \text{flag } \texttt{non\_monotonic\_timestamp} = \text{True}$.

### 2.3 Proposed Class & Data Architecture

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
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

    # Pressure (hPa)
    pressure_min: float = 300.0
    pressure_max: float = 1100.0
    pressure_step_max: float = 3.0
    pressure_rate_per_min: float = 0.6

    # Relative Humidity (%)
    rh_min: float = 0.0
    rh_max: float = 104.0
    rh_step_max: float = 25.0
    rh_rate_per_min: float = 5.0

    # Persistence
    frozen_window_steps: int = 6
    frozen_var_threshold: float = 1e-6
    max_step_gap_minutes: float = 15.0


@dataclass
class Tier1QCResult:
    """Output contract for Tier 1 Quality Control analysis."""
    is_valid: bool = True
    score: float = 0.0  # 1.0 if hard failure, 0.0 if clean
    is_hard_override: bool = False
    flags: Dict[str, bool] = field(default_factory=dict)
    violations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Tier1QCEngine:
    """Deterministic Quality Control & Physical Plausibility Engine."""

    def __init__(self, config: Optional[Tier1QCConfig] = None):
        self.config = config or Tier1QCConfig()

    def check_observation(
        self,
        current: Dict[str, Any],
        previous: Optional[Dict[str, Any]] = None,
        recent_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Tier1QCResult:
        """Evaluate a single real-time observation against deterministic QC rules."""
        ...

    def check_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Batch QC evaluation over a historical DataFrame."""
        ...
```

---

## 3. Module 2: Preprocessor & Feature Engineering (`preprocessor.py`)

### 3.1 9-Feature Mathematical Formulation
The preprocessor transforms raw observations $(t, T, P, RH)$ into a 9-dimensional continuous feature space $\mathbf{z}_t \in \mathbb{R}^9$:

1. **$z_1 = T_t$**: Raw Temperature in $^\circ\text{C}$.
2. **$z_2 = P_t$**: Raw Atmospheric Pressure in $\text{hPa}$.
3. **$z_3 = RH_t$**: Raw Relative Humidity in $\%$.
4. **$z_4 = \Delta T_t$**: First backward difference:
   $$\Delta T_t = \begin{cases} T_t - T_{t-1} & \text{if } t > 0 \\ 0.0 & \text{if } t = 0 \end{cases}$$
5. **$z_5 = \Delta P_t$**: First backward difference:
   $$\Delta P_t = \begin{cases} P_t - P_{t-1} & \text{if } t > 0 \\ 0.0 & \text{if } t = 0 \end{cases}$$
6. **$z_6 = \Delta RH_t$**: First backward difference:
   $$\Delta RH_t = \begin{cases} RH_t - RH_{t-1} & \text{if } t > 0 \\ 0.0 & \text{if } t = 0 \end{cases}$$
7. **$z_7 = \sin(\text{hour})$**: Continuous diurnal solar phase sine:
   $$\sin\left(\frac{2\pi \cdot (\text{hour} + \text{minute}/60)}{24}\right)$$
8. **$z_8 = \cos(\text{hour})$**: Continuous diurnal solar phase cosine:
   $$\cos\left(\frac{2\pi \cdot (\text{hour} + \text{minute}/60)}{24}\right)$$
9. **$z_9 = T_d(t)$**: Magnus-Tetens physical Dew Point Temperature ($^\circ\text{C}$):
   $$\gamma(T, RH) = \frac{17.67 \cdot T}{T + 243.5} + \ln\left( \frac{\text{clip}(RH, 0.01, 100.0)}{100.0} \right)$$
   $$T_d(t) = \frac{243.5 \cdot \gamma(T_t, RH_t)}{17.67 - \gamma(T_t, RH_t)}$$

### 3.2 Scaling & Persistence
- **Scaler**: `sklearn.preprocessing.StandardScaler` fitted on `data/train_clean.csv` over all 9 features:
  $$\tilde{\mathbf{z}} = \frac{\mathbf{z} - \boldsymbol{\mu}}{\boldsymbol{\sigma}}$$
- **Persistence Path**: `models/scaler.joblib`.
- **Handling Outliers in Scaler**: The scaler is fitted strictly on 100% clean baseline data (`train_clean.csv`) to prevent distribution distortion from anomalous spikes.

### 3.3 Sequence Generation for Temporal Model
- **Sliding Window Generation**:
  For an input array of length $N$, generates sequences of shape $(N - W + 1, W, 3)$ where $W = 30$ time steps ($2.5\text{ hours}$ at $5\text{-min}$ intervals) using the 3 core scaled features $(\tilde{T}, \tilde{P}, \widetilde{RH})$.
- **Streaming Rolling Buffer**:
  Maintains a FIFO queue of the last $W=30$ observations per station ID. If buffer length $k < 30$, provides cold-start zero-padding or returns `is_warm = False` with buffer size indicator.

```python
FEATURE_NAMES = [
    "temperature",
    "pressure",
    "humidity",
    "delta_temp",
    "delta_pressure",
    "delta_humidity",
    "sin_hour",
    "cos_hour",
    "dew_point",
]
CORE_FEATURE_NAMES = ["temperature", "pressure", "humidity"]
```

---

## 4. Module 3: Tier 2 Point ML Anomaly Detector (`tier2_point_ml.py`)

### 4.1 Algorithm & Architecture
- **Model**: `sklearn.ensemble.IsolationForest`
- **Hyperparameters**:
  - `n_estimators = 100` (Ensemble of 100 random decision trees)
  - `max_samples = 'auto'` ($\min(256, n_{\text{samples}})$)
  - `contamination = 0.05` (Nominal expected anomaly prior on validation)
  - `random_state = 42`
  - `n_jobs = -1`

### 4.2 Score Calibration Formulation
Scikit-learn's `decision_function(\mathbf{z})` returns raw scores where positive values represent inliers and negative values represent outliers. To output a calibrated probability/anomaly score $S_{\text{point}} \in [0.0, 1.0]$:

#### Logistic Sigmoid Calibration:
$$S_{\text{point}}(t) = \frac{1}{1 + \exp\left( \kappa \cdot (\text{decision\_function}(\tilde{\mathbf{z}}_t) - \tau) \right)}$$
- Where $\kappa = 12.0$ (steepness scaling factor) and $\tau = 0.0$ (decision boundary offset).
- Under clean baseline: $\text{decision\_function} \approx +0.15 \implies S_{\text{point}} \approx \frac{1}{1 + e^{1.8}} \approx 0.14$ (Low/Clean).
- At decision threshold: $\text{decision\_function} = 0.0 \implies S_{\text{point}} = 0.50$ (Anomaly threshold).
- Under severe anomaly: $\text{decision\_function} \approx -0.25 \implies S_{\text{point}} \approx \frac{1}{1 + e^{-3.0}} \approx 0.95$ (Critical anomaly).

### 4.3 Persistence & Artifacts
- **Persistence Path**: `models/isolation_forest.joblib`
- **Class Interface**:
  - `fit(X: np.ndarray) -> PointAnomalyDetector`
  - `predict_score(X: np.ndarray) -> np.ndarray` (vectorized $[0, 1]$ scores)
  - `predict_score_single(z: np.ndarray) -> float` (real-time single observation)
  - `save(path: Union[str, Path]) -> None`
  - `load(path: Union[str, Path]) -> PointAnomalyDetector`

---

## 5. Module 4: Tier 2 Temporal ML Anomaly Detector (`tier2_temporal_ml.py`)

### 5.1 Architecture: PyTorch GRU / LSTM Autoencoder
Temporal anomalies (such as subtle drift, unnatural flatness, or sequence-level pattern disruption) cannot be detected by point models alone. The `GRUAutoencoder` learns the manifold of normal multi-step diurnal dynamics.

```
Input Sequence: (Batch, W=30, Dim=3)
                 │
                 ▼
       ┌──────────────────┐
       │ GRU Encoder      │  (input_dim=3, hidden_dim=32, num_layers=1, batch_first=True)
       └─────────┬────────┘
                 │ Last hidden state h_30: (Batch, 32)
                 ▼
       ┌──────────────────┐
       │ Bottleneck Enc   │  Linear(32 -> 16) + ReLU/Tanh -> Latent z: (Batch, 16)
       └─────────┬────────┘
                 │
                 ▼
       ┌──────────────────┐
       │ Bottleneck Dec   │  Linear(16 -> 32) -> h_0_dec: (Batch, 32)
       │ & Repeat Vector  │  Repeat z across W=30 steps -> (Batch, 30, 16)
       └─────────┬────────┘
                 │
                 ▼
       ┌──────────────────┐
       │ GRU Decoder      │  (input_dim=16, hidden_dim=32, num_layers=1, batch_first=True)
       └─────────┬────────┘
                 │ Decoder Output: (Batch, 30, 32)
                 ▼
       ┌──────────────────┐
       │ Output Projector │  Linear(32 -> 3)
       └─────────┬────────┘
                 │
                 ▼
Reconstructed Sequence: (Batch, W=30, Dim=3)
```

### 5.2 Mathematical Loss & Reconstruction Error
- **Training Loss (MSE)**:
  $$\mathcal{L}(\mathbf{X}, \mathbf{\hat{X}}) = \frac{1}{W \times 3} \sum_{w=1}^W \sum_{j=1}^3 \left( X_{w, j} - \hat{X}_{w, j} \right)^2$$
- **Step Reconstruction Error at Current Time $t$ ($w=W$)**:
  $$e_t = \frac{1}{3} \sum_{j \in \{T, P, RH\}} \left( X_{W, j} - \hat{X}_{W, j} \right)^2$$
- **Statistical Anomaly Threshold $\theta_{\text{temporal}}$**:
  Evaluated on clean validation sequence reconstruction errors:
  $$\theta_{\text{temporal}} = \mu_{\text{val\_MSE}} + 3.0 \cdot \sigma_{\text{val\_MSE}}$$
- **Normalized Temporal Anomaly Score**:
  $$S_{\text{temporal}}(t) = \text{clip}\left( \frac{e_t}{\theta_{\text{temporal}}}, 0.0, 1.0 \right)$$
  *(Or smooth saturating function $S_{\text{temporal}}(t) = 1.0 - \exp\left( -\ln(2) \cdot \frac{e_t}{\theta_{\text{temporal}}} \right)$ where $e_t = \theta \implies S = 0.50$)*.

### 5.3 Model Checkpointing & Persistence
- **Persistence Path**: `models/autoencoder.pt`
- **Saved Metadata Dictionary**:
  ```python
  checkpoint = {
      "model_type": "GRUAutoencoder",
      "model_state_dict": model.state_dict(),
      "input_dim": 3,
      "hidden_dim": 32,
      "bottleneck_dim": 16,
      "window_size": 30,
      "threshold": float(threshold),
      "mean_mse": float(mean_mse),
      "std_mse": float(std_mse),
      "trained_epochs": epochs,
  }
  ```

---

## 6. End-to-End Real-Time Ingestion & Streaming Buffer Specification

When streaming live telemetry into the system, observations arrive one-by-one per station. The following execution flow coordinates the 4 components:

```
Incoming Record: {timestamp, station_id, temperature, pressure, humidity}
                                  │
                                  ▼
                     1. Tier1QCEngine.check_observation(...)
                                  │
                ┌─────────────────┴─────────────────┐
                ▼ [Hard Violation]                  ▼ [Passed QC]
        S_Tier1 = 1.0                       S_Tier1 = 0.0
        is_hard_override = True             Update Station Observation Buffer
        Skip ML Inferences                                  │
                │                                           ▼
                │                          2. Preprocessor.extract_features_single(...)
                │                             (Computes 9D features, scale via scaler.joblib)
                │                                           │
                │                                           ▼
                │                          3. PointAnomalyDetector.predict_score_single(...)
                │                             (Isolation Forest score -> S_point in [0, 1])
                │                                           │
                │                                           ▼
                │                          4. TemporalAnomalyDetector.predict_score_single(...)
                │                             (If buffer len >= 30, GRU Autoencoder MSE -> S_temporal in [0, 1])
                │                             (If buffer len < 30, S_temporal = 0.0, is_warm = False)
                │                                           │
                └─────────────────┬─────────────────────────┘
                                  ▼
                   Output: (S_Tier1, S_point, S_temporal, features, qc_flags)
```

---

## 7. Exhaustive Edge Cases & Defensive Safeguards

| # | Scenario / Edge Case | Mathematical / Physical Consequence | Defensive Safeguard & Implementation |
|---|---|---|---|
| 1 | Relative Humidity $RH \le 0.0\%$ | $\ln(RH / 100)$ evaluates to $\ln(0) = -\infty$ in Dew Point | Clamp $RH = \max(RH, 0.01\%)$ prior to evaluating $\ln$ in Magnus-Tetens. |
| 2 | Division by zero in Dew Point ($T = -243.5^\circ\text{C}$) | Denominator $T + 243.5 = 0$ | Tier 1 range check catches $T < -40^\circ\text{C}$ and aborts; clamp denominator to $\epsilon = 10^{-4}$. |
| 3 | Cold-start stream ($< 30$ historical observations) | Sequence window cannot form $(30, 3)$ tensor for Autoencoder | Return $S_{\text{temporal}} = 0.0$ with `is_warm = False`; Downstream fusion applies buffer penalty $C_{\text{fused}} -= 0.20$. |
| 4 | Offline station gap ($> 15$ min elapsed between records) | High risk of false positive frozen detection across gaps | Reset persistence buffer and sequence history upon gap detection ($\Delta t > 15\text{ min}$). |
| 5 | Non-numeric string payload (e.g. `"$ERR_NaN#"`) | `float()` casting failure | Pydantic validation & Tier 1 regex check catches non-numeric tokens, returns `is_valid=False, corrupt_token=True`. |
| 6 | Out-of-order timestamps ($t_i < t_{i-1}$) | Negative $\Delta t$ and distorted backward differences | Tier 1 flags `non_monotonic_timestamp = True` and rejects/re-sorts record. |
| 7 | Duplicate timestamps ($t_i = t_{i-1}$) | Zero $\Delta t$ causing division-by-zero in derivative rates | Tier 1 flags `duplicate_timestamp = True` with status `DUPLICATE_DISCARDED`. |
| 8 | Singular feature variance ($\sigma_j = 0$) during scaling | Division by zero in standard scaler $\frac{x - \mu}{0}$ | Scaler fitted on 20-day clean baseline where physical diurnal cycle guarantees $\sigma_T > 3.0, \sigma_P > 4.0, \sigma_{RH} > 15.0$. |
| 9 | Model artifact missing from disk (`models/` empty) | `FileNotFoundError` on pipeline initialization | Implement automatic fallback or explicit initialization check with clear actionable exception. |

---

## 8. Verification Strategy & Test Specifications

### 8.1 Tests for `tests/test_tier1_qc.py`
1. `test_wmo_temperature_bounds`: Asserts $T \in [-40, 60]$ passes, $T=-45^\circ\text{C}$ and $T=65^\circ\text{C}$ trigger `range_temp_violation` and $S_{\text{Tier1}}=1.0$.
2. `test_wmo_pressure_bounds`: Asserts $P \in [300, 1100]$ passes, $P=250\text{ hPa}$ and $P=1150\text{ hPa}$ fail.
3. `test_wmo_humidity_bounds`: Asserts $RH \in [0, 104]$ passes, $RH=-5\%$ and $RH=110\%$ fail.
4. `test_rate_of_change_step_limits`: Asserts $\Delta T = 6.0^\circ\text{C}/5\text{min}$ triggers step violation.
5. `test_persistence_frozen_sensor`: Asserts 6 consecutive identical readings trigger `frozen_sensor = True`.
6. `test_missing_and_corrupt_tokens`: Asserts `NaN`, `None`, and `"$ERR#"` trigger `missing_value` or `corrupt_token`.
7. `test_duplicate_and_out_of_order_timestamps`: Asserts non-monotonic and identical timestamps are flagged.

### 8.2 Tests for `tests/test_tier2_ml.py`
1. `test_preprocessor_9_features`: Asserts output dataframe contains all 9 required features with correct Magnus-Tetens dew point.
2. `test_preprocessor_scaler_fit_transform`: Asserts scaler normalizes data with $\mu \approx 0, \sigma \approx 1$ and serializes/deserializes cleanly.
3. `test_sequence_generator_shape`: Asserts sequence generator yields tensor of shape $(N - 30 + 1, 30, 3)$.
4. `test_isolation_forest_training_and_score`: Asserts Isolation Forest trains on scaled data, scores normal samples $\le 0.30$, and scores injected spikes $\ge 0.70$.
5. `test_autoencoder_reconstruction_and_threshold`: Asserts PyTorch `GRUAutoencoder` reconstructs clean baseline with validation MSE $< 0.05$ and flags high MSE on disrupted temporal sequences.
6. `test_point_and_temporal_artifact_persistence`: Asserts `scaler.joblib`, `isolation_forest.joblib`, and `autoencoder.pt` can be saved and reloaded with identical inference output.
