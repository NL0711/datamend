"""
tests/test_tier1_qc.py
Comprehensive Unit Test Suite for Tier 1 Deterministic Quality Control Engine.
"""

import numpy as np
import pandas as pd
import pytest

from backend.app.ml.tier1_qc import Tier1QC, Tier1QCConfig, Tier1QCEngine, Tier1QCResult


@pytest.fixture
def tier1_engine() -> Tier1QC:
    return Tier1QC()


def test_nominal_observation_passes(tier1_engine: Tier1QC) -> None:
    res = tier1_engine.evaluate(temperature=22.5, pressure=1013.25, humidity=60.0)
    assert res.is_valid is True
    assert res.qc_flag is False
    assert res.score == 0.0
    assert res.is_hard_override is False
    assert len(res.violations) == 0


@pytest.mark.parametrize(
    "t, p, rh, viol_param",
    [
        (-45.0, 1013.25, 60.0, "temperature"),
        (65.0, 1013.25, 60.0, "temperature"),
        (22.0, 250.0, 60.0, "pressure"),
        (22.0, 1150.0, 60.0, "pressure"),
        (22.0, 1013.25, -5.0, "humidity"),
        (22.0, 1013.25, 110.0, "humidity"),
    ],
)
def test_wmo_physical_bounds_violations(
    tier1_engine: Tier1QC, t: float, p: float, rh: float, viol_param: str
) -> None:
    res = tier1_engine.evaluate(temperature=t, pressure=p, humidity=rh)
    assert res.qc_flag is True
    assert res.score == 1.0
    assert res.is_hard_override is True
    assert res.flags["out_of_bounds"] is True
    assert res.flags["violating_param"] == viol_param
    assert len(res.violations) >= 1


def test_wmo_exact_boundary_conditions(tier1_engine: Tier1QC) -> None:
    # Exact boundary limits should pass
    res_min = tier1_engine.evaluate(temperature=-40.0, pressure=300.0, humidity=0.0)
    assert res_min.flags["out_of_bounds"] is False

    res_max = tier1_engine.evaluate(temperature=60.0, pressure=1100.0, humidity=104.0)
    assert res_max.flags["out_of_bounds"] is False


def test_rate_of_change_temperature_jump(tier1_engine: Tier1QC) -> None:
    temp_hist = [20.0, 20.2, 20.1]
    res = tier1_engine.evaluate(
        temperature=26.0,  # Jump of 5.9°C > 5.0°C limit
        pressure=1013.25,
        humidity=60.0,
        temp_history=temp_hist,
    )
    assert res.qc_flag is True
    assert res.flags["rate_of_change_exceeded"] is True
    assert res.score >= 0.70


def test_rate_of_change_pressure_jump(tier1_engine: Tier1QC) -> None:
    press_hist = [1013.0, 1013.2]
    res = tier1_engine.evaluate(
        temperature=22.0,
        pressure=1017.5,  # Jump of 4.3 hPa > 3.0 hPa limit
        humidity=60.0,
        press_history=press_hist,
    )
    assert res.qc_flag is True
    assert res.flags["rate_of_change_exceeded"] is True


def test_rate_of_change_humidity_jump(tier1_engine: Tier1QC) -> None:
    humid_hist = [50.0, 52.0]
    res = tier1_engine.evaluate(
        temperature=22.0,
        pressure=1013.25,
        humidity=80.0,  # Jump of 28% > 25% limit
        humid_history=humid_hist,
    )
    assert res.qc_flag is True
    assert res.flags["rate_of_change_exceeded"] is True


def test_persistence_frozen_sensor(tier1_engine: Tier1QC) -> None:
    # 5 previous identical + 1 current = 6 consecutive identical readings
    temp_hist = [24.5, 24.5, 24.5, 24.5, 24.5]
    res = tier1_engine.evaluate(
        temperature=24.5,
        pressure=1013.25,
        humidity=60.0,
        temp_history=temp_hist,
    )
    assert res.is_frozen is True
    assert res.qc_flag is True
    assert res.flags["is_frozen"] is True
    assert res.score >= 0.90


def test_missing_and_sentinel_values(tier1_engine: Tier1QC) -> None:
    # Test None
    res_none = tier1_engine.evaluate(temperature=None, pressure=1013.25, humidity=60.0)
    assert res_none.is_valid is False
    assert res_none.is_missing is True
    assert res_none.is_hard_override is True

    # Test NaN
    res_nan = tier1_engine.evaluate(temperature=np.nan, pressure=1013.25, humidity=60.0)
    assert res_nan.is_valid is False
    assert res_nan.is_missing is True

    # Test Sentinel -999.0 and 9999.0
    res_sentinel1 = tier1_engine.evaluate(temperature=-999.0, pressure=1013.25, humidity=60.0)
    assert res_sentinel1.is_missing is True
    res_sentinel2 = tier1_engine.evaluate(temperature=20.0, pressure=9999.0, humidity=60.0)
    assert res_sentinel2.is_missing is True


def test_corrupt_tokens(tier1_engine: Tier1QC) -> None:
    res = tier1_engine.evaluate(temperature="$ERR_VOLTAGE#", pressure=1013.25, humidity=60.0)
    assert res.is_valid is False
    assert res.flags["corrupt_token"] is True
    assert res.is_hard_override is True


def test_duplicate_and_out_of_order_timestamps(tier1_engine: Tier1QC) -> None:
    # Duplicate
    res_dup = tier1_engine.evaluate(
        temperature=20.0,
        pressure=1013.25,
        humidity=50.0,
        timestamp="2026-08-24T12:00:00Z",
        prev_timestamp="2026-08-24T12:00:00Z",
    )
    assert res_dup.flags["duplicate_timestamp"] is True

    # Non-monotonic
    res_rev = tier1_engine.evaluate(
        temperature=20.0,
        pressure=1013.25,
        humidity=50.0,
        timestamp="2026-08-24T11:55:00Z",
        prev_timestamp="2026-08-24T12:00:00Z",
    )
    assert res_rev.flags["non_monotonic_timestamp"] is True


def test_check_observation_dict_interface(tier1_engine: Tier1QC) -> None:
    curr = {"temperature": 25.0, "pressure": 1012.0, "humidity": 65.0, "timestamp": "2026-08-24T12:05:00Z"}
    prev = {"temperature": 24.8, "pressure": 1012.1, "humidity": 65.2, "timestamp": "2026-08-24T12:00:00Z"}
    res = tier1_engine.check_observation(current=curr, previous=prev)
    assert res.qc_flag is False
    assert res.is_valid is True


def test_check_batch_dataframe(tier1_engine: Tier1QC) -> None:
    df = pd.DataFrame({
        "timestamp": ["2026-08-24 12:00:00", "2026-08-24 12:05:00", "2026-08-24 12:10:00"],
        "temperature": [20.0, 20.2, 70.0],  # 70 is out of bounds
        "pressure": [1013.0, 1013.1, 1013.2],
        "humidity": [60.0, 60.5, 61.0],
    })
    res_df = tier1_engine.check_batch(df)
    assert len(res_df) == 3
    assert res_df["qc_flag"].iloc[0] == False
    assert res_df["qc_flag"].iloc[1] == False
    assert res_df["qc_flag"].iloc[2] == True
