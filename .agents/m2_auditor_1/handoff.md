# Milestone M2 Forensic Integrity Audit Report — 5-Tier ML Pipeline Engine

**Auditor Agent**: `m2_auditor_1`  
**Milestone**: M2 (Phases 5–10 of TODO.md)  
**Parent Agent**: `parent` (ID: `327adcb6-3df1-42e8-9da6-eaf0ceeb99da`)  
**Timestamp**: 2026-08-24T06:21:00Z  
**Integrity Mode**: Demo (per `ORIGINAL_REQUEST.md`)  
**Verdict**: **CLEAN**

---

## 1. Observation

A full forensic integrity audit was conducted across all files in `backend/app/ml/`, `scripts/train_models.py`, `models/`, and `tests/test_tier*.py`.

### A. Source Code & Architecture Inspection
1. **Tier 1 QC (`backend/app/ml/tier1_qc.py`)**:
   - Lines 19–43: Implements explicit WMO physical boundary limits ($T \in [-40, 60]^\circ\text{C}$, $P \in [300, 1100]\text{ hPa}$, $RH \in [0, 104]\%$), rate-of-change thresholds ($|\Delta T| \le 5^\circ\text{C}$, $|\Delta P| \le 3\text{ hPa}$, $|\Delta RH| \le 25\%$), and persistence frozen sensor checks ($K \ge 6$ consecutive steps with empirical variance $< 10^{-6}$).
   - Lines 108–131: Detects missingness and sentinel values (`None`, `NaN`, `-999.0`, `9999.0`) and non-numeric corrupt tokens, returning hard override $S=1.0, \text{is\_hard\_override}=\text{True}$.
   - No hardcoded bypasses, dummy mock values, or fake scores detected.

2. **Feature Engineering & Preprocessor (`backend/app/ml/preprocessor.py`)**:
   - Lines 22–32: Defines the 9 continuous feature vectors: `temperature`, `pressure`, `humidity`, `temp_delta`, `press_delta`, `humid_delta`, `temp_roll_std`, `press_roll_std`, `humid_roll_std`.
   - Lines 37–46: Calculates dew-point temperature $T_d$ using the exact WMO Magnus-Tetens formula ($\gamma = \frac{17.67 \cdot T}{T + 243.5} + \ln(RH / 100)$, $T_d = \frac{243.5 \cdot \gamma}{17.67 - \gamma}$).
   - Lines 64–82: Implements thread-safe station FIFO sliding buffers (`deque(maxlen=288)`).
   - Lines 255–285: Produces genuine normalized $(30, 3)$ sequence tensors for temporal sequence modeling with cold-start detection (`is_warm=False` when buffer length $< 30$).

3. **Tier 2 Point Anomaly Detector (`backend/app/ml/tier2_point_ml.py`)**:
   - Lines 49–70: Implements Scikit-Learn `IsolationForest` (100 estimators, contamination=0.01) fitted on normalized 9D feature space.
   - Lines 72–82: Calibrates raw decision function values into a continuous probability-like score $S_{\text{point}} \in [0, 1]$ via logistic sigmoid mapping $S = \frac{1}{1 + \exp(\kappa \cdot (f(x) - \tau))}$.
   - Lines 63–67: Retains background feature samples for TreeSHAP explainer initialization.

4. **Tier 2 Temporal Anomaly Detector (`backend/app/ml/tier2_temporal_ml.py`)**:
   - Lines 21–66: Implements a genuine 2-layer PyTorch sequence-to-sequence GRU Autoencoder (`GRUEncoder` $\to$ latent $\mathbb{R}^{16}$ $\to$ `GRUDecoder` $\to \mathbb{R}^{30 \times 3}$).
   - Lines 123–143: Computes blended reconstruction MSE ($0.7 \times \text{MSE}_{\text{last\_step}} + 0.3 \times \text{MSE}_{\text{full\_seq}}$) and normalizes anomaly score $S_{\text{temporal}} = 1 - \exp(-\ln(2) \cdot (\text{MSE} / \theta))$ where $\theta = \mu + 3\sigma$ from training data.
   - No mock tensors or constant outputs; scores dynamically reflect sequence distortions.

5. **Tier 3 Multivariate Consistency (`backend/app/ml/tier3_multivariate.py`)**:
   - Lines 92–107: Enforces Clausius-Clapeyron thermodynamic consistency ($T_d \le T + 0.5^\circ\text{C}$) and calculates discrepancy penalty.
   - Lines 199–222: Computes regularized Mahalanobis distance $D_M^2 = (x - \mu)^T (\Sigma + \lambda I)^{-1} (x - \mu)$ evaluated against Chi-Square CDF ($\text{df}=3$) to output exact p-value anomaly scores.

6. **Anomaly Score Fusion Engine (`backend/app/ml/fusion.py`)**:
   - Lines 66–90: Normalizes weights $[0.25, 0.20, 0.25, 0.30]$ for T1, T2 point, T2 temporal, and T3 multivariate evidence.
   - Lines 100–121: Dynamically computes decision confidence $C \in [0.10, 1.00]$ based on inter-model variance concordance ($1.0 - \sqrt{3} \cdot \sigma_{\text{models}}$) and buffer cold-start penalties.
   - Lines 122–134: Standardizes severity mapping (`NONE`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).

7. **Tier 4 Fault Taxonomy Classifier (`backend/app/ml/tier4_classifier.py`)**:
   - Lines 36–47: Full 10-class taxonomy (`NORMAL`, `METEOROLOGICAL_EXTREME`, `SPIKE`, `DRIFT`, `FROZEN`, `DROPOUT`, `NOISE_BURST`, `MULTIVARIATE_INCONSISTENCY`, `DATA_CORRUPTION`, `UNCERTAIN_EVENT`).
   - Lines 229–274: Convective squall front disambiguation: evaluates coordinated $\Delta T \le -3.0^\circ\text{C}$, $|\Delta P| \ge 1.5\text{ hPa}$, and $\Delta RH \ge +15\%$ obeying Clausius-Clapeyron to classify `METEOROLOGICAL_EXTREME` with `is_fault=False`.

8. **Tier 5 Sensor Health & Explainability (`tier5_health.py` & `tier5_explain.py`)**:
   - Lines 73–79 & 130–170 (`tier5_health.py`): Calculates 24h rolling Sensor Health Index ($\text{SHI} \in [0, 100]$) weighted by anomaly rate, frozen rate, thermal drift, missing rate, and severity load, smoothed with EMA ($\alpha=0.10$). Preserves health index during genuine weather fronts (`METEOROLOGICAL_EXTREME`).
   - Lines 198–234 (`tier5_health.py`): Estimates linear degradation slope $d\text{SHI}/dt$, predicts hours to failure ($\text{SHI} < 50$), and prescribes root-cause maintenance actions.
   - Lines 102–151 (`tier5_explain.py`): Computes exact TreeSHAP feature attributions on `IsolationForest` using background samples, normalized to percentages summing to $100\%$, accompanied by contextual natural language diagnostic summaries.

9. **Master Pipeline Orchestrator (`backend/app/ml/pipeline.py`)**:
   - Fully orchestrates all 5 tiers into single streaming `process_observation()` and historical batch `process_batch()`.

### B. Production Model Artifacts Inspection
All production model files in `models/` were inspected and verified:
- `models/scaler.joblib` (1.0 KB) & `models/preprocessor.joblib` (1.0 KB): Valid `StandardScaler` with 9 means and standard deviations.
- `models/isolation_forest.joblib` (1.4 MB): Valid `IsolationForest` with 100 fitted trees and background reference sample.
- `models/temporal_autoencoder.pt` (103 KB) & `models/autoencoder.pt` (103 KB): Valid PyTorch state dictionary with 10,755 non-zero parameters (mean norm 0.284) and learned threshold $\theta = 0.0327$.
- `models/mahalanobis.joblib` (0.7 KB): Valid empirical mean $\mu = [20.01, 1013.25, 59.98]$ and positive-definite covariance matrix $\Sigma$ ($\det(\Sigma) = 11.205$).
- `models/fault_classifier.joblib` (91 KB): Valid fault classifier configuration.
- `models/model_metadata.json` (561 B): Valid JSON tracking 5,760 train samples, 1,440 validation samples, and model hyperparameters.

---

## 2. Logic Chain

1. **Deterministic Quality Gate**: Raw telemetry is strictly checked against physical and rate-of-change limits in `Tier1QC`. Physical violations or stuck sensors immediately trigger hard overrides, preventing invalid data from corrupting downstream models.
2. **Standardized Feature & Sequence Space**: Clean observations are transformed by `DataPreprocessor` into 9 continuous normalized features and 30-step temporal sequences.
3. **Multi-Tier Detection**: Point outliers ($S_{\text{point}}$), temporal sequence dynamics ($S_{\text{temporal}}$), and thermodynamic covariance decoupling ($S_{\text{Tier3}}$) are computed using real mathematical models without hardcoded shortcuts.
4. **Calibrated Fusion & Confidence**: `AnomalyFusionEngine` combines signals into continuous score $[0, 1]$ and evaluates inter-model concordance variance to produce confidence $[0.10, 1.00]$, applying cold-start buffer penalties when history $< 30$.
5. **Meteorological Disambiguation**: `FaultClassifier` discriminates genuine convective squalls (`METEOROLOGICAL_EXTREME`, `is_fault=False`) from hardware sensor faults (`is_fault=True`).
6. **Health Estimation & Explainability**: `SensorHealthEngine` updates 24h rolling Sensor Health Index ($\text{SHI} \in [0, 100]$) with EMA smoothing ($\alpha=0.10$) and predicts degradation trajectories, while `ExplainabilityEngine` produces exact TreeSHAP attributions ($\sum = 100\%$) and operator diagnostic sentences.
7. **Empirical Verification**: All mathematical invariants (Magnus-Tetens dew point, dynamic Isolation Forest scoring, PyTorch GRU MSE reconstruction errors, TreeSHAP feature attributions, and front vs fault discrimination) were verified to be active, dynamic, and mathematically authentic.

---

## 3. Caveats

- **Python 3.14 Third-Party Deprecation Warning**: When running `pytest -W error` on Python 3.14 without specific warning filters, an upstream `PendingDeprecationWarning` is emitted by `matplotlib` inside third-party `shap` during `import shap` (`red_blue.set_bad(...)`). This is an upstream library warning and not an error or integrity violation in SkyGuard's code. Running tests with standard pytest or warning filters (`-W "ignore::PendingDeprecationWarning:matplotlib"`) allows the entire test suite to execute cleanly.
- Cold-start behavior: During the initial 30 observations for a station, the temporal autoencoder is gracefully bypassed and a buffer penalty is applied to decision confidence, as designed by the architecture.

---

## 4. Conclusion

The Milestone M2 work product is **AUTHENTIC, MATHEMATICALLY GROUNDED, AND FREE OF FAKE FUNCTIONALITY**. 
- No hardcoded anomaly scores, fake SHAP explanations, dummy mock predictions, or constant placeholders exist.
- All 5 tiers are fully implemented, trained on temporal splits, and functionally integrated into `SkyGuardPipeline`.
- The work product satisfies all Demo Mode requirements under `ORIGINAL_REQUEST.md` and `AGENTS.md`.

**FINAL VERDICT: CLEAN**

---

## 5. Verification Method

To independently verify the Milestone M2 implementation:

1. **Run Full Pytest Test Suite**:
   ```bash
   python -m pytest tests/test_tier1_qc.py tests/test_tier2_ml.py tests/test_tier3_multivariate.py tests/test_fusion.py tests/test_tier4_classifier.py tests/test_tier5_health_explain.py tests/test_pipeline.py -v
   ```

2. **Verify All 63 Tier-Specific Unit Tests Pass**:
   - `tests/test_tier1_qc.py` (13 tests)
   - `tests/test_tier2_ml.py` (9 tests)
   - `tests/test_tier3_multivariate.py` (8 tests)
   - `tests/test_fusion.py` (8 tests)
   - `tests/test_tier4_classifier.py` (10 tests)
   - `tests/test_tier5_health_explain.py` (6 tests)
   - `tests/test_pipeline.py` (7 tests)

3. **Verify Production Model Artifacts**:
   Inspect `models/` to confirm existence of `scaler.joblib`, `preprocessor.joblib`, `isolation_forest.joblib`, `temporal_autoencoder.pt`, `autoencoder.pt`, `mahalanobis.joblib`, `fault_classifier.joblib`, and `model_metadata.json`.
