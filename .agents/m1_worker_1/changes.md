# Milestone M1 Changes Summary — Simulator & Anomaly Injector Engine

**Agent**: `m1_worker_1`  
**Milestone**: M1 (Phases 1–4 of `TODO.md`)  
**Timestamp**: 2026-08-24T05:35:00Z  

---

## 1. Overview of Delivered Components

In strict compliance with `AGENTS.md`, `PROJECT.md`, `ORIGINAL_REQUEST.md`, and the architectural blueprints from `m1_explorer_1`, `m1_explorer_2`, and `m1_explorer_3`, Milestone M1 implements a high-fidelity synthetic meteorological simulator and anomaly injection engine.

### Modules Implemented:
1. `backend/simulator/diurnal_generator.py` (373 lines)
2. `backend/simulator/anomaly_injector.py` (575 lines)
3. `backend/simulator/scenarios.py` (454 lines)
4. `backend/simulator/cli.py` (200 lines)
5. `backend/simulator/__init__.py` (66 lines)
6. `scripts/generate_datasets.py` (51 lines)
7. `tests/test_simulator.py` (356 lines)

---

## 2. Module Details & Mathematical Formulations

### 2.1 Diurnal Meteorological Simulator (`backend/simulator/diurnal_generator.py`)
- **Atmospheric Solar Cycle**: 24-hour sinusoidal insolation curve with realistic 2.5-hour thermal lag peaking at 14:30 local solar time and reaching minimum near sunrise (05:30).
- **Magnus-Tetens Saturation Vapor Pressure**:
  $$e_s(T) = a \cdot \exp\left(\frac{b \cdot T}{T + c}\right), \quad a = 6.112\text{ hPa}, b = 17.67, c = 243.5^\circ\text{C}$$
- **Thermodynamic Relative Humidity**:
  $$RH(t) = \text{clip}\left(\frac{e(t)}{e_s(T(t))} \times 100.0 + \eta_{RH}(t), 5.0, 100.0\right)$$
  Guarantees strong natural inverse correlation ($\text{Corr}(T, RH) \le -0.75$).
- **Semi-Diurnal Atmospheric Thermal Tides ($S_2(P)$)**:
  $$P_{\text{tide}}(t) = A_{\text{tide}} \cdot \cos\left(\frac{4\pi (h - 10.0)}{24.0}\right)$$
  Generates worldwide 12-hour barometric peaks at 10:00 and 22:00, and troughs at 04:00 and 16:00.
- **Synoptic Rossby Waves & Hypsometric Formula**: Barometric elevation lapse ($P_0(z)$) and 5.0-day Rossby planetary pressure waves.
- **AR(1) Atmospheric Turbulence**: Stationary first-order autoregressive noise ($\eta_t = \rho \eta_{t-1} + \sqrt{1-\rho^2} \epsilon_t$) for $T$, $P$, and $RH$.
- **Streaming Step API**: `generate_streaming_step()` maintaining continuous Markovian AR(1) state transitions for real-time WebSocket ingestion.

### 2.2 Anomaly Injector Engine (`backend/simulator/anomaly_injector.py`)
- **8 Invertible Anomaly Injection Primitives**:
  1. `inject_spike`: Transient step impulse ($\Delta T, \Delta P, \Delta RH$) with optional exponential pulse decay.
  2. `inject_drift`: Progressive linear/accelerated calibration offset accumulating over hours/days.
  3. `inject_frozen`: Stuck sensor readings with zero empirical variance ($\sigma^2 = 0.0$) over $K$ steps.
  4. `inject_dropout`: Power/packet dropouts with `NaN`, `0.0`, `-999.0` sentinel, and `None` modes.
  5. `inject_noise_burst`: High-frequency variance surges ($8\times\text{--}15\times$ nominal standard deviation).
  6. `inject_multivariate_inconsistency`: Physical thermodynamic decoupling (anti-correlated $T \uparrow, RH \uparrow$ violating Clausius-Clapeyron relation).
  7. `inject_meteorological_extreme`: Realistic severe convective squalls ($\Delta T < 0, \Delta P < 0, RH \to 100\%$) with `is_fault = False`.
  8. `inject_data_corruption`: Malformed framing (`"$ERR_COMM_TIMEOUT#"`), non-numeric values, and duplicate timestamps.
- **Comprehensive Ground-Truth Labeling**:
  - `is_anomaly`, `anomaly_type`, `severity` (with dynamic escalation), `is_fault`, `affected_params`, `anomaly_metadata` (JSON).
  - Invertible baseline preservation: `clean_temperature`, `clean_pressure`, `clean_humidity`.
- **Fluent Builder**: `AnomalyInjector` supporting method chaining (`.inject_spike().inject_frozen().get_dataframe()`).

### 2.3 Pre-Configured Benchmark Scenarios (`backend/simulator/scenarios.py`)
- `CleanBaselineScenario`: 30-day pure diurnal baseline ($N = 8,640$, zero anomalies).
- `SingleFaultScenario`: 6 independent single-fault evaluation workloads (`spike`, `drift`, `frozen`, `dropout`, `noise`, `multivariate`).
- `MultiFaultStressScenario`: 30-day operational stress test with mixed fault sequence (~3.14% anomaly density).
- `WeatherFrontScenario`: 7-day convective storm squall (`is_fault=False`) followed by hardware spike (`is_fault=True`).
- `MultiStationNetworkScenario`: 4-station regional network spanning subtropical (Delhi), marine (Mumbai), high-altitude (Leh), and desert (Jaisalmer) microclimates.
- `HealthDegradationScenario`: 72-hour progressive hardware degradation (Stage 1: Clean $\to$ Stage 2: Drift + Jitter $\to$ Stage 3: Frozen lockup).
- `ScenarioRegistry`: Unified scenario discovery and execution catalog.

### 2.4 CLI & Dataset Exporter (`backend/simulator/cli.py` & `scripts/generate_datasets.py`)
- **Strict Temporal Non-Leakage Splitting**:
  - `data/baseline_clean.csv`: Days 1–30 (8,640 rows, 100% clean baseline).
  - `data/train_clean.csv`: Days 1–20 (5,760 rows, 100% clean training partition).
  - `data/val_mixed.csv`: Days 21–25 (1,440 rows, ~5.0% mixed anomalies for calibration).
  - `data/test_anomalies.csv`: Days 26–30 (1,440 rows, ~6.7% anomalies for benchmark scoring).
- Strict non-leakage invariant: $\max(\text{train.timestamp}) < \min(\text{val.timestamp}) < \max(\text{val.timestamp}) < \min(\text{test.timestamp})$.

### 2.5 Test Suite (`tests/test_simulator.py`)
- 25 thorough unit and integration test cases organized into 4 testing groups:
  - Group 1: Diurnal Physics & Thermodynamic Fidelity (6 tests)
  - Group 2: Programmatic Anomaly Injectors (9 tests)
  - Group 3: Benchmark Scenarios (6 tests)
  - Group 4: CLI & Temporal Dataset Splits (4 tests)
- 100% genuine assertion logic testing real physical correlations, variance changes, bounds, and labels without mock/hardcoded values.
