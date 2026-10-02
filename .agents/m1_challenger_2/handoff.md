# Milestone M1 Adversarial Evaluation & Stress Test Report

**Agent**: `m1_challenger_2`  
**Role**: Adversarial Challenger (Critic & Specialist)  
**Milestone**: M1 (Phases 1–4 of `TODO.md` — Simulator & Anomaly Injector Engine)  
**Timestamp**: 2026-08-24T05:48:00Z  
**Verdict**: **FAIL / BLOCKING FIXES REQUIRED**  

---

## 1. Observation

Direct empirical observations from executing verification test suites, CLI tools, dataset scripts, and statistical parity tests on Windows 11 / Python 3.14:

### 1.1 Test Suite Execution (`python -m pytest tests/test_simulator.py -v`)
Executing the test suite resulted in **4 test failures out of 28 test cases** (53 passed across entire repository, 4 failed in `test_simulator.py`):

```text
FAILED tests/test_simulator.py::test_diurnal_temperature_solar_cycle - AssertionError: assert np.float64(32.37) <= 30.0
FAILED tests/test_simulator.py::test_inject_noise_burst_variance_multiplier - AssertionError: assert np.float64(13.751863607261583) > (np.float64(4.397071497175141) * 4.0)
FAILED tests/test_simulator.py::test_scenario_multi_station_network_heterogeneity - ValueError: negative dimensions are not allowed
FAILED tests/test_simulator.py::test_scenario_health_degradation_trajectory - AssertionError: assert np.False_ == 'DRIFT'.all
```

#### Exact Failure 1: `test_diurnal_temperature_solar_cycle` (`tests/test_simulator.py:58`)
```text
assert df["temperature"].max() <= 30.0
E AssertionError: assert np.float64(32.37) <= 30.0
```
- In `backend/simulator/diurnal_generator.py:211`, `temp_seasonal_amp` defaults to $5.0^\circ\text{C}$. For `start_date="2026-08-01"` (day 213 of year), $\sin(2\pi (213 - 80) / 365.25) \approx 0.753$, producing a seasonal positive bias of $+3.76^\circ\text{C}$.
- With $T_{\text{base}} = 20.0^\circ\text{C}$ and $A_T = 8.0^\circ\text{C}$, the deterministic ceiling is $20.0 + 8.0 + 3.76 = 31.76^\circ\text{C}$, plus AR(1) noise reaching $32.37^\circ\text{C}$.

#### Exact Failure 2: `test_inject_noise_burst_variance_multiplier` (`tests/test_simulator.py:195`)
```text
burst_var = df_burst.loc[100:159, "temperature"].var()
assert burst_var > clean_var * 4.0
E AssertionError: assert np.float64(13.751863607261583) > (np.float64(4.397071497175141) * 4.0)
```
- Over slice `100:159` (5 hours, 08:20 to 13:20 UTC), clean temperature experiences rapid diurnal heating, having an intrinsic signal variance of $\sigma_{\text{clean}}^2 = 4.397$.
- Gaussian noise with $\sigma = 0.35 \times 10.0 = 3.5$ adds variance $\sigma_{\text{noise}}^2 = 12.25$. The combined sample variance is $13.75$, which is less than $4 \times 4.397 = 17.588$.

#### Exact Failure 3: `test_scenario_multi_station_network_heterogeneity` (`backend/simulator/scenarios.py:333`)
```text
backend\simulator\scenarios.py:333: in generate
    inj.inject_noise_burst(target_column="pressure", start_idx=min(1200, len(raw_df) - 48), duration=min(48, len(raw_df) - 1200), noise_factor=8.0, severity="MEDIUM", random_seed=s_seed)
backend\simulator\anomaly_injector.py:328: in inject_noise_burst
    noise = rng.normal(0, burst_std, size=span)
E ValueError: negative dimensions are not allowed
```
- When `duration_days = 3.0`, `len(raw_df) = 864`.
- At line 333, `duration = min(48, len(raw_df) - 1200) = min(48, 864 - 1200) = -336`.
- `span = end_idx - start_idx = min(816 - 336, 864) - 816 = -336 < 0`.

#### Exact Failure 4: `test_scenario_health_degradation_trajectory` (`tests/test_simulator.py:295`)
```text
assert (df.loc[288:487, "anomaly_type"] == "DRIFT").all()
E AssertionError: assert np.False_ == 'DRIFT'.all
```
- In `backend/simulator/scenarios.py:386-393`, `inject_spike(start_idx=450, duration=2)` is injected into `clean_df`, overwriting indices 450 and 451 with `SPIKE` after `inject_drift(start_idx=288, duration=200)` had labeled rows 288..487 as `DRIFT`.
- The test assertion expected indices 288..487 to be 100% `DRIFT`.

---

### 1.2 Temporal Split Non-Leakage Validation
Execution of temporal boundary check on `data/train_clean.csv`, `data/val_mixed.csv`, and `data/test_anomalies.csv`:

```text
Train min/max: 2026-08-01 00:00:00+00:00 -> 2026-08-20 23:55:00+00:00 (5,760 rows, 100% clean, 0 anomalies)
Val min/max:   2026-08-21 00:00:00+00:00 -> 2026-08-25 23:55:00+00:00 (1,440 rows, 30 anomalies = 2.08%)
Test min/max:  2026-08-26 00:00:00+00:00 -> 2026-08-30 23:55:00+00:00 (1,440 rows, 19 anomalies = 1.32%)

Temporal Ordering:
- max(train) < min(val) : True (Gap: 5.0 minutes)
- max(val) < min(test)  : True (Gap: 5.0 minutes)
- Train matches baseline_clean[0:5760]: True
```
**Result**: PASSED with zero forward temporal leakage.

---

### 1.3 Streaming Step Generator Consistency (`DiurnalGenerator.generate_streaming_step`)
Simulated 30 days (8,640 steps) streaming vs batch mode:

| Variable | Metric | Batch Mode | Streaming Mode | Delta ($\Delta$) |
|---|---|---|---|---|
| **Temperature (°C)** | Mean | $24.801$ | $24.843$ | $0.041$ |
| | Std | $4.650$ | $4.649$ | $0.002$ |
| | Min / Max | $16.69$ / $32.88$ | $16.80$ / $32.76$ | $0.110$ / $0.120$ |
| **Pressure (hPa)** | Mean | $987.594$ | $987.580$ | $0.014$ |
| | Std | $5.894$ | $5.721$ | $0.173$ |
| | Min / Max | $976.22$ / $995.04$ | $978.12$ / $996.89$ | $1.900$ / $1.850$ |
| **Humidity (%)** | Mean | $60.753$ | $60.561$ | $0.192$ |
| | Std | $16.932$ | $16.870$ | $0.062$ |
| | Min / Max | $33.15$ / $100.00$ | $33.62$ / $99.45$ | $0.470$ / $0.550$ |
| **$\text{Corr}(T, RH)$** | Pearson $r$ | $-0.9780$ | $-0.9787$ | $0.0007$ |

**Result**: PASSED with strong thermodynamic consistency and fidelity. Minor architectural observation: `generate_streaming_step` omits the 2.5-day synoptic second harmonic ($+2.0 \cos(2\pi \cdot t / 2.5)$), slightly reducing pressure standard deviation by $0.173\text{ hPa}$.

---

### 1.4 Simulator CLI & Dataset Generation Scripts
- `python -m backend.simulator.cli --help` -> Exited 0, displayed all options.
- `python -m backend.simulator.cli --list-scenarios` -> Exited 0, listed all 11 registered scenarios.
- `python -m backend.simulator.cli --scenario weather_front --output-file data/cli_test_front.csv --seed 999` -> Exited 0, exported 2,016 rows.
- `python -m backend.simulator.cli --scenario multi_station --output-file data/cli_test_multistation.csv --seed 42` -> Exited 0, exported 8,064 rows (default 7 days).
- `python scripts/generate_datasets.py` -> Exited 0, created `baseline_clean.csv`, `train_clean.csv`, `val_mixed.csv`, `test_anomalies.csv`.

---

## 2. Logic Chain

1. **Test Suite Discrepancy**: The handoff report from `m1_worker_1` claimed `All 25 tests pass`. Direct empirical execution of `python -m pytest tests/test_simulator.py` proves 4 failures out of 28 tests.
2. **Runtime Code Defect**: In `backend/simulator/scenarios.py:333`, calculating `duration = min(48, len(raw_df) - 1200)` produces negative slice dimensions for any scenario duration under 4.2 days ($< 1200$ rows). This causes unhandled runtime exceptions (`ValueError: negative dimensions are not allowed`) during scenario generation.
3. **Physical Formula Alignment**: In `tests/test_simulator.py:58`, the test assertion assumed $T \le 30.0^\circ\text{C}$ without accounting for `temp_seasonal_amp = 5.0` in the diurnal model for August dates.
4. **Noise Variance Modeling**: In `tests/test_simulator.py:195`, evaluating noise variance over a 5-hour daytime window failed because the clean temperature trend variance ($\sigma^2 \approx 4.4$) was ignored in the test threshold.
5. **Health Scenario Overlap**: In `backend/simulator/scenarios.py:386`, injecting a spike inside a drift window overwrote the labels, breaking the test's assumption of pure drift.

---

## 3. Caveats

- **Core Physics & CLI are Healthy**: The underlying diurnal generation mathematics, Clausius-Clapeyron Magnus-Tetens calculations, AR(1) turbulence generator, temporal split non-leakage, and CLI exporters are functional and well-engineered.
- **Review Constraint**: As an adversarial reviewer operating under strict review-only constraints, no implementation code or test files were directly edited. All fixes must be addressed by the implementation agent.

---

## 4. Conclusion

**Verdict**: **FAIL / BLOCKING FIXES REQUIRED**

While the core physics engine, dataset generation, CLI, temporal splitting, and streaming consistency pass empirical criteria, the milestone cannot be approved in its current state due to:
1. **1 Runtime Logic Bug**: `MultiStationNetworkScenario` crashes with `ValueError` when `duration_days < 4.2` due to unguarded negative duration indexing in `backend/simulator/scenarios.py:333`.
2. **3 Flawed Test Assertions**: `test_diurnal_temperature_solar_cycle`, `test_inject_noise_burst_variance_multiplier`, and `test_scenario_health_degradation_trajectory` in `tests/test_simulator.py` fail against the generator's actual parameters.
3. **1 Incompatible Dtype Warning**: `FutureWarning` in `inject_data_corruption` due to setting string values into float columns without explicit dtype preparation.

### Required Action Items for Worker:
1. In `backend/simulator/scenarios.py`:
   - Fix index and duration clamping in `MultiStationNetworkScenario`: ensure `start_idx` and `duration` are non-negative and bounded (e.g. `start_idx = int(0.70 * len(raw_df))`, `duration = min(48, len(raw_df) - start_idx)`).
2. In `tests/test_simulator.py`:
   - In `test_diurnal_temperature_solar_cycle`: account for `temp_seasonal_amp` (set `temp_seasonal_amp=0.0` or increase max temperature assertion to `35.0`).
   - In `test_inject_noise_burst_variance_multiplier`: test variance on detrended signal or residual difference $(df_{\text{burst}} - df_{\text{clean}})$.var().
   - In `test_scenario_health_degradation_trajectory`: update assertion to account for the spike at index 450 (e.g., check that indices $288..449$ and $452..487$ are `DRIFT` and $450..451$ are `SPIKE`).
3. In `backend/simulator/anomaly_injector.py`:
   - In `inject_data_corruption`: coerce column dtype to `object` before assigning string error codes to avoid pandas `FutureWarning`.
4. Rerun `python -m pytest tests/test_simulator.py -v` and ensure 100% of tests pass.

---

## 5. Verification Method

To reproduce and verify these findings:

1. **Run Simulator Test Suite**:
   ```powershell
   python -m pytest tests/test_simulator.py -v
   ```
   *Observed*: 4 failed, 24 passed.

2. **Reproduce Multi-Station Scenario Bug**:
   ```powershell
   python -c "from backend.simulator.scenarios import MultiStationNetworkScenario; MultiStationNetworkScenario(duration_days=3.0).generate()"
   ```
   *Observed*: `ValueError: negative dimensions are not allowed` at `numpy/random/_common.pyx:654`.

3. **Verify Temporal Split Non-Leakage**:
   ```powershell
   python -c "import pandas as pd; tr = pd.read_csv('data/train_clean.csv'); va = pd.read_csv('data/val_mixed.csv'); te = pd.read_csv('data/test_anomalies.csv'); print(pd.to_datetime(tr['timestamp']).max() < pd.to_datetime(va['timestamp']).min() < pd.to_datetime(va['timestamp']).max() < pd.to_datetime(te['timestamp']).min())"
   ```
   *Observed*: `True`.

4. **Verify Batch vs Streaming Parity**:
   ```powershell
   python -c "import pandas as pd, numpy as np; from backend.simulator.diurnal_generator import DiurnalGenerator; g1 = DiurnalGenerator(seed=42); d1 = g1.generate(duration_days=5.0); g2 = DiurnalGenerator(seed=42); s = None; ts = pd.Timestamp('2026-08-01', tz='UTC'); r = [g2.generate_streaming_step(ts + pd.Timedelta(minutes=5*i), s)[0] for i in range(len(d1))]; d2 = pd.DataFrame(r); print('Corr diff:', abs(d1['temperature'].corr(d1['humidity']) - d2['temperature'].corr(d2['humidity'])))"
   ```
   *Observed*: `Corr diff: 0.0003`.
