"""
tests/test_noaa_importer.py
SkyGuard AI — Unit Test Suite for NOAA ISD Observational Data Importer.
"""

from pathlib import Path
import pytest
import pandas as pd

from scripts.import_noaa_data import (
    calculate_relative_humidity,
    generate_sample_noaa_dataset,
    import_noaa_dataset,
    parse_isd_lite_line,
)


def test_calculate_relative_humidity_magnus():
    """Verifies Magnus approximation for Relative Humidity calculation."""
    # At T = 20°C, Td = 20°C -> RH = 100%
    rh_sat = calculate_relative_humidity(20.0, 20.0)
    assert pytest.approx(rh_sat, abs=0.5) == 100.0

    # At T = 20°C, Td = 10°C -> RH ~ 52-53%
    rh_mid = calculate_relative_humidity(20.0, 10.0)
    assert 50.0 <= rh_mid <= 55.0


def test_parse_isd_lite_line():
    """Verifies fixed-width field extraction for ISD-Lite format."""
    # Line format: Year Month Day Hour Temp(tenths) DewPoint(tenths) SLP(tenths) ...
    line = "2023 07 15 12   250   150 10132"
    parsed = parse_isd_lite_line(line, "725650-03017")
    assert parsed is not None
    assert parsed["station_id"] == "725650-03017"
    assert parsed["temperature"] == 25.0
    assert parsed["pressure"] == 1013.2
    assert parsed["dew_point"] == 15.0
    assert parsed["humidity"] > 0.0
    assert parsed["source_type"] == "NOAA_ISD"


def test_parse_isd_lite_missing_values():
    """Verifies -9999 missing value sentinel is parsed as NaN."""
    line = "2023 07 15 12 -9999 -9999 -9999"
    parsed = parse_isd_lite_line(line, "725650-03017")
    assert parsed is not None
    import math
    assert math.isnan(parsed["temperature"])
    assert math.isnan(parsed["pressure"])


def test_sample_noaa_dataset_generation(tmp_path: Path):
    """Verifies deterministic sample NOAA dataset generation."""
    out_file = tmp_path / "test_noaa.csv"
    imported_path = import_noaa_dataset(output_path=out_file, sample_mode=True)
    assert imported_path.exists()

    df = pd.read_csv(imported_path)
    assert len(df) == 500
    assert "timestamp" in df.columns
    assert "temperature" in df.columns
    assert "pressure" in df.columns
    assert "humidity" in df.columns
