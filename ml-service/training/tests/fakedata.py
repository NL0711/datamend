"""Tiny synthetic RF25-like archive for tests (8x9 grid, 60 days per year, 2002 missing)."""

import numpy as np
import xarray as xr

YEARS = [2000, 2001, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010]


def write_year(path, year, rng, days=60, scale=1.0):
    rain = (rng.gamma(0.3, 8.0, size=(days, 8, 9)) * scale).astype("float32")
    rain[rng.random(rain.shape) < 0.6] = 0.0
    rain[:, :2, :] = np.nan  # off-land rows
    xr.Dataset(
        {"RAINFALL": (("TIME", "LATITUDE", "LONGITUDE"), rain)},
        coords={"TIME": np.datetime64(f"{year}-01-01") + np.arange(days),
                "LATITUDE": np.linspace(7, 12, 8), "LONGITUDE": np.linspace(70, 75, 9)},
    ).to_netcdf(path, engine="scipy")


def write_fake_archive(root, years=YEARS):
    rng = np.random.default_rng(0)
    for y in years:
        write_year(root / f"RF25_ind{y}_rfp25.nc", y, rng)
    return root
