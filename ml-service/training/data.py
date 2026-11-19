"""RF25 archive access: one NetCDF file per year -> float32 cubes of shape (T, H, W)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import numpy as np
import xarray as xr

_NAME = re.compile(r"RF25_ind(\d{4})_rfp25\.nc$")


class RainfallArchive:
    """Lazy view over a directory of ``RF25_ind<year>_rfp25.nc`` files.

    Invariants: cubes are float32 mm, off-land / fill cells are NaN, shape is
    always (days, lat, lon). Years that are absent from the directory are
    exposed via ``missing_years`` and are never interpolated.
    """

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._files = {
            int(m.group(1)): p
            for p in sorted(self.data_dir.glob("RF25_ind*_rfp25.nc"))
            if (m := _NAME.search(p.name))
        }
        if not self._files:
            raise FileNotFoundError(f"No RF25_ind<year>_rfp25.nc files in {self.data_dir}")
        self.years: List[int] = sorted(self._files)
        self.missing_years: List[int] = [
            y for y in range(self.years[0], self.years[-1] + 1) if y not in self._files
        ]
        first = self._open(self.years[0])
        self.lat = first["LATITUDE"].values.astype(np.float32)
        self.lon = first["LONGITUDE"].values.astype(np.float32)
        cube = self._cube(first)
        self.land_mask: np.ndarray = ~np.isnan(cube).all(axis=0)  # (H, W)

    def _open(self, year: int) -> xr.Dataset:
        try:
            return xr.open_dataset(self._files[year], engine="scipy")
        except Exception:  # NetCDF4/HDF5 files need the netcdf4/h5netcdf engines
            return xr.open_dataset(self._files[year])

    @staticmethod
    def _cube(ds: xr.Dataset) -> np.ndarray:
        var = ds["RAINFALL"].transpose("TIME", "LATITUDE", "LONGITUDE")
        cube = var.values.astype(np.float32)
        cube[cube < 0] = np.nan  # fill sentinels that survived decoding
        return cube

    def load(self, year: int) -> np.ndarray:
        if year not in self._files:
            raise KeyError(f"Year {year} not in archive (missing: {self.missing_years})")
        with self._open(year) as ds:
            return self._cube(ds)
