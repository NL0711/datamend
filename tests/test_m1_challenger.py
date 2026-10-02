"""
SkyGuard AI — Milestone M1 Challenger Empirical Verification & Stress Test Suite.

Adversarially evaluates:
1. Thermodynamic validity and diurnal physical cycles (Corr(T, RH) < -0.6, S2(P) tidal harmonics at 10:00 & 22:00 UTC).
2. All 8 anomaly pattern signatures, mathematical distinctiveness, and ground-truth metadata contracts.
3. Edge cases: extreme temperatures (-50°C, +60°C), leap years, sub-minute frequencies, out-of-bounds handling, scenario duration scalability.
"""

import math
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
# Section 1: Physical Realism & Thermodynamic Verification
# ============================================================================

def test_empirical_temperature_rh_correlation_across_presets():
    """Verify Corr(T, RH) < -0.60 across all standard regional presets."""
    for name, preset in PRESETS.items():
        gen = DiurnalGenerator(params=preset, seed=42)
        df = gen.generate(start_date="2026-08-01", duration_days=30.0, sampling_interval_min=5.0)
        corr = df["temperature"].corr(df["humidity"])
        print(f"Preset {name}: Corr(T, RH) = {corr:.4f}")
        assert corr < -0.60, f"Preset {name} failed Corr(T, RH) < -0.60, got {corr:.4f}"


def test_empirical_pressure_semidiurnal_tides_peak_hours():
    """
    Verify 12-hour S2(P) thermal atmospheric tides produce local maxima at 10:00 and 22:00 UTC,
    and minima at 04:00 and 16:00 UTC.
    """
    params = DiurnalParameters(
        sea_level_pressure=1013.25,
        pressure_tide_amp=1.5,
        pressure_synoptic_amp=0.0,  # Isolate pure tidal component
        pressure_noise_sigma=0.01,
    )
    gen = DiurnalGenerator(params=params, seed=42)
    df = gen.generate(start_date="2026-08-01", duration_days=10.0, sampling_interval_min=5.0)
    df["dt"] = pd.to_datetime(df["timestamp"])
    df["minute_of_day"] = df["dt"].dt.hour * 60 + df["dt"].dt.minute

    hourly_mean = df.groupby("minute_of_day")["pressure"].mean()

    # Peak 1 should be around 10:00 (minute 600)
    # Peak 2 should be around 22:00 (minute 1320)
    # Trough 1 should be around 04:00 (minute 240)
    # Trough 2 should be around 16:00 (minute 960)
    peak1_time = hourly_mean.loc[480:720].idxmax() / 60.0  # 8am to 12pm window
    peak2_time = hourly_mean.loc[1200:1435].idxmax() / 60.0 # 8pm to midnight window
    trough1_time = hourly_mean.loc[120:360].idxmin() / 60.0 # 2am to 6am window
    trough2_time = hourly_mean.loc[840:1080].idxmin() / 60.0 # 2pm to 6pm window

    print(f"Empirical S2(P) Peaks: {peak1_time:.2f}h and {peak2_time:.2f}h | Troughs: {trough1_time:.2f}h and {trough2_time:.2f}h")
    assert abs(peak1_time - 10.0) <= 0.25, f"Peak 1 expected at 10.0h, got {peak1_time:.2f}h"
    assert abs(peak2_time - 22.0) <= 0.25, f"Peak 2 expected at 22.0h, got {peak2_time:.2f}h"
    assert abs(trough1_time - 4.0) <= 0.25, f"Trough 1 expected at 4.0h, got {trough1_time:.2f}h"
    assert abs(trough2_time - 16.0) <= 0.25, f"Trough 2 expected at 16.0h, got {trough2_time:.2f}h"


def test_empirical_magnus_psychrometric_consistency():
    """Verify Magnus-Tetens saturation vapor pressure e_s(T) and dew point inversion."""
    gen = DiurnalGenerator()
    # Test across broad temperature range -30°C to +50°C
    temps = np.linspace(-30.0, 50.0, 100)
    es = gen.calculate_saturation_vapor_pressure(temps)
    # e_s must be strictly positive and monotonically increasing with T
    assert np.all(es > 0)
    assert np.all(np.diff(es) > 0)

    # Invert Dew Point for RH=50%
    td = gen.calculate_dew_point(temps, np.full_like(temps, 50.0))
    # Dew point must always be less than or equal to ambient temperature
    assert np.all(td < temps)


# ============================================================================
# Section 2: Mathematical Distinctiveness & Ground-Truth Contracts of 8 Anomalies
# ============================================================================

def test_empirical_all_8_anomaly_signatures_and_labels():
    """Verify all 8 anomaly patterns produce distinct mathematical signatures and accurate labels."""
    gen = DiurnalGenerator(seed=42)
    clean_df = gen.generate(duration_days=5.0, sampling_interval_min=5.0)

    # 1. SPIKE
    df_spike = inject_spike(clean_df, target_column="temperature", start_idx=50, magnitude=20.0, duration=1)
    assert df_spike.loc[50, "is_anomaly"] == True
    assert df_spike.loc[50, "is_fault"] == True
    assert df_spike.loc[50, "anomaly_type"] == "SPIKE"
    assert df_spike.loc[50, "temperature"] == clean_df.loc[50, "temperature"] + 20.0
    assert df_spike.loc[50, "clean_temperature"] == clean_df.loc[50, "temperature"]

    # 2. DRIFT
    df_drift = inject_drift(clean_df, target_column="pressure", start_idx=100, duration=30, drift_rate=0.2)
    assert (df_drift.loc[100:129, "anomaly_type"] == "DRIFT").all()
    assert (df_drift.loc[100:129, "is_fault"] == True).all()
    drift_deltas = df_drift.loc[100:129, "pressure"] - clean_df.loc[100:129, "pressure"]
    # Check linear growth
    assert np.all(np.diff(drift_deltas) >= 0.19)

    # 3. FROZEN
    df_frozen = inject_frozen(clean_df, target_column="humidity", start_idx=200, duration=25, stuck_value=45.0)
    assert (df_frozen.loc[200:224, "humidity"] == 45.0).all()
    assert df_frozen.loc[200:224, "humidity"].var() == 0.0
    assert (df_frozen.loc[200:224, "anomaly_type"] == "FROZEN").all()

    # 4. DROPOUT
    df_drop = inject_dropout(clean_df, target_column="temperature", start_idx=250, duration=10, fill_mode="nan")
    assert df_drop.loc[250:259, "temperature"].isna().all()
    assert (df_drop.loc[250:259, "anomaly_type"] == "DROPOUT").all()

    # 5. NOISE BURST
    df_noise = inject_noise_burst(clean_df, target_column="temperature", start_idx=300, duration=50, noise_factor=15.0, random_seed=42)
    assert (df_noise.loc[300:349, "anomaly_type"] == "NOISE_BURST").all()
    assert (df_noise.loc[300:349, "is_fault"] == True).all()

    # 6. MULTIVARIATE INCONSISTENCY
    df_multi = inject_multivariate_inconsistency(clean_df, start_idx=400, duration=20, temp_shift=15.0, rh_shift=30.0)
    assert (df_multi.loc[400:419, "anomaly_type"] == "MULTIVARIATE_INCONSISTENCY").all()
    assert (df_multi.loc[400:419, "is_fault"] == True).all()
    assert (df_multi.loc[400:419, "temperature"] > clean_df.loc[400:419, "temperature"]).all()
    assert (df_multi.loc[400:419, "humidity"] > clean_df.loc[400:419, "humidity"]).all()

    # 7. METEOROLOGICAL EXTREME (Genuine event: is_fault == False)
    df_storm = inject_meteorological_extreme(clean_df, start_idx=500, duration=12, temp_drop=-8.0, pressure_drop=-5.0, rh_surge=35.0)
    assert (df_storm.loc[500:511, "anomaly_type"] == "METEOROLOGICAL_EXTREME").all()
    assert (df_storm.loc[500:511, "is_anomaly"] == True).all()
    assert (df_storm.loc[500:511, "is_fault"] == False).all()  # Crucial: Genuine event must NOT be flagged as sensor fault!

    # 8. DATA CORRUPTION
    df_corr = inject_data_corruption(clean_df, target_column="pressure", start_idx=600, duration=5, corruption_mode="string_err")
    assert (df_corr.loc[600:604, "anomaly_type"] == "DATA_CORRUPTION").all()
    assert df_corr.loc[600, "pressure"] == "$ERR_COMM_TIMEOUT#"


# ============================================================================
# Section 3: Edge Cases & Boundary Stress Testing
# ============================================================================

def test_edge_case_extreme_temperatures():
    """Verify simulator stability under extreme polar (-50°C) and hyper-arid desert (+55°C) environments."""
    # Polar -50°C
    polar_params = DiurnalParameters(temp_base=-50.0, temp_amplitude=5.0, sea_level_pressure=1025.0)
    polar_gen = DiurnalGenerator(params=polar_params, seed=42)
    df_polar = polar_gen.generate(duration_days=3.0)
    assert df_polar["temperature"].max() < -35.0
    assert not df_polar[["temperature", "pressure", "humidity"]].isna().any().any()
    assert (df_polar["humidity"] >= 5.0).all() and (df_polar["humidity"] <= 100.0).all()

    # Hyper-arid +55°C
    hot_params = DiurnalParameters(temp_base=50.0, temp_amplitude=8.0, dew_point_depression=25.0)
    hot_gen = DiurnalGenerator(params=hot_params, seed=42)
    df_hot = hot_gen.generate(duration_days=3.0)
    assert df_hot["temperature"].max() > 50.0
    assert not df_hot[["temperature", "pressure", "humidity"]].isna().any().any()
    assert (df_hot["humidity"] >= 5.0).all() and (df_hot["humidity"] <= 100.0).all()


def test_edge_case_leap_year_transition():
    """Verify simulator generates continuous time series across leap day (2024-02-28 to 2024-03-01)."""
    gen = DiurnalGenerator(seed=42)
    df_leap = gen.generate(start_date="2024-02-28 00:00:00", end_date="2024-03-01 23:55:00", sampling_interval_min=5.0)
    assert len(df_leap) == 3 * 288  # 3 full days: Feb 28, Feb 29, Mar 1
    # Check Feb 29 exists
    feb29_rows = df_leap[pd.to_datetime(df_leap["timestamp"]).dt.strftime("%m-%d") == "02-29"]
    assert len(feb29_rows) == 288
    assert not df_leap.isna().any().any()


def test_edge_case_sub_minute_frequencies():
    """Verify simulator supports high-frequency sampling (e.g. 10s, 30s)."""
    gen = DiurnalGenerator(seed=42)
    df_30s = gen.generate(start_date="2026-08-01 00:00:00", duration_days=0.1, freq="30s")
    assert len(df_30s) == int(0.1 * 86400 / 30)
    assert not df_30s.isna().any().any()
    # Check time delta is exactly 30s
    dt_diff = pd.to_datetime(df_30s["timestamp"]).diff().dropna()
    assert (dt_diff == pd.Timedelta(seconds=30)).all()


def test_edge_case_injector_out_of_bounds_and_overflow():
    """Verify anomaly injector handles indices at boundary conditions gracefully."""
    gen = DiurnalGenerator(seed=42)
    df = gen.generate(duration_days=1.0)
    n = len(df)

    # 1. start_idx out of bounds raises IndexError
    with pytest.raises(IndexError):
        inject_spike(df, target_column="temperature", start_idx=n + 10, magnitude=10.0)

    with pytest.raises(IndexError):
        inject_spike(df, target_column="temperature", start_idx=-5, magnitude=10.0)

    # 2. duration extending beyond end of DataFrame clamps cleanly without IndexError
    df_clamped = inject_drift(df, target_column="temperature", start_idx=n - 10, duration=50, drift_rate=0.1)
    assert len(df_clamped) == n
    assert (df_clamped.loc[n-10:n-1, "anomaly_type"] == "DRIFT").all()


def test_edge_case_scenario_duration_scalability():
    """
    Stress-test scenario generators across varied durations (1 day, 3 days, 7 days, 30 days).
    Tests for duration edge cases and index bounds.
    """
    # Test CleanBaselineScenario
    for days in [0.5, 1.0, 3.0, 7.0, 30.0]:
        df = CleanBaselineScenario(duration_days=days).generate(seed=42)
        assert len(df) == int(days * 288)

    # Test SingleFaultScenario
    for ftype in ["spike", "drift", "frozen", "dropout", "noise", "multivariate"]:
        scen = SingleFaultScenario(fault_type=ftype, duration_days=2.0)
        df = scen.generate(seed=42)
        assert len(df) == int(2.0 * 288)
        assert df["is_anomaly"].sum() > 0
