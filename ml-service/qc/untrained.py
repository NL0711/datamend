"""Components and baselines that need no training: rules, the slow component, and the neighbour-average baseline.

All are causal in time (they read day t and earlier) and score every land cell-day. Reference statistics
come from training years only.

rules      max of: implausibly large value and stuck run (existing daily rules), value above the
           climatological upper bound (existing statistical baseline), and a day-to-day step rule (new).
slow       trailing 30- and 90-day totals compared with (a) the cell's own training-year totals for that
           day of year, as a robust z (median and MAD across years), and (b) the same totals at surrounding
           cells outside the hidden disc, as a robust z (median and MAD across neighbours). Score = the
           larger, over the two windows, of the mean of |z_own| and |z_neighbours|.
neighbour  baseline: residual of log1p(value) from the mean of the surrounding cells outside the hidden
           disc on the same day, divided by their spread.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Sequence

import numpy as np

from ensemble.branches import daily_rule_severity
from qc.neighbours import gather
from qc.scoring import Block
from qc.splits import Split, assert_years_allowed
from qc.stats import TrainStats

MAD_TO_SIGMA = 1.4826


# ---------------------------------------------------------------------------------------------- rules

def rules_score(block: Block, stats: TrainStats) -> np.ndarray:
    x = block.obs                                                    # (pad + T, n)
    daily = daily_rule_severity(np.nan_to_num(x, nan=0.0).T).T        # stuck runs may start in the history days
    bound = stats.bound_mm[np.minimum(block.doy, 365)] + 1.0          # (pad + T, n); +1 mm floor as in StatBaseline
    over = np.clip((x / bound - 1.0) / 2.0, 0.0, 1.0)                 # 0 at the bound, 1 at three times the bound
    step = np.zeros_like(x)
    step[1:] = np.abs(x[1:] - x[:-1])
    jump = np.clip((step / bound - 1.0) / 2.0, 0.0, 1.0)              # a day-to-day change larger than the bound
    sev = np.fmax(np.fmax(daily, over), jump)[block.pad:]
    return np.where(np.isfinite(block.target), sev, np.nan).astype(np.float32)


# ---------------------------------------------------------------------------------------------- slow

def trailing_total(x: np.ndarray, window: int) -> np.ndarray:
    """Sum over days t-window+1 .. t (missing values count as 0). Rows with less than a full window are NaN."""
    c = np.cumsum(np.nan_to_num(x, nan=0.0), axis=0, dtype=np.float64)
    out = np.full(x.shape, np.nan, np.float32)
    out[window - 1] = c[window - 1]
    out[window:] = c[window:] - c[:-window]
    return out


@dataclass
class SlowReference:
    years: Sequence[int]
    windows: Sequence[int]
    median: Dict[int, np.ndarray]      # window -> (366, n_land) median trailing total for that day of year
    mad: Dict[int, np.ndarray]         # window -> (366, n_land)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {f"median_{w}": self.median[w] for w in self.windows}
        arrays.update({f"mad_{w}": self.mad[w] for w in self.windows})
        np.savez_compressed(path, years=np.array(self.years), windows=np.array(self.windows), **arrays)

    @classmethod
    def load(cls, path: Path) -> "SlowReference":
        z = np.load(path)
        ws = [int(w) for w in z["windows"]]
        return cls([int(y) for y in z["years"]], ws, {w: z[f"median_{w}"] for w in ws}, {w: z[f"mad_{w}"] for w in ws})


def fit_slow_reference(series: np.ndarray, year: np.ndarray, doy: np.ndarray, split: Split, windows=(30, 90)) -> SlowReference:
    """``series`` is the contiguous training-year series (T, n_land) with its ``year`` and ``doy`` per row."""
    years = sorted(int(y) for y in np.unique(year))
    assert_years_allowed("slow reference", years, split, "train")
    med, mad = {}, {}
    for w in windows:
        tot = trailing_total(series, w)
        m = np.full((366, series.shape[1]), np.nan, np.float32)
        d = np.full((366, series.shape[1]), np.nan, np.float32)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            for k in range(366):
                rows = tot[doy == k]
                if rows.size:
                    m[k] = np.nanmedian(rows, axis=0)
                    d[k] = np.nanmedian(np.abs(rows - m[k]), axis=0)
        m[365] = np.where(np.isfinite(m[365]), m[365], m[364])        # day 366 exists in leap years only
        d[365] = np.where(np.isfinite(d[365]), d[365], d[364])
        med[int(w)], mad[int(w)] = m, d
    return SlowReference(years, [int(w) for w in windows], med, mad)


def slow_score(block: Block, ref: SlowReference, ring: np.ndarray, floor_mm: float = 5.0, chunk: int = 60) -> np.ndarray:
    """``ring`` is (n_land, K) neighbour indices outside the hidden disc (see ``qc.neighbours.ring_index``)."""
    T = block.days
    best = np.zeros((T, block.obs.shape[1]), np.float32)
    doy = np.minimum(block.doy[block.pad:], 365)
    for w in ref.windows:
        tot = trailing_total(block.obs, w)[block.pad:]                              # NaN where history is too short
        med, mad = ref.median[w][doy], ref.mad[w][doy]
        z_own = np.abs(tot - med) / (MAD_TO_SIGMA * mad + floor_mm)
        anom = np.log1p(tot) - np.log1p(med)                                        # relative anomaly of the total
        z_nb = np.zeros_like(anom)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            for s in range(0, T, chunk):
                nb = gather(anom[s:s + chunk], ring)                                # (t, n, K)
                nmed = np.nanmedian(nb, axis=2)
                nmad = np.nanmedian(np.abs(nb - nmed[:, :, None]), axis=2)
                z_nb[s:s + chunk] = np.abs(anom[s:s + chunk] - nmed) / (MAD_TO_SIGMA * nmad + 0.1)
        z_nb = np.nan_to_num(z_nb, nan=0.0)                                         # no usable neighbours: no evidence
        best = np.fmax(best, np.nan_to_num(0.5 * (z_own + z_nb), nan=0.0))
    return np.where(np.isfinite(block.target), best, np.nan).astype(np.float32)


# ---------------------------------------------------------------------------------------------- neighbour baseline

def neighbour_score(block: Block, ring: np.ndarray, floor: float = 1.0, chunk: int = 30) -> np.ndarray:
    z = np.log1p(np.clip(block.target, 0, None))
    out = np.zeros_like(z)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for s in range(0, z.shape[0], chunk):
            nb = gather(z[s:s + chunk], ring)
            out[s:s + chunk] = np.abs(z[s:s + chunk] - np.nanmean(nb, axis=2)) / (np.nanstd(nb, axis=2) + floor)
    out = np.nan_to_num(out, nan=0.0)                                               # no neighbours: no evidence
    return np.where(np.isfinite(block.target), out, np.nan).astype(np.float32)
