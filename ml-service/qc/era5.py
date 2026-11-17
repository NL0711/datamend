"""ERA5 hourly single-level fields -> daily fields on the RF25 grid (temperature, relative humidity, pressure).

Input   monthly GRIB or NetCDF files from ``scripts/download_era5.py`` (``era5_single_<year>_<month>.grib``): 2 m
        temperature (t2m, K), 2 m dewpoint (d2m, K), surface pressure (sp, Pa), all 24 hours.
Steps   per hour: temperature in degC, pressure in hPa, relative humidity from temperature and dewpoint (Magnus
        formula over water, clipped to 100 %); then daily mean / min / max of each.
Output  one file per year, ``ERA5D_<year>.nc``: dims (TIME, LATITUDE, LONGITUDE), latitude ascending as in RF25,
        variables ``TEMP_MEAN``, ``TEMP_MIN``, ``TEMP_MAX``, ``RH_MEAN`` ... ``PRES_MEAN`` ... (float32, NaN where a
        day is incomplete). Hourly files are never rewritten; they are deleted only when ``delete_consumed`` is set.

Open choices, set in the ``era5:`` config section and recorded in every output file:
  * Day alignment (``label_offset_hours``). A day is the 24 hours whose (UTC time + offset) falls on that date.
    0 = UTC calendar day (default). 21 = the 24 h ending 03:00 UTC (08:30 IST) labelled with the date of its end,
    which is how the IMD rain day is believed to run. UNVERIFIED: check the RF25/IMD documentation before using it;
    a wrong shift misaligns cross-variable checks against rainfall.
  * Which daily statistics to keep (``stats``): OPEN. All three are kept by default because they are cheap.
A day is complete only if every cell has exactly 24 hourly values; otherwise the whole day is NaN and listed in the
file attributes and the build report, never filled.

ERA5 is a reanalysis (modelled), not a measurement. Faults injected into it are easier to detect than real sensor
faults, because the field is smooth and spatially consistent by construction. See ``qc.multivar`` for the use of it.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import xarray as xr

from qc.grid import ContractError

log = logging.getLogger(__name__)
VARS = ("TEMP", "RH", "PRES")                         # temperature degC, relative humidity %, surface pressure hPa
UNITS = {"TEMP": "degC", "RH": "%", "PRES": "hPa"}
STATS = ("mean", "min", "max")
DEFAULT_STATS = {"TEMP": ("mean", "min", "max"), "RH": ("mean", "min", "max"), "PRES": ("mean", "min", "max")}
MAGNUS_A, MAGNUS_B = 17.625, 243.04                   # Alduchov and Eskridge (1996) constants, over water, T in degC
HOURS = 24


def saturation_vapour_pressure(t_c: np.ndarray) -> np.ndarray:
    """Saturation vapour pressure over water (hPa), Magnus form: 6.1094 exp(17.625 T / (T + 243.04))."""
    return 6.1094 * np.exp(MAGNUS_A * t_c / (t_c + MAGNUS_B))


def relative_humidity(t_c: np.ndarray, td_c: np.ndarray) -> np.ndarray:
    """Percent, from temperature and dewpoint, clipped to [0, 100] (dewpoint can exceed temperature by rounding)."""
    return np.clip(100.0 * saturation_vapour_pressure(td_c) / saturation_vapour_pressure(t_c), 0.0, 100.0)


@dataclass
class Alignment:
    label_offset_hours: float = 0.0

    def label(self, times: np.ndarray) -> np.ndarray:
        """Date (datetime64[D]) each hourly timestamp belongs to."""
        shifted = times.astype("datetime64[s]") + np.timedelta64(int(round(self.label_offset_hours * 3600)), "s")
        return shifted.astype("datetime64[D]")


def monthly_name(year: int, month: int, ext: str = "grib") -> str:
    return f"era5_single_{year}_{month:02d}.{ext}"


def find_monthly(hourly_dir: Path, year: int, month: int) -> Optional[Path]:
    for ext in ("grib", "nc"):
        f = Path(hourly_dir) / monthly_name(year, month, ext)
        if f.is_file():
            return f
    return None


# ---------------------------------------------------------------------------------------------- reading

def read_hourly(path: Path, spec) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """(times (n,) datetime64[ns], {TEMP, RH, PRES} each (n, H, W) float32), latitude ascending, grid checked against
    ``spec`` (= ``cfg.grid``). GRIB needs ``cfgrib`` and ``eccodes`` (``requirements-train.txt``)."""
    path = Path(path)
    if path.suffix == ".grib":
        try:
            ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})
        except ImportError as e:
            raise ContractError("reading GRIB needs cfgrib and eccodes: pip install cfgrib eccodes") from e
    else:
        ds = xr.open_dataset(path)
    with ds:
        tdim = next(d for d in ds["t2m"].dims if d not in ("latitude", "longitude"))       # "time" (cfgrib) or "valid_time" (CDS netcdf)
        tname = "valid_time" if "valid_time" in ds.coords and ds["valid_time"].dims == (tdim,) else tdim
        miss = [v for v in ("t2m", "d2m", "sp") if v not in ds]
        if miss:
            raise ContractError(f"{path.name}: missing variables {miss} (found {list(ds.data_vars)}).")
        ds = ds.sortby("latitude")
        lat, lon = ds["latitude"].values.astype(float), ds["longitude"].values.astype(float)
        for name, arr, n, first in (("latitude", lat, spec.n_lat, spec.lat0), ("longitude", lon, spec.n_lon, spec.lon0)):
            want = first + spec.step * np.arange(n)
            if arr.size != n or not np.allclose(arr, want, atol=1e-4):
                raise ContractError(f"{path.name}: {name} has {arr.size} points from {arr[0]} to {arr[-1]}; "
                                    f"expected {n} from {want[0]} to {want[-1]} in steps of {spec.step}.")
        times = ds[tname].values.astype("datetime64[ns]")
        order = np.argsort(times)
        dims = (tdim, "latitude", "longitude")
        t2m = ds["t2m"].transpose(*dims).values[order].astype(np.float32)
        d2m = ds["d2m"].transpose(*dims).values[order].astype(np.float32)
        sp = ds["sp"].transpose(*dims).values[order].astype(np.float32)
        times = times[order]
    t_c, td_c = t2m - 273.15, d2m - 273.15
    return times, {"TEMP": t_c, "RH": relative_humidity(t_c, td_c).astype(np.float32), "PRES": sp / 100.0}


# ---------------------------------------------------------------------------------------------- daily build

@dataclass
class YearBuild:
    year: int
    days: int
    complete_days: int
    incomplete: List[str]
    files_used: List[str]
    files_missing: List[str]
    path: Optional[Path] = None


def _needed_months(year: int) -> List[Tuple[int, int]]:
    """Months that can hold hours of this label year: the neighbours matter when the alignment shifts the day."""
    return [(year - 1, 12)] + [(year, m) for m in range(1, 13)] + [(year + 1, 1)]


def build_year(hourly_dir: Path, year: int, spec, align: Alignment, stats: Dict[str, Sequence[str]]) -> Tuple[Dict[str, np.ndarray], YearBuild]:
    """Daily fields of one label year, from whichever monthly files exist. Returns ({TEMP_MEAN: (D, H, W)...}, report)."""
    D = (dt.date(year, 12, 31) - dt.date(year, 1, 1)).days + 1
    H, W = spec.n_lat, spec.n_lon
    first = np.datetime64(f"{year}-01-01")
    acc = {v: {"sum": np.zeros((D, H, W), np.float64), "min": np.full((D, H, W), np.inf, np.float32),
               "max": np.full((D, H, W), -np.inf, np.float32)} for v in VARS}
    cnt = np.zeros((D, H, W), np.int16)
    used, missing = [], []
    for y, m in _needed_months(year):
        f = find_monthly(hourly_dir, y, m)
        if f is None:
            if y == year:
                missing.append(monthly_name(y, m))
            continue
        times, data = read_hourly(f, spec)
        day = (align.label(times) - first).astype(int)
        keep = (day >= 0) & (day < D)
        if not keep.any():
            continue
        used.append(f.name)
        ok_all = np.ones(times.shape + (H, W), bool)
        for v in VARS:
            ok_all &= np.isfinite(data[v])
        for d in np.unique(day[keep]):
            sel = np.nonzero(day == d)[0]
            ok = ok_all[sel]
            cnt[d] += ok.sum(axis=0).astype(np.int16)
            for v in VARS:
                x = data[v][sel]
                acc[v]["sum"][d] += np.where(ok, x, 0.0).sum(axis=0)
                acc[v]["min"][d] = np.minimum(acc[v]["min"][d], np.where(ok, x, np.inf).min(axis=0))
                acc[v]["max"][d] = np.maximum(acc[v]["max"][d], np.where(ok, x, -np.inf).max(axis=0))
    complete = (cnt == HOURS)
    day_ok = complete.all(axis=(1, 2))
    out: Dict[str, np.ndarray] = {}
    for v in VARS:
        for s in stats.get(v, ()):
            if s == "mean":
                arr = (acc[v]["sum"] / np.maximum(cnt, 1)).astype(np.float32)
            else:
                arr = acc[v][s].copy()
            out[f"{v}_{s.upper()}"] = np.where(day_ok[:, None, None], arr, np.nan).astype(np.float32)
    dates = first + np.arange(D)
    rep = YearBuild(year, D, int(day_ok.sum()), [str(d) for d in dates[~day_ok]], used, missing)
    return out, rep


def write_year(path: Path, year: int, fields: Dict[str, np.ndarray], spec, align: Alignment, rep: YearBuild) -> Path:
    D = next(iter(fields.values())).shape[0]
    lat = spec.lat0 + spec.step * np.arange(spec.n_lat)
    lon = spec.lon0 + spec.step * np.arange(spec.n_lon)
    data = {k: (("TIME", "LATITUDE", "LONGITUDE"), v, {"units": UNITS[k.split("_")[0]]}) for k, v in fields.items()}
    ds = xr.Dataset(data, coords={"TIME": np.datetime64(f"{year}-01-01") + np.arange(D), "LATITUDE": lat, "LONGITUDE": lon})
    ds.attrs.update({
        "source": "ERA5 hourly single levels (reanalysis, modelled: not station observations)",
        "variables_from": "t2m, d2m, sp; relative humidity from Magnus formula over water, clipped to 100",
        "label_offset_hours": float(align.label_offset_hours),
        "day_alignment_note": "0 = UTC calendar day. IMD rain-day alignment (21) is UNVERIFIED.",
        "incomplete_days": ",".join(rep.incomplete[:400]),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part.nc")
    ds.to_netcdf(tmp, engine="scipy")
    tmp.replace(path)
    return path


def daily_path(daily_dir: Path, year: int) -> Path:
    return Path(daily_dir) / f"ERA5D_{year}.nc"


def build_daily(hourly_dir: Path, daily_dir: Path, years: Sequence[int], spec, align: Alignment,
                stats: Optional[Dict[str, Sequence[str]]] = None, delete_consumed: bool = False,
                overwrite: bool = False) -> List[YearBuild]:
    """Build ``ERA5D_<year>.nc`` for each year. Skips years already built. ``delete_consumed`` removes hourly files
    that no later year needs (months Feb-Nov of the year and the previous December), only after the year came out
    complete and only when years are built in ascending order. Default: nothing is deleted."""
    stats = {**DEFAULT_STATS, **(stats or {})}
    reports = []
    built = set()
    for year in sorted(years):
        path = daily_path(daily_dir, year)
        if path.is_file() and not overwrite:
            log.info("ERA5 daily %d exists", year)
            built.add(year)
            continue
        fields, rep = build_year(hourly_dir, year, spec, align, stats)
        if rep.complete_days == 0:
            log.warning("ERA5 %d: no complete day (hourly files missing?)", year)
            reports.append(rep)
            continue
        rep.path = write_year(path, year, fields, spec, align, rep)
        reports.append(rep)
        built.add(year)
        log.info("ERA5 daily %d: %d of %d days complete", year, rep.complete_days, rep.days)
        if delete_consumed and rep.complete_days == rep.days:
            for y, m in [(year, mm) for mm in range(2, 12)] + [(year - 1, 12)]:
                f = find_monthly(hourly_dir, y, m)
                if f is not None and (y == year or (y in built)):
                    f.unlink()
    return reports


# ---------------------------------------------------------------------------------------------- reading daily

class Era5Daily:
    """Daily fields on disk. ``year(y, 'TEMP_MEAN')`` -> (days, H, W) float32."""

    def __init__(self, daily_dir: Path):
        self.dir = Path(daily_dir)

    def has(self, year: int) -> bool:
        return daily_path(self.dir, year).is_file()

    def year(self, year: int, name: str) -> np.ndarray:
        path = daily_path(self.dir, year)
        if not path.is_file():
            raise FileNotFoundError(f"{path} not found. Build it with `python -m qc era5-daily --years {year} {year}`.")
        with xr.open_dataset(path, engine="scipy") as ds:
            if name not in ds:
                raise ContractError(f"{path.name}: no variable {name} (found {list(ds.data_vars)}).")
            return ds[name].transpose("TIME", "LATITUDE", "LONGITUDE").values.astype(np.float32)

    def grid(self, year: int):
        with xr.open_dataset(daily_path(self.dir, year), engine="scipy") as ds:
            return ds["LATITUDE"].values.astype(np.float32), ds["LONGITUDE"].values.astype(np.float32)
