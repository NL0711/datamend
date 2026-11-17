"""Versioned model artifact: weights + transform + config + calibration + provenance."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import numpy as np
import torch

from training.calibration import Calibration
from training.trainer import LocalTrainer, TrainConfig
from training.transform import RainfallTransform

FORMAT_VERSION = 2


@dataclass
class Artifact:
    trainer: LocalTrainer
    calibration: Calibration
    meta: Dict[str, Any] = field(default_factory=dict)  # years, metrics, history, ...


def _jsonable(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    raise TypeError(f"not JSON serialisable: {type(o)}")


def save(art: Artifact, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    torch.save(art.trainer.state_dict(), out / "model.pt")
    (out / "manifest.json").write_text(json.dumps({
        "format_version": FORMAT_VERSION,
        "config": art.trainer.config.to_dict(),
        "transform": art.trainer.transform.to_dict(),
        "calibration": art.calibration.to_dict(),
        "meta": art.meta,
    }, indent=2, default=_jsonable))
    return out


def load(path: str | Path, device: str = "cpu") -> Artifact:
    p = Path(path)
    m = json.loads((p / "manifest.json").read_text())
    if m["format_version"] != FORMAT_VERSION:
        raise ValueError(f"Unsupported artifact version {m['format_version']} (need {FORMAT_VERSION}); retrain")
    cfg = TrainConfig(**{**m["config"], "device": device})
    trainer = LocalTrainer(RainfallTransform.from_dict(m["transform"]), cfg)
    trainer.load_state(torch.load(p / "model.pt", map_location=device))
    return Artifact(trainer, Calibration.from_dict(m["calibration"]), m["meta"])
