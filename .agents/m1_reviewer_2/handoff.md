# Milestone M1 Review & Adversarial Challenge Report

**Agent**: `m1_reviewer_2`  
**Roles**: Reviewer, Critic  
**Milestone**: M1 — Simulator & Anomaly Injector Engine (Phases 1–4 of `TODO.md`)  
**Timestamp**: 2026-08-24T05:45:00Z  
**Verdict**: **REQUEST_CHANGES**  

---

## 1. Observation

Direct observations from independent inspection and test suite execution:

### 1.1 Test Suite Execution Failures
Running `python -m pytest tests/ -v` produced **4 failures out of 57 tests** (4 failed in `tests/test_simulator.py`):

1. **`tests/test_simulator.py::test_diurnal_temperature_solar_cycle`**:
   ```
   AssertionError: assert np.float64(32.37) <= 30.0
   tests/test_simulator.py:58: assert df["temperature"].max() <= 30.0
   ```
   - *Cause*: In `backend/simulator/diurnal_generator.py` line 211, `temp_seasonal_amp` defaults to `5.0`. On August 1 (day of year 213), the seasonal term contributes $+3.77^\circ\text{C}$. Base ($20^\circ\text{C}$) + Season ($3.77^\circ\text{C}$) + Diurnal Amplitude ($8.0^\circ\text{C}$) + Noise reaches $32.37^\circ\text{C}$, exceeding the test bound of $30.0^\circ\text{C}$.

2. **`tests/test_simulator.py::test_inject_noise_burst_variance_multiplier`**:
   ```
   AssertionError: assert np.float64(13.751863607261583) > (np.float64(4.397071497175141) * 4.0)
   tests/test_simulator.py:195: assert burst_var > clean_var * 4.0
   ```
   - *Cause*: Over the 60-step window (indices 100 to 159, spanning 5 hours), the clean baseline undergoes a large diurnal temperature change, resulting in `clean_var = 4.397`. Adding noise with `burst_std = 3.5` ($\sigma^2 = 12.25$) yields `burst_var = 13.75`, which is not $> 4 \times 4.397 = 17.59$. The test compared total series variance against a $4\times$ multiplier of diurnal trend variance rather than white-noise residuals.

3. **`tests/test_simulator.py::test_scenario_multi_station_network_heterogeneity`**:
   ```
   ValueError: negative dimensions are not allowed
   File "backend/simulator/scenarios.py", line 333, in generate
     inj.inject_noise_burst(target_column="pressure", start_idx=min(1200, len(raw_df) - 48), duration=min(48, len(raw_df) - 1200), noise_factor=8.0, severity="MEDIUM", random_seed=s_seed)
   File "backend/simulator/anomaly_injector.py", line 328, in inject_noise_burst
     noise = rng.normal(0, burst_std, size=span)
   ```
   - *Cause*: When `MultiStationNetworkScenario(duration_days=3.0)` generates 864 rows, `len(raw_df) - 1200 = 864 - 1200 = -336`. This sets `duration = -336`, causing `span = -336` and triggering a negative dimension `ValueError` in numpy.

4. **`tests/test_simulator.py::test_scenario_health_degradation_trajectory`**:
   ```
   AssertionError: assert np.False_ where np.False_ = all()
   tests/test_simulator.py:295: assert (df.loc[288:487, "anomaly_type"] == "DRIFT").all()
   ```
   - *Cause*: In `backend/simulator/scenarios.py` lines 386–393, an intermittent spike is injected at `start_idx=450, duration=2` during the drift phase. `inject_spike` sets `df.loc[450:451, "anomaly_type"] = "SPIKE"`. Consequently, steps 450 and 451 have `anomaly_type == "SPIKE"`, failing the assertion that all rows from 288 to 487 are `"DRIFT"`.

---

### 1.2 Scenario Indexing Fragility on Custom Durations
Stress-testing the scenarios with custom durations surfaced multiple unhandled bounds errors:
- **`SingleFaultScenario(fault_type, duration_days)`**: Hardcodes `start_idx` values (500, 600, 800, 1000, 1200, 1400) without scaling by `duration_days`. If `duration_days < 5.0`, `dropout` (start_idx 1000) and `multivariate` (start_idx 1400) crash with `IndexError: start_idx out of range`.
- **`WeatherFrontScenario(duration_days)`**: Hardcodes `start_idx=864` (day 3) and `start_idx=1440` (day 5). If `duration_days < 6.0`, it crashes with `IndexError`.
- **`HealthDegradationScenario(duration_days)`**: Hardcodes `start_idx=288` and `start_idx=576`. If `duration_days < 3.0`, it crashes with `IndexError`.
- *Contrast*: `MultiFaultStressScenario` correctly uses dynamic scaling (`scale = self.duration_days / 30.0; s = min(int(k * scale), n_rows - duration)`), which makes it immune to these crashes.

---

### 1.3 Scenario Metadata Discrepancies
- **`SingleFaultScenario.get_metadata()`** (lines 149–159): Returns `expected_anomaly_count = 2 if self.fault_type == "spike" else 72`.
  - For `drift` (duration 80), actual count is 80 (metadata claims 72).
  - For `dropout` (duration 24), actual count is 24 (metadata claims 72).
  - For `noise` (duration 36), actual count is 36 (metadata claims 72).
  - For `multivariate` (duration 24), actual count is 24 (metadata claims 72).
- **`HealthDegradationScenario.get_metadata()`** (lines 407–417): Returns `expected_anomaly_count = 490`. Actual count is 488 because the 2-step spike at indices 450–451 overlaps with the 200-step drift at 288–487.

---

### 1.4 Missing Input Validation in Anomaly Injectors
In `backend/simulator/anomaly_injector.py`:
- `inject_dropout(fill_mode=...)`: Only checks `if fill_mode in ["nan", "zero", "sentinel_neg999", "null"]`. If an unrecognized string is passed, no values are altered, but `is_anomaly=True` is still tagged.
- `inject_multivariate_inconsistency(mode=...)`: Only checks `thermodynamic_inversion`, `unphysical_supersaturation`, and `barometric_decoupling`. Unrecognized modes silently leave data unchanged while tagging `is_anomaly=True`.
- `inject_data_corruption(corruption_mode=...)`: Unrecognized modes apply no modification but tag `is_anomaly=True`.

---

### 1.5 Positive Quality Findings & Compliant Components
- **Physical Realism**: `DiurnalGenerator` correctly computes Clausius-Clapeyron saturation vapor pressure $e_s(T)$ via Magnus-Tetens, psychrometric dew points, $S_2(P)$ 12-hour barometric thermal tides (10:00/22:00 peaks), and AR(1) stationary turbulence. $\text{Corr}(T, RH) \le -0.75$ is naturally maintained.
- **Ground-Truth Traceability & Invertibility**: Uncorrupted telemetry is preserved in `clean_temperature`, `clean_pressure`, `clean_humidity`.
- **Weather Front vs Fault Discrimination**: `inject_meteorological_extreme` correctly sets `is_fault = False` and `anomaly_type = "METEOROLOGICAL_EXTREME"` while physical variables shift covariantly ($\Delta T < 0, \Delta P < 0, RH \to 100\%$). Synthetic faults set `is_fault = True`.
- **Strict Temporal Non-Leakage**: `cli.generate_temporal_splits()` strictly partitions `train_clean` (Days 1–20, 100% clean), `val_mixed` (Days 21–25, ~5.0% anomalies), and `test_anomalies` (Days 26–30, ~6.7% anomalies) such that $\max(t_{\text{train}}) < \min(t_{\text{val}}) < \max(t_{\text{val}}) < \min(t_{\text{test}})$.

---

## 2. Logic Chain

1. **Test Failure Impact**: The project definition of done and test protocol mandate that all unit and integration tests must pass cleanly. 4 tests in `tests/test_simulator.py` fail due to a combination of runtime bugs (negative array dimension in `MultiStationNetworkScenario`) and misaligned test assertions/parameters (`test_diurnal_temperature_solar_cycle`, `test_inject_noise_burst_variance_multiplier`, `test_scenario_health_degradation_trajectory`).
2. **Scenario Execution Fragility**: `MultiStationNetworkScenario` crashes whenever `duration_days < 5.0` because `len(raw_df) - 1200` becomes negative. Similarly, `SingleFaultScenario`, `WeatherFrontScenario`, and `HealthDegradationScenario` hardcode absolute index constants without scaling by total duration, leading to `IndexError` when users specify shorter durations.
3. **Overlapping Anomaly Type Conflict**: In `HealthDegradationScenario`, injecting a spike at step 450 within a drift spanning 288–487 overwrites `anomaly_type` from `"DRIFT"` to `"SPIKE"`, causing the test asserting pure DRIFT across the entire slice to fail and introducing an off-by-2 count discrepancy in scenario metadata.
4. **Conclusion Support**: Because code runtime bugs and test failures exist in the milestone deliverables, the milestone cannot be approved in its current state and requires concrete, targeted fixes.

---

## 3. Caveats

- **No Integrity Violations Detected**: No hardcoded test outputs, dummy implementations, or fake predictions were found. The simulator engine implements genuine atmospheric physics and mathematical models.
- **Worker Report Discrepancy**: The worker handoff report claimed all 25 tests pass, but independent execution revealed 4 test failures. This appears to be an oversight from modifying physics parameters (adding seasonal amplitude) or scenario configurations without re-running the full test suite.
- **Review Constraint**: As a reviewer/critic, implementation code was not modified. The required fixes are clearly specified below for the worker agent.

---

## 4. Conclusion

**Verdict**: **`REQUEST_CHANGES`**

### Required Action Items for Worker (`m1_worker_1`):

1. **Fix `MultiStationNetworkScenario` Bounds Calculation** (`backend/simulator/scenarios.py` lines 326–334):
   - Replace absolute index subtractions (`len(raw_df) - 1000`, `len(raw_df) - 1200`) with dynamic duration scaling (e.g. `scale = self.duration_days / 7.0`) and safe durations `duration = min(nominal_dur, len(raw_df) - start_idx)`.
2. **Fix Index Scalability in All Scenarios** (`backend/simulator/scenarios.py`):
   - In `SingleFaultScenario`, `WeatherFrontScenario`, and `HealthDegradationScenario`, scale `start_idx` dynamically based on `self.duration_days` or guard with `min(start_idx, len(clean_df) - duration - 1)`.
3. **Resolve `HealthDegradationScenario` Test & Metadata Inconsistency** (`scenarios.py` & `test_simulator.py`):
   - In `tests/test_simulator.py:295`, update the assertion to account for the spike at 450–451 (e.g. check `df.loc[288:449, "anomaly_type"] == "DRIFT"` and `df.loc[450:451, "anomaly_type"] == "SPIKE"`, or remove the overlapping spike if pure drift was intended). Update metadata `expected_anomaly_count` to match the actual row count (488).
4. **Fix `test_diurnal_temperature_solar_cycle`** (`tests/test_simulator.py:54-58`):
   - In `test_diurnal_temperature_solar_cycle`, specify `temp_seasonal_amp=0.0` in `DiurnalParameters` to test pure diurnal amplitude, or adjust the upper bound to $35.0^\circ\text{C}$ to accommodate the August seasonal insolation term.
5. **Fix `test_inject_noise_burst_variance_multiplier`** (`tests/test_simulator.py:190-197`):
   - Adjust the test to compare variance on a flat/detrended segment, or adjust the variance multiplier check so that the test reliably tests noise burst variance without failing on diurnal baseline slope.
6. **Add Input Validation Guards in `AnomalyInjector`** (`backend/simulator/anomaly_injector.py`):
   - Add `ValueError` exceptions for unsupported `fill_mode` in `inject_dropout`, unsupported `mode` in `inject_multivariate_inconsistency`, and unsupported `corruption_mode` in `inject_data_corruption`.
7. **Fix `SingleFaultScenario.get_metadata()` Counts** (`backend/simulator/scenarios.py:156`):
   - Dynamically report actual expected anomaly counts for each single fault type.

---

## 5. Verification Method

To verify the fixes once implemented:

1. **Run Pytest Suite**:
   ```powershell
   python -m pytest tests/test_simulator.py -v
   ```
   *Expected Result*: All tests pass (0 failures, 0 errors).

2. **Run Full Test Suite**:
   ```powershell
   python -m pytest tests/ -v
   ```
   *Expected Result*: 100% of test cases pass.

3. **Verify Variable Duration Scenario Execution**:
   ```powershell
   python -c "from backend.simulator.scenarios import MultiStationNetworkScenario, SingleFaultScenario, HealthDegradationScenario, WeatherFrontScenario; [MultiStationNetworkScenario(duration_days=d).generate() for d in [1.0, 3.0, 7.0]]; [SingleFaultScenario('dropout', duration_days=d).generate() for d in [1.0, 3.0, 7.0]]"
   ```
   *Expected Result*: Executes without `ValueError` or `IndexError`.

4. **Invalidation Conditions**:
   - Any pytest test in `tests/test_simulator.py` fails.
   - `MultiStationNetworkScenario(duration_days=3.0).generate()` raises `ValueError`.
   - `SingleFaultScenario(fault_type='dropout', duration_days=2.0).generate()` raises `IndexError`.
