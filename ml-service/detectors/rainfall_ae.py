"""Trained rainfall model as an ``AnomalyDetector`` (loads a training artifact)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from detectors.base import AnomalyDetector
from detectors.scoring import api_score
from training import artifact
from training.sampler import Batch
from training.sources import SourceSpec, meta_array


class RainfallAEDetector(AnomalyDetector):
    """Works for any trained arch (``rainnet``, ``msnet``, ``lstm_ae``) from a training artifact."""

    def __init__(self, artifact_dir: str, device: str = "cpu"):
        self._art = artifact.load(artifact_dir, device)
        self.specs: List[SourceSpec] = [SourceSpec(**d) for d in self._art.meta.get("sources", [])]

    @property
    def threshold(self) -> float:
        return self._art.calibration.threshold

    @property
    def window(self) -> int:
        return self._art.trainer.config.window

    def detect_detailed(self, data: Any, context: Optional[Dict[str, Any]] = None) -> Dict[str, np.ndarray]:
        """``data``: (T,) rainfall in mm. Returns calibrated ``scores`` and boolean ``flags``.

        ``context`` (all optional, each (T,) aligned with ``data`` unless noted):
          ``nbr_mean`` / ``nbr_max``: mean / max of surrounding cells or stations, in mm
          ``clim``: day-of-year climatology in mm;  ``doy0``: day-of-year index of data[0]
          ``lat`` / ``lon``: floats in 0-1 over the training grid
          ``sources``: {source name: (T,) mm} for the granularity sources the model was trained with
          ``source_distance_km``: {source name: km from the target}

        Anything omitted is treated as unavailable (multi-scale model: masked out; others: neutral).
        Unavailable context removes evidence, so spatial and seasonal anomalies are caught less reliably.
        """
        ctx = context or {}
        x = np.asarray(data, dtype=np.float32).ravel()
        w, n = self.window, len(x)
        if n < w:
            return {"scores": np.zeros(n, dtype=np.float32), "flags": np.zeros(n, dtype=bool)}
        starts = list(range(0, n - w + 1, max(w // 2, 1)))
        if starts[-1] != n - w:
            starts.append(n - w)  # make sure the tail is covered
        idx = np.array([np.arange(s, s + w) for s in starts])

        def win(key):
            a = ctx.get(key)
            return None if a is None else np.asarray(a, dtype=np.float32)[idx]

        sources = mask = meta = None
        if self.specs:
            avail = dict(ctx.get("sources") or {})
            if ctx.get("nbr_mean") is not None:
                avail.setdefault("nbr8", ctx["nbr_mean"])
            sources = np.zeros((len(idx), len(self.specs), w), np.float32)
            mask = np.zeros((len(idx), len(self.specs)), bool)
            for j, sp in enumerate(self.specs):
                if sp.name in avail:
                    sources[:, j] = np.asarray(avail[sp.name], dtype=np.float32)[idx]
                    mask[:, j] = True
            meta = np.broadcast_to(meta_array(self.specs, ctx.get("source_distance_km")),
                                   (len(idx), len(self.specs), 3))

        doy = (ctx.get("doy0", 0) + idx) % 366
        batch = Batch.from_windows(x[idx], win("nbr_mean"), win("nbr_max"), win("clim"), doy,
                                   ctx.get("lat", 0.5), ctx.get("lon", 0.5), sources, mask, meta)
        fused = self._art.calibration.fuse(self._art.trainer.score(batch))
        scores = np.full(n, -np.inf, dtype=np.float32)
        for row, ix in zip(fused, idx):
            scores[ix] = np.maximum(scores[ix], row)
        return {"scores": scores, "flags": scores >= self.threshold}

    def detect(self, data: Any, context: Optional[Dict[str, Any]] = None) -> np.ndarray:
        """API contract: per-row scores in [0, 1] where the calibrated threshold maps to 0.8.

        ``data`` is (T,) or (T, C) rainfall in mm; multiple columns are scored independently and
        max-pooled. ``context`` applies to 1-D input only.
        """
        x = np.asarray(data, dtype=np.float64)
        if x.ndim == 2 and x.shape[1] > 1:
            if context:
                raise ValueError("context is only supported for a single series")
            raw = np.max([self.detect_detailed(x[:, j])["scores"] for j in range(x.shape[1])], axis=0)
        else:
            raw = self.detect_detailed(x.ravel(), context)["scores"]
        return api_score(raw, self.threshold)
