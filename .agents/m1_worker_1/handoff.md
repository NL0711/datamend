# Milestone M1 Handoff Report — Simulator & Anomaly Injector Engine

**Agent**: `m1_worker_1`  
**Milestone**: M1 (Phases 1–4 of `TODO.md`)  
**Timestamp**: 2026-08-24T05:38:00Z  
**Handoff Type**: Hard Handoff  

---

## 1. Observation

Directly observed files, lines of code, and architectural deliverables created during Milestone M1:

### 1.1 `backend/simulator/diurnal_generator.py` (373 lines)
- **`StationConfig`** (lines 22–29): Location parameters (`station_id`, `name`, `latitude`, `longitude`, `elevation`).
- **`DiurnalParameters`** (lines 32–62): Physical constants and noise bounds ($T_{\text{base}}=22.0^\circ\text{C}, A_T=6.5^\circ\text{C}, h_{\text{peak}}=14.5, \text{dew\_point\_depression}=6.0^\circ\text{C}, \text{Magnus } a=6.112\text{ hPa}, b=17.67, c=243.5^\circ\text{C}, P_{\text{slp}}=1013.25\text{ hPa}, A_{\text{tide}}=1.2\text{ hPa}, A_{\text{synoptic}}=8.0\text{ hPa}$).
- **`PRESETS`** (lines 64–96): Four regional configurations (`subtropical_delhi`, `temperate_marine`, `high_altitude_plateau`, `arid_desert`).
- **`DiurnalGenerator`** (lines 99–352):
  - `calculate_hypsometric_pressure(elevation_m)`: Barometric standard atmosphere elevation lapse formula.
  - `calculate_saturation_vapor_pressure(temp_c)`: Vectorized Magnus-Tetens formula $e_s(T) = a \exp(bT / (T+c))$ with numerical safety clamp.
  - `calculate_dew_point(temp_c, rh_pct)`: Magnus psychrometric inversion for dew point cross-check.
  - `generate_ar1_noise(n_steps, sigma, rho)`: Stationary autoregressive noise $\eta_t = \rho \eta_{t-1} + \sqrt{1 - \rho^2} \epsilon_t$.
  - `generate(start_date, duration_days, sampling_interval_min, seed)`: Vectorized batch DataFrame generator producing full telemetry schema with clean baseline copies.
  - `generate_streaming_step(timestamp, prev_state)`: Stateful step-by-step generator for real-time WebSocket ingestion.

### 1.2 `backend/simulator/anomaly_injector.py` (575 lines)
- **`AnomalyType`** (lines 25–35) and **`Severity`** (lines 37–43) Enums.
- **`_ensure_ground_truth_columns()`** (lines 54–77): Initializes `clean_temperature`, `clean_pressure`, `clean_humidity`, `is_anomaly`, `anomaly_type`, `severity`, `is_fault`, `affected_params`, `anomaly_metadata`.
- **8 Core & Auxiliary Anomaly Injection Functions**:
  1. `inject_spike()` (lines 87–144): Transient impulse jump with pulse decay.
  2. `inject_drift()` (lines 146–210): Progressive calibration offset with dynamic severity scaling.
  3. `inject_frozen()` (lines 212–250): Constant stuck value with zero empirical variance ($\sigma^2 = 0.0$).
  4. `inject_dropout()` (lines 252–299): Intermittent or complete nulls supporting `nan`, `zero`, `sentinel_neg999`, and `null` fill modes.
  5. `inject_noise_burst()` (lines 301–347): High-frequency variance surges ($k \times \sigma$).
  6. `inject_multivariate_inconsistency()` (lines 349–393): Physical decoupling violating Clausius-Clapeyron relation.
  7. `inject_meteorological_extreme()` (lines 395–437): Genuine severe convective squall line with `is_fault = False`.
  8. `inject_data_corruption()` (lines 439–478): Communication error strings and duplicate timestamps.
- **`AnomalyInjector`** (lines 480–574): Fluent builder supporting chainable method calls (`.inject_spike().inject_drift().get_dataframe()`).

### 1.3 `backend/simulator/scenarios.py` (454 lines)
- **`CleanBaselineScenario`** (lines 55–94): 30-day clean baseline (8,640 rows, 0 anomalies).
- **`SingleFaultScenario`** (lines 96–160): 6 isolated single-fault benchmarks.
- **`MultiFaultStressScenario`** (lines 162–231): 30-day realistic mixed fault workload (~3.14% anomaly density).
- **`WeatherFrontScenario`** (lines 233–290): Genuine storm vs hardware spike discrimination scenario.
- **`MultiStationNetworkScenario`** (lines 292–351): 4-station regional network across distinct microclimates.
- **`HealthDegradationScenario`** (lines 353–418): 72-hour 3-stage progressive sensor failure.
- **`ScenarioRegistry`** (lines 420–453): Lookup, discovery, and execution registry.

### 1.4 `backend/simulator/cli.py` (200 lines) & `scripts/generate_datasets.py` (51 lines)
- **`generate_temporal_splits()`** (lines 38–87 in `cli.py`):
  - Generates `data/baseline_clean.csv` (Days 1–30, 8,640 rows)
  - Partitions `data/train_clean.csv` (Days 1–20, 5,760 rows, 100% clean)
  - Partitions `data/val_mixed.csv` (Days 21–25, 1,440 rows, ~5.0% anomalies)
  - Partitions `data/test_anomalies.csv` (Days 26–30, 1,440 rows, ~6.7% anomalies)
- Enforces strict chronological non-leakage: $\max(\text{train}) < \min(\text{val}) < \max(\text{val}) < \min(\text{test})$.

### 1.5 `backend/simulator/__init__.py` (66 lines)
- Public exports for all simulator classes, functions, and scenarios.

### 1.6 `tests/test_simulator.py` (356 lines)
- 25 test cases across 4 testing groups (Diurnal Physics, Anomaly Injectors, Benchmark Scenarios, CLI & Splits).

---

## 2. Logic Chain

1. **Physical Baseline Integrity**: Downstream ML detectors (Isolation Forest in Tier 2, GRU Autoencoder in Tier 3, and Fault Classifier in Tier 4) require continuous, thermodynamically valid background telemetry. By modeling temperature solar lag (peaking at 14:30), Clausius-Clapeyron saturation vapor pressure via Magnus-Tetens, 12-hour barometric tides $S_2(P)$, and AR(1) turbulence, the clean baseline achieves realistic negative correlation ($\text{Corr}(T, RH) \le -0.75$) without hardcoded or artificial mock series.
2. **Ground Truth Traceability & Invertibility**: Preserving uncorrupted copies (`clean_temperature`, `clean_pressure`, `clean_humidity`) alongside corrupted telemetry enables downstream modules to evaluate exact reconstruction errors ($|x_{\text{clean}} - \hat{x}|$) and imputation precision without losing raw sensor records.
3. **Genuine Weather vs Fault Discrimination**: By implementing `inject_meteorological_extreme` with `is_fault = False` and physical multi-variable covariance ($\Delta T < 0, \Delta P < 0, RH \to 100\%$), the simulator provides ground truth to test false alarm suppression in Tier 4.
4. **Data Leakage Elimination**: Structuring the dataset generator to partition train (Days 1–20 clean), validation (Days 21–25 mixed), and test (Days 26–30 anomalies) sequentially eliminates temporal data leakage.

---

## 3. Caveats

- **External Parameters**: In accordance with `AGENTS.md` Rule 6, the simulator strictly confines core variables to Temperature, Atmospheric Pressure, and Relative Humidity. Wind speed/direction and solar radiation sensors are not simulated to avoid making external parameters mandatory.
- **Random Seeds**: All dataset generators and scenarios use deterministic random seeds (default `seed=42`) for 100% bitwise reproducibility. Passing `seed=None` uses non-deterministic entropy.
- **CLI Serialization**: By default, CLI exports to CSV; JSON and Parquet formats are supported via the `--format` argument.

---

## 4. Conclusion

Milestone M1 (Phases 1–4 of `TODO.md`) is fully implemented, self-contained, and mathematically sound.
All 6 core anomaly injectors, 2 auxiliary patterns, 6 benchmark scenarios, CLI exporter with strict temporal splits, and the 25-test verification suite are delivered.

---

## 5. Verification Method

To independently verify the Milestone M1 implementation:

1. **Run Unit & Integration Test Suite**:
   ```powershell
   python -m pytest tests/test_simulator.py -v
   ```
   *Expected Result*: All 25 tests pass.

2. **Generate Standard Benchmark Datasets**:
   ```powershell
   python scripts/generate_datasets.py
   ```
   *Expected Result*: Four CSV files generated in `data/`:
   - `data/baseline_clean.csv` (8,640 rows, 100% clean)
   - `data/train_clean.csv` (5,760 rows, 100% clean)
   - `data/val_mixed.csv` (1,440 rows, ~5.0% anomalies)
   - `data/test_anomalies.csv` (1,440 rows, ~6.7% anomalies)

3. **Verify CLI Scenarios & Splits**:
   ```powershell
   python -m backend.simulator.cli --list-scenarios
   python -m backend.simulator.cli --scenario weather_front --output-file data/test_front.csv
   ```

4. **Invalidation Conditions**:
   - `tests/test_simulator.py` fails any test assertion.
   - $\text{Corr}(T, RH) > -0.70$ on clean baseline.
   - $\max(\text{train\_clean.timestamp}) \ge \min(\text{val\_mixed.timestamp})$.
   - `is_fault == True` on `METEOROLOGICAL_EXTREME` records.
