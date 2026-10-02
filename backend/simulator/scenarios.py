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

    def __init__(
        self,
        duration_days: float = 30.0,
        sampling_interval_min: float = 5.0,
        station_id: str = "AWS-001",
    ) -> None:
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
            seed=seed,
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


FAULT_DURATIONS: Dict[str, int] = {
    "spike": 2,
    "drift": 80,
    "frozen": 72,
    "dropout": 24,
    "noise": 36,
    "noise_burst": 36,
    "multivariate": 24,
}


class SingleFaultScenario(BenchmarkScenario):
    """Scenario isolating a single specific fault class with dynamic length scaling."""

    def __init__(
        self,
        fault_type: str = "spike",
        duration_days: float = 7.0,
        sampling_interval_min: float = 5.0,
    ) -> None:
        self.fault_type = fault_type.lower()
        self.name = f"single_fault_{self.fault_type}"
        self.description = f"{duration_days:g}-day scenario containing an isolated {self.fault_type.upper()} fault."
        self.duration_days = duration_days
        self.sampling_interval_min = sampling_interval_min

    def generate(self, seed: Optional[int] = 42) -> pd.DataFrame:
        generator = DiurnalGenerator(seed=seed)
        clean_df = generator.generate(
            start_date="2026-08-01 00:00:00",
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            seed=seed,
        )
        injector = AnomalyInjector(clean_df)
        n_rows = len(clean_df)

        nominal_dur = FAULT_DURATIONS.get(self.fault_type, 24)
        dur = min(nominal_dur, max(1, n_rows // 3))
        start_idx = min(int(n_rows * 0.35), max(0, n_rows - dur))

        if self.fault_type == "spike":
            dur = min(2, max(1, n_rows))
            start_idx = min(int(n_rows * 0.35), max(0, n_rows - dur))
            injector.inject_spike(
                target_column="temperature", start_idx=start_idx, magnitude=16.0, duration=dur, severity="CRITICAL", random_seed=seed
            )
        elif self.fault_type == "drift":
            injector.inject_drift(
                target_column="temperature", start_idx=start_idx, duration=dur, drift_rate=0.10, max_drift=8.0, severity="HIGH", random_seed=seed
            )
        elif self.fault_type == "frozen":
            injector.inject_frozen(
                target_column="temperature", start_idx=start_idx, duration=dur, stuck_value=24.5, severity="HIGH", random_seed=seed
            )
        elif self.fault_type == "dropout":
            injector.inject_dropout(
                target_column="humidity", start_idx=start_idx, duration=dur, fill_mode="nan", severity="CRITICAL", random_seed=seed
            )
        elif self.fault_type in ["noise", "noise_burst"]:
            injector.inject_noise_burst(
                target_column="pressure", start_idx=start_idx, duration=dur, noise_factor=8.0, severity="MEDIUM", random_seed=seed
            )
        elif self.fault_type == "multivariate":
            injector.inject_multivariate_inconsistency(
                start_idx=start_idx, duration=dur, temp_shift=15.0, rh_shift=40.0, severity="HIGH", random_seed=seed
            )
        else:
            raise ValueError(f"Unknown single fault type: {self.fault_type}")

        return injector.get_dataframe()

    def get_metadata(self) -> ScenarioMetadata:
        n_rows = int(round(self.duration_days * (1440.0 / self.sampling_interval_min)))
        nominal_dur = FAULT_DURATIONS.get(self.fault_type, 24)
        if self.fault_type == "spike":
            expected_count = min(2, max(1, n_rows))
        else:
            expected_count = min(nominal_dur, max(1, n_rows // 3))

        return ScenarioMetadata(
            name=self.name,
            description=self.description,
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            station_count=1,
            expected_anomaly_count=expected_count,
            fault_types_included=[self.fault_type.upper()],
            target_milestone="M1-M2",
        )


class MultiFaultStressScenario(BenchmarkScenario):
    """30-day realistic stress scenario with mixed, non-overlapping and compound faults."""
    name = "multi_fault_stress"
    description = "30-day evaluation scenario containing a realistic sequence of all 6 fault classes."

    def __init__(
        self,
        duration_days: float = 30.0,
        sampling_interval_min: float = 5.0,
    ) -> None:
        self.duration_days = duration_days
        self.sampling_interval_min = sampling_interval_min

    def generate(self, seed: Optional[int] = 42) -> pd.DataFrame:
        generator = DiurnalGenerator(seed=seed)
        clean_df = generator.generate(
            start_date="2026-08-01 00:00:00",
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            seed=seed,
        )
        injector = AnomalyInjector(clean_df)

        # Scale indices proportionally if duration is customized
        scale = self.duration_days / 30.0
        n_rows = len(clean_df)

        # Day 2: Transient temperature spike
        s1 = min(int(576 * scale), n_rows - 2)
        injector.inject_spike(target_column="temperature", start_idx=s1, magnitude=18.0, duration=2, severity="CRITICAL", random_seed=seed)

        # Day 5: Frozen humidity sensor
        s2 = min(int(1440 * scale), n_rows - 60)
        injector.inject_frozen(target_column="humidity", start_idx=s2, duration=60, stuck_value=62.0, severity="HIGH", random_seed=seed)

        # Day 9: Complete station telemetry dropout
        s3 = min(int(2592 * scale), n_rows - 12)
        injector.inject_dropout(target_column="all", start_idx=s3, duration=12, fill_mode="nan", severity="CRITICAL", random_seed=seed)

        # Day 14: Progressive linear calibration drift in temperature
        s4 = min(int(4032 * scale), n_rows - 100)
        injector.inject_drift(target_column="temperature", start_idx=s4, duration=100, drift_rate=0.08, max_drift=8.0, severity="HIGH", random_seed=seed)

        # Day 19: High-frequency pressure noise burst
        s5 = min(int(5472 * scale), n_rows - 48)
        injector.inject_noise_burst(target_column="pressure", start_idx=s5, duration=48, noise_factor=10.0, severity="MEDIUM", random_seed=seed)

        # Day 23: Thermodynamic multivariate inconsistency
        s6 = min(int(6624 * scale), n_rows - 30)
        injector.inject_multivariate_inconsistency(start_idx=s6, duration=30, temp_shift=14.0, rh_shift=45.0, severity="HIGH", random_seed=seed)

        # Day 26 (Test Partition): Thermal Spike + Stuck/Frozen Sensor
        s7 = min(int(7488 * scale), n_rows - 35)
        injector.inject_spike(target_column="temperature", start_idx=s7, magnitude=22.0, duration=3, severity="CRITICAL", random_seed=seed)
        injector.inject_frozen(target_column="temperature", start_idx=s7 + 10, duration=25, stuck_value=24.5, severity="HIGH", random_seed=seed)

        # Day 27 (Test Partition): Compound pressure drop followed by dropout
        s8 = min(int(7776 * scale), n_rows - 30)
        injector.inject_spike(target_column="pressure", start_idx=s8, magnitude=-35.0, duration=2, severity="CRITICAL", random_seed=seed)
        injector.inject_dropout(target_column="humidity", start_idx=s8 + 4, duration=24, fill_mode="nan", severity="HIGH", random_seed=seed)

        # Day 28 (Test Partition): Multivariate inconsistency
        s9 = min(int(8064 * scale), n_rows - 30)
        injector.inject_multivariate_inconsistency(start_idx=s9, duration=28, temp_shift=15.0, rh_shift=50.0, severity="HIGH", random_seed=seed)

        # Day 29 (Test Partition): Progressive Temperature Calibration Drift
        s10 = min(int(8352 * scale), n_rows - 40)
        injector.inject_drift(target_column="temperature", start_idx=s10, duration=40, drift_rate=0.15, max_drift=6.0, severity="HIGH", random_seed=seed)

        return injector.get_dataframe()

    def get_metadata(self) -> ScenarioMetadata:
        return ScenarioMetadata(
            name=self.name,
            description=self.description,
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            station_count=1,
            expected_anomaly_count=271,
            fault_types_included=["SPIKE", "FROZEN", "DROPOUT", "DRIFT", "NOISE_BURST", "MULTIVARIATE_INCONSISTENCY"],
            target_milestone="M1-M5",
        )


class WeatherFrontScenario(BenchmarkScenario):
    """Scenario with a genuine convective storm squall followed by an unphysical sensor fault."""
    name = "weather_front"
    description = "Meteorological front scenario verifying discrimination between genuine storms and faults."

    def __init__(
        self,
        duration_days: float = 7.0,
        sampling_interval_min: float = 5.0,
    ) -> None:
        self.duration_days = duration_days
        self.sampling_interval_min = sampling_interval_min

    def generate(self, seed: Optional[int] = 42) -> pd.DataFrame:
        generator = DiurnalGenerator(seed=seed)
        clean_df = generator.generate(
            start_date="2026-08-01 00:00:00",
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            seed=seed,
        )
        injector = AnomalyInjector(clean_df)
        n_rows = len(clean_df)

        # Proportional placement across duration
        front_dur = min(24, max(4, int(n_rows * 0.05)))
        s1 = min(int(n_rows * 0.40), max(0, n_rows - front_dur))

        spike_dur = min(2, max(1, n_rows))
        s2 = min(int(n_rows * 0.70), max(0, n_rows - spike_dur))

        # Genuine convective thunderstorm squall line (is_fault=False)
        injector.inject_meteorological_extreme(
            start_idx=s1,
            duration=front_dur,
            temp_drop=-9.5,
            pressure_drop=-6.5,
            rh_surge=35.0,
            severity="HIGH",
            random_seed=seed,
        )

        # Hardware sensor spike (is_fault=True)
        injector.inject_spike(
            target_column="temperature",
            start_idx=s2,
            magnitude=22.0,
            duration=spike_dur,
            severity="CRITICAL",
            random_seed=seed,
        )

        return injector.get_dataframe()

    def get_metadata(self) -> ScenarioMetadata:
        n_rows = int(round(self.duration_days * (1440.0 / self.sampling_interval_min)))
        front_dur = min(24, max(4, int(n_rows * 0.05)))
        spike_dur = min(2, max(1, n_rows))
        return ScenarioMetadata(
            name=self.name,
            description=self.description,
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            station_count=1,
            expected_anomaly_count=front_dur + spike_dur,
            fault_types_included=["METEOROLOGICAL_EXTREME", "SPIKE"],
            target_milestone="M2-M4",
        )


class MultiStationNetworkScenario(BenchmarkScenario):
    """Scenario simulating a regional network of 4 distinct AWS stations with microclimates."""
    name = "multi_station"
    description = "Multi-station network simulation across 4 distinct microclimates."

    def __init__(
        self,
        duration_days: float = 7.0,
        sampling_interval_min: float = 5.0,
    ) -> None:
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
                seed=s_seed,
            )
            inj = AnomalyInjector(raw_df)
            n_rows = len(raw_df)

            if s_id == "AWS-DEL-01":
                spike_dur = min(2, max(1, n_rows))
                s = min(int(n_rows * 0.40), max(0, n_rows - spike_dur))
                inj.inject_spike(target_column="temperature", start_idx=s, magnitude=15.0, duration=spike_dur, severity="CRITICAL", random_seed=s_seed)
            elif s_id == "AWS-MUM-02":
                drift_dur = min(120, max(10, int(n_rows * 0.15)))
                s = min(int(n_rows * 0.50), max(0, n_rows - drift_dur))
                inj.inject_drift(target_column="humidity", start_idx=s, duration=drift_dur, drift_rate=0.08, max_drift=10.0, severity="HIGH", random_seed=s_seed)
            elif s_id == "AWS-LEH-03":
                frozen_dur = min(96, max(10, int(n_rows * 0.12)))
                s = min(int(n_rows * 0.30), max(0, n_rows - frozen_dur))
                inj.inject_frozen(target_column="temperature", start_idx=s, duration=frozen_dur, stuck_value=-8.5, severity="HIGH", random_seed=s_seed)
            elif s_id == "AWS-JAI-04":
                noise_dur = min(48, max(10, int(n_rows * 0.08)))
                s = min(int(n_rows * 0.60), max(0, n_rows - noise_dur))
                inj.inject_noise_burst(target_column="pressure", start_idx=s, duration=noise_dur, noise_factor=8.0, severity="MEDIUM", random_seed=s_seed)

            dfs.append(inj.get_dataframe())

        combined_df = pd.concat(dfs, ignore_index=True)
        return combined_df.sort_values(by=["timestamp", "station_id"]).reset_index(drop=True)

    def get_metadata(self) -> ScenarioMetadata:
        n_rows = int(round(self.duration_days * (1440.0 / self.sampling_interval_min)))
        spike_dur = min(2, max(1, n_rows))
        drift_dur = min(120, max(10, int(n_rows * 0.15)))
        frozen_dur = min(96, max(10, int(n_rows * 0.12)))
        noise_dur = min(48, max(10, int(n_rows * 0.08)))
        expected_count = spike_dur + drift_dur + frozen_dur + noise_dur
        return ScenarioMetadata(
            name=self.name,
            description=self.description,
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            station_count=4,
            expected_anomaly_count=expected_count,
            fault_types_included=["SPIKE", "DRIFT", "FROZEN", "NOISE_BURST"],
            target_milestone="M3-M4",
        )


class HealthDegradationScenario(BenchmarkScenario):
    """Scenario modeling progressive hardware sensor failure over 3 stages."""
    name = "health_degradation"
    description = "Lifecycle scenario demonstrating progressive sensor health decay across 3 stages."

    def __init__(
        self,
        duration_days: float = 3.0,
        sampling_interval_min: float = 5.0,
    ) -> None:
        self.duration_days = duration_days
        self.sampling_interval_min = sampling_interval_min

    def generate(self, seed: Optional[int] = 42) -> pd.DataFrame:
        generator = DiurnalGenerator(seed=seed)
        clean_df = generator.generate(
            start_date="2026-08-01 00:00:00",
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            seed=seed,
        )
        injector = AnomalyInjector(clean_df)
        n_rows = len(clean_df)

        # Proportional 3-phase partition: Phase 1 (0-1/3), Phase 2 (1/3-2/3), Phase 3 (2/3-end)
        p2_start = int(n_rows * (1.0 / 3.0))
        p3_start = int(n_rows * (2.0 / 3.0))

        p2_dur = min(200, max(10, p3_start - p2_start))
        spike_start = min(p2_start + int(p2_dur * 0.81), max(p2_start, p3_start - 2))
        spike_dur = min(2, max(1, p3_start - spike_start))
        p3_dur = n_rows - p3_start

        # Phase 2 (Steps p2_start to p2_start + p2_dur): Linear drift + intermittent jitter
        injector.inject_drift(
            target_column="temperature",
            start_idx=p2_start,
            duration=p2_dur,
            drift_rate=0.04,
            max_drift=5.0,
            severity="MEDIUM",
            random_seed=seed,
        )
        injector.inject_spike(
            target_column="temperature",
            start_idx=spike_start,
            magnitude=8.0,
            duration=spike_dur,
            severity="HIGH",
            random_seed=seed,
        )

        # Phase 3 (Steps p3_start to end): Permanent frozen sensor failure
        injector.inject_frozen(
            target_column="temperature",
            start_idx=p3_start,
            duration=p3_dur,
            stuck_value=31.2,
            severity="CRITICAL",
            random_seed=seed,
        )

        return injector.get_dataframe()

    def get_metadata(self) -> ScenarioMetadata:
        n_rows = int(round(self.duration_days * (1440.0 / self.sampling_interval_min)))
        p2_start = int(n_rows * (1.0 / 3.0))
        p3_start = int(n_rows * (2.0 / 3.0))
        p2_dur = min(200, max(10, p3_start - p2_start))
        p3_dur = n_rows - p3_start
        # Total unique anomalous steps = p2_dur + p3_dur (spike is contained within p2_dur)
        expected_count = p2_dur + p3_dur
        return ScenarioMetadata(
            name=self.name,
            description=self.description,
            duration_days=self.duration_days,
            sampling_interval_min=self.sampling_interval_min,
            station_count=1,
            expected_anomaly_count=expected_count,
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
        "single_fault_noise_burst": lambda: SingleFaultScenario("noise_burst"),
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
        return [cls.get(name).get_metadata() for name in cls._registry.keys() if name != "single_fault_noise_burst"]

    @classmethod
    def run_scenario(cls, name: str, seed: Optional[int] = 42) -> pd.DataFrame:
        return cls.get(name).generate(seed=seed)

