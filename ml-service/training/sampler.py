"""Random windows (target + neighbour + climatology + multi-granularity sources) for a set of cells and years."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from training.injection import KINDS, inject
from training.sources import SourceSpec, coarse_cube, meta_array, proxy_specs

log = logging.getLogger(__name__)


def neighbour_stats(cube: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """NaN-aware mean and max over the 8 surrounding cells; NaN where none are valid."""
    _, h, w = cube.shape
    total = np.zeros_like(cube)
    count = np.zeros_like(cube)
    peak = np.full_like(cube, np.nan)
    padded = np.pad(cube, ((0, 0), (1, 1), (1, 1)), constant_values=np.nan)
    for di in range(3):
        for dj in range(3):
            if di == 1 and dj == 1:
                continue
            nb = padded[:, di : di + h, dj : dj + w]
            ok = ~np.isnan(nb)
            total += np.where(ok, nb, 0)
            count += ok
            peak = np.fmax(peak, nb)
    with np.errstate(invalid="ignore", divide="ignore"):
        return total / count, peak


@dataclass
class YearCube:
    """One year of rainfall plus precomputed context, float16 to halve memory.

    ``coarse`` holds derived coarser-granularity sources, keyed ``coarse<block>``.
    """

    rain: np.ndarray
    nmean: np.ndarray
    nmax: np.ndarray
    coarse: Dict[str, np.ndarray] = field(default_factory=dict)

    @classmethod
    def build(cls, cube: np.ndarray, blocks: Sequence[int] = ()) -> "YearCube":
        mean, peak = neighbour_stats(cube)
        return cls(
            cube.astype(np.float16), mean.astype(np.float16), peak.astype(np.float16),
            {f"coarse{b}": coarse_cube(cube, b).astype(np.float16) for b in blocks},
        )


def _static(doy: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    ang = 2 * np.pi * doy / 366.0
    n, w = doy.shape
    return np.stack(
        [np.sin(ang), np.cos(ang), np.broadcast_to(lat[:, None], (n, w)), np.broadcast_to(lon[:, None], (n, w))],
        axis=-1,
    ).astype(np.float32)


class NullStationProvider:
    """Stub for the optional station branch: no station data is available, so every window is
    marked unavailable. Replace with a provider backed by real station series (see
    ``training/stations.py``). Logs a warning once."""

    _warned = False

    def get(self, rows, cols, years_idx, t0, window):
        if not NullStationProvider._warned:
            log.warning("station branch enabled but no station data is configured: "
                        "using the NullStationProvider stub (stations marked unavailable)")
            NullStationProvider._warned = True
        n = len(rows)
        return np.zeros((n, window), np.float32), np.zeros(n, bool)


@dataclass
class Batch:
    x_mm: np.ndarray      # (n, W, 2) mm: [target (maybe corrupted), neighbour mean]
    clean_mm: np.ndarray  # (n, W) uncorrupted target
    labels: np.ndarray    # (n, W) bool, True where injected
    kind: np.ndarray      # (n,) index into KINDS, -1 = clean
    aux_mm: np.ndarray    # (n, W, 2) mm: [neighbour max, day-of-year climatology]
    static: np.ndarray    # (n, W, 4): [sin doy, cos doy, lat 0-1, lon 0-1]
    src_mm: np.ndarray    # (n, S, W) mm per granularity source (0 where unavailable)
    src_meta: np.ndarray  # (n, S, 3) see SourceSpec.meta
    src_mask: np.ndarray  # (n, S) bool, True = source available for this window
    # optional extras (None = not provided)
    valid: Optional[np.ndarray] = None         # (n, W) bool, target value present (not NaN)
    doy: Optional[np.ndarray] = None           # (n, W) int day-of-year index
    cell: Optional[np.ndarray] = None          # (n, 2) int (row, col) of the target cell
    patch: Optional[np.ndarray] = None         # (n, P, W) mm, neighbourhood patch EXCLUDING the centre cell
    patch_valid: Optional[np.ndarray] = None   # (n, P, W) bool
    station_mm: Optional[np.ndarray] = None    # (n, W) mm, station-calibrated value
    station_mask: Optional[np.ndarray] = None  # (n,) bool
    elev: Optional[np.ndarray] = None          # (n,) normalized elevation
    elev_ok: Optional[np.ndarray] = None       # (n,) bool, elevation available

    def slice(self, sl: slice) -> "Batch":
        return Batch(**{f.name: None if getattr(self, f.name) is None else getattr(self, f.name)[sl]
                        for f in fields(self)})

    def with_sources(self, keep: Sequence[bool]) -> "Batch":
        """Copy in which only sources with ``keep[i]`` are available (for ablations)."""
        mask = self.src_mask & np.asarray(keep, dtype=bool)[None, :]
        return Batch(**{**{f.name: getattr(self, f.name) for f in fields(self)},
                        "src_mask": mask, "src_mm": np.where(mask[:, :, None], self.src_mm, 0.0)})

    @classmethod
    def from_windows(cls, x, nbr_mean=None, nbr_max=None, clim=None, doy=None, lat=0.5, lon=0.5,
                     sources=None, source_mask=None, source_meta=None,
                     patch=None, patch_valid=None, n_patch: int = 0, station=None, station_mask=None,
                     elev=None, cell=None) -> "Batch":
        """Inference batch from (n, W) mm windows. NaNs in ``x`` become ``valid=False`` zeros.

        Context left out defaults to the series itself (neutral, but it removes that evidence).
        ``sources`` (n, S, W) / ``source_mask`` / ``source_meta`` feed the multi-granularity model.
        ``patch`` (n, P, W) mm (centre excluded) feeds the multi-scale model; with ``n_patch`` > 0 and
        no patch given, an all-unavailable patch of that size is used.
        """
        x = np.asarray(x, dtype=np.float32)
        valid = np.isfinite(x)
        x = np.nan_to_num(x, nan=0.0)
        n, w = x.shape
        pick = lambda a: x if a is None else np.nan_to_num(np.asarray(a, dtype=np.float32), nan=0.0)
        doy = np.broadcast_to(np.arange(w) if doy is None else np.asarray(doy), (n, w))
        lat = np.broadcast_to(np.asarray(lat, dtype=np.float32), (n,))
        lon = np.broadcast_to(np.asarray(lon, dtype=np.float32), (n,))
        if sources is None:
            sources, source_mask = np.zeros((n, 1, w), np.float32), np.zeros((n, 1), bool)
        sources = np.asarray(sources, dtype=np.float32)
        source_mask = np.ones(sources.shape[:2], bool) if source_mask is None else np.asarray(source_mask, bool)
        source_meta = np.zeros((n, sources.shape[1], 3), np.float32) if source_meta is None else source_meta
        if patch is None:
            patch, patch_valid = np.zeros((n, n_patch, w), np.float32), np.zeros((n, n_patch, w), bool)
        else:
            patch = np.asarray(patch, dtype=np.float32)
            patch_valid = np.isfinite(patch) if patch_valid is None else np.asarray(patch_valid, bool)
            patch = np.nan_to_num(patch, nan=0.0)
        if station is None:
            station, station_mask = np.zeros((n, w), np.float32), np.zeros(n, bool)
        elev_ok = np.zeros(n, bool) if elev is None else np.ones(n, bool)
        return cls(
            np.stack([x, pick(nbr_mean)], -1), x.copy(), np.zeros((n, w), bool),
            np.full(n, -1, dtype=np.int64),
            np.stack([pick(nbr_max), pick(clim)], -1), _static(doy, lat, lon),
            sources, np.asarray(source_meta, np.float32), source_mask,
            valid, np.array(doy), None if cell is None else np.asarray(cell),
            patch, patch_valid, np.asarray(station, np.float32),
            np.ones(n, bool) if station_mask is None else np.asarray(station_mask, bool),
            np.zeros(n, np.float32) if elev is None else np.broadcast_to(np.asarray(elev, np.float32), (n,)).copy(),
            elev_ok,
        )


class WindowSampler:
    """Draws windows only from within a single year's cube, so year gaps and year boundaries
    never create fake continuity. Sources are ``nbr8`` plus every ``coarse<k>`` in the cubes.

    ``patch_size`` (0, 3 or 5) adds a neighbourhood patch that excludes the centre cell, so it cannot
    leak the clean target. ``elevation`` is an optional (H, W) array normalized to 0-1.
    """

    def __init__(
        self,
        cubes: Sequence[YearCube],
        land_mask: np.ndarray,
        cells: Optional[np.ndarray] = None,
        window: int = 30,
        seed: int = 0,
        clim: Optional[np.ndarray] = None,
        lat_norm: Optional[np.ndarray] = None,
        lon_norm: Optional[np.ndarray] = None,
        patch_size: int = 0,
        elevation: Optional[np.ndarray] = None,
        station_provider=None,
    ):
        if patch_size not in (0, 3, 5):
            raise ValueError("patch_size must be 0, 3 or 5")
        self.window = window
        self.rng = np.random.default_rng(seed)
        h, w = land_mask.shape
        flat = np.nonzero(land_mask.ravel())[0] if cells is None else np.asarray(cells)
        self.rows, self.cols = flat // w, flat % w
        self.cubes: List[YearCube] = list(cubes)
        self.clim = clim
        self.lat_norm = np.linspace(0, 1, h, dtype=np.float32) if lat_norm is None else lat_norm
        self.lon_norm = np.linspace(0, 1, w, dtype=np.float32) if lon_norm is None else lon_norm
        self.patch_size, self.elevation, self.station_provider = patch_size, elevation, station_provider
        self.coarse_names: List[str] = list(self.cubes[0].coarse)
        self.specs: List[SourceSpec] = proxy_specs([int(n[len("coarse"):]) for n in self.coarse_names])
        self._meta = meta_array(self.specs)
        weights = np.array([c.rain.shape[0] - window + 1 for c in self.cubes], dtype=float)
        self._weights = weights / weights.sum()

    @property
    def n_patch(self) -> int:
        return self.patch_size ** 2 - 1 if self.patch_size else 0

    def _gather_patch(self, yi, t0, rows, cols, w):
        r = self.patch_size // 2
        offs = [(dr, dc) for dr in range(-r, r + 1) for dc in range(-r, r + 1) if (dr, dc) != (0, 0)]
        n, (h, wd) = len(yi), self.cubes[0].rain.shape[1:]
        out = np.zeros((n, len(offs), w), np.float32)
        ok = np.zeros((n, len(offs), w), bool)
        tt = t0[:, None] + np.arange(w)[None, :]
        for y in np.unique(yi):
            ix = np.nonzero(yi == y)[0]
            rain = self.cubes[y].rain
            for p, (dr, dc) in enumerate(offs):
                rr, cc = rows[ix] + dr, cols[ix] + dc
                inb = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < wd)
                v = rain[tt[ix], np.clip(rr, 0, h - 1)[:, None], np.clip(cc, 0, wd - 1)[:, None]].astype(np.float32)
                good = inb[:, None] & np.isfinite(v)
                out[ix, p], ok[ix, p] = np.where(good, v, 0.0), good
        return out, ok

    def batch(self, n: int, inject_rate: float = 0.0, kinds: Sequence[str] = KINDS,
              source_dropout: float = 0.0) -> Batch:
        """``source_dropout``: each granularity source is hidden independently per window with this
        probability, so the model learns to work with whatever sources are present."""
        w, s = self.window, len(self.specs)
        xs, nm, nx, cl = (np.empty((n, w), dtype=np.float32) for _ in range(4))
        src = np.zeros((n, s, w), dtype=np.float32)
        doy = np.empty((n, w), dtype=np.int64)
        t0s = np.empty(n, dtype=np.int64)
        yi = self.rng.choice(len(self.cubes), size=n, p=self._weights)
        ci = self.rng.integers(0, self.rows.size, size=n)
        rows, cols = self.rows[ci], self.cols[ci]
        for k in range(n):
            cube = self.cubes[yi[k]]
            r, c = rows[k], cols[k]
            t0 = int(self.rng.integers(0, cube.rain.shape[0] - w + 1))
            t0s[k] = t0
            sl = slice(t0, t0 + w)
            xs[k], nm[k], nx[k] = cube.rain[sl, r, c], cube.nmean[sl, r, c], cube.nmax[sl, r, c]
            src[k, 0] = nm[k]
            for j, name in enumerate(self.coarse_names, start=1):
                src[k, j] = cube.coarse[name][sl, r, c]
            doy[k] = np.arange(t0, t0 + w)
            cl[k] = self.clim[np.minimum(doy[k], 365), r, c] if self.clim is not None else cube.rain[sl, r, c]
        valid = np.isfinite(xs)
        # NaNs carry no signal: zero-fill all channels; `valid` keeps the mask for losses and scores.
        xs, nm, nx, cl, src = (np.nan_to_num(a, nan=0.0) for a in (xs, nm, nx, cl, src))
        mask = self.rng.random((n, s)) >= source_dropout if source_dropout > 0 else np.ones((n, s), bool)
        src = np.where(mask[:, :, None], src, 0.0)
        corrupted, labels, kind = inject(xs, self.rng, inject_rate, kinds)
        labels &= valid
        patch = pvalid = None
        if self.patch_size:
            patch, pvalid = self._gather_patch(yi, t0s, rows, cols, w)
        else:
            patch, pvalid = np.zeros((n, 0, w), np.float32), np.zeros((n, 0, w), bool)
        if self.station_provider is not None:
            st, st_mask = self.station_provider.get(rows, cols, yi, t0s, w)
        else:
            st, st_mask = np.zeros((n, w), np.float32), np.zeros(n, bool)
        if self.elevation is not None:
            elev = self.elevation[rows, cols].astype(np.float32)
            elev_ok = np.isfinite(elev)
            elev = np.nan_to_num(elev, nan=0.0)
        else:
            elev, elev_ok = np.zeros(n, np.float32), np.zeros(n, bool)
        return Batch(
            np.stack([corrupted, nm], -1), xs, labels, kind,
            np.stack([nx, cl], -1), _static(doy, self.lat_norm[rows], self.lon_norm[cols]),
            src, np.broadcast_to(self._meta, (n, s, 3)).copy(), mask,
            valid, doy, np.stack([rows, cols], -1), patch, pvalid, st, st_mask, elev, elev_ok,
        )
