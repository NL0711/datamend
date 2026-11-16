"""Detector registry used by the API and the evaluation harness.

Detectors come from trained artifacts (see ``training/``); nothing is downloaded or run zero-shot.

  RAINFALL_AE_ARTIFACT        path to one artifact directory          -> ``rainfall_ae``
  RAINFALL_ENSEMBLE_ARTIFACTS comma-separated artifact directories    -> ``rainfall_ensemble``
"""

from __future__ import annotations

import os
from typing import Callable, Dict

from detectors.base import AnomalyDetector


class DetectorUnavailable(RuntimeError):
    """The detector is known but not configured (no trained artifact available)."""


def _single() -> AnomalyDetector:
    path = os.environ.get("RAINFALL_AE_ARTIFACT")
    if not path:
        raise DetectorUnavailable("Set RAINFALL_AE_ARTIFACT to a trained artifact directory (python -m training train ...)")
    from detectors.rainfall_ae import RainfallAEDetector
    return RainfallAEDetector(path)


def _ensemble() -> AnomalyDetector:
    paths = [p.strip() for p in os.environ.get("RAINFALL_ENSEMBLE_ARTIFACTS", "").split(",") if p.strip()]
    if not paths:
        raise DetectorUnavailable("Set RAINFALL_ENSEMBLE_ARTIFACTS to comma-separated artifact directories")
    from detectors.ensemble import EnsembleDetector
    from detectors.rainfall_ae import RainfallAEDetector
    return EnsembleDetector([(os.path.basename(p.rstrip("/\\")), RainfallAEDetector(p), 1.0) for p in paths])


DETECTOR_FACTORIES: Dict[str, Callable[[], AnomalyDetector]] = {
    "rainfall_ae": _single,
    "rainfall_ensemble": _ensemble,
}

_cache: Dict[str, AnomalyDetector] = {}


def get_detector(name: str) -> AnomalyDetector:
    """Build (once) and return a detector. ``KeyError`` = unknown name, ``DetectorUnavailable`` = not configured."""
    if name not in DETECTOR_FACTORIES:
        raise KeyError(name)
    if name not in _cache:
        _cache[name] = DETECTOR_FACTORIES[name]()
    return _cache[name]
