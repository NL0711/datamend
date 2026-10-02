# Handoff Report — Milestone M1 Anomaly Injector Architecture

**Agent**: `m1_explorer_2`  
**Working Directory**: `c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\.agents\m1_explorer_2`  
**Handoff Type**: Hard Handoff (Investigation & Architectural Specification Complete)  
**Target Module**: `backend/simulator/anomaly_injector.py`  
**Recipient**: Orchestrator (`327adcb6-3df1-42e8-9da6-eaf0ceeb99da`)

---

## 1. Observation

- Examined `PROJECT.md`, `ORIGINAL_REQUEST.md`, `AGENTS.md`, `ARCHITECTURE.md`, `TODO.md`, `GOAL.md`, and `.agents/survey_spec_miner_2/report.md`.
- `backend/simulator/anomaly_injector.py` currently contains only a 4-line docstring placeholder.
- Requirements mandate 6 primary programmatic anomaly injection functions:
  1. `inject_spike`: Instantaneous step jumps in $T, P, RH$ (single/multi-step transient impulse).
  2. `inject_drift`: Progressive linear/exponential calibration offset accumulating over hours/days.
  3. `inject_frozen`: Sensor values stuck/repeating with zero variance ($\sigma^2 = 0$) over $K$ steps.
  4. `inject_dropout`: Abrupt null/zero/sentinel values representing signal loss.
  5. `inject_noise_burst`: High-frequency variance noise surge violating nominal variance bounds.
  6. `inject_multivariate_inconsistency`: Physical decoupling where $T$ increases while $RH$ also increases sharply without pressure drop, violating Clausius-Clapeyron laws.
- In addition, two critical auxiliary patterns were identified from specifications:
  7. `inject_meteorological_extreme`: Genuine convective storm/squall line where multi-variable physics remain valid (`is_fault=False`), enabling rigorous evaluation of the genuine extreme vs sensor fault classifier.
  8. `inject_data_corruption`: Malformed framing, string tokens (`"$ERR_COMM#"`, `None`), bit-flips, duplicate or reversed timestamps.
- Ground truth labeling requirements mandate tracking: `is_anomaly`, `anomaly_type`, `severity`, `is_fault`, `affected_params`, `clean_temperature`, `clean_pressure`, `clean_humidity`, and `anomaly_metadata` (JSON).

---

## 2. Logic Chain

1. **Clean Baseline Immutability & Invertibility**:
   - To benchmark reconstruction errors for autoencoders and evaluate imputation without data destruction, the original clean series must be preserved alongside injected perturbations (`clean_temperature`, `clean_pressure`, `clean_humidity`).
2. **Ground Truth Consistency**:
   - Every injected step must be accurately labeled so that downstream benchmark scripts (`scripts/test_anomaly_detection.py`) can compute Precision, Recall, and F1 per fault type against an unambiguous ground truth.
3. **Severity Escalation & Chained Composition**:
   - Multiple anomalies can be applied sequentially to different sensor channels and time windows. Overlapping injections must use bitwise OR (`is_anomaly`) and hierarchical severity escalation (`CRITICAL > HIGH > MEDIUM > LOW > NONE`).
4. **Distinguishing Weather Extremes from Sensor Faults**:
   - By explicitly modeling `inject_meteorological_extreme` with `is_fault=False`, we provide the benchmark data required to verify Tier 4's ability to avoid false alarms during genuine convective squalls.

---

## 3. Caveats

- **No Caveats**: All 6 required anomaly patterns plus 2 auxiliary patterns and the fluent `AnomalyInjector` builder class have been mathematically formalized and mapped directly to the project architecture. Implementation will take place in the worker phase of Milestone M1.

---

## 4. Conclusion

The complete architectural blueprint and mathematical specifications for `backend/simulator/anomaly_injector.py` have been designed and documented in `.agents/m1_explorer_2/analysis.md`. The design provides:
- Mathematical formulations, parameter bounds, and default values for all 8 anomaly types.
- A standardized ground-truth DataFrame schema.
- Deterministic seed management for 100% reproducible benchmark generation.
- A chainable `AnomalyInjector` builder supporting both batch generation and real-time streaming steps.

---

## 5. Verification Method

To independently verify the architecture and specifications:
1. Inspect the detailed analysis file:
   `view_file c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\.agents\m1_explorer_2\analysis.md`
2. Verify that all 6 required functions (`inject_spike`, `inject_drift`, `inject_frozen`, `inject_dropout`, `inject_noise_burst`, `inject_multivariate_inconsistency`) and ground truth columns are fully defined.
3. Once implemented in M1 Worker phase, run pytest:
   `pytest tests/test_simulator.py -v`
