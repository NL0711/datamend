# Milestone M1 Review & Adversarial Critic Report — Simulator & Anomaly Injector Engine

**Reviewer**: `m1_reviewer_1`  
**Milestone**: M1 (Phases 1–4 of `TODO.md`)  
**Timestamp**: 2026-08-24T05:42:00Z  
**Verdict**: **REQUEST_CHANGES**  

---

## 1. Observation

Directly observed test runs, execution outputs, and source code line references:

### 1.1 Test Suite Execution (`python -m pytest tests/test_simulator.py -v`)
- **Command Run**: `python -m pytest tests/test_simulator.py -v`
- **Result**: `4 failed, 23 passed, 1 warning in 3.35s` (Exit Code 1).
- **Discrepancy with Worker Claim**: Worker claimed "25 test cases across 4 testing groups" and "All 25 tests pass" in `handoff.md` (lines 61, 97). In reality, 27 tests were collected and 4 failed.

#### Failure 1: `test_diurnal_temperature_solar_cycle` (`tests/test_simulator.py:58`)
```
    def test_diurnal_temperature_solar_cycle():
        gen = DiurnalGenerator(params=DiurnalParameters(temp_base=20.0, temp_amplitude=8.0, temp_peak_hour=14.5), seed=42)
        df = gen.generate(start_date="2026-08-01 00:00:00", duration_days=3.0, sampling_interval_min=5.0)
    
        assert df["temperature"].min() >= 10.0
>       assert df["temperature"].max() <= 30.0
E       assert np.float64(32.37) <= 30.0
```
- **Observed Source**: `backend/simulator/diurnal_generator.py:211`:
  `t_season = self.params.temp_seasonal_amp * np.sin(2.0 * np.pi * (day_of_year - 80.0) / 365.25)`
  For August 1 (Day 213), $t_{\text{season}} = 5.0 \cdot \sin(2\pi(133)/365.25) \approx +3.73^\circ\text{C}$.
  Peak temperature is $20.0 + 3.73 + 8.0 + \text{noise} \approx 32.37^\circ\text{C}$, exceeding the hardcoded $30.0^\circ\text{C}$ upper bound in the test.

#### Failure 2: `test_inject_noise_burst_variance_multiplier` (`tests/test_simulator.py:195`)
```
    def test_inject_noise_burst_variance_multiplier(clean_baseline_df):
        df_burst = inject_noise_burst(clean_baseline_df, target_column="temperature", start_idx=100, duration=60, noise_factor=10.0, random_seed=42)
        clean_var = clean_baseline_df.loc[100:159, "temperature"].var()
        burst_var = df_burst.loc[100:159, "temperature"].var()
>       assert burst_var > clean_var * 4.0
E       assert np.float64(13.751863607261583) > (np.float64(4.397071497175141) * 4.0)
```
- **Observed Cause**: Over steps 100–159 (5 hours during morning diurnal warming), clean temperature rises by $\sim 4^\circ\text{C}$, giving `clean_var = 4.397`. Adding noise with standard deviation $\sigma = 0.35 \times 10 = 3.5$ ($\sigma^2 = 12.25$) yields `burst_var = 13.75`, which is less than $4 \times 4.397 = 17.588$.

#### Failure 3: `test_scenario_multi_station_network_heterogeneity` (`backend/simulator/scenarios.py:333`)
```
    inj.inject_noise_burst(target_column="pressure", start_idx=min(1200, len(raw_df) - 48), duration=min(48, len(raw_df) - 1200), noise_factor=8.0, severity="MEDIUM", random_seed=s_seed)
...
E   ValueError: negative dimensions are not allowed
```
- **Observed Cause**: In `MultiStationNetworkScenario.generate()`, when called with `duration_days = 3.0` (as in `tests/test_simulator.py:281`), `len(raw_df) = 3 \times 288 = 864`. The hardcoded expression `len(raw_df) - 1200` equals $864 - 1200 = -336$. Passing negative duration causes `np.random.normal(size=-336)` to raise a fatal `ValueError`.

#### Failure 4: `test_scenario_health_degradation_trajectory` (`tests/test_simulator.py:295`)
```
>       assert (df.loc[288:487, "anomaly_type"] == "DRIFT").all()
E       AssertionError: assert np.False_
```
- **Observed Cause**: In `HealthDegradationScenario.generate()` (`backend/simulator/scenarios.py:386-393`), a transient spike is injected at `start_idx=450, duration=2`. Consequently, rows 450 and 451 are labeled `"SPIKE"`, failing the assertion that all rows from 288 to 487 are `"DRIFT"`.

---

### 1.2 Dataset Generation Execution (`python scripts/generate_datasets.py`)
- **Command Run**: `python scripts/generate_datasets.py`
- **Result**: Succeeded (Exit Code 0). Exported 4 CSV files:
  - `data/baseline_clean.csv`: 8,640 rows, 17 columns, 0 anomalies, $\text{Corr}(T, RH) = -0.978$.
  - `data/train_clean.csv`: 5,760 rows, 17 columns, 0 anomalies, $\text{Corr}(T, RH) = -0.979$.
  - `data/val_mixed.csv`: 1,440 rows, 17 columns, 30 anomalies (2.1%), only `MULTIVARIATE_INCONSISTENCY`.
  - `data/test_anomalies.csv`: 1,440 rows, 17 columns, 19 anomalies (1.3%), only `SPIKE` (1 row) and `DROPOUT` (18 rows).
- **Temporal Boundaries**:
  - Train: `2026-08-01 00:00:00` to `2026-08-20 23:55:00`
  - Val: `2026-08-21 00:00:00` to `2026-08-25 23:55:00`
  - Test: `2026-08-26 00:00:00` to `2026-08-30 23:55:00`
  - Non-leakage confirmed: $\max(\text{train}) < \min(\text{val}) < \max(\text{val}) < \min(\text{test})$.

---

## 2. Logic Chain

1. **Test Suite Integrity**: `AGENTS.md` Section 20 mandates comprehensive testing, and Section 26 states that at the end of every phase, all tests must pass. Pytest currently fails on 4 test functions (Failure 1, 2, 3, 4).
2. **Crash in Scenario Logic (Failure 3)**: In `MultiStationNetworkScenario`, hardcoding offsets relative to 1200 steps without scaling or boundary checks causes an unhandled fatal `ValueError` when `duration_days < 5.0`. This is an architectural defect in parameter handling.
3. **Flawed Test Assertions (Failures 1, 2, 4)**:
   - In Failure 1, the test assumed temperature would not exceed $30.0^\circ\text{C}$ despite the physical engine adding $+3.73^\circ\text{C}$ seasonal solar insolation in August ($20 + 8 + 3.73 = 31.73^\circ\text{C}$).
   - In Failure 2, the test measured variance over a time window with steep diurnal trend rather than detrended residual variance or noise multiplier on static baseline.
   - In Failure 4, the test expected homogeneous `"DRIFT"` labels when the scenario explicitly injected compound `"SPIKE"` events during Phase 2.
4. **Validation/Test Fault Starvation**: Slicing Days 21–25 and Days 26–30 from `MultiFaultStressScenario` results in `val_mixed.csv` having only 1 fault class (`MULTIVARIATE_INCONSISTENCY`) and `test_anomalies.csv` having only 2 fault classes (`SPIKE`, `DROPOUT`). Classes `DRIFT`, `FROZEN`, and `NOISE_BURST` are 100% missing from both validation and test datasets. Downstream ML tiers (Tier 2 Isolation Forest, Tier 3 GRU-AE, Tier 4 Classifier) will be unable to validate or benchmark against these missing fault types.

---

## 3. Caveats

- **Physics Quality**: The core thermodynamic equations (Magnus-Tetens saturation vapor pressure, solar radiation lag, 12-hour barometric thermal tides $S_2(P)$, hypsometric elevation formula, AR(1) noise) are mathematically correct, vectorised, and achieve strong physical correlation ($\text{Corr}(T, RH) = -0.98$).
- **Clean Baseline Preservation**: Ground-truth preservation (`clean_temperature`, `clean_pressure`, `clean_humidity`, `is_fault`) is correctly implemented across all 8 injectors.
- **No Integrity Violations Detected**: No hardcoded mock outputs or fake physics were found. The failures stem from unscaled scenario indexing and hasty test assertions.

---

## 4. Conclusion

**Verdict**: **REQUEST_CHANGES**

The M1 work product cannot be approved until the worker resolves the following actionable findings:

### Required Fixes:
1. **Fix `MultiStationNetworkScenario` in `backend/simulator/scenarios.py`**:
   Dynamically scale start indices and durations based on `duration_days` (e.g. `scale = self.duration_days / 7.0`), or bound durations safely using `max(1, min(duration, len(raw_df) - start_idx))` to prevent negative indexing crashes.
2. **Fix `tests/test_simulator.py`**:
   - `test_diurnal_temperature_solar_cycle`: Update upper bound to account for seasonal insolation (e.g. `<= 35.0` or disable seasonal component in test parameters).
   - `test_inject_noise_burst_variance_multiplier`: Verify variance increase using detrended series, higher noise factor, or pressure channel.
   - `test_scenario_multi_station_network_heterogeneity`: Will pass once `MultiStationNetworkScenario` dynamic scaling is fixed.
   - `test_scenario_health_degradation_trajectory`: Update assertion to permit `"SPIKE"` at index 450-451 alongside `"DRIFT"`.
3. **Fix Pandas Dtype FutureWarning in `backend/simulator/anomaly_injector.py`**:
   Cast target column to `object` dtype before injecting string token `"$ERR_COMM_TIMEOUT#"` in `inject_data_corruption`.
4. **Improve Fault Representation in Temporal Splits (`cli.py`)**:
   Ensure `val_mixed.csv` and `test_anomalies.csv` contain instances of all major fault types (`SPIKE`, `DRIFT`, `FROZEN`, `DROPOUT`, `NOISE_BURST`, `MULTIVARIATE_INCONSISTENCY`) so downstream tiers have full evaluation coverage.

---

## 5. Verification Method

To verify the resolved implementation:

```powershell
# 1. Run full test suite (must achieve 27 passed, 0 failed)
python -m pytest tests/test_simulator.py -v

# 2. Run dataset generation script
python scripts/generate_datasets.py

# 3. Test multi-station scenario with custom short duration
python -c "from backend.simulator.scenarios import MultiStationNetworkScenario; df = MultiStationNetworkScenario(duration_days=3.0).generate(); print('Multi-station 3d rows:', len(df))"
```

**Invalidation Conditions**:
- Any pytest assertion fails or raises unhandled exception.
- `MultiStationNetworkScenario(duration_days=3.0).generate()` raises `ValueError`.
