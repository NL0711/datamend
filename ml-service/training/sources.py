"""Data sources at different granularities, described uniformly.

A *source* is any series that observes the same weather as the target at some other
scale: a coarser grid (IMD, CHIRPS, IMERG), nearby stations, radar. The
multi-scale model never cares what a source is, only its ``SourceSpec`` (resolution,
distance) and whether it is available for a given window.

Until real second sources are wired in, ``proxy_specs`` / ``coarse_cube`` derive coarser
sources from RF25 itself (block means) so the machinery can be trained and tested today.
Proxy sources are a stand-in: they prove the structure, not the physics of IMERG vs. a
street-level gauge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

KM_PER_CELL = 27.8  # 0.25 degrees


@dataclass(frozen=True)
class SourceSpec:
    name: str
    resolution_km: float
    kind: str = "grid"  # grid | station | radar | model

    def meta(self, distance_km: float = 0.0) -> List[float]:
        """Per-source scalars the model sees: [log10(resolution)/3, distance/100 km, 1]."""
        return [float(np.log10(max(self.resolution_km, 0.1)) / 3.0), float(distance_km) / 100.0, 1.0]


def proxy_specs(blocks: Sequence[int]) -> List[SourceSpec]:
    """``nbr8`` (mean of the 8 surrounding cells) plus one block-mean source per entry in ``blocks``."""
    return [SourceSpec("nbr8", KM_PER_CELL)] + [
        SourceSpec(f"coarse{b}", KM_PER_CELL * b) for b in blocks
    ]


def meta_array(specs: Sequence[SourceSpec], distance_km: Optional[dict] = None) -> np.ndarray:
    """(S, 3) float32 metadata, optionally overriding each source's distance to the target."""
    d = distance_km or {}
    return np.array([s.meta(d.get(s.name, 0.0)) for s in specs], dtype=np.float32)


def coarse_cube(cube: np.ndarray, block: int) -> np.ndarray:
    """Block-mean a (T, H, W) cube and broadcast each block back onto the fine grid.

    Each fine cell therefore sees the coarse value covering it, which is exactly what a
    coarser product would report at that location. Off-land cells are ignored in the mean.
    """
    t, h, w = cube.shape
    ph, pw = (-h) % block, (-w) % block
    padded = np.pad(cube, ((0, 0), (0, ph), (0, pw)), constant_values=np.nan)
    ok = ~np.isnan(padded)

    def blk(a: np.ndarray) -> np.ndarray:
        return a.reshape(t, (h + ph) // block, block, (w + pw) // block, block).sum(axis=(2, 4))

    with np.errstate(invalid="ignore", divide="ignore"):
        mean = blk(np.where(ok, padded, 0.0)) / blk(ok.astype(np.float32))
    return np.repeat(np.repeat(mean, block, axis=1), block, axis=2)[:, :h, :w].astype(np.float32)
