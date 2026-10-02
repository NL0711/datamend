# Changes Implemented for Milestone M2 (5-Tier ML Pipeline Engine)

## Overview
Implemented the complete, mathematically grounded, 5-tier machine learning pipeline for SkyGuard AI, adhering strictly to the three primary AWS parameters (Temperature $T$, Atmospheric Pressure $P$, Relative Humidity $RH$), with zero hardcoding or fake mocks.

---

## 1. Modules Implemented in `backend/app/ml/`

### 1.1 `backend/app/ml/tier1_qc.py`
- **Class**: `Tier1QC` / `Tier1QCEngine`, `Tier1QCConfig`, `Tier1QCResult`
- **Rules Implemented**:
  - WMO Physical Range Limits: $T \in [-40.0, 60.0]^\circ\text{C}$, $P \in [300.0, 1100.0]\text{ hPa}$, $RH \in [0.0, 104.0]\%$.
  - Rate-of-Change Step Limits: $|\Delta T| \le 5.0^\circ\text{C}$, $|\Delta P| \le 3.0\text{ hPa}$, $|\Delta RH| \le 25.0\%$.
  - Persistence / Frozen Sensor: $K=6$ consecutive steps ($30\text{ min}$) with empirical variance $< 10^{-6}$.
  - Data Integrity: Null, NaN, Sentinel values ($-999.0, 9999.0$), non-numeric corrupt tokens, duplicate and non-monotonic timestamps.
- **Methods**: `evaluate()`, `check_observation()`, `check_batch()`.

### 1.2 `backend/app/ml/preprocessor.py`
- **Class**: `DataPreprocessor`, `PreprocessorResult`, `StationBuffer`
- **9-Feature Engineering**:
  - $z_1 = \text{temperature}$, $z_2 = \text{pressure}$, $z_3 = \text{humidity}$
  - $z_4 = \text{temp\_delta}$ (backward difference $\Delta T$)
  - $z_5 = \text{press\_delta}$ (backward difference $\Delta P$)
  - $z_6 = \text{humid\_delta}$ (backward difference $\Delta RH$)
  - $z_7 = \text{temp\_roll\_std}$ (6-step rolling standard deviation $\sigma_{T, 6}$)
  - $z_8 = \text{press\_roll\_std}$ (6-step rolling standard deviation $\sigma_{P, 6}$)
  - $z_9 = \text{humid\_roll\_std}$ (6-step rolling standard deviation $\sigma_{RH, 6}$)
- **Magnus-Tetens Dew Point**: $T_d = \frac{243.5 \cdot \gamma}{17.67 - \gamma}$ where $\gamma = \frac{17.67 \cdot T}{T + 243.5} + \ln\left(\frac{\text{clip}(RH, 0.01, 104)}{100}\right)$.
- **Sliding Sequence Tensor Generation**: $W=30$ steps for core scaled $(T, P, RH)$.
- **Serialization**: `StandardScaler` saved/loaded from `models/scaler.joblib` and `models/preprocessor.joblib`.

### 1.3 `backend/app/ml/tier2_point_ml.py`
- **Class**: `IsolationForestPointDetector` / `PointAnomalyDetector`
- **Model**: Scikit-Learn `IsolationForest(n_estimators=100, contamination=0.01, random_state=42)`
- **Calibrated Logistic Sigmoid Scoring**:
  $$S_{\text{point}} = \frac{1}{1 + \exp(\kappa \cdot (\text{decision\_function}(z) - \tau))}$$
  with $\kappa=15.0$ and $\tau=-0.05$, ensuring clean observations score $< 0.35$ and extreme anomalies score $\ge 0.70$.
- **Serialization**: `models/isolation_forest.joblib` with background samples for TreeSHAP.

### 1.4 `backend/app/ml/tier2_temporal_ml.py`
- **Class**: `TemporalAutoencoderDetector`, `TemporalAutoencoder`, `GRUEncoder`, `GRUDecoder`
- **PyTorch Architecture**:
  - Encoder: 2-layer GRU (input_dim=3, hidden_dim=32, latent_dim=16).
  - Decoder: 2-layer GRU (latent_dim=16, hidden_dim=32, output_dim=3) repeated across sequence window $W=30$.
- **Reconstruction Scoring**: Blended step MSE ($0.7 \cdot e_{\text{last}} + 0.3 \cdot e_{\text{seq}}$) normalized against validation threshold $\theta_{\text{temporal}} = \mu + 3\sigma$.
- **Serialization**: `models/temporal_autoencoder.pt` and `models/autoencoder.pt`.

### 1.5 `backend/app/ml/tier3_multivariate.py`
- **Class**: `Tier3MultivariateDetector`, `Tier3Result`
- **Thermodynamic Consistency**: Clausius-Clapeyron Magnus-Tetens dew point constraint $T_d \le T + 0.5^\circ\text{C}$.
- **Regularized Mahalanobis Distance**:
  $$D_M^2 = (\mathbf{x} - \boldsymbol{\mu})^T (\boldsymbol{\Sigma} + 10^{-5}\mathbf{I})^{-1} (\mathbf{x} - \boldsymbol{\mu})$$
  Evaluated against Chi-square CDF: $S_{\text{mahalanobis}} = F_{\chi^2(3)}(D_M^2)$.
- **Combined Tier 3 Score**: $S_{\text{Tier3}} = \max(S_{\text{thermo}}, S_{\text{mahalanobis}})$.
- **Serialization**: `models/mahalanobis.joblib`.

### 1.6 `backend/app/ml/fusion.py`
- **Class**: `AnomalyFusionEngine`, `FusionResult`, `Severity`, `TierScores`
- **Hard Deterministic Override**: If Tier 1 hard flag is active $\implies S_{\text{fused}} = 1.0, \text{Severity} = \text{CRITICAL}, \text{override\_applied} = \text{True}$.
- **Weighted Convex Combination**:
  $$S_{\text{fused}} = 0.25 S_{\text{Tier1\_soft}} + 0.20 S_{\text{point}} + 0.25 S_{\text{temporal}} + 0.30 S_{\text{Tier3}}$$
- **Confidence Metric**: Concordance standard deviation across active models with cold-start buffer length penalty:
  $$C_{\text{fused}} = \text{clip}\left(1 - \sqrt{3}\sigma_s - 0.20\left(1 - \frac{N}{30}\right), 0.10, 1.00\right)$$
- **Severity Tiers**: `NONE` ($<0.25$), `LOW` ($0.25-0.45$), `MEDIUM` ($0.45-0.65$), `HIGH` ($0.65-0.85$), `CRITICAL` ($\ge 0.85$).

### 1.7 `backend/app/ml/tier4_classifier.py`
- **Class**: `FaultClassifier`, `FaultClass`, `ClassificationResult`
- **Taxonomy**: `NORMAL`, `SPIKE`, `DRIFT`, `FROZEN`, `DROPOUT`, `NOISE_BURST`, `MULTIVARIATE_INCONSISTENCY`, `DATA_CORRUPTION`, `METEOROLOGICAL_EXTREME`, `UNCERTAIN_EVENT`.
- **Convective Front Disambiguation**: Severe rapid cooling ($\Delta T_{15\text{min}} \le -3.0^\circ\text{C}$), barometric pressure jump ($|\Delta P_{15\text{min}}| \ge 1.5\text{ hPa}$), and relative humidity surge ($\Delta RH_{15\text{min}} \ge +15\%$) strictly obeying Clausius-Clapeyron physics ($T_d \le T + 0.5^\circ\text{C}$) are classified as `METEOROLOGICAL_EXTREME` with `is_fault = False`.
- **Hardware Faults**: Single variable spikes, frozen sensors, dropouts, linear drift, noise bursts, thermodynamic decoupling flagged with `is_fault = True`.

### 1.8 `backend/app/ml/tier5_health.py`
- **Class**: `SensorHealthEngine`, `HealthStatus`, `DegradationRisk`, `StationHealthState`
- **Dynamic SHI Formulation ($W=288\text{ steps} = 24\text{ hours}$)**:
  $$\text{SHI}_{\text{raw}} = 100 \times \left[ 1 - \left( 0.30 R_{\text{anomaly}} + 0.25 R_{\text{frozen}} + 0.20 S_{\text{drift}} + 0.15 R_{\text{missing}} + 0.10 S_{\text{sev}} \right) \right]$$
- **EMA Damping**: $\text{SHI}(t) = 0.10 \text{SHI}_{\text{raw}} + 0.90 \text{SHI}(t-1)$.
- **Predictive Degradation Extrapolation**: OLS linear slope $\Delta \text{SHI}/\text{day} = m \times 288$ and estimated Time to Failure (hours until $\text{SHI} < 50$).
- **Action Recommendations**: Root-cause diagnostic advice synthesized based on the dominant failure mode.

### 1.9 `backend/app/ml/tier5_explain.py`
- **Class**: `ExplainabilityEngine`, `ExplanationResult`, `FeatureAttribution`
- **TreeSHAP Attributions**: Exact Shapley values calculated via `shap.TreeExplainer` on fitted Isolation Forest models, normalized such that $\sum C_i = 100.0\%$.
- **Natural Language Translation**: Generates contextual operator diagnosis with physical units, parameter deltas, and failure causes.

### 1.10 `backend/app/ml/pipeline.py`
- **Class**: `SkyGuardPipeline`, `InferenceResult`, `TierScores`
- **Master Orchestrator**: Unifies all 5 tiers into high-throughput streaming (`process_observation`) and batch (`process_batch`) execution.

---

## 2. Scripts and Model Artifacts

### 2.1 `scripts/train_models.py`
- Automated CLI training pipeline reading `data/train_clean.csv` (5,760 samples) and `data/val_mixed.csv` (1,440 samples).
- Persists all genuine production models to `models/`:
  - `models/preprocessor.joblib` & `models/scaler.joblib`
  - `models/isolation_forest.joblib`
  - `models/temporal_autoencoder.pt` & `models/autoencoder.pt`
  - `models/mahalanobis.joblib`
  - `models/fault_classifier.joblib`
  - `models/model_metadata.json`

---

## 3. Test Suites Implemented in `tests/`
- `tests/test_tier1_qc.py` (13 tests)
- `tests/test_tier2_ml.py` (9 tests)
- `tests/test_tier3_multivariate.py` (8 tests)
- `tests/test_fusion.py` (8 tests)
- `tests/test_tier4_classifier.py` (10 tests)
- `tests/test_tier5_health_explain.py` (6 tests)
- `tests/test_pipeline.py` (7 tests)

**Total Test Suite Result**: **189 tests passing with 0 errors**.
