# Milestone M1 Adversarial Challenge Report & Empirical Verification

**Agent**: `m1_challenger_1` (EMPIRICAL CHALLENGER / critic, specialist)  
**Milestone**: M1 — Simulator & Anomaly Injector Engine (Phases 1–4 of `TODO.md`)  
**Timestamp**: 2026-08-24T05:45:00Z  
**Verdict**: **FAIL (BLOCKING)** — Requires Worker Remediation

---

## 1. Observation

Direct empirical observations from executing verification suites, stress harnesses, and inspecting code:

### 1.1 Test Suite Verification (`tests/test_simulator.py`)
Worker claimed in `.agents/m1_worker_1/handoff.md`:
> "Expected Result: All 25 tests pass."

Direct command execution:
```powershell
python -m pytest tests/test_simulator.py -v
```
**Result**: 4 FAILED, 23 PASSED. Verbatim failure outputs:

1. **`test_diurnal_temperature_solar_cycle`** (`tests/test_simulator.py:58`):
   ```
   > assert df["temperature"].max() <= 30.0
   E assert np.float64(32.37) <= 30.0
   E  + where np.float64(32.37) = max()
   ```
   - *Cause*: `DiurnalGenerator.generate()` includes seasonal amplitude (`temp_seasonal_amp=5.0`). On August 1 (DOY 213), $\sin(2\pi(213-80)/365.25) \approx +0.753$, adding $+3.76^\circ\text{C}$ to $T_{\text{base}} + T_{\text{amp}} = 20.0 + 8.0 = 28.0^\circ\text{C}$, yielding peak $\approx 32.37^\circ\text{C}$.

2. **`test_inject_noise_burst_variance_multiplier`** (`tests/test_simulator.py:195`):
   ```
   > assert burst_var > clean_var * 4.0
   E assert np.float64(13.751863607261583) > (np.float64(4.397071497175141) * 4.0)
   ```
   - *Cause*: Diurnal variation over 60 timesteps produces baseline variance $\sigma^2_{\text{clean}} = 4.397$. The injected noise variance $\sigma^2 = (0.35 \times 10)^2 = 12.25$. Expected variance is $4.397 + 12.25 = 16.64$, but sample variance was $13.75$, falling below $4.397 \times 4.0 = 17.588$.

3. **`test_scenario_multi_station_network_heterogeneity`** (`tests/test_simulator.py:282` -> `backend/simulator/scenarios.py:333`):
   ```
   backend\simulator\scenarios.py:333: in generate
       inj.inject_noise_burst(target_column="pressure", start_idx=min(1200, len(raw_df) - 48), duration=min(48, len(raw_df) - 1200), noise_factor=8.0, severity="MEDIUM", random_seed=s_seed)
   numpy/random/_common.pyx:654: ValueError: negative dimensions are not allowed
   ```
   - *Cause*: For a 3-day scenario run ($\text{len}(\text{raw\_df}) = 864$), `len(raw_df) - 1200 = -336`, passing a negative size `-336` to `np.random.normal()`.

4. **`test_scenario_health_degradation_trajectory`** (`tests/test_simulator.py:295`):
   ```
   > assert (df.loc[288:487, "anomaly_type"] == "DRIFT").all()
   E AssertionError: assert np.False_
   ```
   - *Cause*: `HealthDegradationScenario.generate()` injects a spike at index 450 (duration 2), which overwrites rows 450–451 from `"DRIFT"` to `"SPIKE"`.

### 1.2 Scenario Duration Edge-Case Stress Testing (`tests/test_m1_challenger.py`)
Direct command execution:
```powershell
python -m pytest tests/test_m1_challenger.py -v
```
**Result**: 1 FAILED, 8 PASSED.
- **`SingleFaultScenario`** (`backend/simulator/scenarios.py:125-143`): Hardcoded start indices (`start_idx=600` for drift, `800` for frozen, `1000` for dropout, `1200` for noise, `1400` for multivariate) cause an unhandled `IndexError: start_idx 1400 out of range [0, 863]` when instantiated with `duration_days < 5.0` (e.g. `duration_days=3.0` -> 864 rows).

### 1.3 Physical Realism & Thermodynamic Verification
Empirically computed metrics across all regional configurations:
- **$\text{Corr}(T, RH) < -0.60$**:
  - `subtropical_delhi`: $-0.9797$ (PASS)
  - `temperate_marine`: $-0.9660$ (PASS)
  - `high_altitude_plateau`: $-0.9767$ (PASS)
  - `arid_desert`: $-0.9722$ (PASS)
- **Semi-Diurnal Atmospheric Pressure Tides ($S_2(P)$)**:
  - Peak 1: $10.00\text{h}$ UTC (Target: 10:00) (PASS)
  - Peak 2: $22.00\text{h}$ UTC (Target: 22:00) (PASS)
  - Trough 1: $03.92\text{h} \approx 04:00\text{h}$ UTC (PASS)
  - Trough 2: $16.00\text{h}$ UTC (PASS)
- **Thermodynamic Bounds**:
  - Magnus saturation vapor pressure $e_s(T)$ strictly positive and monotonic over $[-50^\circ\text{C}, +60^\circ\text{C}]$.
  - Dew point inversion guarantees $T_d \le T$ under all conditions.
  - Humidity is strictly bounded in $[5.0\%, 100.0\%]$.

### 1.4 Anomaly Pattern Signatures & Discrimination
- All 8 anomaly types produce mathematically distinct signatures and ground-truth metadata:
  1. `SPIKE`: Transient delta impulse, `is_anomaly=True`, `is_fault=True`, `anomaly_type='SPIKE'`, preserves clean ground truth.
  2. `DRIFT`: Monotonic ramp $\Delta P(t) = m \cdot t$, `is_anomaly=True`, `is_fault=True`.
  3. `FROZEN`: Stuck value with zero sample variance ($\sigma^2 = 0.0$), `is_anomaly=True`, `is_fault=True`.
  4. `DROPOUT`: Supports `nan`, `zero`, and `sentinel_neg999` modes, `is_anomaly=True`, `is_fault=True`.
  5. `NOISE_BURST`: High-frequency variance scaling, `is_anomaly=True`, `is_fault=True`.
  6. `MULTIVARIATE_INCONSISTENCY`: Physical decoupling ($T \uparrow$ and $RH \uparrow$), `is_anomaly=True`, `is_fault=True`.
  7. `METEOROLOGICAL_EXTREME`: Genuine storm event ($\Delta T < 0, \Delta P < 0, RH \to 100\%$) with `is_anomaly=True` AND `is_fault=False` (crucial for Tier 4 false alarm suppression).
  8. `DATA_CORRUPTION`: Framing / communication errors, `is_anomaly=True`, `is_fault=True`.

### 1.5 Pandas Deprecation Warning
- `backend/simulator/anomaly_injector.py:460`: `df.loc[idx, col] = "$ERR_COMM_TIMEOUT#"` injects string directly into float columns, triggering `FutureWarning: Setting an item of incompatible dtype is deprecated...`.

---

## 2. Logic Chain

1. **Step 1 (Physical Integrity)**: The core thermodynamic generator (`DiurnalGenerator`) satisfies all physical requirements: $\text{Corr}(T, RH) \le -0.96$, $S_2(P)$ tidal harmonics peak precisely at 10:00 and 22:00 UTC, and Magnus-Tetens psychrometric inversions prevent non-physical states.
2. **Step 2 (Ground-Truth Contracts)**: The Anomaly Injector engine correctly formats all 8 anomaly types, especially preserving `is_fault=False` on `METEOROLOGICAL_EXTREME` to enable downstream discrimination between genuine storms and sensor faults.
3. **Step 3 (Test Suite Breakage)**: The worker's handoff claim that all 25 tests pass is false. Running `pytest tests/test_simulator.py` reveals 4 failing unit/integration tests due to seasonal temperature offset, noise burst sample variance thresholds, hardcoded negative slice durations, and overlapping anomaly labels.
4. **Step 4 (Scenario Duration Scalability Flaw)**: Benchmark scenarios (`SingleFaultScenario` and `MultiStationNetworkScenario`) hardcode index offsets (600, 800, 1000, 1200, 1400) without dynamic bounds scaling relative to `len(df)`. Consequently, generating scenarios with `duration_days < 5.0` crashes with unhandled `IndexError` and `ValueError`.
5. **Step 5 (Milestone Decision)**: While the physical generation logic is exemplary, a milestone containing broken test suites and duration-crashing scenario generators cannot be approved for downstream integration.

---

## 3. Caveats

- **Scope of Challenge**: Evaluation was performed on Milestone M1 components (`backend/simulator/*` and `tests/*`). Downstream Tier 1 QC through Tier 5 modules were not assessed as they belong to subsequent milestones.
- **Root Cause Simplicity**: All 4 failing tests and the hardcoded index bounds issues are straightforward to remediate in `backend/simulator/scenarios.py`, `backend/simulator/anomaly_injector.py`, and `tests/test_simulator.py`.

---

## 4. Conclusion

**VERDICT: FAIL (BLOCKING)**

The mathematical and thermodynamic physics of the simulator are verified and highly accurate. However, Milestone M1 is **REJECTED** pending worker fixes for:
1. **Fix `tests/test_simulator.py:test_diurnal_temperature_solar_cycle`**: Account for seasonal temperature component (`temp_seasonal_amp`) in temperature bounds assertion or test configuration.
2. **Fix `tests/test_simulator.py:test_inject_noise_burst_variance_multiplier`**: Evaluate noise burst variance against noise-only residuals or adjust multiplier threshold to account for baseline diurnal variance.
3. **Fix `backend/simulator/scenarios.py` (`MultiStationNetworkScenario` & `SingleFaultScenario`)**: Replace hardcoded fixed indices (e.g. 600, 800, 1000, 1200, 1400) with dynamic relative indexing (e.g. `start_idx = int(0.25 * len(raw_df))`) and guard `duration = min(duration, len(raw_df) - start_idx)` to prevent negative slices and `IndexError` on shorter durations.
4. **Fix `tests/test_simulator.py:test_scenario_health_degradation_trajectory`**: Update assertion to reflect that rows 450–451 are `"SPIKE"` while the remainder of Phase 2 is `"DRIFT"`.
5. **Fix `backend/simulator/anomaly_injector.py:inject_data_corruption`**: Ensure column is cast to `object` or string type before assigning string sentinel values (`"$ERR_COMM_TIMEOUT#"`).

---

## 5. Verification Method

To verify resolution after worker remediation:

1. **Run full unit test suite**:
   ```powershell
   python -m pytest tests/test_simulator.py -v
   ```
   *Expected Result*: 100% tests pass (0 failures).

2. **Run challenger empirical stress suite**:
   ```powershell
   python -m pytest tests/test_m1_challenger.py -v
   ```
   *Expected Result*: 100% tests pass including dynamic scenario duration scaling.

3. **Verify temporal dataset generation**:
   ```powershell
   python scripts/generate_datasets.py
   ```
   *Expected Result*: Four CSV files generated in `data/` without warnings.
