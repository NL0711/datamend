"""Optional elevation covariate."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)


def load_elevation(path: Optional[str], shape: Tuple[int, int]) -> Optional[np.ndarray]:
    """Elevation on the rainfall grid, min-max normalized to 0-1, or None.

    Accepts a ``.npy`` array of shape (H, W) matching the rainfall grid. With no path, a missing file
    or a shape mismatch it logs a warning and returns None: the model then sees elevation as
    "unavailable" (a zero value plus an availability flag) instead of failing.
    """
    if not path:
        log.warning("no elevation file configured: elevation is marked unavailable")
        return None
    p = Path(path)
    if not p.exists() or p.suffix != ".npy":
        log.warning("elevation file %s not found or not a .npy array: elevation is marked unavailable", p)
        return None
    e = np.load(p).astype(np.float32)
    if e.shape != tuple(shape):
        log.warning("elevation shape %s does not match the grid %s: elevation is marked unavailable", e.shape, shape)
        return None
    lo, hi = np.nanmin(e), np.nanmax(e)
    return ((e - lo) / max(hi - lo, 1e-6)).astype(np.float32)
