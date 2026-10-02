"""
tests/test_tier0_screener.py
Unit tests for the Tier 0 In-Memory Deterministic Screener.
"""

import math
import pytest
from backend.app.ml.tier0_screener import Tier0Screener, Tier0Result


@pytest.fixture
def screener():
    return Tier0Screener(window_size=6)


def test_normal_observation_passes(screener):
    reading = {"temperature": 25.4, "pressure": 1013.2, "humidity": 65.0}
    res: Tier0Result = screener.screen("AWS-001", reading)
    assert res.status == "PASS"
    assert res.flag == "PASS"
    assert res.violated_param is None


def test_out_of_range_temperature(screener):
    # Above 60°C
    reading = {"temperature": 75.0, "pressure": 1013.2, "humidity": 50.0}
    res = screener.screen("AWS-001", reading)
    assert res.status == "REJECTED"
    assert res.flag == "OUT_OF_RANGE"
    assert res.violated_param == "temperature"

    # Below -10°C
    reading_low = {"temperature": -25.0, "pressure": 1013.2, "humidity": 50.0}
    res_low = screener.screen("AWS-001", reading_low)
    assert res_low.status == "REJECTED"
    assert res_low.flag == "OUT_OF_RANGE"
    assert res_low.violated_param == "temperature"


def test_out_of_range_humidity_and_pressure(screener):
    # Humidity > 100%
    reading_h = {"temperature": 25.0, "pressure": 1013.2, "humidity": 105.0}
    res_h = screener.screen("AWS-001", reading_h)
    assert res_h.status == "REJECTED"
    assert res_h.flag == "OUT_OF_RANGE"
    assert res_h.violated_param == "humidity"

    # Pressure < 870 hPa
    reading_p = {"temperature": 25.0, "pressure": 750.0, "humidity": 50.0}
    res_p = screener.screen("AWS-001", reading_p)
    assert res_p.status == "REJECTED"
    assert res_p.flag == "OUT_OF_RANGE"
    assert res_p.violated_param == "pressure"


def test_null_or_nan_dropout(screener):
    # None value
    reading_none = {"temperature": None, "pressure": 1013.2, "humidity": 50.0}
    res_none = screener.screen("AWS-001", reading_none)
    assert res_none.status == "REJECTED"
    assert res_none.flag == "NULL_DROPOUT"
    assert res_none.violated_param == "temperature"

    # NaN float
    reading_nan = {"temperature": 25.0, "pressure": float("nan"), "humidity": 50.0}
    res_nan = screener.screen("AWS-001", reading_nan)
    assert res_nan.status == "REJECTED"
    assert res_nan.flag == "NULL_DROPOUT"
    assert res_nan.violated_param == "pressure"


def test_step_delta_spike(screener):
    # Base reading
    screener.screen("AWS-001", {"temperature": 20.0, "pressure": 1010.0, "humidity": 50.0})

    # Sudden 10°C jump (limit is 8.0°C)
    res = screener.screen("AWS-001", {"temperature": 30.5, "pressure": 1010.0, "humidity": 50.0})
    assert res.status == "SUSPICIOUS"
    assert res.flag == "STEP_SPIKE"
    assert res.violated_param == "temperature"


def test_frozen_sensor_detection(screener):
    station = "AWS-TEST-FROZEN"
    # Feed 5 identical readings
    for _ in range(5):
        res = screener.screen(station, {"temperature": 28.12, "pressure": 1012.0, "humidity": 60.0})
        assert res.status == "PASS"

    # 6th identical reading triggers frozen detection
    res_frozen = screener.screen(station, {"temperature": 28.12, "pressure": 1012.0, "humidity": 60.0})
    assert res_frozen.status == "SUSPICIOUS"
    assert res_frozen.flag == "FROZEN_SENSOR"
