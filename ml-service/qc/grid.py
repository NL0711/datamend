"""RF25 access for the QC system: data-contract check and land-only daily series.

Two shapes are used throughout ``qc``:
  field   (T, H, W) float32 mm, NaN off land          -- what the spatial component and fault injection see
  series  (T, n_land) float32 mm, land cells only     -- compact form for per-cell statistics and the temporal component
``Grid.to_field`` / ``Grid.to_series`` convert between them. Original values are never modified in place.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import xarray as xr

from training.data import RainfallArchive


class ContractError(RuntimeError):
    """The data does not match the data contract. The message says what to fix."""


@dataclass
class Grid:
    lat: np.ndarray          # (H,)
    lon: np.ndarray          # (W,)
    land: np.ndarray         # (H, W) bool
    rows: np.ndarray         # (n_land,) row index of each land cell, row-major order
    cols: np.ndarray         # (n_land,)

    @classmethod
    def from_land(cls, lat, lon, land) -> "Grid":
        rows, cols = np.nonzero(land)
        return cls(np.asarray(lat, np.float32), np.asarray(lon, np.float32), land.astype(bool), rows, cols)

    @property
    def shape(self):
        return self.land.shape

    @property
    def n_land(self) -> int:
        return int(self.rows.size)

    def to_series(self, field: np.ndarray) -> np.ndarray:
        """(..., H, W) -> (..., n_land)."""
        return field[..., self.rows, self.cols]

    def to_field(self, series: np.ndarray, fill=np.nan) -> np.ndarray:
        """(..., n_land) -> (..., H, W) with ``fill`` off land."""
        out = np.full(series.shape[:-1] + self.shape, fill, dtype=series.dtype)
        out[..., self.rows, self.cols] = series
        return out

    def land_hash(self) -> str:
        return hashlib.sha256(np.packbits(self.land).tobytes()).hexdigest()[:16]


def check_contract(data_dir: Path, years: Sequence[int], spec) -> Dict:
    """Validate every requested year file against the data contract. Raises ``ContractError`` on the first
    violation; returns a small report (land mask, per-year day counts) when everything holds.

    ``spec`` is ``cfg.grid``: n_lat, n_lon, lat0, lon0, step, land_cells, fill_value, units.
    """
    data_dir = Path(data_dir)
    land_ref = None
    days: Dict[int, int] = {}
    missing_on_land: Dict[int, int] = {}
    for year in years:
        path = data_dir / f"RF25_ind{year}_rfp25.nc"
        if not path.is_file():
            raise ContractError(f"{path.name} is missing from {data_dir}. The contract needs every year {years[0]}-{years[-1]}.")
        try:
            ds = xr.open_dataset(path, engine="scipy", mask_and_scale=False)
        except Exception:
            ds = xr.open_dataset(path, mask_and_scale=False)
        with ds:
            if "RAINFALL" not in ds:
                raise ContractError(f"{path.name}: variable RAINFALL not found (variables: {list(ds.data_vars)}).")
            var = ds["RAINFALL"]
            if tuple(var.dims) != ("TIME", "LATITUDE", "LONGITUDE"):
                raise ContractError(f"{path.name}: RAINFALL dims are {var.dims}, expected (TIME, LATITUDE, LONGITUDE).")
            units = str(var.attrs.get("units", "")).strip().lower()
            if spec.units and units and units != spec.units:
                raise ContractError(f"{path.name}: units are {units!r}, expected {spec.units!r}.")
            lat, lon = ds["LATITUDE"].values.astype(float), ds["LONGITUDE"].values.astype(float)
            for name, arr, n, first in (("LATITUDE", lat, spec.n_lat, spec.lat0), ("LONGITUDE", lon, spec.n_lon, spec.lon0)):
                want = first + spec.step * np.arange(n)
                if arr.size != n or not np.allclose(arr, want, atol=1e-4):
                    raise ContractError(
                        f"{path.name}: {name} has {arr.size} points from {arr[0]} to {arr[-1]}; expected {n} points "
                        f"from {want[0]} to {want[-1]} in steps of {spec.step}."
                    )
            time = ds["TIME"].values.astype("datetime64[D]")
            if np.unique(time).size != time.size:
                raise ContractError(f"{path.name}: duplicate timestamps in TIME.")
            if time.size > 1 and not (np.diff(time).astype(int) == 1).all():
                raise ContractError(f"{path.name}: TIME is not strictly daily and increasing.")
            first_day, last_day = np.datetime64(f"{year}-01-01"), np.datetime64(f"{year}-12-31")
            if time[0] != first_day or time[-1] != last_day:
                raise ContractError(f"{path.name}: TIME runs {time[0]} to {time[-1]}, expected {first_day} to {last_day}.")
            raw = var.values
            fill = raw == spec.fill_value
            bad = (raw < 0) & ~fill
            if bad.any():
                raise ContractError(
                    f"{path.name}: {int(bad.sum())} negative values other than the fill value {spec.fill_value} "
                    f"(for example {float(raw[bad][0])}). Negative rainfall must not be silently turned into missing."
                )
            if np.isnan(raw).any() and not np.isnan(spec.fill_value):
                fill = fill | np.isnan(raw)
            land = ~fill.all(axis=0)
            if land_ref is None:
                land_ref = land
                if spec.land_cells and int(land.sum()) != spec.land_cells:
                    raise ContractError(f"{path.name}: {int(land.sum())} land cells, expected {spec.land_cells}.")
            elif not np.array_equal(land, land_ref):
                raise ContractError(
                    f"{path.name}: the land mask differs from {years[0]} in {int((land != land_ref).sum())} cells."
                )
            days[year] = int(time.size)
            missing_on_land[year] = int(fill[:, land].sum())
    return {"years": [int(years[0]), int(years[-1])], "days": days, "missing_on_land": missing_on_land,
            "land_cells": int(land_ref.sum()), "lat": lat.astype(np.float32), "lon": lon.astype(np.float32), "land": land_ref}


class SeriesStore:
    """Land-only daily series per year, cached as ``cache/land_<year>.npy`` (float32, about 7 MB a year)."""

    def __init__(self, data_dir: Path, cache_dir: Path):
        self.arch = RainfallArchive(data_dir)
        self.grid = Grid.from_land(self.arch.lat, self.arch.lon, self.arch.land_mask)
        self.cache_dir = Path(cache_dir)

    def year(self, year: int) -> np.ndarray:
        """(days, n_land) float32 mm for one year; NaN where a land value is missing."""
        path = self.cache_dir / f"land_{year}_{self.grid.land_hash()}.npy"
        if path.is_file():
            return np.load(path)
        series = self.grid.to_series(self.arch.load(year)).astype(np.float32)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.npy")
        np.save(tmp, series)
        tmp.replace(path)
        return series

    def years(self, years: Sequence[int]):
        """Concatenate years. Returns ``(series (T, n_land), year (T,), doy (T,) 0-based)``."""
        parts: List[np.ndarray] = [self.year(y) for y in years]
        year = np.concatenate([np.full(p.shape[0], y, np.int16) for p, y in zip(parts, years)])
        doy = np.concatenate([np.arange(p.shape[0], dtype=np.int16) for p in parts])
        return np.concatenate(parts, axis=0), year, doy
