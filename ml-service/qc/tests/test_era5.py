"""ERA5 daily conversion (qc/era5.py) and the temperature / humidity / pressure experts (qc/multivar.py)."""

import calendar
import glob
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from qc import era5
from qc.config import load_config
from qc.era5 import Alignment, Era5Daily, build_daily, relative_humidity
from qc.grid import ContractError
from qc.multivar import (KINDS, NAMES, VARIABLES, _RING1, _RING2, _ring_median, fit_experts, fit_gbm, fit_stats, inject,
                         run_validation)

SPEC = SimpleNamespace(n_lat=4, n_lon=5, lat0=10.0, lon0=70.0, step=0.25)


def _hourly(folder: Path, year: int, month: int, tfun):
    """Monthly hourly file (latitude stored descending, as GRIB does). ``tfun(h)``: temperature degC from the hour index."""
    n = calendar.monthrange(year, month)[1] * 24
    times = np.datetime64(f"{year}-{month:02d}-01T00:00") + np.arange(n) * np.timedelta64(1, "h")
    lat = SPEC.lat0 + SPEC.step * np.arange(SPEC.n_lat)
    lon = SPEC.lon0 + SPEC.step * np.arange(SPEC.n_lon)
    h = np.arange(n, dtype=np.float64)[:, None, None]
    t = (tfun(h) + np.zeros((1, SPEC.n_lat, SPEC.n_lon))).astype(np.float32)
    dims = ("time", "latitude", "longitude")
    ds = xr.Dataset({"t2m": (dims, t + 273.15), "d2m": (dims, t - 10 + 273.15), "sp": (dims, np.full(t.shape, 95000.0, np.float32))},
                    coords={"time": times, "latitude": lat, "longitude": lon}).isel(latitude=slice(None, None, -1))
    folder.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(folder / era5.monthly_name(year, month, "nc"), engine="scipy")


def test_relative_humidity_formula_and_clip():
    assert relative_humidity(np.array([20.0]), np.array([20.0]))[0] == pytest.approx(100.0)
    assert relative_humidity(np.array([20.0]), np.array([10.0]))[0] == pytest.approx(52.5, abs=0.6)    # Magnus over water
    assert relative_humidity(np.array([10.0]), np.array([10.5]))[0] == 100.0                        # dewpoint above temperature: clipped
    assert relative_humidity(np.array([30.0]), np.array([-40.0]))[0] >= 0.0


def test_daily_statistics_complete_days_only_and_ascending_latitude(tmp_path):
    hourly = tmp_path / "h"
    _hourly(hourly, 2016, 3, lambda h: 10.0 + (h % 24))                        # 10..33 degC within each UTC day
    rep = build_daily(hourly, tmp_path / "d", [2016], SPEC, Alignment(0.0))[0]
    assert rep.complete_days == 31 and "2016-03-01" not in rep.incomplete and "2016-02-29" in rep.incomplete
    d = Era5Daily(tmp_path / "d")
    mean, mn, mx = d.year(2016, "TEMP_MEAN"), d.year(2016, "TEMP_MIN"), d.year(2016, "TEMP_MAX")
    day = 31 + 29                                                                 # 1 March 2016 has day-of-year index 60
    assert mean[day, 0, 0] == pytest.approx(21.5) and mn[day, 0, 0] == 10.0 and mx[day, 0, 0] == 33.0
    assert np.isnan(mean[0]).all() and np.isnan(mean[day - 1]).all()              # a day without data is NaN, never filled
    assert d.year(2016, "PRES_MEAN")[day, 0, 0] == pytest.approx(950.0)
    rh = d.year(2016, "RH_MEAN")[day]
    assert np.isfinite(rh).all() and ((rh > 0) & (rh <= 100)).all()
    lat, _ = d.grid(2016)
    assert lat[0] == pytest.approx(SPEC.lat0) and np.all(np.diff(lat) > 0)        # flipped to ascending, as in RF25
    attrs = xr.open_dataset(tmp_path / "d" / "ERA5D_2016.nc", engine="scipy").attrs
    assert "UNVERIFIED" in attrs["day_alignment_note"] and "modelled" in attrs["source"]


def test_day_alignment_shifts_which_hours_make_a_day(tmp_path):
    hourly = tmp_path / "h"
    for m in (2, 3, 4):
        _hourly(hourly, 2016, m, lambda h: (h // 24) + (h % 24) / 100.0)         # value = day index + hour / 100
    build_daily(hourly, tmp_path / "u", [2016], SPEC, Alignment(0.0))
    build_daily(hourly, tmp_path / "i", [2016], SPEC, Alignment(21.0))
    day = 31 + 29 + 10                                                            # 11 March: month-day index 10
    u, i = Era5Daily(tmp_path / "u"), Era5Daily(tmp_path / "i")
    # UTC day: hours 00..23 of that date
    assert u.year(2016, "TEMP_MIN")[day, 0, 0] == pytest.approx(10.00, abs=1e-4)
    assert u.year(2016, "TEMP_MAX")[day, 0, 0] == pytest.approx(10.23, abs=1e-4)
    # 24 h ending 03:00 UTC (08:30 IST) labelled with the end date: hours 03..23 of the day before, then 00..02
    assert i.year(2016, "TEMP_MIN")[day, 0, 0] == pytest.approx(9.03, abs=1e-4)
    assert i.year(2016, "TEMP_MAX")[day, 0, 0] == pytest.approx(10.02, abs=1e-4)
    expect = (sum(9 + h / 100 for h in range(3, 24)) + sum(10 + h / 100 for h in range(0, 3))) / 24
    assert i.year(2016, "TEMP_MEAN")[day, 0, 0] == pytest.approx(expect, abs=1e-4)
    # a shifted day needs the neighbouring month: the first of March is incomplete without February's last hours... here
    # February is present, so it is complete; the first of February is not (no January file)
    assert not np.isnan(i.year(2016, "TEMP_MEAN")[31 + 29, 0, 0]) and np.isnan(i.year(2016, "TEMP_MEAN")[31, 0, 0])


def test_hourly_files_are_kept_unless_asked_and_deleted_only_when_every_year_they_touch_is_complete(tmp_path):
    hourly = tmp_path / "h"
    for m in range(1, 13):
        _hourly(hourly, 2016, m, lambda h: 15.0 + 0 * h)
    _hourly(hourly, 2015, 12, lambda h: 15.0 + 0 * h)
    rep = build_daily(hourly, tmp_path / "d", [2016], SPEC, Alignment(0.0))[0]
    assert rep.complete_days == 366 and len(list(hourly.glob("*.nc"))) == 13       # default: nothing deleted
    build_daily(hourly, tmp_path / "d2", [2016], SPEC, Alignment(0.0), delete_consumed=True)
    assert {p.name for p in hourly.glob("*.nc")} == {era5.monthly_name(2015, 12, "nc")}   # 2015 was never built: its file stays
    # with the 21 h alignment the late hours of 31 December belong to the next label year: December stays until that year is built
    hourly2 = tmp_path / "h2"
    for m in range(1, 13):
        _hourly(hourly2, 2016, m, lambda h: 15.0 + 0 * h)
    _hourly(hourly2, 2015, 12, lambda h: 15.0 + 0 * h)
    rep = build_daily(hourly2, tmp_path / "e", [2016], SPEC, Alignment(21.0), delete_consumed=True)[0]
    assert rep.complete_days == 366
    assert {p.name for p in hourly2.glob("*.nc")} == {era5.monthly_name(2015, 12, "nc"), era5.monthly_name(2016, 12, "nc")}
    # an incomplete year (June missing) deletes nothing
    hourly3 = tmp_path / "h3"
    for m in range(1, 13):
        if m != 6:
            _hourly(hourly3, 2016, m, lambda h: 15.0 + 0 * h)
    before = {p.name for p in hourly3.glob("*.nc")}
    rep = build_daily(hourly3, tmp_path / "f", [2016], SPEC, Alignment(0.0), delete_consumed=True)[0]
    assert rep.complete_days < rep.days and rep.incomplete_months == ["2016-06"]
    assert {p.name for p in hourly3.glob("*.nc")} == before


def test_an_incomplete_year_is_rebuilt_when_more_hourly_data_arrives(tmp_path):
    h = tmp_path / "h"
    f = lambda t: 10.0 + 0 * t
    _range_file(h / "first_half.nc", "2015-01-01T00:00", 181 * 24, f)
    rep = build_daily(h, tmp_path / "d", [2015], SPEC, Alignment(0.0))[0]
    assert rep.complete_days == 181
    _range_file(h / "second_half.nc", "2015-07-01T00:00", 184 * 24, f)
    rep = build_daily(h, tmp_path / "d", [2015], SPEC, Alignment(0.0))[0]                  # same output folder: rebuilt, not skipped
    assert rep.complete_days == 365 and era5._year_complete(tmp_path / "d", 2015)
    assert build_daily(h, tmp_path / "d", [2015], SPEC, Alignment(0.0)) == []                # complete now: skipped


def test_wrong_grid_is_refused(tmp_path):
    _hourly(tmp_path / "h", 2016, 3, lambda h: 10.0 + 0 * h)
    bad = SimpleNamespace(n_lat=4, n_lon=5, lat0=11.0, lon0=70.0, step=0.25)
    with pytest.raises(ContractError, match="latitude"):
        build_daily(tmp_path / "h", tmp_path / "d", [2016], bad, Alignment(0.0))


def _range_file(path: Path, start: str, hours: int, tfun, pad: float = 0.0):
    """One file of ``hours`` consecutive hours from ``start``, with an optional margin of ``pad`` degrees around the grid."""
    times = np.datetime64(start) + np.arange(hours) * np.timedelta64(1, "h")
    k = int(round(pad / SPEC.step))
    lat = SPEC.lat0 + SPEC.step * (np.arange(SPEC.n_lat + 2 * k) - k)
    lon = SPEC.lon0 + SPEC.step * (np.arange(SPEC.n_lon + 2 * k) - k)
    t = (tfun(np.arange(hours, dtype=np.float64)[:, None, None]) + np.zeros((1, lat.size, lon.size))).astype(np.float32)
    dims = ("valid_time", "latitude", "longitude")                              # the CDS NetCDF layout
    ds = xr.Dataset({"t2m": (dims, t + 273.15), "d2m": (dims, t - 10 + 273.15), "sp": (dims, np.full(t.shape, 95000.0, np.float32))},
                    coords={"valid_time": times, "latitude": lat, "longitude": lon})
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.isel(latitude=slice(None, None, -1)).to_netcdf(path, engine="scipy")


def test_hand_downloaded_files_any_name_any_span_larger_area_and_overlap(tmp_path):
    f = lambda h: 10.0 + (h % 24)
    ref = tmp_path / "ref"
    _range_file(ref / "one.nc", "2016-03-01T00:00", 31 * 24, f)
    build_daily(ref, tmp_path / "dref", [2016], SPEC, Alignment(0.0))
    # a differently named file per half-month, on a larger area, with 3 days of overlap between them
    man = tmp_path / "man"
    _range_file(man / "download (1).nc", "2016-03-01T00:00", 18 * 24, f, pad=0.5)
    _range_file(man / "sub" / "era5 part two.nc", "2016-03-15T00:00", 17 * 24, lambda h: f(h + 14 * 24), pad=0.5)
    rep = build_daily(man, tmp_path / "dman", [2016], SPEC, Alignment(0.0))[0]
    assert rep.complete_days == 31 and len(rep.files_used) == 2
    a, b = Era5Daily(tmp_path / "dref"), Era5Daily(tmp_path / "dman")
    for k in ("TEMP_MEAN", "TEMP_MIN", "RH_MEAN", "PRES_MEAN"):
        np.testing.assert_allclose(b.year(2016, k), a.year(2016, k), equal_nan=True, atol=1e-5)       # overlap counted once
    # a file that does not cover the grid is refused with the area to download
    _range_file(tmp_path / "small" / "x.nc", "2016-03-01T00:00", 24, f, pad=-0.25)
    with pytest.raises(ContractError, match="N 38.5, W 66.5, S 6.5, E 100.0"):
        build_daily(tmp_path / "small", tmp_path / "ds", [2016], SPEC, Alignment(0.0))


def test_inventory_shows_gaps_and_complete_years_and_zips_are_flagged(tmp_path, caplog):
    h = tmp_path / "h"
    f = lambda t: 10.0 + 0 * t
    _range_file(h / "jan_feb.nc", "2016-01-01T00:00", (31 + 29) * 24, f)
    _range_file(h / "mar_short.nc", "2016-03-01T00:00", 30 * 24, f)               # 24 hours short of a full March
    (h / "mystery.zip").write_bytes(b"PK")
    inv = era5.inventory(h, SPEC)
    assert inv["years"][2016]["01"] == "ok" and inv["years"][2016]["02"] == "ok" and inv["years"][2016]["03"] == "720/744 h"
    assert inv["complete_years"] == [] and {x["file"] for x in inv["files"]} == {"jan_feb.nc", "mar_short.nc"}
    assert any("unzip" in r.message for r in caplog.records)


REAL = (glob.glob(str(Path(__file__).resolve().parents[3] / "data" / "*.grib")) or [None])[0]


@pytest.mark.skipif(REAL is None, reason="no ERA5 sample GRIB in datamend/data")
def test_real_grib_sample_reads_on_the_rf25_grid(tmp_path):
    cfg = load_config(Path(__file__).resolve().parents[1] / "configs" / "base.yaml", [])
    (tmp_path / "h").mkdir()
    shutil.copy(REAL, tmp_path / "h" / era5.monthly_name(2016, 1, "grib"))
    rep = build_daily(tmp_path / "h", tmp_path / "d", [2016], cfg.grid, Alignment(0.0))[0]
    assert rep.complete_days == 31                                                # the sample is January 2016
    d = Era5Daily(tmp_path / "d")
    t, rh, p = d.year(2016, "TEMP_MEAN")[:31], d.year(2016, "RH_MEAN")[:31], d.year(2016, "PRES_MEAN")[:31]
    assert t.shape[1:] == (129, 135) and -60 < np.nanmin(t) and np.nanmax(t) < 45
    assert 0 <= np.nanmin(rh) and np.nanmax(rh) <= 100 and 400 < np.nanmin(p) and np.nanmax(p) < 1100


# ---------------------------------------------------------------------------------------------- multivariate

def _daily_world(folder: Path, years, seed=0, H=6, W=7):
    """Seasonal temperature, humidity anticorrelated with temperature anomalies, pressure with its own noise."""
    rng = np.random.default_rng(seed)
    lat, lon = 10.0 + 0.25 * np.arange(H), 70.0 + 0.25 * np.arange(W)
    for y in years:
        T = 366 if y % 4 == 0 else 365
        doy = np.arange(T)[:, None, None]
        a = rng.normal(0, 1.0, (T, H, W))
        temp = 25 + 6 * np.sin(2 * np.pi * doy / 365) + 2.0 * a
        rh = np.clip(60 - 8 * a + rng.normal(0, 2.0, (T, H, W)) + 10 * np.cos(2 * np.pi * doy / 365), 5, 99)
        pres = 950 + 3 * np.sin(2 * np.pi * doy / 365) + rng.normal(0, 1.5, (T, H, W))
        ds = xr.Dataset({k: (("TIME", "LATITUDE", "LONGITUDE"), v.astype(np.float32)) for k, v in
                         (("TEMP_MEAN", temp), ("RH_MEAN", rh), ("PRES_MEAN", pres))},
                        coords={"TIME": np.datetime64(f"{y}-01-01") + np.arange(T), "LATITUDE": lat, "LONGITUDE": lon})
        folder.mkdir(parents=True, exist_ok=True)
        ds.to_netcdf(folder / f"ERA5D_{y}.nc", engine="scipy")


@pytest.fixture(scope="module")
def daily(tmp_path_factory):
    d = tmp_path_factory.mktemp("era5d")
    _daily_world(d, range(1990, 2000))
    return Era5Daily(d)


YEARS = {"train": list(range(1990, 1996)), "fusion_fit": [1996, 1997], "threshold": [1998, 1999]}


def test_fault_injection_is_deterministic_labelled_and_inside_physical_bounds(daily):
    st = fit_stats(daily, YEARS["train"])
    x = {n: daily.year(1998, v.field) for n, v in VARIABLES.items()}
    a, la = inject(x, st, [0, 1], 0.01)
    b, _ = inject(x, st, [0, 1], 0.01)
    c, _ = inject(x, st, [0, 2], 0.01)
    for n in NAMES:
        assert np.array_equal(a[n], b[n]) and not np.array_equal(a[n], c[n])
        assert a[n].min() >= VARIABLES[n].lo and a[n].max() <= VARIABLES[n].hi
        any_label = np.zeros(x[n].shape, bool)
        for k in KINDS:
            assert la[n][k].any(), (n, k)
            any_label |= la[n][k]
        assert np.array_equal(a[n][~any_label], x[n][~any_label])               # nothing changes outside the labelled spans
        assert (a[n] != x[n]).any() and 0.0005 < any_label.mean() < 0.06


def test_validation_detects_spikes_and_reports_limits(daily, tmp_path):
    res = run_validation(daily, YEARS, rate=0.01, seed=0, budgets=(1.0, 5.0), out_path=tmp_path / "v.json")
    row = res["scores"]["fusion"]["5.0"]
    assert row["recall"]["temperature"]["spike"] > 0.8 and row["recall"]["pressure"]["spike"] > 0.8
    assert 0 <= row["false_per_1000_clean"] < 40
    assert set(res["scores"]) == {"temperature", "humidity", "pressure", "consistency", "gbm_temperature", "gbm_humidity",
                                  "gbm_pressure", "fusion", "fusion_max"}
    assert (tmp_path / "v.json").is_file()
    assert any("modelled" in s for s in res["limits"]) and any("NOT IMPLEMENTED" in s for s in res["limits"])
    with pytest.raises(ValueError, match="disjoint"):
        run_validation(daily, {**YEARS, "threshold": [1996, 1999]})


def test_consistency_expert_prefers_the_inconsistent_combination(daily):
    st = fit_stats(daily, YEARS["train"])
    ex = fit_experts(daily, st, YEARS["threshold"])
    assert st.cov[0, 1] < -0.5                                                    # humidity falls when the temperature anomaly rises

    def score(zt, zr):
        f = {n: np.repeat(st.mean[n][100][None], 101, axis=0).copy() for n in NAMES}     # 101 days so day index 100 exists
        f["temperature"][100] += zt * st.sd["temperature"][100]
        f["humidity"][100] += zr * st.sd["humidity"][100]
        return {k: float(np.nanmean(s[100])) for k, s in ex.scores(f).items()}
    consistent, inconsistent = score(2.0, -2.0), score(2.0, +2.0)
    assert inconsistent["consistency"] > consistent["consistency"]


# ---------------------------------------------------------------------------------------------- neighbour regression experts

def _smooth_world(folder: Path, years, seed=0, H=16, W=18):
    """Like _daily_world but with spatially smooth anomalies, as real temperature and pressure fields are."""
    from scipy.ndimage import gaussian_filter
    rng = np.random.default_rng(seed)
    lat, lon = 10.0 + 0.25 * np.arange(H), 70.0 + 0.25 * np.arange(W)
    for y in years:
        T = 366 if y % 4 == 0 else 365
        doy = np.arange(T)[:, None, None]
        smooth = lambda sd: gaussian_filter(rng.normal(0, 1.0, (T, H, W)), sigma=(0, 2.5, 2.5)) * sd
        a = smooth(4.0)
        temp = 25 + 6 * np.sin(2 * np.pi * doy / 365) + 2.0 * a
        rh = np.clip(60 - 6 * a + smooth(6.0) + 10 * np.cos(2 * np.pi * doy / 365), 5, 99)
        pres = 950 + 3 * np.sin(2 * np.pi * doy / 365) + smooth(4.5)
        ds = xr.Dataset({k: (("TIME", "LATITUDE", "LONGITUDE"), v.astype(np.float32)) for k, v in
                         (("TEMP_MEAN", temp), ("RH_MEAN", rh), ("PRES_MEAN", pres))},
                        coords={"TIME": np.datetime64(f"{y}-01-01") + np.arange(T), "LATITUDE": lat, "LONGITUDE": lon})
        folder.mkdir(parents=True, exist_ok=True)
        ds.to_netcdf(folder / f"ERA5D_{y}.nc", engine="scipy")


@pytest.fixture(scope="module")
def smooth(tmp_path_factory):
    d = tmp_path_factory.mktemp("era5smooth")
    _smooth_world(d, range(1990, 2000))
    return Era5Daily(d)


def test_neighbour_median_is_not_dragged_by_one_faulty_neighbour():
    a = np.zeros((2, 6, 6), np.float32)
    a[:, 3, 3] = 500.0                                   # one faulty cell
    r1, r2 = _ring_median(a, _RING1), _ring_median(a, _RING2)
    assert float(np.abs(r1).max()) == 0.0 and float(np.abs(r2).max()) == 0.0
    b = np.arange(36, dtype=np.float32).reshape(1, 6, 6)
    assert _ring_median(b, _RING1)[0, 2, 2] == b[0, 2, 2]                              # symmetric neighbours: the median is the centre value
    assert len(_RING1) == 8 and len(_RING2) == 16


def test_regression_expert_never_reads_the_cells_own_other_variables(smooth):
    st = fit_stats(smooth, YEARS["train"])
    g = fit_gbm(smooth, st, YEARS["train"][:3], YEARS["threshold"], rows_per_year=8000)
    x = {n: smooth.year(1998, v.field) for n, v in VARIABLES.items()}
    base = g.scores(x)
    y = {n: v.copy() for n, v in x.items()}
    y["humidity"][100, 7, 9] += 40.0                                                   # a humidity fault at one cell and day
    moved = g.scores(y)
    assert moved["gbm_temperature"][100, 7, 9] == base["gbm_temperature"][100, 7, 9]   # its own temperature score does not move
    assert moved["gbm_pressure"][100, 7, 9] == base["gbm_pressure"][100, 7, 9]
    assert moved["gbm_humidity"][100, 7, 9] > 3 * base["gbm_humidity"][100, 7, 9]      # while its own humidity score jumps


def test_neighbour_regression_improves_drift_and_scale_detection_on_smooth_fields(smooth):
    rows = {}
    for use in (False, True):
        r = run_validation(smooth, YEARS, rate=0.01, seed=0, budgets=(2.0,), gbm=use)
        rec = r["scores"]["fusion_max"]["2.0"]["recall"]
        rows[use] = float(np.mean([rec[v][k] for v in NAMES for k in ("drift", "scale")]))
    assert rows[True] > rows[False] + 0.15, rows
