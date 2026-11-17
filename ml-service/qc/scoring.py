"""What a component is asked to score: one year of observed values, with history days in front.

``Block.obs`` is (pad + T, n_land): ``pad`` history days followed by the T days to score. History comes from
the previous year: its benchmark (corrupted) version when that year is in the same split, otherwise the
original values. The first year of the archive gets NaN history. A component returns (T, n_land) float32,
higher = more anomalous, NaN where it cannot score (missing observation).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from qc.benchmark import BenchYear, load_bench_year
from qc.prepare import Prepared


@dataclass
class Block:
    year: int
    split: str                      # val, test, stress, or "clean" for uncorrupted data
    obs: np.ndarray                 # (pad + T, n_land) mm
    pad: int
    doy: np.ndarray                 # (pad + T,) 0-based day of year of every row
    bench: Optional[BenchYear]      # labels and masks; None for clean blocks

    @property
    def days(self) -> int:
        return self.obs.shape[0] - self.pad

    @property
    def target(self) -> np.ndarray:
        return self.obs[self.pad:]


def _history(p: Prepared, year: int, split: Optional[str], pad: int):
    prev = year - 1
    if prev not in p.store.arch.years:
        n = p.grid.n_land
        return np.full((pad, n), np.nan, np.float32), np.arange(365 - pad, 365, dtype=np.int16)
    if split in ("val", "test", "stress") and prev in p.split.years[split]:
        series = load_bench_year(p, split, prev).corrupted
    else:
        series = p.store.year(prev)
    t = series.shape[0]
    return series[t - pad:], np.arange(t - pad, t, dtype=np.int16)


def make_block(p: Prepared, year: int, split: Optional[str] = None, pad: int = 90) -> Block:
    """``split=None`` gives the uncorrupted year (used to set false-alarm thresholds on clean data)."""
    bench = load_bench_year(p, split, year) if split else None
    cur = bench.corrupted if bench is not None else p.store.year(year)
    hist, hdoy = _history(p, year, split, pad)
    obs = np.concatenate([hist, cur], axis=0).astype(np.float32)
    doy = np.concatenate([hdoy, np.arange(cur.shape[0], dtype=np.int16)])
    return Block(int(year), split or "clean", obs, pad, doy, bench)


class ScoreStore:
    """Scores on disk: ``<run>/scores/<component>/<split>_<year>.npy`` (float32, (T, n_land))."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, component: str, split: str, year: int) -> Path:
        return self.root / component / f"{split}_{year}.npy"

    def has(self, component: str, split: str, year: int) -> bool:
        return self.path(component, split, year).is_file()

    def save(self, component: str, split: str, year: int, score: np.ndarray) -> None:
        path = self.path(component, split, year)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.npy")
        np.save(tmp, score.astype(np.float32))
        tmp.replace(path)

    def load(self, component: str, split: str, year: int) -> np.ndarray:
        return np.load(self.path(component, split, year))
