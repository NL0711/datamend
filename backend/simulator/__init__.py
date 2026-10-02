"""SkyGuard AI Weather Simulator Package."""

from backend.simulator.anomaly_injector import (
    AnomalyInjector,
    AnomalyType,
    Severity,
    inject_data_corruption,
    inject_drift,
    inject_dropout,
    inject_frozen,
    inject_meteorological_extreme,
    inject_multivariate_inconsistency,
    inject_noise_burst,
    inject_spike,
)
from backend.simulator.cli import export_dataframe, generate_temporal_splits
from backend.simulator.diurnal_generator import (
    PRESETS,
    DiurnalGenerator,
    DiurnalParameters,
    StationConfig,
    generate_diurnal_data,
)
from backend.simulator.scenarios import (
    BenchmarkScenario,
    CleanBaselineScenario,
    HealthDegradationScenario,
    MultiFaultStressScenario,
    MultiStationNetworkScenario,
    ScenarioMetadata,
    ScenarioRegistry,
    SingleFaultScenario,
    WeatherFrontScenario,
)

__all__ = [
    "DiurnalGenerator",
    "DiurnalParameters",
    "StationConfig",
    "PRESETS",
    "generate_diurnal_data",
    "AnomalyInjector",
    "AnomalyType",
    "Severity",
    "inject_spike",
    "inject_drift",
    "inject_frozen",
    "inject_dropout",
    "inject_noise_burst",
    "inject_multivariate_inconsistency",
    "inject_meteorological_extreme",
    "inject_data_corruption",
    "BenchmarkScenario",
    "CleanBaselineScenario",
    "SingleFaultScenario",
    "MultiFaultStressScenario",
    "WeatherFrontScenario",
    "MultiStationNetworkScenario",
    "HealthDegradationScenario",
    "ScenarioRegistry",
    "ScenarioMetadata",
    "generate_temporal_splits",
    "export_dataframe",
]

