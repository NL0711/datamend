"""
tests/test_tier2_ml.py
Comprehensive Unit Test Suite for Tier 2 Point ML, Temporal Autoencoder, and Preprocessor.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import torch

from backend.app.ml.preprocessor import (
    DataPreprocessor,
    FEATURE_NAMES,
    calculate_magnus_dew_point,
)
from backend.app.ml.tier2_point_ml import IsolationForestPointDetector, PointAnomalyDetector
from backend.app.ml.tier2_temporal_ml import (
    TemporalAutoencoder,
    TemporalAutoencoderDetector,
)
from scripts.train_models import train_all_models


@pytest.fixture
def clean_sample_df() -> pd.DataFrame:
    """Generates synthetic clean baseline telemetry."""
    n = 200
    t = np.linspace(0, 4 * np.pi, n)
    temp = 20.0 + 5.0 * np.sin(t) + np.random.normal(0, 0.2, n)
    pres = 1013.25 + 2.0 * np.cos(t) + np.random.normal(0, 0.1, n)
    hum = 60.0 - 15.0 * np.sin(t) + np.random.normal(0, 0.5, n)
    dates = pd.date_range("2026-08-01", periods=n, freq="5min")
    return pd.DataFrame({
        "timestamp": dates,
        "temperature": temp,
        "pressure": pres,
        "humidity": hum,
    })


def test_preprocessor_9_features(clean_sample_df: pd.DataFrame) -> None:
    prep = DataPreprocessor(window_size=30)
    df_feat = prep.compute_feature_dataframe(clean_sample_df)

    for feat in FEATURE_NAMES:
        assert feat in df_feat.columns, f"Feature '{feat}' missing from feature dataframe."

    assert len(df_feat) == len(clean_sample_df)
    assert not df_feat[FEATURE_NAMES].isna().any().any()


def test_preprocessor_dew_point_accuracy() -> None:
    # Standard meteorological condition: T=20°C, RH=50% -> Td ~= 9.27°C
    td = calculate_magnus_dew_point(20.0, 50.0)
    assert pytest.approx(td, abs=0.1) == 9.27


def test_preprocessor_scaler_fit_transform(clean_sample_df: pd.DataFrame) -> None:
    prep = DataPreprocessor(window_size=30)
    X_scaled = prep.fit_transform(clean_sample_df)

    assert X_scaled.shape == (len(clean_sample_df), 9)
    means = np.mean(X_scaled, axis=0)
    stds = np.std(X_scaled, axis=0)

    # Standardized features should have mean ~= 0 and std ~= 1
    assert np.allclose(means, 0.0, atol=1e-2)
    assert np.allclose(stds, 1.0, atol=1e-2)


def test_preprocessor_streaming_update() -> None:
    prep = DataPreprocessor(window_size=30)
    # Stream 35 observations
    for i in range(35):
        res = prep.update(
            station_id="AWS-001",
            timestamp=f"2026-08-24T12:{i:02d}:00Z",
            temperature=20.0 + i * 0.1,
            pressure=1013.0,
            humidity=50.0,
        )

    assert res.station_id == "AWS-001"
    assert res.buffer_length == 35
    assert res.is_warm is True
    assert res.scaled_vector.shape == (9,)
    assert res.sequence_tensor.shape == (30, 3)
    assert len(res.recent_temperatures) == 35


def test_preprocessor_serialization(tmp_path: Path, clean_sample_df: pd.DataFrame) -> None:
    prep = DataPreprocessor(window_size=30)
    prep.fit(clean_sample_df)

    save_path = tmp_path / "scaler.joblib"
    prep.save(save_path)
    assert save_path.exists()

    loaded_prep = DataPreprocessor().load(save_path)
    assert loaded_prep.is_fitted is True

    X1 = prep.transform(clean_sample_df)
    X2 = loaded_prep.transform(clean_sample_df)
    assert np.allclose(X1, X2)


def test_isolation_forest_scoring_range(clean_sample_df: pd.DataFrame) -> None:
    prep = DataPreprocessor(window_size=30)
    X_scaled = prep.fit_transform(clean_sample_df)

    detector = IsolationForestPointDetector(n_estimators=50, random_state=42)
    detector.fit(X_scaled)

    # Normal sample
    normal_score = detector.predict_score(X_scaled[10])
    assert 0.0 <= normal_score <= 1.0
    assert normal_score < 0.40  # Normal point should have low anomaly score

    # Injected extreme outlier vector (+8 std deviations)
    outlier_vec = np.array([8.0, -8.0, 7.5, 10.0, -6.0, 8.0, 5.0, 5.0, 5.0])
    outlier_score = detector.predict_score(outlier_vec)
    assert outlier_score >= 0.70  # Outlier must produce high score


def test_temporal_autoencoder_architecture() -> None:
    model = TemporalAutoencoder(seq_len=30, input_dim=3, hidden_dim=32, latent_dim=16)
    x = torch.randn(4, 30, 3)
    recon = model(x)
    assert recon.shape == (4, 30, 3)


def test_temporal_autoencoder_reconstruction_and_score() -> None:
    detector = TemporalAutoencoderDetector(window_size=30, threshold=0.10)

    # Normal smooth diurnal sequence
    t = np.linspace(0, 1, 30)
    normal_seq = np.column_stack([np.sin(t), np.cos(t), -np.sin(t)]).astype(np.float32)

    score_normal = detector.predict_score(normal_seq)
    assert 0.0 <= score_normal <= 1.0

    # Distorted extreme sequence
    distorted_seq = normal_seq.copy()
    distorted_seq[-5:, 0] += 10.0  # Big jump
    score_distorted = detector.predict_score(distorted_seq)
    assert score_distorted > score_normal


def test_train_all_models_script_execution(tmp_path: Path) -> None:
    """End-to-end test verifying train_models script produces genuine artifacts."""
    train_file = Path("data/train_clean.csv")
    val_file = Path("data/val_mixed.csv")

    if not train_file.exists():
        pytest.skip("data/train_clean.csv not found")

    models_dir = tmp_path / "test_models"
    train_all_models(
        train_path=train_file,
        val_path=val_file,
        output_dir=models_dir,
        seq_len=30,
        epochs=3,  # Fast test run
    )

    assert (models_dir / "preprocessor.joblib").exists()
    assert (models_dir / "scaler.joblib").exists()
    assert (models_dir / "isolation_forest.joblib").exists()
    assert (models_dir / "temporal_autoencoder.pt").exists()
    assert (models_dir / "mahalanobis.joblib").exists()
    assert (models_dir / "fault_classifier.joblib").exists()
    assert (models_dir / "model_metadata.json").exists()
