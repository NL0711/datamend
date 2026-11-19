"""Event-coherence context features: how many of a cell's neighbours corroborate the observation on the same day.

A genuine heavy-rain event is spatially coherent: the cells around it are wet or heavy too. A faulty spike is typically isolated. These two
features give the fusion that evidence, separately from "how unusual is this value":

  ``nbr_wet``    share of the usable neighbours with at least ``WET_MM`` mm
  ``nbr_heavy``  share of the usable neighbours at or above their own heavy-rain threshold (``stats.heavy_mm``)

Neighbours come from the same ring as the neighbour baseline: outside the target's hidden disc, so a fault footprint cannot vouch for itself.
They read only the same day's field (no future, no history). They are context, not anomaly scores: high means "corroborated". They are meant
for the learned fusion variants (logistic, boosted), never for the mean or the OR variant. A cell with no usable neighbour gets 0 (no
corroboration), and a cell whose own value is missing gets NaN.
"""

from __future__ import annotations

import warnings
from typing import Dict

import numpy as np

from qc.neighbours import gather, ring_index
from qc.prepare import Prepared
from qc.scoring import Block

CONTEXT = ("nbr_wet", "nbr_heavy")
WET_MM = 1.0


def _features(block: Block, ring: np.ndarray, heavy_mm: np.ndarray, chunk: int = 30):
    obs = block.target
    wet = np.zeros(obs.shape, np.float32)
    heavy = np.zeros(obs.shape, np.float32)
    thr = np.concatenate([heavy_mm.astype(np.float32), np.array([np.nan], np.float32)])[ring]         # (n, K); -1 -> NaN
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for s in range(0, obs.shape[0], chunk):
            nb = gather(obs[s:s + chunk], ring)                                                       # (c, n, K), NaN where unusable
            usable = np.isfinite(nb)
            n = np.maximum(usable.sum(axis=2), 1)
            wet[s:s + chunk] = ((nb >= WET_MM) & usable).sum(axis=2) / n
            heavy[s:s + chunk] = ((nb >= thr[None]) & usable & np.isfinite(thr)[None]).sum(axis=2) / n
    own = np.isfinite(obs)
    return np.where(own, wet, np.nan).astype(np.float32), np.where(own, heavy, np.nan).astype(np.float32)


def context_functions(p: Prepared) -> Dict:
    c = p.cfg.components
    ring = ring_index(p.grid, c.hidden_radius, c.neighbour_baseline.radius)
    cache: Dict = {}

    def pair(block: Block):
        if cache.get("block") is not block:                        # both features come from one pass over the same block object
            cache["block"], cache["val"] = block, _features(block, ring, p.stats.heavy_mm)
        return cache["val"]

    return {"nbr_wet": lambda b: pair(b)[0], "nbr_heavy": lambda b: pair(b)[1]}
