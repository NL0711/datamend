# Summary of Changes — Milestone M1 Remediation (Iteration 2)

**Agent**: `m1_worker_2`  
**Milestone**: M1 — Simulator & Anomaly Injector Engine  
**Timestamp**: 2026-08-24T05:50:00Z  

---

### 1. `backend/simulator/scenarios.py`
- **Dynamic Scenario Slicing and Duration Scaling**:
  - Replaced hardcoded index arithmetic and subtraction expressions (`min(48, len(raw_df) - 1200)`, `min(120, len(raw_df) - 1000)`, `min(96, len(raw_df) - 600)`) with dynamic proportional indexing relative to `len(raw_df)` in `MultiStationNetworkScenario`.
  - Added dynamic proportional placement and duration clamping in `SingleFaultScenario`, `WeatherFrontScenario`, and `HealthDegradationScenario` so that scenarios execute without index errors on arbitrary durations from 0.5 days up to 30+ days.
- **Dynamic Anomaly Counts in Metadata**:
  - Defined `FAULT_DURATIONS` lookup mapping nominal anomaly lengths for each single fault class (`spike: 2`, `drift: 80`, `frozen: 72`, `dropout: 24`, `noise: 36`, `multivariate: 24`).
  - In `SingleFaultScenario.get_metadata()`, dynamically compute `expected_anomaly_count` according to the actual injected count rather than a hardcoded 72.
  - In `HealthDegradationScenario.get_metadata()`, accurately calculate `expected_anomaly_count` (488 for 3-day scenario) taking into account that the transient spike at index 450 is embedded within the Phase 2 drift interval.
  - In `MultiStationNetworkScenario.get_metadata()`, dynamically aggregate anomaly counts across all 4 stations (`AWS-DEL-01`, `AWS-MUM-02`, `AWS-LEH-03`, `AWS-JAI-04`).

---

### 2. `backend/simulator/anomaly_injector.py`
- **FutureWarning Prevention**:
  - In `inject_data_corruption()`, explicitly cast target columns to `object` dtype before injecting string sentinel tokens (`"$ERR_COMM_TIMEOUT#"`), completely eliminating pandas dtype deprecation warnings.
- **Input Validation & ValueError Guards**:
  - Added strict parameter validation guards:
    - `inject_dropout()`: raises `ValueError` if `fill_mode` is not in `["nan", "zero", "sentinel_neg999", "null"]`.
    - `inject_noise_burst()`: raises `ValueError` if `noise_type` is not in `["gaussian", "uniform"]`.
    - `inject_multivariate_inconsistency()`: raises `ValueError` if `mode` is not in `["thermodynamic_inversion", "unphysical_supersaturation", "barometric_decoupling"]`.
    - `inject_data_corruption()`: raises `ValueError` if `corruption_mode` is not in `["string_err", "out_of_bounds", "duplicate_timestamp"]`.
  - Verified target column existence across all injectors with `ValueError(f"Column '{col}' not found in DataFrame.")`.

---

### 3. `tests/test_simulator.py`
- **Solar Cycle Seasonal Parameter Alignment**:
  - In `test_diurnal_temperature_solar_cycle()`, set `temp_seasonal_amp=0.0` in `DiurnalParameters` to isolate the pure diurnal solar radiation cycle without seasonal August solar insolation offsets.
- **Noise Burst Variance Calculation**:
  - In `test_inject_noise_burst_variance_multiplier()`, evaluated differenced signal variance (`burst_diff_var > clean_diff_var * 4.0`) and residual noise variance (`(df_burst - df_clean).var() > 5.0`) to avoid baseline diurnal slope variance distortion.
- **Multi-Station Multi-Duration Verification**:
  - In `test_scenario_multi_station_network_heterogeneity()`, verified that multi-station network generation succeeds on both 3.0-day and 7.0-day durations.
- **Compound Health Degradation Slice Assertion**:
  - In `test_scenario_health_degradation_trajectory()`, updated Phase 2 assertions to verify that slices `288:449` and `452:487` are `"DRIFT"`, slice `450:451` is `"SPIKE"`, and all rows in `288:487` have `is_anomaly == True`.
- **Validation Guard Unit Tests**:
  - Added `test_injector_validation_guards()` to verify that all 4 invalid injector parameter cases raise `ValueError`.

---

### 4. `data/*.csv` Re-Generation
- Ran `python scripts/generate_datasets.py` to regenerate all 4 benchmark datasets:
  - `data/baseline_clean.csv`: 8,640 rows, 100% clean, zero anomalies.
  - `data/train_clean.csv`: 5,760 rows, 100% clean, zero anomalies.
  - `data/val_mixed.csv`: 1,440 rows, 30 anomalies.
  - `data/test_anomalies.csv`: 1,440 rows, 19 anomalies.
- Verified strict forward temporal ordering ($\max(\text{train}) < \min(\text{val}) < \max(\text{val}) < \min(\text{test})$) with zero temporal leakage.
