"""Ensemble branches. Each turns a ``Batch`` into raw per-timestep scores (n, W), higher = more anomalous.

Branches: ``rule`` (daily rule engine), ``stat`` (per-cell per-day climatological bound), and one
``TrainerBranch`` per (trained model, score stream): lstm_baseline, RainNet, the multi-scale model, and
the supervised head (as just one branch among the others, never as a stacking meta-model).
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np

from ensemble.statbaseline import StatBaseline
from training.artifact import Artifact
from training.sampler import Batch

log = logging.getLogger(__name__)

STUCK_RUN = 5          # identical non-zero daily values in a row
EXTREME_MM = (300.0, 1000.0)  # severity ramps from 0 at 300 mm/day to 1 at 1000 mm/day


class Branch:
    name: str = ""
    norm: str = "rank"  # "rank" or "likelihood" (likelihood branches also get a temperature-scaled probability)

    def raw(self, b: Batch, cache: Dict) -> Optional[np.ndarray]:  # pragma: no cover - interface
        raise NotImplementedError


def daily_rule_severity(x: np.ndarray) -> np.ndarray:
    """Severity in [0, 1] from the daily rules: negative rainfall (1.0), implausibly large values
    (ramp from 300 to 1000 mm/day) and stuck runs of identical non-zero values (0.8)."""
    x = np.asarray(x, float)
    neg = (x < 0).astype(float)
    ext = np.clip((x - EXTREME_MM[0]) / (EXTREME_MM[1] - EXTREME_MM[0]), 0.0, 1.0)
    n, w = x.shape
    eq = np.zeros((n, w), bool)
    eq[:, 1:] = (x[:, 1:] == x[:, :-1]) & (x[:, 1:] > 0)
    run = np.ones((n, w), int)
    for t in range(1, w):
        run[:, t] = np.where(eq[:, t], run[:, t - 1] + 1, 1)
    flat = run >= STUCK_RUN
    for t in range(w - 2, -1, -1):  # extend flag backwards over the whole run
        flat[:, t] |= flat[:, t + 1] & eq[:, t + 1]
    return np.maximum.reduce([neg, ext, 0.8 * flat])


class RuleBranch(Branch):
    name = "rule"

    def raw(self, b, cache):
        sev = daily_rule_severity(b.x_mm[..., 0])
        return np.where(b.valid, sev, 0.0) if b.valid is not None else sev


class StatBranch(Branch):
    name = "stat"

    def __init__(self, baseline: StatBaseline):
        self.baseline = baseline

    def raw(self, b, cache):
        r = self.baseline.raw(b)
        if r is None:
            log.warning("stat branch inactive: batch has no cell/doy information")
            return None
        return np.where(b.valid, r, 0.0) if b.valid is not None else r


class TrainerBranch(Branch):
    """One score stream (``nll``, ``head``, ``resid``, ``recon``) of a trained model.

    ``dirname`` is where the model artifact is stored under the pipeline directory. Branches that share
    a model share an ``Artifact`` and a ``dirname`` (the model is scored once per batch).
    """

    def __init__(self, name: str, art: Artifact, stream: str, norm: str = "rank", dirname: Optional[str] = None):
        self.name, self.art, self.stream, self.norm = name, art, stream, norm
        self.dirname = dirname or name

    def raw(self, b, cache):
        key = id(self.art)
        if key not in cache:
            cache[key] = self.art.trainer.score(b)
        streams = cache[key]
        if self.stream not in streams:
            raise KeyError(f"model for branch {self.name!r} has no stream {self.stream!r}: {sorted(streams)}")
        return streams[self.stream]
