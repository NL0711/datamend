"""
backend/app/ml/tier2_temporal_ml.py
Tier 2: Temporal ML Anomaly Detector using PyTorch GRU Autoencoder.

Learns normal diurnal multi-step dynamics across 30-step sequences of (T, P, RH)
and scores sequence deviations using normalized reconstruction MSE.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class GRUEncoder(nn.Module):
    def __init__(self, input_dim: int = 3, hidden_dim: int = 32, latent_dim: int = 16, num_layers: int = 2):
        super().__init__()
        self.gru = nn.GRU(input_dim, hidden_dim, num_layers=num_layers, batch_first=True, dropout=0.1 if num_layers > 1 else 0.0)
        self.fc = nn.Linear(hidden_dim, latent_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.gru(x)
        # Latent vector from last time step
        latent = self.fc(out[:, -1, :])
        return latent


class GRUDecoder(nn.Module):
    def __init__(self, seq_len: int = 30, latent_dim: int = 16, hidden_dim: int = 32, output_dim: int = 3, num_layers: int = 2):
        super().__init__()
        self.seq_len = seq_len
        self.fc = nn.Linear(latent_dim, hidden_dim)
        self.gru = nn.GRU(hidden_dim, hidden_dim, num_layers=num_layers, batch_first=True, dropout=0.1 if num_layers > 1 else 0.0)
        self.out = nn.Linear(hidden_dim, output_dim)

    def forward(self, latent: torch.Tensor) -> torch.Tensor:
        h = self.fc(latent).unsqueeze(1).repeat(1, self.seq_len, 1)
        out, _ = self.gru(h)
        recon = self.out(out)
        return recon


class TemporalAutoencoder(nn.Module):
    """Sequence-to-sequence GRU Autoencoder for multi-step temporal reconstruction."""

    def __init__(self, seq_len: int = 30, input_dim: int = 3, hidden_dim: int = 32, latent_dim: int = 16, num_layers: int = 2):
        super().__init__()
        self.seq_len = seq_len
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
        self.num_layers = num_layers
        self.encoder = GRUEncoder(input_dim, hidden_dim, latent_dim, num_layers=num_layers)
        self.decoder = GRUDecoder(seq_len, latent_dim, hidden_dim, input_dim, num_layers=num_layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        latent = self.encoder(x)
        recon = self.decoder(latent)
        return recon


class TemporalAutoencoderDetector:
    """
    Tier 2 Temporal Anomaly Detector wrapping PyTorch TemporalAutoencoder.
    """

    def __init__(
        self,
        window_size: int = 30,
        input_dim: int = 3,
        hidden_dim: int = 32,
        latent_dim: int = 16,
        threshold: float = 0.50,
        device: Optional[str] = None,
    ):
        self.window_size = window_size
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
        self.threshold = threshold
        self.mean_mse: float = 0.05
        self.std_mse: float = 0.05

        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.model = TemporalAutoencoder(
            seq_len=window_size,
            input_dim=input_dim,
            hidden_dim=hidden_dim,
            latent_dim=latent_dim,
        ).to(self.device)
        self.model.eval()
        self.is_loaded: bool = False

    def predict_score(self, seq: Union[np.ndarray, torch.Tensor]) -> Union[float, np.ndarray]:
        """
        Compute normalized reconstruction anomaly score S_temporal in [0, 1].
        Input shape: (W, 3) for single sequence, or (Batch, W, 3) for batch.
        """
        if isinstance(seq, np.ndarray):
            if seq.size == 0 or np.all(seq == 0.0):
                return 0.0 if seq.ndim <= 2 else np.zeros(len(seq), dtype=np.float32)
            tensor_x = torch.from_numpy(seq).float()
        else:
            tensor_x = seq.float()

        is_single = (tensor_x.ndim == 2)
        if is_single:
            tensor_x = tensor_x.unsqueeze(0)

        tensor_x = tensor_x.to(self.device)
        self.model.eval()

        with torch.no_grad():
            recon = self.model(tensor_x)
            # Step MSE at current time step (last time step) + overall sequence MSE
            last_step_mse = torch.mean((recon[:, -1, :] - tensor_x[:, -1, :]) ** 2, dim=-1)
            full_seq_mse = torch.mean((recon - tensor_x) ** 2, dim=(1, 2))
            # Blended reconstruction error
            blended_mse = 0.7 * last_step_mse + 0.3 * full_seq_mse
            raw_mse = blended_mse.cpu().numpy()

        # Score normalization against threshold theta
        # S = 1 - exp(-ln(2) * (mse / theta))
        # At mse = threshold, S = 0.50. At mse = 3*threshold, S = 0.875.
        eff_thresh = max(self.threshold, 1e-4)
        scaled_err = raw_mse / eff_thresh
        scores = 1.0 - np.exp(-0.693147 * scaled_err)
        scores = np.clip(scores, 0.0, 1.0)

        if is_single:
            return float(scores[0])
        return scores

    def save(self, filepath: Union[str, Path]) -> None:
        """Persist model state dictionary and metadata to disk."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "model_type": "TemporalAutoencoder",
            "model_state_dict": self.model.state_dict(),
            "window_size": self.window_size,
            "input_dim": self.input_dim,
            "hidden_dim": self.hidden_dim,
            "latent_dim": self.latent_dim,
            "threshold": float(self.threshold),
            "mean_mse": float(self.mean_mse),
            "std_mse": float(self.std_mse),
        }
        torch.save(checkpoint, path)
        logger.info("Saved PyTorch Temporal Autoencoder to %s", path)

    def load(self, filepath: Union[str, Path]) -> "TemporalAutoencoderDetector":
        """Load model state dictionary and configuration from disk."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Model checkpoint not found at {path}")

        checkpoint = torch.load(path, map_location=self.device)
        self.window_size = checkpoint.get("window_size", self.window_size)
        self.input_dim = checkpoint.get("input_dim", self.input_dim)
        self.hidden_dim = checkpoint.get("hidden_dim", self.hidden_dim)
        self.latent_dim = checkpoint.get("latent_dim", self.latent_dim)
        self.threshold = checkpoint.get("threshold", self.threshold)
        self.mean_mse = checkpoint.get("mean_mse", 0.05)
        self.std_mse = checkpoint.get("std_mse", 0.05)

        self.model = TemporalAutoencoder(
            seq_len=self.window_size,
            input_dim=self.input_dim,
            hidden_dim=self.hidden_dim,
            latent_dim=self.latent_dim,
        ).to(self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()
        self.is_loaded = True
        return self


# Backward-compatible alias
TemporalAnomalyDetector = TemporalAutoencoderDetector
