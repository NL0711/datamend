"""Small synthetic RF25-like world for the QC tests: a 24 x 30 grid, full calendar years, three clients."""

import numpy as np
import pytest
import xarray as xr

from qc.clients import save_client_map
from qc.config import load_config

H, W = 24, 30
YEARS = list(range(1990, 2002))      # train 1990-1995, val 1996-1999, test 2000-2001


def _land():
    land = np.ones((H, W), bool)
    land[:2, :] = False               # sea rows
    land[:, :2] = False               # sea columns
    return land


def _client_map():
    cm = np.zeros((H, W), np.int8)
    cm[:, :12] = 1
    cm[:, 12:21] = 2
    cm[:, 21:] = 3                    # client 3 is the held-out (unseen) client
    cm[~_land()] = 0
    return cm


def write_year(path, year, rng, negative=False, short=False):
    days = 366 if year % 4 == 0 else 365
    if short:
        days -= 5
    doy = np.arange(days)
    season = 0.15 + 0.5 * np.exp(-((doy - 200) / 45.0) ** 2)            # one wet season
    wet = rng.random((days, H, W)) < season[:, None, None]
    rain = np.where(wet, rng.gamma(0.7, 12.0, size=(days, H, W)), 0.0)
    rain *= np.linspace(0.6, 1.6, W)[None, None, :]                    # wetter towards the east
    rain = rain.astype("float64")
    rain[:, ~_land()] = -999.0
    if negative:
        rain[3, 5, 5] = -4.0
    xr.Dataset(
        {"RAINFALL": (("TIME", "LATITUDE", "LONGITUDE"), rain, {"units": "mm"})},
        coords={"TIME": np.datetime64(f"{year}-01-01") + np.arange(days),
                "LATITUDE": 10.0 + 0.25 * np.arange(H), "LONGITUDE": 70.0 + 0.25 * np.arange(W)},
    ).to_netcdf(path, engine="scipy", encoding={"RAINFALL": {"_FillValue": -999.0}})


@pytest.fixture(scope="session")
def world(tmp_path_factory):
    """Returns the folder holding ``rf25/``, ``client_map.json`` and ``test.yaml`` (a config for this world)."""
    root = tmp_path_factory.mktemp("qcworld")
    rf = root / "rf25"
    rf.mkdir()
    rng = np.random.default_rng(0)
    for y in YEARS:
        write_year(rf / f"RF25_ind{y}_rfp25.nc", y, rng)
    save_client_map(root / "client_map.json", _client_map(), 3, 0)
    (root / "test.yaml").write_text(f"""
extends: base.yaml
name: test
paths: {{rf25: "{rf.as_posix()}", work: "{(root / 'work').as_posix()}", out: "{(root / 'out').as_posix()}"}}
grid: {{n_lat: {H}, n_lon: {W}, lat0: 10.0, lon0: 70.0, step: 0.25, land_cells: {int(_land().sum())}}}
years: {{train: [1990, 1995], val: [1996, 1999], test: [2000, 2001], fusion_fit: [1996, 1997], threshold: [1998, 1999], stress: [1989, 1989]}}
benchmark: {{name: t, allow_unpinned: true, radius: {{min: 1.5, max_seen: 2.5, max: 4.0}}}}
clients: {{k: 3, seed: 0, heldout: [3], buffer_cells: 3, map: "{(root / 'client_map.json').as_posix()}"}}
""", encoding="utf-8")
    return root


@pytest.fixture(scope="session")
def cfg(world):
    return load_config(world / "test.yaml")


@pytest.fixture(scope="session")
def prepared(cfg):
    from qc.prepare import prepare
    return prepare(cfg, check_data=False)


@pytest.fixture(scope="session")
def bench(prepared):
    from qc.benchmark import build_benchmark
    return build_benchmark(prepared, splits=("val", "test"), overwrite=True)
