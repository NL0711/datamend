"""
scripts/train_models.py
SkyGuard AI — Automated 5-Tier ML Model Training and Artifact Persistence Pipeline.

Trains and persists production artifacts in models/:
- preprocessor.joblib & scaler.joblib
- isolation_forest.joblib
- temporal_autoencoder.pt & autoencoder.pt
- mahalanobis.joblib
- fault_classifier.joblib
- model_metadata.json
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from backend.app.ml.preprocessor import DataPreprocessor, FEATURE_NAMES
from backend.app.ml.tier2_point_ml import IsolationForestPointDetector
from backend.app.ml.tier2_temporal_ml import TemporalAutoencoder, TemporalAutoencoderDetector
from backend.app.ml.tier3_multivariate import Tier3MultivariateDetector
from backend.app.ml.tier4_classifier import FaultClassifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def train_all_models(
    train_path: Path,
    val_path: Path,
    output_dir: Path,
    seq_len: int = 30,
    epochs: int = 30,
    batch_size: int = 64,
    lr: float = 1e-3,
    seed: int = 42,
) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("================================================================================")
    logger.info("  SkyGuard AI — 5-Tier ML Model Training & Artifact Generation Pipeline")
    logger.info("================================================================================")
    logger.info("Training Data:    %s", train_path)
    logger.info("Validation Data:  %s", val_path)
    logger.info("Target Artifacts: %s\n", output_dir)

    if not train_path.exists():
        raise FileNotFoundError(f"Training dataset not found at {train_path}")

    # 1. Load Data
    df_train = pd.read_csv(train_path)
    df_val = pd.read_csv(val_path) if val_path.exists() else df_train.copy()

    # 2. Fit Preprocessor Scaler
    logger.info("[1/5] Fitting StandardScaler & Feature Preprocessor on clean baseline...")
    preprocessor = DataPreprocessor(window_size=seq_len)
    preprocessor.fit(df_train)

    # Save to both standard names
    preprocessor.save(output_dir / "preprocessor.joblib")
    preprocessor.save(output_dir / "scaler.joblib")
    logger.info("  --> Saved %s and %s", output_dir / "preprocessor.joblib", output_dir / "scaler.joblib")

    # Transform features
    X_train_scaled = preprocessor.transform(df_train)
    X_val_scaled = preprocessor.transform(df_val)

    # 3. Train Isolation Forest (Point ML)
    logger.info("\n[2/5] Training Isolation Forest Point Outlier Detector...")
    point_detector = IsolationForestPointDetector(
        n_estimators=100,
        contamination=0.01,
        random_state=seed,
    )
    point_detector.fit(X_train_scaled)
    point_detector.save(output_dir / "isolation_forest.joblib")
    logger.info("  --> Saved %s", output_dir / "isolation_forest.joblib")

    # 4. Train PyTorch GRU Autoencoder (Temporal ML)
    logger.info("\n[3/5] Training PyTorch GRU Temporal Autoencoder (seq_len=%d)...", seq_len)
    # Core 3D features scaled (T, P, RH) are the first 3 columns
    raw_3d_train = X_train_scaled[:, :3]

    X_seq_train = preprocessor.create_sequences(raw_3d_train, window_size=seq_len)
    if len(X_seq_train) == 0:
        raise ValueError(f"Insufficient samples to create sequences of length {seq_len}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_ae = TemporalAutoencoder(
        seq_len=seq_len,
        input_dim=3,
        hidden_dim=32,
        latent_dim=16,
        num_layers=2,
    ).to(device)

    train_dataset = TensorDataset(torch.from_numpy(X_seq_train).float())
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

    optimizer = torch.optim.Adam(model_ae.parameters(), lr=lr, weight_decay=1e-5)
    criterion = nn.MSELoss()

    model_ae.train()
    for epoch in range(epochs):
        epoch_loss = 0.0
        for (batch_x,) in train_loader:
            batch_x = batch_x.to(device)
            optimizer.zero_grad()
            recon = model_ae(batch_x)
            loss = criterion(recon, batch_x)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * len(batch_x)
        epoch_loss /= len(X_seq_train)
        if (epoch + 1) % 5 == 0 or epoch == epochs - 1:
            logger.info("  Epoch [%02d/%02d] Train MSE Loss: %.6f", epoch + 1, epochs, epoch_loss)

    # Compute baseline reconstruction threshold on clean training set
    model_ae.eval()
    with torch.no_grad():
        all_train_tensor = torch.from_numpy(X_seq_train).float().to(device)
        train_recon = model_ae(all_train_tensor)
        last_step_err = torch.mean((train_recon[:, -1, :] - all_train_tensor[:, -1, :]) ** 2, dim=-1)
        full_seq_err = torch.mean((train_recon - all_train_tensor) ** 2, dim=(1, 2))
        blended_err = (0.7 * last_step_err + 0.3 * full_seq_err).cpu().numpy()

        mu_err = float(np.mean(blended_err))
        std_err = float(np.std(blended_err))
        threshold_temporal = max(0.01, mu_err + 3.0 * std_err)

    ae_checkpoint = {
        "model_type": "TemporalAutoencoder",
        "model_state_dict": model_ae.state_dict(),
        "window_size": seq_len,
        "input_dim": 3,
        "hidden_dim": 32,
        "latent_dim": 16,
        "threshold": float(threshold_temporal),
        "mean_mse": float(mu_err),
        "std_mse": float(std_err),
    }
    torch.save(ae_checkpoint, output_dir / "temporal_autoencoder.pt")
    torch.save(ae_checkpoint, output_dir / "autoencoder.pt")
    logger.info(
        "  --> Saved %s and %s (Threshold theta = %.6f, Mean = %.6f, Std = %.6f)",
        output_dir / "temporal_autoencoder.pt",
        output_dir / "autoencoder.pt",
        threshold_temporal,
        mu_err,
        std_err,
    )

    # 5. Fit Mahalanobis Covariance Matrix (Tier 3)
    logger.info("\n[4/5] Fitting Tier 3 Mahalanobis Covariance & Clausius-Clapeyron Engine...")
    t3_detector = Tier3MultivariateDetector()
    t3_detector.fit(df_train)
    t3_detector.save(output_dir / "mahalanobis.joblib")
    logger.info("  --> Saved %s", output_dir / "mahalanobis.joblib")

    # 6. Fit Fault Classifier (Tier 4)
    logger.info("\n[5/5] Fitting Fault Taxonomy Classifier...")
    fault_classifier = FaultClassifier()
    # Train ML auxiliary classifier on labeled validation set if available
    if "anomaly_type" in df_val.columns:
        y_val = df_val["anomaly_type"].values
        clf = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=seed)
        clf.fit(X_val_scaled, y_val)
        fault_classifier.ml_model = clf
    fault_classifier.save(output_dir / "fault_classifier.joblib")
    logger.info("  --> Saved %s", output_dir / "fault_classifier.joblib")

    # 7. Model Metadata JSON
    metadata = {
        "version": "1.0.0",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "train_samples": len(df_train),
        "val_samples": len(df_val),
        "features": list(FEATURE_NAMES),
        "temporal_threshold": float(threshold_temporal),
        "temporal_mean_mse": float(mu_err),
        "temporal_std_mse": float(std_err),
        "isolation_forest_n_trees": 100,
        "autoencoder_latent_dim": 16,
        "mahalanobis_df": 3,
    }
    with open(output_dir / "model_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info("  --> Saved %s", output_dir / "model_metadata.json")

    logger.info("\n[SUCCESS] All 5-Tier ML Model Artifacts successfully trained and persisted in %s/", output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SkyGuard AI Model Training Pipeline")
    parser.add_argument("--train", type=str, default="data/train_clean.csv")
    parser.add_argument("--val", type=str, default="data/val_mixed.csv")
    parser.add_argument("--output-dir", type=str, default="models")
    parser.add_argument("--epochs", type=int, default=30)
    args = parser.parse_args()

    train_all_models(
        train_path=Path(args.train),
        val_path=Path(args.val),
        output_dir=Path(args.output_dir),
        epochs=args.epochs,
    )
