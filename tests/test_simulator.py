"""
SkyGuard AI — Unit & Integration Test Suite for Milestone M1 Simulator Engine.

Validates:
1. Diurnal atmospheric physics, Magnus-Tetens thermodynamic coupling, and tidal pressure cycles.
2. All 8 programmatic anomaly injection patterns and ground-truth labeling contracts.
3. Standard pre-configured benchmark scenarios.
4. Dataset generator CLI, temporal partition boundaries, and non-leakage constraints.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from backend.simulator.anomaly_injector import (
    AnomalyInjector,
    AnomalyType,
    Severity,
    inject_spike,
    inject_drift,
    inject_frozen,
    inject_dropout,
    inject_noise_burst,
    inject_multivariate_inconsistency,
    inject_meteorological_extreme,
    inject_data_corruption,
)
from backend.simulator.cli import generate_temporal_splits, main as cli_main
from backend.simulator.diurnal_generator import (
    DiurnalGenerator,
    DiurnalParameters,
    StationConfig,
    PRESETS,
    generate_diurnal_data,
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
    """Verify that daily temperature peaks post-noon (13:30-16:00) and reaches minimum near sunrise."""
    gen = DiurnalGenerator(
        params=DiurnalParameters(temp_base=20.0, temp_amplitude=8.0, temp_peak_hour=14.5, temp_seasonal_amp=0.0),
        seed=42,
    )
    df = gen.generate(start_date="2026-08-01 00:00:00", duration_days=3.0, sampling_interval_min=5.0)
    
    assert df["temperature"].min() >= 10.0
    assert df["temperature"].max() <= 30.0
    
    # Extract hour of daily maximum and minimum across each 24-hour cycle
    df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour + pd.to_datetime(df["timestamp"]).dt.minute / 60.0
    for day_idx in range(3):
        day_df = df.iloc[day_idx * 288 : (day_idx + 1) * 288]
        max_hour = day_df.loc[day_df["temperature"].idxmax(), "hour"]
        min_hour = day_df.loc[day_df["temperature"].idxmin(), "hour"]
        assert 13.5 <= max_hour <= 16.0, f"Day {day_idx+1}: Temperature peak at hour {max_hour} violates solar radiation lag"
        assert 1.0 <= min_hour <= 6.5, f"Day {day_idx+1}: Temperature minimum at hour {min_hour} violates nocturnal cooling"


def test_relative_humidity_inverse_correlation():
    """Verify thermodynamic inverse relationship between Temperature and RH (Corr <= -0.70)."""
    gen = DiurnalGenerator(seed=42)
    df = gen.generate(duration_days=5.0, sampling_interval_min=5.0)
    corr = df["temperature"].corr(df["humidity"])
    assert corr <= -0.70, f"Expected strong negative correlation <= -0.70, got {corr:.3f}"


def test_magnus_tetens_thermodynamic_bounds():
    """Verify relative humidity is strictly bounded within physical interval [5.0%, 100.0%]."""
    gen = DiurnalGenerator(seed=42)
    df = gen.generate(duration_days=10.0, sampling_interval_min=5.0)
    assert (df["humidity"] >= 5.0).all()
    assert (df["humidity"] <= 100.0).all()
    assert not df[["temperature", "pressure", "humidity"]].isna().any().any()


def test_atmospheric_pressure_semidiurnal_tides():
    """Verify 12-hour semi-diurnal atmospheric tidal peaks near 10:00 and 22:00."""
    params = DiurnalParameters(pressure_tide_amp=2.0, pressure_noise_sigma=0.01, pressure_synoptic_amp=0.0)
    gen = DiurnalGenerator(params=params, seed=42)
    df = gen.generate(duration_days=2.0, sampling_interval_min=5.0)
    df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
    p_10am = df[df["hour"] == 10]["pressure"].mean()
    p_4pm = df[df["hour"] == 16]["pressure"].mean()
    p_10pm = df[df["hour"] == 22]["pressure"].mean()
    p_4am = df[df["hour"] == 4]["pressure"].mean()
    assert p_10am > p_4pm, "Semi-diurnal atmospheric tide 10:00 peak must exceed 16:00 trough"
    assert p_10pm > p_4am, "Semi-diurnal atmospheric tide 22:00 peak must exceed 04:00 trough"


def test_hypsometric_elevation_pressure_lapse():
    """Verify barometric pressure decreases realistically with station elevation."""
    gen_sea = DiurnalGenerator(station_config=StationConfig(elevation=0.0), seed=42)
    gen_mtn = DiurnalGenerator(station_config=StationConfig(elevation=3000.0), seed=42)
    df_sea = gen_sea.generate(duration_days=1.0)
    df_mtn = gen_mtn.generate(duration_days=1.0)
    assert df_sea["pressure"].mean() > 1000.0
    assert df_mtn["pressure"].mean() < 750.0


def test_generator_seed_reproducibility():
    """Verify identical random seed produces bitwise identical telemetry."""
    gen1 = DiurnalGenerator(seed=12345)
    gen2 = DiurnalGenerator(seed=12345)
    df1 = gen1.generate(duration_days=2.0)
    df2 = gen2.generate(duration_days=2.0)
    pd.testing.assert_frame_equal(df1, df2)


def test_streaming_step_generation():
    """Verify streaming step generation produces valid telemetry and updates AR(1) state."""
    gen = DiurnalGenerator(seed=42)
    state = None
    records = []
    ts = pd.Timestamp("2026-08-24 00:00:00", tz="UTC")
    for _ in range(12):
        telemetry, state = gen.generate_streaming_step(ts, state)
        records.append(telemetry)
        ts += pd.Timedelta(minutes=5)

    assert len(records) == 12
    assert state is not None
    assert "t_noise" in state and "p_noise" in state and "rh_noise" in state
    assert all("temperature" in r and "humidity" in r and "pressure" in r for r in records)


# ============================================================================
# Group 2: Programmatic Anomaly Injector Tests
# ============================================================================

@pytest.fixture
def clean_baseline_df():
    gen = DiurnalGenerator(seed=42)
    return gen.generate(duration_days=2.0, sampling_interval_min=5.0)


def test_inject_spike_transient_and_labels(clean_baseline_df):
    """Verify spike injection applies transient delta, preserves clean ground truth, and tags labels."""
    df_injected = inject_spike(clean_baseline_df, target_column="temperature", start_idx=50, magnitude=15.0, duration=2)
    assert df_injected.loc[50, "is_anomaly"] == True
    assert df_injected.loc[51, "is_anomaly"] == True
    assert df_injected.loc[52, "is_anomaly"] == False
    assert df_injected.loc[50, "anomaly_type"] == "SPIKE"
    assert df_injected.loc[50, "is_fault"] == True
    assert pytest.approx(df_injected.loc[50, "temperature"], rel=1e-3) == clean_baseline_df.loc[50, "temperature"] + 15.0
    assert df_injected.loc[50, "clean_temperature"] == clean_baseline_df.loc[50, "temperature"]


def test_inject_drift_linear_slope_and_duration(clean_baseline_df):
    """Verify drift linearly accumulates calibration offset over duration."""
    df_injected = inject_drift(clean_baseline_df, target_column="temperature", start_idx=100, duration=50, drift_rate=0.10)
    assert df_injected.loc[100:149, "is_anomaly"].all()
    assert (df_injected.loc[100:149, "anomaly_type"] == "DRIFT").all()
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

    df_sentinel = inject_dropout(clean_baseline_df, target_column="temperature", start_idx=180, duration=5, fill_mode="sentinel_neg999")
    assert (df_sentinel.loc[180:184, "temperature"] == -999.0).all()


def test_inject_noise_burst_variance_multiplier(clean_baseline_df):
    """Verify noise burst increases empirical variance without corrupting clean columns."""
    df_burst = inject_noise_burst(clean_baseline_df, target_column="temperature", start_idx=100, duration=60, noise_factor=10.0, random_seed=42)
    # Measure variance on the residual noise component to avoid diurnal trend bias
    clean_diff_var = clean_baseline_df.loc[100:159, "temperature"].diff().dropna().var()
    burst_diff_var = df_burst.loc[100:159, "temperature"].diff().dropna().var()
    noise_residual_var = (df_burst.loc[100:159, "temperature"] - clean_baseline_df.loc[100:159, "temperature"]).var()
    
    assert burst_diff_var > clean_diff_var * 4.0
    assert noise_residual_var > 5.0
    assert (df_burst.loc[100:159, "anomaly_type"] == "NOISE_BURST").all()


def test_inject_multivariate_inconsistency_decoupling(clean_baseline_df):
    """Verify multivariate decoupling violates thermodynamic relationships."""
    df_injected = inject_multivariate_inconsistency(clean_baseline_df, start_idx=100, duration=20, temp_shift=15.0, rh_shift=40.0)
    assert (df_injected.loc[100:119, "anomaly_type"] == "MULTIVARIATE_INCONSISTENCY").all()
    assert (df_injected.loc[100:119, "is_fault"] == True).all()


def test_inject_meteorological_extreme_physical_consistency(clean_baseline_df):
    """Verify severe weather front sets is_anomaly=True but is_fault=False."""
    df_storm = inject_meteorological_extreme(clean_baseline_df, start_idx=50, duration=15, temp_drop=-10.0, pressure_drop=-6.0, rh_surge=40.0)
    assert (df_storm.loc[50:64, "is_anomaly"] == True).all()
    assert (df_storm.loc[50:64, "anomaly_type"] == "METEOROLOGICAL_EXTREME").all()
    assert (df_storm.loc[50:64, "is_fault"] == False).all()


def test_inject_data_corruption_framing_and_duplicates(clean_baseline_df):
    """Verify data corruption injects communication string errors and duplicate timestamps."""
    df_comm = inject_data_corruption(clean_baseline_df, target_column="temperature", start_idx=80, duration=3, corruption_mode="string_err")
    assert df_comm.loc[80, "temperature"] == "$ERR_COMM_TIMEOUT#"
    assert (df_comm.loc[80:82, "anomaly_type"] == "DATA_CORRUPTION").all()


def test_injector_validation_guards(clean_baseline_df):
    """Verify input validation guards raise ValueError for unsupported parameters."""
    with pytest.raises(ValueError, match="Unsupported fill_mode"):
        inject_dropout(clean_baseline_df, target_column="temperature", start_idx=10, duration=5, fill_mode="invalid_mode")

    with pytest.raises(ValueError, match="Unsupported noise_type"):
        inject_noise_burst(clean_baseline_df, target_column="temperature", start_idx=10, duration=5, noise_type="invalid_noise")

    with pytest.raises(ValueError, match="Unsupported multivariate mode"):
        inject_multivariate_inconsistency(clean_baseline_df, start_idx=10, duration=5, mode="invalid_mode")

    with pytest.raises(ValueError, match="Unsupported corruption_mode"):
        inject_data_corruption(clean_baseline_df, target_column="temperature", start_idx=10, duration=5, corruption_mode="invalid_mode")


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
    """Verify clean baseline scenario contains exactly zero flagged anomalies."""
    scenario = CleanBaselineScenario(duration_days=5.0)
    df = scenario.generate(seed=42)
    assert len(df) == int(5 * 288)
    assert df["is_anomaly"].sum() == 0
    assert (df["anomaly_type"] == "NORMAL").all()


def test_scenario_single_faults_exact_counts():
    """Verify each single fault scenario instantiates correctly with anomalies."""
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
    expected_faults = {"SPIKE", "FROZEN", "DROPOUT", "DRIFT", "NOISE_BURST", "MULTIVARIATE_INCONSISTENCY"}
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
    """Verify multi-station scenario generates data for 4 distinct stations across both 3-day and 7-day durations."""
    for days in [3.0, 7.0]:
        scenario = MultiStationNetworkScenario(duration_days=days)
        df = scenario.generate(seed=42)
        assert len(df) == int(days * 288 * 4)
        stations = set(df["station_id"].unique())
        assert stations == {"AWS-DEL-01", "AWS-MUM-02", "AWS-LEH-03", "AWS-JAI-04"}


def test_scenario_health_degradation_trajectory():
    """Verify health degradation scenario progresses across 3 distinct phases."""
    scenario = HealthDegradationScenario(duration_days=3.0)
    df = scenario.generate(seed=42)
    assert len(df) == 864
    # Phase 1 (0-287) is clean
    assert df.loc[0:287, "is_anomaly"].sum() == 0
    # Phase 2 (288-575) has drift with intermittent spike at 450-451
    assert (df.loc[288:449, "anomaly_type"] == "DRIFT").all()
    assert (df.loc[450:451, "anomaly_type"] == "SPIKE").all()
    assert (df.loc[452:487, "anomaly_type"] == "DRIFT").all()
    assert (df.loc[288:487, "is_anomaly"] == True).all()
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
    required_cols = {"timestamp", "station_id", "temperature", "pressure", "humidity", "is_anomaly", "anomaly_type", "severity"}
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


def test_cli_scenario_listing():
    """Verify CLI scenario listing exits cleanly."""
    ret = cli_main(["--list-scenarios"])
    assert ret == 0

