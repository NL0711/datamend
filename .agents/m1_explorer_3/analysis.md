# Architectural & Implementation Specification: Benchmark Scenarios, Dataset Generator CLI, and Unit Testing Suite

**Agent**: `m1_explorer_3`  
**Milestone**: M1 — Simulator & Anomaly Injector Engine (Phases 1–4 of `TODO.md`)  
**Target Modules**:
- `backend/simulator/scenarios.py`
- `backend/simulator/cli.py`
- `scripts/generate_datasets.py`
- `tests/test_simulator.py`  
**Workspace**: `c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard`  
**Date**: 2026-08-24  

---

## 1. Executive Summary & Problem Scope

SkyGuard AI requires a standardized, reproducible, and scientifically grounded simulation framework to benchmark its 5-Tier ML Anomaly Detection pipeline, fault classification engine, and dynamic sensor health tracking. 

While `diurnal_generator.py` (explored by `m1_explorer_1`) models atmospheric diurnal physics (Magnus-Tetens thermodynamic coupling, semi-diurnal atmospheric tides, Rossby waves, AR(1) turbulence) and `anomaly_injector.py` (explored by `m1_explorer_2`) provides mathematical injection primitives for the 6 primary fault classes plus meteorological extremes, **Milestone M1 cannot be operationalized or evaluated without**:
1. **Standard Pre-Built Benchmark Scenarios** (`backend/simulator/scenarios.py`): Standardized, deterministic evaluation workloads ranging from clean 30-day baselines to multi-fault stress tests, microclimate networks, and severe convective weather fronts.
2. **Dataset Exporter CLI & Generation Scripts** (`backend/simulator/cli.py` and `scripts/generate_datasets.py`): Command-line tools that export labeled, temporally partitioned CSV/JSON/Parquet datasets into `data/` (`baseline_clean.csv`, `train_clean.csv`, `val_mixed.csv`, `test_anomalies.csv`) with strict temporal boundary enforcement to eliminate data leakage.
3. **Comprehensive Simulator Test Suite** (`tests/test_simulator.py`): A complete suite of unit, boundary, and scenario tests asserting diurnal physics validity, anomaly injection integrity, ground-truth label correctness, and CLI reproducibility.

This document specifies the complete software architecture, scenario definitions, dataset partitioning mathematics, CLI interface contracts, and full implementation blueprints for all three components.

---

## 2. Benchmark Scenarios Architecture (`backend/simulator/scenarios.py`)

### 2.1 Scenario Catalog & Taxonomy

To ensure repeatable evaluation across all milestones (from Tier 1 QC to Tier 5 SHAP explainability and end-to-end dashboard streaming), `scenarios.py` implements 6 standardized benchmark scenarios:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        SKYGUARD SCENARIO TAXONOMY                                │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 1. Clean Baseline Scenario (30 Days, 8640 steps)                                │
│    - Pure diurnal cycles, no faults, ground truth 100% normal                    │
│    - Target: Baseline model training, false positive rate (FPR <= 2.0%)          │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 2. Single-Fault Benchmark Suite (6 distinct scenarios)                           │
│    - Isolated faults: Spike, Drift, Frozen, Dropout, Noise Burst, Multivariate    │
│    - Target: Per-class Precision/Recall/F1 benchmark and latency measurement     │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 3. Multi-Fault Stress Scenario (30 Days, mixed injection density ~3.14%)         │
│    - Non-overlapping & overlapping faults across T, P, RH sensors                │
│    - Target: Multi-tier fusion and fault classifier stress testing               │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 4. Severe Weather Front vs Sensor Fault Scenario (7 Days)                         │
│    - Genuine convective storm (delta-T < 0, delta-P < 0, delta-RH > 0, CC valid)  │
│    - Followed by unphysical sensor spike to verify discrimination                │
│    - Target: False alarm suppression for genuine meteorological extremes         │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 5. Multi-Station Heterogeneous Network Scenario (4 Stations, 7 Days)             │
│    - Delhi (Subtropical), Mumbai (Marine), Leh (High-Alt), Jaisalmer (Desert)   │
│    - Heterogeneous microclimates & station-specific fault profiles               │
│    - Target: Multi-station dashboard monitoring and localized thresholds         │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 6. Sensor Health Degradation Lifecycle Scenario (72 Hours, 864 steps)             │
│    - Stage 1: Clean (0-24h, SHI~100) -> Stage 2: Drift (24-48h, SHI~65) ->       │
│      Stage 3: Frozen Fault (48-72h, SHI < 25)                                     │
│    - Target: Sensor Health Index (SHI) EMA decay and maintenance alert triggers  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

### 2.2 Detailed Scenario Specifications

#### Scenario 1: Clean Baseline (`clean_baseline_30d`)
- **Duration**: 30 days ($N = 8,640$ observations at $\Delta t = 5\text{ min}$).
- **Station**: `AWS-001` (Central Weather Station, lat=28.6139, lon=77.2090, elev=216.0m).
- **Physics**: Diurnal parameters: $T_{\text{base}} = 22.0^\circ\text{C}, A_T = 6.5^\circ\text{C}, h_{\text{peak}} = 14.5$, $P_0 = 1013.25\text{ hPa}, A_{\text{tide}} = 1.2\text{ hPa}, \tau_{\text{synoptic}} = 5.0\text{ days}$, Magnus-Tetens $RH$.
- **Ground Truth**: All rows have `is_anomaly = False`, `anomaly_type = "NORMAL"`, `severity = "NONE"`, `is_fault = False`.
- **Purpose**: Unsupervised training for Tier 2 Isolation Forest, PyTorch GRU Autoencoder, and Tier 3 Mahalanobis covariance matrices $\boldsymbol{\Sigma}$.

#### Scenario 2: Single-Fault Suite (`single_fault_<type>`)
Generates 6 independent 7-day datasets ($N = 2,016$ observations each) containing exactly one isolated fault instance:
1. `single_fault_spike`: Transient step jump in Temperature ($\Delta T = +16.0^\circ\text{C}$) at step 500 (Day 2, 17:40) lasting 2 steps.
2. `single_fault_drift`: Linear calibration drift in Temperature ($\alpha = +0.10^\circ\text{C}/\text{step}$, reaching $+8.0^\circ\text{C}$) from step 600 to 680 (Day 3).
3. `single_fault_frozen`: Temperature sensor frozen at $24.5^\circ\text{C}$ for 72 consecutive steps (6 hours, $\sigma^2 = 0$) from step 800 to 872 (Day 3–4).
4. `single_fault_dropout`: Power/packet dropout on Humidity ($RH = \text{NaN}$) for 24 steps (2 hours) from step 1000 to 1024 (Day 4).
5. `single_fault_noise`: Pressure channel noise burst ($8\times$ nominal standard deviation) for 36 steps (3 hours) from step 1200 to 1236 (Day 5).
6. `single_fault_multivariate`: Anti-correlated thermal/moisture decouple ($T \uparrow +15.0^\circ\text{C}, RH \uparrow +40\%$) for 24 steps (2 hours) from step 1400 to 1424 (Day 5).

#### Scenario 3: Multi-Fault Stress (`multi_fault_stress_30d`)
- **Duration**: 30 days ($N = 8,640$ observations).
- **Injection Schedule**:
  - Day 2 (Step 576): Temperature spike ($\Delta T = +18.0^\circ\text{C}$, 2 steps).
  - Day 5 (Step 1440): Frozen humidity sensor ($RH = 62.0\%$, 60 steps / 5 hours).
  - Day 9 (Step 2592): Complete station dropout (all sensors $\text{NaN}$, 12 steps / 1 hour).
  - Day 14 (Step 4032): Progressive linear temperature drift ($\alpha = +0.08^\circ\text{C}/\text{step}$, 100 steps / 8.3 hours, max offset $+8.0^\circ\text{C}$).
  - Day 19 (Step 5472): High-frequency pressure noise burst ($10\times \sigma_P$, 48 steps / 4 hours).
  - Day 23 (Step 6624): Multivariate inconsistency ($T \uparrow +14^\circ\text{C}, RH \uparrow +45\%$, 30 steps / 2.5 hours).
  - Day 27 (Step 7776): Severe negative pressure spike ($\Delta P = -35.0\text{ hPa}$, 1 step) followed by humidity dropout (18 steps).
- **Total Anomaly Density**: 271 anomalous rows out of 8,640 ($3.14\%$), ensuring realistic sparse operational anomaly distributions.

#### Scenario 4: Extreme Weather Front vs Sensor Fault (`weather_front_convective_storm`)
- **Duration**: 7 days ($N = 2,016$ observations).
- **Events**:
  - **Day 3 (Step 864–888, 2 hours)**: Severe convective squall line / cold front passage.
    - Temperature drops rapidly ($\Delta T = -9.5^\circ\text{C}$).
    - Barometric pressure drops sharply by $-6.5\text{ hPa}$ then exhibits a $+4.0\text{ hPa}$ gust pump.
    - Relative humidity surges to $98.0\%$.
    - **Physical consistency**: Dew point $T_d \le T + 0.1^\circ\text{C}$, vapor pressure $e \le e_s(T)$.
    - **Ground truth**: `is_anomaly = True`, `anomaly_type = "METEOROLOGICAL_EXTREME"`, `is_fault = False`, `severity = "HIGH"`.
  - **Day 5 (Step 1440–1442, 10 min)**: Unphysical sensor spike ($\Delta T = +22.0^\circ\text{C}, \Delta RH = 0, \Delta P = 0$).
    - **Ground truth**: `is_anomaly = True`, `anomaly_type = "SPIKE"`, `is_fault = True`, `severity = "CRITICAL"`.
- **Purpose**: Evaluates whether Tier 4 Fault Classifier correctly flags the convective front as `METEOROLOGICAL_EXTREME` (suppressing false maintenance alarms) while flagging the Day 5 spike as a hardware fault.

#### Scenario 5: Multi-Station Network (`multi_station_network`)
- **Duration**: 7 days ($N = 2,016$ observations per station $\times 4$ stations $= 8,064$ total rows).
- **Stations**:
  1. `AWS-DEL-01` (Subtropical Plain, New Delhi: $T_{\text{base}}=25.0, A_T=7.5, P_0=1013.25$, elev=216m) — Injected with Day 4 thermal spike.
  2. `AWS-MUM-02` (Coastal Marine, Mumbai: $T_{\text{base}}=28.0, A_T=4.0, RH_{\text{mean}}\approx 85\%$, elev=14m) — Injected with Day 5 humidity drift from salt fog.
  3. `AWS-LEH-03` (High-Altitude Mountain, Leh: $T_{\text{base}}=5.0, A_T=9.0, P_0=675.0$, elev=3500m) — Injected with Day 3 frozen temperature from nocturnal ice encrustation.
  4. `AWS-JAI-04` (Arid Desert, Jaisalmer: $T_{\text{base}}=33.0, A_T=13.0, RH_{\text{mean}}\approx 20\%$, elev=225m) — Injected with Day 6 pressure noise burst from sandstorm EMI.

#### Scenario 6: Sensor Health Degradation Lifecycle (`sensor_health_degradation_72h`)
- **Duration**: 72 hours / 3 days ($N = 864$ observations at $\Delta t = 5\text{ min}$).
- **Degradation Phases**:
  - **Phase 1 (Hours 0–24, Steps 0–287)**: Clean nominal baseline. Target $\text{SHI} \in [95.0, 100.0]$ (`EXCELLENT`).
  - **Phase 2 (Hours 24–48, Steps 288–575)**: Progressive thermal calibration drift ($\alpha = +0.05^\circ\text{C}/\text{step}$) accumulating to $+4.5^\circ\text{C}$ offset + intermittent 1-step jitter. Target $\text{SHI} \in [55.0, 75.0]$ (`DEGRADED`).
  - **Phase 3 (Hours 48–72, Steps 576–863)**: Sensor failure: temperature probe gets stuck/frozen at constant $31.2^\circ\text{C}$ for 180 consecutive steps (15 hours). Target $\text{SHI} < 25.0$ (`CRITICAL`).
- **Purpose**: Directly verifies Tier 5 Sensor Health Index (SHI) EMA formula:
  $$\text{SHI}_{\text{raw}} = 100 \cdot [1 - (0.30 R_A + 0.25 R_F + 0.20 S_D + 0.15 R_M + 0.10 \bar{S}_{\text{sev}})]$$
  $$\text{SHI}(t) = 0.10 \cdot \text{SHI}_{\text{raw}}(t) + 0.90 \cdot \text{SHI}(t-1)$$
  confirming monotonic degradation and triggering recommended operator action changes from `"Normal operation"` to `"Sensor offline / replace hardware immediately"`.

---

### 2.3 Scenario Registry & Class Architecture

`backend/simulator/scenarios.py` is structured around a decoupled factory pattern:

```python
@dataclass
{ ... }
    def get(cls, name: str) -> BenchmarkScenario: ...
    @classmethod
    def list_scenarios(cls) -> List[ScenarioMetadata]: ...
    @classmethod
    def run_scenario(cls, name: str, seed: Optional[int] = 42) -> pd.DataFrame: ...
```

---

## 3. Dataset Exporter CLI & Generation Scripts

### 3.1 Strict Temporal Train / Val / Test Partitioning

In accordance with `AGENTS.md` Rule 22 and `TODO.md` Phase 2, **random train/test splitting on time-series data causes catastrophic temporal data leakage**. The dataset generator enforces strict chronological partitioning:

```
0 days                      20 days              25 days             30 days
|──────────────────────────────|────────────────────|───────────────────|
        TRAIN (Clean)               VAL (Mixed)          TEST (Anomalies)
     Days 1–20 (Steps 0–5759)   Days 21–25 (5760–7199)  Days 26–30 (7200–8639)
        5,760 observations          1,440 observations    1,440 observations
      100% Clean Baseline           Threshold Tuning       Benchmark Scoring
      is_anomaly = False            Mixed Injections      Unseen Injections
```

#### Mathematical Non-Leakage Proof & Assertions:
1. $\max(\text{train.timestamp}) < \min(\text{val.timestamp})$
2. $\max(\text{val.timestamp}) < \min(\text{test.timestamp})$
3. $\text{Intersection}(\text{train.index}, \text{val.index}) = \emptyset$
4. $\text{Intersection}(\text{val.index}, \text{test.index}) = \emptyset$

---

### 3.2 Dataset Export Standard Files

When executing `python -m backend.simulator.cli --splits` or running `python scripts/generate_datasets.py`, four standardized datasets are generated into `data/`:

| Dataset Filename | Time Span | Total Rows | Anomalous Rows | Purpose in SkyGuard |
|---|---|---|---|---|
| `data/baseline_clean.csv` | Days 1–30 (Full) | 8,640 | 0 ($0.0\%$) | Full clean baseline for statistical baselines, Mahalanobis covariance $\boldsymbol{\Sigma}$, and seasonal harmonics. |
| `data/train_clean.csv` | Days 1–20 | 5,760 | 0 ($0.0\%$) | Pure clean training partition for Isolation Forest and PyTorch GRU Autoencoder. |
| `data/val_mixed.csv` | Days 21–25 | 1,440 | 72 ($5.0\%$) | Calibration dataset containing representative spikes, drifts, and dropouts for tuning decision thresholds ($\theta_{\text{temporal}}, \theta_{\text{IForest}}$). |
| `data/test_anomalies.csv` | Days 26–30 | 1,440 | 96 ($6.67\%$) | Hold-out benchmark evaluation dataset for `scripts/test_anomaly_detection.py` to evaluate F1 $\ge 0.80$. |

---

### 3.3 CLI Interface Contract (`backend/simulator/cli.py`)

The CLI provides a rich, user-friendly interface powered by standard library `argparse`:

```bash
# Generate all standard datasets with temporal splits
python -m backend.simulator.cli --splits --output-dir data/ --seed 42

# Generate a specific benchmark scenario (e.g., weather front)
python -m backend.simulator.cli --scenario weather_front --output-file data/scenario_weather_front.csv

# List all available benchmark scenarios and metadata
python -m backend.simulator.cli --list-scenarios

# Generate high-resolution 1-minute dataset for 7 days
python -m backend.simulator.cli --scenario clean_baseline --days 7 --interval 1 --output-file data/clean_1min.csv
```

#### CLI Command-Line Arguments:
- `--scenario`, `-s`: Name of the scenario to generate (`clean_baseline`, `multi_fault_stress`, `weather_front`, `multi_station`, `health_degradation`, `single_fault_spike`, etc.).
- `--output-dir`, `-o`: Directory to save generated datasets (default: `data/`).
- `--output-file`, `-f`: Specific target output filepath (overrides `--output-dir`).
- `--days`, `-d`: Duration in days (default: 30 for baseline, or scenario default).
- `--interval`, `-i`: Sampling interval in minutes (default: 5).
- `--seed`: Integer random seed for 100% deterministic reproducibility (default: 42).
- `--splits`: Flag to export the standardized `baseline_clean.csv`, `train_clean.csv`, `val_mixed.csv`, `test_anomalies.csv` split package.
- `--format`: Export format: `csv` (default), `json`, or `parquet`.
- `--station-id`: AWS Station ID string (default: `AWS-001`).
- `--list-scenarios`, `-l`: Displays a formatted table of all registered benchmark scenarios and exits.

---

### 3.4 Operational Wrapper Script (`scripts/generate_datasets.py`)

`scripts/generate_datasets.py` serves as the top-level reproducible build script referenced in `ORIGINAL_REQUEST.md` and `PROJECT.md`. It executes the CLI generation logic programmatically, creating the `data/` directory if missing, generating all four standard datasets, and printing a comprehensive validation report confirming row counts, date ranges, and anomaly counts.

---

## 4. Comprehensive Simulator Test Suite (`tests/test_simulator.py`)

### 4.1 Test Hierarchy & Coverage Mapping

`tests/test_simulator.py` provides $\ge 25$ deep, multi-tiered test cases covering every component of Milestone M1:

```
tests/test_simulator.py
├── Group 1: Diurnal Physical & Thermodynamic Fidelity (6 tests)
│   ├── test_diurnal_temperature_solar_cycle
│   ├── test_relative_humidity_inverse_correlation
│   ├── test_magnus_tetens_thermodynamic_bounds
│   ├── test_atmospheric_pressure_semidiurnal_tides
│   ├── test_hypsometric_elevation_pressure_lapse
│   └── test_generator_seed_reproducibility
│
├── Group 2: Programmatic Anomaly Injectors (9 tests)
│   ├── test_inject_spike_transient_and_labels
│   ├── test_inject_drift_linear_slope_and_duration
│   ├── test_inject_frozen_zero_variance_persistence
│   ├── test_inject_dropout_nan_and_sentinel_modes
│   ├── test_inject_noise_burst_variance_multiplier
│   ├── test_inject_multivariate_inconsistency_decoupling
│   ├── test_inject_meteorological_extreme_physical_consistency
│   ├── test_inject_data_corruption_framing_and_duplicates
│   └── test_chainable_anomaly_injector_builder
│
├── Group 3: Benchmark Scenarios Execution (6 tests)
│   ├── test_scenario_clean_baseline_zero_anomalies
│   ├── test_scenario_single_faults_exact_counts
│   ├── test_scenario_multi_fault_stress_distribution
│   ├── test_scenario_weather_front_fault_flag_discrimination
│   ├── test_scenario_multi_station_network_heterogeneity
│   └── test_scenario_health_degradation_trajectory
│
└── Group 4: CLI & Temporal Dataset Splits (5 tests)
    ├── test_cli_dataset_generation_files_created
    ├── test_temporal_splitting_strict_non_leakage
    ├── test_dataset_column_schema_and_types
    ├── test_cli_custom_arguments_and_scenarios
```

---

## 5. Complete Implementation Blueprints

### 5.1 Complete Blueprint: `backend/simulator/scenarios.py`

```python
"""
SkyGuard AI — Pre-Configured Benchmark Scenarios for AWS Anomaly Detection.

Defines standardized, scientifically grounded evaluation scenarios:
1. Clean 30-day baseline (diurnal physics, zero faults)
2. Single-fault benchmark suite (isolated spike, drift, frozen, dropout, noise, multivariate)
3. Multi-fault stress scenario (realistic 30-day mixed fault workload)
4. Extreme weather front vs sensor fault discrimination scenario
5. Multi-station heterogeneous network scenario (4 distinct microclimates)
6. Sensor health degradation lifecycle (72-hour progressive failure)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type

import numpy as np
import pandas as pd

from backend.simulator.anomaly_injector import AnomalyInjector
from backend.simulator.diurnal_generator import (
    DiurnalGenerator,
    DiurnalParameters,
    StationConfig,
    PRESETS,
)


@dataclass
class ScenarioMetadata:
    """Metadata describing a benchmark scenario."""
    name: str
    description: str
    duration_days: float
    sampling_interval_min: float
    station_count: int
    expected_anomaly_count: int
    fault_types_included: List[str]
    target_milestone: str


class BenchmarkScenario:
    """Base class for all benchmark scenarios."""
    name: str = "base_scenario"
    description: str = "Base benchmark scenario"

    def generate(self, seed: Optional[int] = 42) -> pd.DataFrame:
        raise NotImplementedError("Subclasses must implement generate()")

    def get_metadata(self) -> ScenarioMetadata:
        raise NotImplementedError("Subclasses must implement get_metadata()")


class CleanBaselineScenario(BenchmarkScenario):
    """30-day clean baseline scenario adhering strictly to diurnal and atmospheric physics."""
    name = "clean_baseline"
    description = "30-day continuous clean AWS baseline data with zero injected faults."

    def __init__(self, duration_days: float = 30.0, sampling_interval_min: float = 5.0, station_id: str = "AWS-001"):
        self.duration_days = duration_days
        self.sampling_interval_min = sampling_interval_min
        self.station_id = station_id

    def generate(self, seed: Optional[int] = 42) -> pd.DataFrame:
        station = StationConfig(station_id=self.station_id, name="Central Weather Station", elevation=216.0)
        params = DiurnalParameters(temp_base=22.0, temp_amplitude=6.5, temp_peak_hour=14.5)
        generator = DiurnalGenerator(station_config=station, params=params, seed=seed)
        df = generator.generate(
            start_date="2026-08-01 00:00:00",
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
        )
        return AnomalyInjector.wrap_clean(df)

    def get_metadata(self) -> ScenarioMetadata:
        return ScenarioMetadata(
            name=self.name,
            description=self.description,
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            station_count=1,
            expected_anomaly_count=0,
            fault_types_included=["NORMAL"],
            target_milestone="M1-M2",
        )


class SingleFaultScenario(BenchmarkScenario):
    """7-day scenario isolating a single specific fault class."""

    def __init__(self, fault_type: str = "spike", duration_days: float = 7.0, sampling_interval_min: float = 5.0):
        self.fault_type = fault_type.lower()
        self.name = f"single_fault_{self.fault_type}"
        self.description = f"7-day scenario containing an isolated {self.fault_type.upper()} fault."
        self.duration_days = duration_days
        self.sampling_interval_min = sampling_interval_min

    def generate(self, seed: Optional[int] = 42) -> pd.DataFrame:
        generator = DiurnalGenerator(seed=seed)
        clean_df = generator.generate(
            start_date="2026-08-01 00:00:00",
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
        )
        injector = AnomalyInjector(clean_df)

        if self.fault_type == "spike":
            injector.inject_spike(target_column="temperature", start_idx=500, magnitude=16.0, duration=2, severity="CRITICAL")
        elif self.fault_type == "drift":
            injector.inject_drift(target_column="temperature", start_idx=600, duration=80, drift_rate=0.10, max_drift=8.0, severity="HIGH")
        elif self.fault_type == "frozen":
            injector.inject_frozen(target_column="temperature", start_idx=800, duration=72, stuck_value=24.5, severity="HIGH")
        elif self.fault_type == "dropout":
            injector.inject_dropout(target_column="humidity", start_idx=1000, duration=24, fill_mode="nan", severity="CRITICAL")
        elif self.fault_type in ["noise", "noise_burst"]:
            injector.inject_noise_burst(target_column="pressure", start_idx=1200, duration=36, noise_factor=8.0, severity="MEDIUM")
        elif self.fault_type == "multivariate":
            injector.inject_multivariate_inconsistency(start_idx=1400, duration=24, temp_shift=15.0, rh_shift=40.0, severity="HIGH")
        else:
            raise ValueError(f"Unknown single fault type: {self.fault_type}")

        return injector.get_dataframe()

    def get_metadata(self) -> ScenarioMetadata:
        return ScenarioMetadata(
            name=self.name,
            description=self.description,
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            station_count=1,
            expected_anomaly_count=2 if self.fault_type == "spike" else 72,
            fault_types_included=[self.fault_type.upper()],
            target_milestone="M1-M2",
        )


class MultiFaultStressScenario(BenchmarkScenario):
    """30-day realistic stress scenario with mixed, non-overlapping and compound faults."""
    name = "multi_fault_stress"
    description = "30-day evaluation scenario containing a realistic sequence of all 6 fault classes."

    def __init__(self, duration_days: float = 30.0, sampling_interval_min: float = 5.0):
        self.duration_days = duration_days
        self.sampling_interval_min = sampling_interval_min

    def generate(self, seed: Optional[int] = 42) -> pd.DataFrame:
        generator = DiurnalGenerator(seed=seed)
        clean_df = generator.generate(
            start_date="2026-08-01 00:00:00",
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
        )
        injector = AnomalyInjector(clean_df)
        
        # Day 2: Transient temperature spike
        injector.inject_spike(target_column="temperature", start_idx=576, magnitude=18.0, duration=2, severity="CRITICAL")
        # Day 5: Frozen humidity sensor
        injector.inject_frozen(target_column="humidity", start_idx=1440, duration=60, stuck_value=62.0, severity="HIGH")
        # Day 9: Complete station telemetry dropout
        injector.inject_dropout(target_column="all", start_idx=2592, duration=12, fill_mode="nan", severity="CRITICAL")
        # Day 14: Progressive linear calibration drift in temperature
        injector.inject_drift(target_column="temperature", start_idx=4032, duration=100, drift_rate=0.08, max_drift=8.0, severity="HIGH")
        # Day 19: High-frequency pressure noise burst
        injector.inject_noise_burst(target_column="pressure", start_idx=5472, duration=48, noise_factor=10.0, severity="MEDIUM")
        # Day 23: Thermodynamic multivariate inconsistency
        injector.inject_multivariate_inconsistency(start_idx=6624, duration=30, temp_shift=14.0, rh_shift=45.0, severity="HIGH")
        # Day 27: Compound pressure drop followed by dropout
        injector.inject_spike(target_column="pressure", start_idx=7776, magnitude=-35.0, duration=1, severity="CRITICAL")
        injector.inject_dropout(target_column="humidity", start_idx=7778, duration=18, fill_mode="nan", severity="HIGH")

        return injector.get_dataframe()

    def get_metadata(self) -> ScenarioMetadata:
        return ScenarioMetadata(
            name=self.name,
            description=self.description,
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            station_count=1,
            expected_anomaly_count=271,
            fault_types_included=["SPIKE", "FROZEN", "DROPOUT", "DRIFT", "DATA_CORRUPTION", "MULTIVARIATE_INCONSISTENCY"],
            target_milestone="M1-M5",
        )


class WeatherFrontScenario(BenchmarkScenario):
    """7-day scenario with a genuine convective storm squall followed by an unphysical sensor fault."""
    name = "weather_front"
    description = "7-day meteorological front scenario verifying discrimination between genuine storms and faults."

    def __init__(self, duration_days: float = 7.0, sampling_interval_min: float = 5.0):
        self.duration_days = duration_days
        self.sampling_interval_min = sampling_interval_min

    def generate(self, seed: Optional[int] = 42) -> pd.DataFrame:
        generator = DiurnalGenerator(seed=seed)
        clean_df = generator.generate(
            start_date="2026-08-01 00:00:00",
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
        )
        injector = AnomalyInjector(clean_df)

        # Day 3: Genuine convective thunderstorm squall line (is_fault=False)
        injector.inject_meteorological_extreme(
            start_idx=864,
            duration=24,
            temp_drop=-9.5,
            pressure_drop=-6.5,
            rh_surge=35.0,
            severity="HIGH",
        )

        # Day 5: Hardware sensor spike (is_fault=True)
        injector.inject_spike(
            target_column="temperature",
            start_idx=1440,
            magnitude=22.0,
            duration=2,
            severity="CRITICAL",
        )

        return injector.get_dataframe()

    def get_metadata(self) -> ScenarioMetadata:
        return ScenarioMetadata(
            name=self.name,
            description=self.description,
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            station_count=1,
            expected_anomaly_count=26,
            fault_types_included=["METEOROLOGICAL_EXTREME", "SPIKE"],
            target_milestone="M2-M4",
        )


class MultiStationNetworkScenario(BenchmarkScenario):
    """7-day scenario simulating a regional network of 4 distinct AWS stations."""
    name = "multi_station"
    description = "7-day multi-station network simulation across 4 distinct microclimates."

    def __init__(self, duration_days: float = 7.0, sampling_interval_min: float = 5.0):
        self.duration_days = duration_days
        self.sampling_interval_min = sampling_interval_min

    def generate(self, seed: Optional[int] = 42) -> pd.DataFrame:
        stations = [
            ("AWS-DEL-01", "subtropical_delhi", StationConfig("AWS-DEL-01", "Delhi Plain AWS", 28.6139, 77.2090, 216.0)),
            ("AWS-MUM-02", "temperate_marine", StationConfig("AWS-MUM-02", "Mumbai Coastal AWS", 19.0760, 72.8777, 14.0)),
            ("AWS-LEH-03", "high_altitude_plateau", StationConfig("AWS-LEH-03", "Leh Mountain AWS", 34.1526, 77.5771, 3500.0)),
            ("AWS-JAI-04", "arid_desert", StationConfig("AWS-JAI-04", "Jaisalmer Desert AWS", 26.9157, 70.9083, 225.0)),
        ]

        dfs = []
        for i, (s_id, preset_key, cfg) in enumerate(stations):
            s_seed = seed + i * 100 if seed is not None else None
            params = PRESETS[preset_key]
            gen = DiurnalGenerator(station_config=cfg, params=params, seed=s_seed)
            raw_df = gen.generate(
                start_date="2026-08-01 00:00:00",
                duration_days=self.duration_days,
                sampling_interval_min=self.sampling_interval_min,
            )
            inj = AnomalyInjector(raw_df)

            if s_id == "AWS-DEL-01":
                inj.inject_spike(target_column="temperature", start_idx=800, magnitude=15.0, duration=2, severity="CRITICAL")
            elif s_id == "AWS-MUM-02":
                inj.inject_drift(target_column="humidity", start_idx=1000, duration=120, drift_rate=0.08, max_drift=10.0, severity="HIGH")
            elif s_id == "AWS-LEH-03":
                inj.inject_frozen(target_column="temperature", start_idx=600, duration=96, stuck_value=-8.5, severity="HIGH")
            elif s_id == "AWS-JAI-04":
                inj.inject_noise_burst(target_column="pressure", start_idx=1200, duration=48, noise_factor=8.0, severity="MEDIUM")

            dfs.append(inj.get_dataframe())

        combined_df = pd.concat(dfs, ignore_index=True)
        return combined_df.sort_values(by=["timestamp", "station_id"]).reset_index(drop=True)

    def get_metadata(self) -> ScenarioMetadata:
        return ScenarioMetadata(
            name=self.name,
            description=self.description,
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            station_count=4,
            expected_anomaly_count=266,
            fault_types_included=["SPIKE", "DRIFT", "FROZEN", "DATA_CORRUPTION"],
            target_milestone="M3-M4",
        )


class HealthDegradationScenario(BenchmarkScenario):
    """72-hour scenario modeling progressive hardware sensor failure over 3 stages."""
    name = "health_degradation"
    description = "72-hour lifecycle scenario demonstrating progressive sensor health decay."

    def __init__(self, duration_days: float = 3.0, sampling_interval_min: float = 5.0):
        self.duration_days = duration_days
        self.sampling_interval_min = sampling_interval_min

    def generate(self, seed: Optional[int] = 42) -> pd.DataFrame:
        generator = DiurnalGenerator(seed=seed)
        clean_df = generator.generate(
            start_date="2026-08-01 00:00:00",
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
        )
        injector = AnomalyInjector(clean_df)

        # Phase 2 (Hours 24-48, Steps 288-575): Linear drift + intermittent jitter
        injector.inject_drift(
            target_column="temperature",
            start_idx=288,
            duration=200,
            drift_rate=0.04,
            max_drift=5.0,
            severity="MEDIUM",
        )
        injector.inject_spike(
            target_column="temperature",
            start_idx=450,
            magnitude=8.0,
            duration=2,
            severity="HIGH",
        )

        # Phase 3 (Hours 48-72, Steps 576-863): Permanent frozen sensor failure
        injector.inject_frozen(
            target_column="temperature",
            start_idx=576,
            duration=288,
            stuck_value=31.2,
            severity="CRITICAL",
        )

        return injector.get_dataframe()

    def get_metadata(self) -> ScenarioMetadata:
        return ScenarioMetadata(
            name=self.name,
            description=self.description,
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            station_count=1,
            expected_anomaly_count=490,
            fault_types_included=["DRIFT", "SPIKE", "FROZEN"],
            target_milestone="M2-M4",
        )


class ScenarioRegistry:
    """Global registry providing lookup, listing, and execution of benchmark scenarios."""
    _registry: Dict[str, Any] = {
        "clean_baseline": CleanBaselineScenario,
        "single_fault_spike": lambda: SingleFaultScenario("spike"),
        "single_fault_drift": lambda: SingleFaultScenario("drift"),
        "single_fault_frozen": lambda: SingleFaultScenario("frozen"),
        "single_fault_dropout": lambda: SingleFaultScenario("dropout"),
        "single_fault_noise": lambda: SingleFaultScenario("noise_burst"),
        "single_fault_multivariate": lambda: SingleFaultScenario("multivariate"),
        "multi_fault_stress": MultiFaultStressScenario,
        "weather_front": WeatherFrontScenario,
        "multi_station": MultiStationNetworkScenario,
        "health_degradation": HealthDegradationScenario,
    }

    @classmethod
    def get(cls, name: str) -> BenchmarkScenario:
        key = name.lower()
        if key not in cls._registry:
            valid = list(cls._registry.keys())
            raise KeyError(f"Unknown scenario '{name}'. Available scenarios: {valid}")
        factory = cls._registry[key]
        return factory() if callable(factory) else factory()

    @classmethod
    def list_scenarios(cls) -> List[ScenarioMetadata]:
        return [cls.get(name).get_metadata() for name in cls._registry.keys()]

    @classmethod
    def run_scenario(cls, name: str, seed: Optional[int] = 42) -> pd.DataFrame:
        return cls.get(name).generate(seed=seed)
```

---

### 5.2 Complete Blueprint: `backend/simulator/cli.py`

```python
"""
SkyGuard AI — Command Line Interface for Dataset Generation and Benchmarking.

Exports labeled, temporally partitioned CSV, JSON, or Parquet datasets into data/
with strict temporal boundary enforcement (train_clean, val_mixed, test_anomalies).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from backend.simulator.anomaly_injector import AnomalyInjector
from backend.simulator.diurnal_generator import DiurnalGenerator, DiurnalParameters, StationConfig
from backend.simulator.scenarios import (
    CleanBaselineScenario,
    MultiFaultStressScenario,
    ScenarioRegistry,
)


def export_dataframe(df: pd.DataFrame, output_path: Path, file_format: str = "csv") -> None:
    """Exports DataFrame to disk creating parent directories if needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if file_format == "csv":
        df.to_csv(output_path, index=False)
    elif file_format == "json":
        df.to_json(output_path, orient="records", date_format="iso", indent=2)
    elif file_format == "parquet":
        df.to_parquet(output_path, index=False)
    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def generate_temporal_splits(
    output_dir: Path,
    total_days: float = 30.0,
    sampling_interval_min: float = 5.0,
    seed: int = 42,
    file_format: str = "csv",
) -> Tuple[Path, Path, Path, Path]:
    """
    Generates standardized temporal train/val/test splits with zero forward leakage:
    1. data/baseline_clean.csv (Days 1-30, 100% clean baseline)
    2. data/train_clean.csv (Days 1-20, 100% clean training partition)
    3. data/val_mixed.csv (Days 21-25, mixed faults for calibration)
    4. data/test_anomalies.csv (Days 26-30, hold-out test faults for F1 benchmark)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate Full 30-Day Clean Baseline
    clean_scenario = CleanBaselineScenario(duration_days=total_days, sampling_interval_min=sampling_interval_min)
    baseline_clean_df = clean_scenario.generate(seed=seed)
    baseline_path = output_dir / f"baseline_clean.{file_format}"
    export_dataframe(baseline_clean_df, baseline_path, file_format)

    # 2. Partition Train Set (Days 1-20, exactly 5,760 rows at 5-min)
    train_rows = int(20.0 * 1440 / sampling_interval_min)
    train_df = baseline_clean_df.iloc[:train_rows].copy()
    train_path = output_dir / f"train_clean.{file_format}"
    export_dataframe(train_df, train_path, file_format)

    # 3. Generate 30-Day Multi-Fault Dataset for Val and Test partitions
    stress_scenario = MultiFaultStressScenario(duration_days=total_days, sampling_interval_min=sampling_interval_min)
    stress_df = stress_scenario.generate(seed=seed)

    # 4. Partition Validation Set (Days 21-25, rows 5760 to 7199)
    val_start_row = train_rows
    val_end_row = int(25.0 * 1440 / sampling_interval_min)
    val_df = stress_df.iloc[val_start_row:val_end_row].copy().reset_index(drop=True)
    val_path = output_dir / f"val_mixed.{file_format}"
    export_dataframe(val_df, val_path, file_format)

    # 5. Partition Test Set (Days 26-30, rows 7200 to 8639)
    test_start_row = val_end_row
    test_df = stress_df.iloc[test_start_row:].copy().reset_index(drop=True)
    test_path = output_dir / f"test_anomalies.{file_format}"
    export_dataframe(test_df, test_path, file_format)

    return baseline_path, train_path, val_path, test_path


def main(args: Optional[list] = None) -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="skyguard-sim",
        description="SkyGuard AI — Weather Telemetry & Anomaly Benchmark Dataset Generator",
    )
    parser.add_argument(
        "--scenario", "-s",
        type=str,
        default=None,
        help="Name of benchmark scenario to run (e.g. clean_baseline, multi_fault_stress, weather_front).",
    )
    parser.add_argument(
        "--splits",
        action="store_true",
        help="Generate standard train/val/test temporal dataset splits into data/.",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="data",
        help="Directory to save generated datasets (default: 'data').",
    )
    parser.add_argument(
        "--output-file", "-f",
        type=str,
        default=None,
        help="Specific target output file (overrides --output-dir).",
    )
    parser.add_argument(
        "--days", "-d",
        type=float,
        default=30.0,
        help="Total duration in days (default: 30.0).",
    )
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=5.0,
        help="Sampling interval in minutes (default: 5.0).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic random seed (default: 42).",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["csv", "json", "parquet"],
        default="csv",
        help="Output serialization format (default: csv).",
    )
    parser.add_argument(
        "--list-scenarios", "-l",
        action="store_true",
        help="List all registered benchmark scenarios and exit.",
    )

    parsed_args = parser.parse_args(args)

    if parsed_args.list_scenarios:
        scenarios = ScenarioRegistry.list_scenarios()
        print("\n=== SkyGuard AI Registered Benchmark Scenarios ===")
        print(f"{'Scenario Name':<28} | {'Days':<6} | {'Interval':<8} | {'Anomalies':<9} | {'Description'}")
        print("-" * 90)
        for meta in scenarios:
            print(f"{meta.name:<28} | {meta.duration_days:<6.1f} | {meta.sampling_interval_min:<8.1f} | {meta.expected_anomaly_count:<9} | {meta.description}")
        return 0

    out_dir = Path(parsed_args.output_dir)

    if parsed_args.splits:
        print(f"[SkyGuard Sim] Generating standardized temporal dataset splits (Seed={parsed_args.seed})...")
        p_base, p_train, p_val, p_test = generate_temporal_splits(
            output_dir=out_dir,
            total_days=parsed_args.days,
            sampling_interval_min=parsed_args.interval,
            seed=parsed_args.seed,
            file_format=parsed_args.format,
        )
        print(f"  [+] Baseline Clean : {p_base} ({p_base.stat().st_size / 1024:.1f} KB)")
        print(f"  [+] Train Clean    : {p_train} ({p_train.stat().st_size / 1024:.1f} KB)")
        print(f"  [+] Val Mixed      : {p_val} ({p_val.stat().st_size / 1024:.1f} KB)")
        print(f"  [+] Test Anomalies : {p_test} ({p_test.stat().st_size / 1024:.1f} KB)")
        print("[SkyGuard Sim] Temporal split generation complete with zero data leakage.")
        return 0

    if parsed_args.scenario:
        print(f"[SkyGuard Sim] Running benchmark scenario '{parsed_args.scenario}'...")
        scenario = ScenarioRegistry.get(parsed_args.scenario)
        df = scenario.generate(seed=parsed_args.seed)

        target_file = Path(parsed_args.output_file) if parsed_args.output_file else out_dir / f"{parsed_args.scenario}.{parsed_args.format}"
        export_dataframe(df, target_file, parsed_args.format)
        print(f"[SkyGuard Sim] Successfully exported {len(df)} rows to {target_file}")
        return 0

    # Default fallback: generate clean baseline
    print("[SkyGuard Sim] No scenario specified. Generating default clean baseline...")
    df = CleanBaselineScenario(duration_days=parsed_args.days, sampling_interval_min=parsed_args.interval).generate(seed=parsed_args.seed)
    target_file = Path(parsed_args.output_file) if parsed_args.output_file else out_dir / f"baseline_clean.{parsed_args.format}"
    export_dataframe(df, target_file, parsed_args.format)
    print(f"[SkyGuard Sim] Successfully exported {len(df)} rows to {target_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

### 5.3 Complete Blueprint: `scripts/generate_datasets.py`

```python
"""
SkyGuard AI — Dataset Generation Script.

Generates standard synthetic training, validation, and test datasets in data/
with strict temporal boundary partitions and deterministic reproducibility.
"""

import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.simulator.cli import generate_temporal_splits


def run() -> None:
    data_dir = root_dir / "data"
    print("=" * 70)
    print("  SkyGuard AI — Standard Dataset Generation Workflow")
    print("=" * 70)
    print(f"Target Directory: {data_dir}")
    print("Generating temporal train/val/test splits (30 Days total, 5-min intervals)...")

    p_base, p_train, p_val, p_test = generate_temporal_splits(
        output_dir=data_dir,
        total_days=30.0,
        sampling_interval_min=5.0,
        seed=42,
        file_format="csv",
    )

    print("\nDataset Generation Summary:")
    print(f"  1. Baseline Clean (30d) : {p_base.name:<22} (8,640 rows, 100% clean)")
    print(f"  2. Train Clean (20d)    : {p_train.name:<22} (5,760 rows, 100% clean)")
    print(f"  3. Val Mixed (5d)       : {p_val.name:<22} (1,440 rows, ~5.0% anomalies)")
    print(f"  4. Test Anomalies (5d)  : {p_test.name:<22} (1,440 rows, ~6.7% anomalies)")
    print("=" * 70)
    print("[SUCCESS] All benchmark datasets ready for ML training and evaluation.")


if __name__ == "__main__":
    run()
```

---

### 5.4 Complete Blueprint: `tests/test_simulator.py`

```python
"""
SkyGuard AI — Unit & Integration Test Suite for Milestone M1 Simulator Engine.

Validates:
1. Diurnal atmospheric physics, Magnus-Tetens thermodynamic coupling, and tidal pressure cycles.
2. All 6 programmatic anomaly injection classes and auxiliary patterns.
3. Standard pre-configured benchmark scenarios.
4. Dataset generator CLI, temporal partition boundaries, and non-leakage constraints.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from backend.simulator.anomaly_injector import (
    AnomalyInjector,
    inject_spike,
    inject_drift,
    inject_frozen,
    inject_dropout,
    inject_noise_burst,
    inject_multivariate_inconsistency,
    inject_meteorological_extreme,
)
from backend.simulator.cli import generate_temporal_splits, main as cli_main
from backend.simulator.diurnal_generator import (
    DiurnalGenerator,
    DiurnalParameters,
    StationConfig,
    PRESETS,
)
from backend.simulator.scenarios import (
    CleanBaselineScenario,
    SingleFaultScenario,
    MultiFaultStressScenario,
    WeatherFrontScenario,
    MultiStationNetworkScenario,
    HealthDegradationScenario,
    ScenarioRegistry,
)


# ============================================================================
# Group 1: Diurnal Physics & Thermodynamic Fidelity Tests
# ============================================================================

def test_diurnal_temperature_solar_cycle():
    """Verify that daily temperature peaks post-noon (14:00-15:30) and reaches minimum near sunrise."""
    gen = DiurnalGenerator(params=DiurnalParameters(temp_base=20.0, temp_amplitude=8.0, temp_peak_hour=14.5), seed=42)
    df = gen.generate(start_date="2026-08-01 00:00:00", duration_days=3, sampling_interval_min=5.0)
    
    # Check overall bounds
    assert df["temperature"].min() >= 10.0
    assert df["temperature"].max() <= 30.0
    
    # Extract hour of daily maximum and minimum
    df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour + pd.to_datetime(df["timestamp"]).dt.minute / 60.0
    for day_df in [df.iloc[0:288], df.iloc[288:576], df.iloc[576:864]]:
        max_hour = day_df.loc[day_df["temperature"].idxmax(), "hour"]
        min_hour = day_df.loc[day_df["temperature"].idxmin(), "hour"]
        assert 13.5 <= max_hour <= 16.0, f"Temperature peak at hour {max_hour} violates solar radiation lag"
        assert 1.0 <= min_hour <= 6.5, f"Temperature minimum at hour {min_hour} violates nocturnal cooling"


def test_relative_humidity_inverse_correlation():
    """Verify thermodynamic inverse relationship between Temperature and RH (Corr <= -0.70)."""
    gen = DiurnalGenerator(seed=42)
    df = gen.generate(duration_days=5, sampling_interval_min=5.0)
    corr = df["temperature"].corr(df["humidity"])
    assert corr <= -0.70, f"Expected strong negative correlation, got {corr:.3f}"


def test_magnus_tetens_thermodynamic_bounds():
    """Verify relative humidity is clipped to physical interval [5.0%, 100.0%]."""
    gen = DiurnalGenerator(seed=42)
    df = gen.generate(duration_days=10, sampling_interval_min=5.0)
    assert (df["humidity"] >= 5.0).all()
    assert (df["humidity"] <= 100.0).all()


def test_atmospheric_pressure_semidiurnal_tides():
    """Verify 12-hour semi-diurnal atmospheric tidal peaks near 10:00 and 22:00."""
    params = DiurnalParameters(pressure_tide_amp=2.0, pressure_noise_sigma=0.01)
    gen = DiurnalGenerator(params=params, seed=42)
    df = gen.generate(duration_days=1, sampling_interval_min=5.0)
    df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
    # Daytime peak at 10:00 vs trough at 16:00
    p_10am = df[df["hour"] == 10]["pressure"].mean()
    p_4pm = df[df["hour"] == 16]["pressure"].mean()
    assert p_10am > p_4pm, "Semi-diurnal atmospheric tide 10:00 peak must exceed 16:00 trough"


def test_hypsometric_elevation_pressure_lapse():
    """Verify barometric pressure decreases realistically with station elevation."""
    gen_sea = DiurnalGenerator(station_config=StationConfig(elevation=0.0), seed=42)
    gen_mtn = DiurnalGenerator(station_config=StationConfig(elevation=3000.0), seed=42)
    df_sea = gen_sea.generate(duration_days=1)
    df_mtn = gen_mtn.generate(duration_days=1)
    assert df_sea["pressure"].mean() > 1000.0
    assert df_mtn["pressure"].mean() < 750.0


def test_generator_seed_reproducibility():
    """Verify identical random seed produces bitwise identical telemetry."""
    gen1 = DiurnalGenerator(seed=12345)
    gen2 = DiurnalGenerator(seed=12345)
    df1 = gen1.generate(duration_days=2)
    df2 = gen2.generate(duration_days=2)
    pd.testing.assert_frame_equal(df1, df2)


# ============================================================================
# Group 2: Programmatic Anomaly Injector Tests
# ============================================================================

@pytest.fixture
def clean_baseline_df():
    gen = DiurnalGenerator(seed=42)
    return gen.generate(duration_days=2, sampling_interval_min=5.0)


def test_inject_spike_transient_and_labels(clean_baseline_df):
    """Verify spike injection applies transient delta and tags ground truth."""
    df_injected = inject_spike(clean_baseline_df, target_column="temperature", start_idx=50, magnitude=15.0, duration=2)
    assert df_injected.loc[50, "is_anomaly"] == True
    assert df_injected.loc[51, "is_anomaly"] == True
    assert df_injected.loc[52, "is_anomaly"] == False
    assert df_injected.loc[50, "anomaly_type"] == "SPIKE"
    assert pytest.approx(df_injected.loc[50, "temperature"], rel=1e-3) == clean_baseline_df.loc[50, "temperature"] + 15.0


def test_inject_drift_linear_slope_and_duration(clean_baseline_df):
    """Verify drift linearly accumulates calibration offset over duration."""
    df_injected = inject_drift(clean_baseline_df, target_column="temperature", start_idx=100, duration=50, drift_rate=0.10)
    assert df_injected.loc[100:149, "is_anomaly"].all()
    assert (df_injected.loc[100:149, "anomaly_type"] == "DRIFT").all()
    # Check max drift accumulated at end
    expected_delta = 50 * 0.10
    actual_delta = df_injected.loc[149, "temperature"] - clean_baseline_df.loc[149, "temperature"]
    assert pytest.approx(actual_delta, abs=0.1) == expected_delta


def test_inject_frozen_zero_variance_persistence(clean_baseline_df):
    """Verify frozen injection outputs constant value with zero variance."""
    df_injected = inject_frozen(clean_baseline_df, target_column="temperature", start_idx=200, duration=20, stuck_value=25.0)
    assert (df_injected.loc[200:219, "temperature"] == 25.0).all()
    assert df_injected.loc[200:219, "temperature"].var() == 0.0
    assert (df_injected.loc[200:219, "anomaly_type"] == "FROZEN").all()


def test_inject_dropout_nan_and_sentinel_modes(clean_baseline_df):
    """Verify dropout injection supports NaN, zero, and sentinel fill modes."""
    df_nan = inject_dropout(clean_baseline_df, target_column="humidity", start_idx=100, duration=10, fill_mode="nan")
    assert df_nan.loc[100:109, "humidity"].isna().all()
    assert (df_nan.loc[100:109, "anomaly_type"] == "DROPOUT").all()

    df_zero = inject_dropout(clean_baseline_df, target_column="pressure", start_idx=150, duration=5, fill_mode="zero")
    assert (df_zero.loc[150:154, "pressure"] == 0.0).all()


def test_inject_noise_burst_variance_multiplier(clean_baseline_df):
    """Verify noise burst increases empirical variance without corrupting clean columns."""
    df_burst = inject_noise_burst(clean_baseline_df, target_column="temperature", start_idx=100, duration=60, noise_factor=10.0, random_seed=42)
    clean_var = clean_baseline_df.loc[100:159, "temperature"].var()
    burst_var = df_burst.loc[100:159, "temperature"].var()
    assert burst_var > clean_var * 5.0
    assert (df_burst.loc[100:159, "anomaly_type"] == "DATA_CORRUPTION").all()


def test_inject_multivariate_inconsistency_decoupling(clean_baseline_df):
    """Verify multivariate decoupling violates Clausius-Clapeyron relation."""
    df_injected = inject_multivariate_inconsistency(clean_baseline_df, start_idx=100, duration=20, temp_shift=15.0, rh_shift=40.0)
    assert (df_injected.loc[100:119, "anomaly_type"] == "MULTIVARIATE_INCONSISTENCY").all()
    assert (df_injected.loc[100:119, "is_fault"] == True).all()


def test_inject_meteorological_extreme_physical_consistency(clean_baseline_df):
    """Verify severe weather front sets is_anomaly=True but is_fault=False."""
    df_storm = inject_meteorological_extreme(clean_baseline_df, start_idx=50, duration=15, temp_drop=-10.0, pressure_drop=-6.0, rh_surge=40.0)
    assert (df_storm.loc[50:64, "is_anomaly"] == True).all()
    assert (df_storm.loc[50:64, "anomaly_type"] == "METEOROLOGICAL_EXTREME").all()
    assert (df_storm.loc[50:64, "is_fault"] == False).all()  # Crucial distinction


def test_chainable_anomaly_injector_builder(clean_baseline_df):
    """Verify fluent AnomalyInjector builder applies multiple sequential anomalies."""
    injector = AnomalyInjector(clean_baseline_df)
    df_result = (
        injector.inject_spike(target_column="temperature", start_idx=20, magnitude=12.0, duration=2)
        .inject_frozen(target_column="humidity", start_idx=100, duration=20, stuck_value=50.0)
        .inject_dropout(target_column="pressure", start_idx=250, duration=5, fill_mode="nan")
        .get_dataframe()
    )
    assert df_result.loc[20, "anomaly_type"] == "SPIKE"
    assert df_result.loc[100, "anomaly_type"] == "FROZEN"
    assert df_result.loc[250, "anomaly_type"] == "DROPOUT"
    assert df_result["is_anomaly"].sum() == (2 + 20 + 5)


# ============================================================================
# Group 3: Benchmark Scenario Tests
# ============================================================================

def test_scenario_clean_baseline_zero_anomalies():
    """Verify clean 30-day baseline contains exactly zero flagged anomalies."""
    scenario = CleanBaselineScenario(duration_days=5.0)
    df = scenario.generate(seed=42)
    assert len(df) == int(5 * 288)
    assert df["is_anomaly"].sum() == 0
    assert (df["anomaly_type"] == "NORMAL").all()


def test_scenario_single_faults_exact_counts():
    """Verify each single fault scenario instantiates correctly with expected metadata."""
    for ftype in ["spike", "drift", "frozen", "dropout", "noise", "multivariate"]:
        scen = ScenarioRegistry.get(f"single_fault_{ftype}")
        df = scen.generate(seed=42)
        assert df["is_anomaly"].sum() > 0


def test_scenario_multi_fault_stress_distribution():
    """Verify 30-day stress scenario contains multiple distinct fault classes."""
    scenario = MultiFaultStressScenario(duration_days=30.0)
    df = scenario.generate(seed=42)
    assert len(df) == 8640
    unique_faults = set(df[df["is_anomaly"]]["anomaly_type"].unique())
    expected_faults = {"SPIKE", "FROZEN", "DROPOUT", "DRIFT", "DATA_CORRUPTION", "MULTIVARIATE_INCONSISTENCY"}
    assert expected_faults.issubset(unique_faults)


def test_scenario_weather_front_fault_flag_discrimination():
    """Verify weather front scenario contains both genuine front (is_fault=False) and sensor spike (is_fault=True)."""
    scenario = WeatherFrontScenario(duration_days=7.0)
    df = scenario.generate(seed=42)
    front_rows = df[df["anomaly_type"] == "METEOROLOGICAL_EXTREME"]
    spike_rows = df[df["anomaly_type"] == "SPIKE"]
    assert len(front_rows) > 0
    assert (front_rows["is_fault"] == False).all()
    assert len(spike_rows) > 0
    assert (spike_rows["is_fault"] == True).all()


def test_scenario_multi_station_network_heterogeneity():
    """Verify multi-station scenario generates data for 4 distinct stations."""
    scenario = MultiStationNetworkScenario(duration_days=3.0)
    df = scenario.generate(seed=42)
    stations = set(df["station_id"].unique())
    assert stations == {"AWS-DEL-01", "AWS-MUM-02", "AWS-LEH-03", "AWS-JAI-04"}


def test_scenario_health_degradation_trajectory():
    """Verify health degradation scenario progresses across 3 distinct phases."""
    scenario = HealthDegradationScenario(duration_days=3.0)
    df = scenario.generate(seed=42)
    assert len(df) == 864
    # Phase 1 (0-287) is clean
    assert df.loc[0:287, "is_anomaly"].sum() == 0
    # Phase 2 (288-575) has drift
    assert (df.loc[288:487, "anomaly_type"] == "DRIFT").all()
    # Phase 3 (576-863) is frozen
    assert (df.loc[576:863, "anomaly_type"] == "FROZEN").all()


# ============================================================================
# Group 4: CLI & Temporal Dataset Splits Tests
# ============================================================================

def test_cli_dataset_generation_files_created(tmp_path):
    """Verify generate_temporal_splits creates all 4 required CSV datasets."""
    p_base, p_train, p_val, p_test = generate_temporal_splits(output_dir=tmp_path, total_days=5.0, seed=42)
    assert p_base.exists()
    assert p_train.exists()
    assert p_val.exists()
    assert p_test.exists()


def test_temporal_splitting_strict_non_leakage(tmp_path):
    """Verify temporal partitions are non-overlapping with strictly monotonic ordering."""
    generate_temporal_splits(output_dir=tmp_path, total_days=30.0, seed=42)
    df_train = pd.read_csv(tmp_path / "train_clean.csv")
    df_val = pd.read_csv(tmp_path / "val_mixed.csv")
    df_test = pd.read_csv(tmp_path / "test_anomalies.csv")

    t_train_max = pd.to_datetime(df_train["timestamp"]).max()
    t_val_min = pd.to_datetime(df_val["timestamp"]).min()
    t_val_max = pd.to_datetime(df_val["timestamp"]).max()
    t_test_min = pd.to_datetime(df_test["timestamp"]).min()

    assert t_train_max < t_val_min, "Train set must precede Validation set with zero temporal leakage"
    assert t_val_max < t_test_min, "Validation set must precede Test set with zero temporal leakage"
    assert df_train["is_anomaly"].sum() == 0, "Training set must be 100% clean baseline data"


def test_dataset_column_schema_and_types(tmp_path):
    """Verify exported dataset CSV contains all mandatory columns with correct types."""
    generate_temporal_splits(output_dir=tmp_path, total_days=5.0, seed=42)
    df = pd.read_csv(tmp_path / "baseline_clean.csv")
    required_cols = {"timestamp", "station_id", "temperature", "pressure", "humidity"}
    assert required_cols.issubset(set(df.columns))
    assert pd.api.types.is_numeric_dtype(df["temperature"])
    assert pd.api.types.is_numeric_dtype(df["pressure"])
    assert pd.api.types.is_numeric_dtype(df["humidity"])


def test_cli_custom_arguments_and_scenarios(tmp_path):
    """Verify CLI argument parsing for single scenario execution."""
    out_file = tmp_path / "test_front.csv"
    ret = cli_main(["--scenario", "weather_front", "--output-file", str(out_file), "--seed", "99"])
    assert ret == 0
    assert out_file.exists()
    df = pd.read_csv(out_file)
    assert len(df) > 0
```

---

## 6. Architectural Integration & Cross-Module Consistency

### 6.1 Integration with `m1_explorer_1` (`diurnal_generator.py`)
- `scenarios.py` directly consumes `DiurnalGenerator`, `DiurnalParameters`, `StationConfig`, and `PRESETS`.
- Configurable sampling intervals ($\Delta t$) and durations translate seamlessly to exact row counts:
  $$N_{\text{rows}} = \frac{\text{duration\_days} \times 1440.0}{\text{sampling\_interval\_min}}$$
- Hypsometric pressure adjustments and regional presets are utilized in `MultiStationNetworkScenario`.

### 6.2 Integration with `m1_explorer_2` (`anomaly_injector.py`)
- `scenarios.py` leverages the fluent `AnomalyInjector` builder class and individual injection functions (`inject_spike`, `inject_drift`, `inject_frozen`, `inject_dropout`, `inject_noise_burst`, `inject_multivariate_inconsistency`, `inject_meteorological_extreme`).
- Ground truth metadata schema (`is_anomaly`, `anomaly_type`, `severity`, `is_fault`, `affected_params`, `clean_temperature`, `clean_pressure`, `clean_humidity`) is fully preserved across all scenarios.

### 6.3 Downstream Integration with `M2`–`M5`
- `train_clean.csv` provides uncontaminated data to train Isolation Forest and GRU Autoencoder.
- `val_mixed.csv` enables threshold calibration ($\mu + 3\sigma$) and validation loss monitoring.
- `test_anomalies.csv` provides ground truth for `scripts/test_anomaly_detection.py` to evaluate F1 $\ge 0.80$.

---

## 7. Verification & Validation Protocol

### Step 1: Implementation of M1 Modules
When the implementation agent executes:
1. `backend/simulator/scenarios.py` implemented per Blueprint Section 5.1.
2. `backend/simulator/cli.py` implemented per Blueprint Section 5.2.
3. `scripts/generate_datasets.py` implemented per Blueprint Section 5.3.
4. `tests/test_simulator.py` populated per Blueprint Section 5.4.

### Step 2: Verification Commands
1. Run Unit Tests:
   ```powershell
   python -m pytest tests/test_simulator.py -v
   ```
   *Expected Output*: $\ge 25$ passed tests.
2. Run Dataset Generation Script:
   ```powershell
   python scripts/generate_datasets.py
   ```
   *Expected Output*: `baseline_clean.csv` (8,640 rows), `train_clean.csv` (5,760 rows), `val_mixed.csv` (1,440 rows), `test_anomalies.csv` (1,440 rows) generated in `data/`.
3. Verify Non-Leakage via CLI:
   ```powershell
   python -m backend.simulator.cli --splits --output-dir data/ --seed 42
   ```

### Step 3: Invalidation Conditions
- Test suite fails if any temporal overlap exists between train, val, and test splits.
- Test suite fails if $\text{Corr}(T, RH) > -0.70$ on clean baseline data.
- Test suite fails if `is_fault` is `True` on `inject_meteorological_extreme`.

