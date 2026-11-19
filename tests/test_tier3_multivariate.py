"""
tests/test_tier3_multivariate.py
Comprehensive Unit Test Suite for Tier 3 Thermodynamic Consistency & Mahalanobis Distance Engine.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from backend.app.ml.tier3_multivariate import (
    Tier3MultivariateDetector,
    calculate_dew_point,
    evaluate_thermodynamic_consistency,
)


@pytest.fixture
def clean_baseline_df() -> pd.DataFrame:
    np.random.seed(42)
    n = 500
    temp = np.random.normal(22.0, 4.0, n)
    pres = np.random.normal(1013.25, 6.0, n)
    hum = np.random.normal(55.0, 15.0, n)
    hum = np.clip(hum, 10.0, 95.0)
    return pd.DataFrame({"temperature": temp, "pressure": pres, "humidity": hum})


@pytest.fixture
def t3_detector(clean_baseline_df: pd.DataFrame) -> Tier3MultivariateDetector:
    detector = Tier3MultivariateDetector()
    detector.fit(clean_baseline_df)
    return detector


def test_dew_point_magnus_tetens_accuracy() -> None:
    # At T=20°C, RH=50% -> Td should be ~9.27°C
    td = calculate_dew_point(20.0, 50.0)
    assert pytest.approx(td, abs=0.1) == 9.27

    # At T=30°C, RH=80% -> Td should be ~26.2°C
    td2 = calculate_dew_point(30.0, 80.0)
    assert pytest.approx(td2, abs=0.2) == 26.2


def test_dew_point_physical_consistency() -> None:
    # At RH=100%, Td == T
    is_cons, td, diff, score = evaluate_thermodynamic_consistency(25.0, 100.0)
    assert is_cons is True
    assert pytest.approx(td, abs=0.1) == 25.0
    assert score == 0.0

    # At RH=40%, Td < T
    is_cons2, td2, diff2, score2 = evaluate_thermodynamic_consistency(25.0, 40.0)
    assert is_cons2 is True
    assert td2 < 25.0
    assert score2 == 0.0


def test_dew_point_supersaturation_violation() -> None:
    # At RH=104% (operational tolerance), tolerance of 0.5°C is checked
    is_cons, td, diff, score = evaluate_thermodynamic_consistency(25.0, 104.0, tolerance=0.5)
    # Td is only slightly above T (< 0.5°C), so it stays within tolerance
    assert diff <= 1.0


def test_dew_point_negative_zero_rh_clamping() -> None:
    # Zero or negative humidity should not crash or produce NaN
    td_zero = calculate_dew_point(20.0, 0.0)
    assert not np.isnan(td_zero)
    assert td_zero < 0.0

    td_neg = calculate_dew_point(20.0, -10.0)
    assert not np.isnan(td_neg)


def test_mahalanobis_fit_and_persistence(tmp_path: Path, clean_baseline_df: pd.DataFrame) -> None:
    detector = Tier3MultivariateDetector()
    detector.fit(clean_baseline_df)

    save_path = tmp_path / "mahalanobis.joblib"
    detector.save(save_path)
    assert save_path.exists()

    loaded = Tier3MultivariateDetector.load(save_path)
    assert np.allclose(detector.mean, loaded.mean)
    assert np.allclose(detector.covariance, loaded.covariance)

    res1 = detector.evaluate(22.0, 1013.25, 55.0)
    res2 = loaded.evaluate(22.0, 1013.25, 55.0)
    assert pytest.approx(res1.mahalanobis_distance, abs=1e-4) == res2.mahalanobis_distance
    assert pytest.approx(res1.mahalanobis_score, abs=1e-4) == res2.mahalanobis_score


def test_mahalanobis_distance_nominal_p_value(t3_detector: Tier3MultivariateDetector) -> None:
    # Center of distribution
    res = t3_detector.evaluate(22.0, 1013.25, 55.0)
    assert res.is_valid is True
    assert res.mahalanobis_sq < 3.0
    assert res.mahalanobis_score < 0.60
    assert res.tier3_score < 0.60


def test_mahalanobis_distance_anomalous_coupling(t3_detector: Tier3MultivariateDetector) -> None:
    # Decoupled anomaly: Extreme T=45°C, Extreme P=970 hPa, RH=98% (rare combined covariance)
    res = t3_detector.evaluate(45.0, 970.0, 98.0)
    assert res.is_valid is True
    assert res.mahalanobis_distance > 3.0
    assert res.mahalanobis_score >= 0.85
    assert res.tier3_score >= 0.85


def test_tier3_nan_inf_handling(t3_detector: Tier3MultivariateDetector) -> None:
    res = t3_detector.evaluate(np.nan, 1013.25, 50.0)
    assert res.is_valid is False
    assert res.tier3_score == 0.0

    res_inf = t3_detector.evaluate(25.0, np.inf, 50.0)
    assert res_inf.is_valid is False
