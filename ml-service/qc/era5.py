"""ERA5 hourly single-level fields -> daily fields on the RF25 grid (temperature, relative humidity, pressure).

Built for FILES DOWNLOADED BY HAND from the Copernicus CDS web form: any file names, any number of months or years per
file, GRIB or NetCDF, a larger area than needed. Put the files in ``era5.hourly_dir`` (default ``ml-service/data/era5``).
The converter reads the timestamps inside each file, so names do not matter; it reads one chunk of hours at a time, so
a multi-year file does not have to fit in memory; and hours that appear in two files are counted once.

Input   variables ``t2m`` (K), ``d2m`` (K), ``sp`` (Pa), all 24 hours of each day. ``.grib`` needs ``cfgrib`` and
        ``eccodes`` (``requirements-train.txt``). Unzip any ``.zip`` first (choose "Unarchived" on the form).
Grid    must contain every cell of the RF25 grid (129 x 135 at 0.25 degree, 6.5-38.5 N, 66.5-100 E). A larger area is
        cut down to it; a smaller or shifted one is refused with the axis named.
Steps   per hour: temperature in degC, pressure in hPa, relative humidity from temperature and dewpoint (Magnus
        formula over water, clipped to 100 %); then daily mean / min / max of each.
Output  one file per year, ``ERA5D_<year>.nc``: dims (TIME, LATITUDE, LONGITUDE), latitude ascending as in RF25,
        variables ``TEMP_MEAN``, ``TEMP_MIN``, ``TEMP_MAX``, ``RH_MEAN`` ... ``PRES_MAX`` (float32, NaN where a day is
        incomplete). Hourly files are never modified; they are deleted only when ``delete_consumed`` is set.

Open choices, set in the ``era5:`` config section and recorded in every output file:
  * Day alignment (``label_offset_hours``). A day is the 24 hours whose (UTC time + offset) falls on that date.
    0 = UTC calendar day (default). 21 = the 24 h ending 03:00 UTC (08:30 IST) labelled with the date of its end,
    which is how the IMD rain day is believed to run. UNVERIFIED: check the RF25/IMD documentation before using it;
    a wrong shift misaligns cross-variable checks. A shifted day also needs hours from the neighbouring year.
  * Which daily statistics to keep (``stats``): OPEN. All three are kept by default because they are cheap.
A day is complete only if every cell has exactly 24 hourly values; otherwise the whole day is NaN and listed in the
file attributes and the build report, never filled. ``inventory`` shows what the files cover before you convert.

ERA5 is a reanalysis (modelled), not a measurement. Faults injected into it are easier to detect than real sensor
faults, because the field is smooth and spatially consistent by construction. See ``qc.multivar`` for the use of it.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

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
CHUNK_HOURS = 24 * 31
EXTS = (".grib", ".grib2", ".nc")
HOUR = np.timedelta64(1, "h")


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
    """Name the download script gives a monthly file. Hand-downloaded files may be named anything."""
    return f"era5_single_{year}_{month:02d}.{ext}"


# ---------------------------------------------------------------------------------------------- opening files

def _open(path: Path):
    path = Path(path)
    if path.suffix.lower() in (".grib", ".grib2"):
        try:
            return xr.open_dataset(path, engine="cfgrib")
        except ImportError as e:
            raise ContractError("reading GRIB needs cfgrib and eccodes: pip install cfgrib eccodes") from e
    return xr.open_dataset(path)


def _time_dim(ds) -> Tuple[str, np.ndarray]:
    """(name of the time dimension of t2m, the hourly timestamps). cfgrib: dim ``time``; CDS NetCDF: ``valid_time``."""
    tdim = next((d for d in ds["t2m"].dims if d not in ("latitude", "longitude", "expver", "number")), None)
    if tdim is None:
        raise ContractError("t2m has no time dimension")
    name = "valid_time" if "valid_time" in ds.coords and ds["valid_time"].dims == (tdim,) else tdim
    return tdim, ds[name].values.astype("datetime64[ns]")


def _grid_index(ds, spec, label: str) -> Tuple[np.ndarray, np.ndarray]:
    """Positions of the spec grid's latitudes and longitudes inside the file (ascending spec order)."""
    out = []
    for name, n, first in (("latitude", spec.n_lat, spec.lat0), ("longitude", spec.n_lon, spec.lon0)):
        have = ds[name].values.astype(float)
        want = first + spec.step * np.arange(n)
        pos = np.full(n, -1)
        for i, w in enumerate(want):
            hit = np.nonzero(np.isclose(have, w, atol=1e-4))[0]
            if hit.size:
                pos[i] = hit[0]
        if (pos < 0).any():
            raise ContractError(
                f"{label}: {name} runs {have.min()} to {have.max()} ({have.size} points); the RF25 grid needs every point from "
                f"{want[0]} to {want[-1]} in steps of {spec.step}. Download area N 38.5, W 66.5, S 6.5, E 100.0 (a larger area is fine).")
        out.append(pos)
    return out[0], out[1]


@dataclass
class FileInfo:
    path: Path
    tmin: np.datetime64
    tmax: np.datetime64
    n: int

    @property
    def regular(self) -> bool:
        """True if the file holds every hour between its first and last timestamp exactly once."""
        return self.n == int((self.tmax - self.tmin) / HOUR) + 1


def scan(hourly_dir: Path, spec, use_cache: bool = True) -> List[FileInfo]:
    """Every GRIB / NetCDF file under ``hourly_dir`` with its time span. Cached in ``.era5_index.json`` by size and mtime."""
    hourly_dir = Path(hourly_dir)
    cache_path = hourly_dir / ".era5_index.json"
    cache = {}
    if use_cache and cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except ValueError:
            cache = {}
    infos, fresh = [], {}
    for f in sorted(p for p in hourly_dir.rglob("*") if p.is_file() and p.suffix.lower() in EXTS):
        key = str(f.relative_to(hourly_dir))
        st = f.stat()
        c = cache.get(key)
        if c and c["size"] == st.st_size and c["mtime"] == st.st_mtime:
            info = FileInfo(f, np.datetime64(c["tmin"]), np.datetime64(c["tmax"]), c["n"])
        else:
            with _open(f) as ds:
                miss = [v for v in ("t2m", "d2m", "sp") if v not in ds]
                if miss:
                    log.warning("%s: missing variables %s (found %s); file ignored", f.name, miss, list(ds.data_vars))
                    continue
                _grid_index(ds, spec, f.name)
                _, times = _time_dim(ds)
            info = FileInfo(f, times.min(), times.max(), int(np.unique(times).size))
        fresh[key] = {"size": st.st_size, "mtime": st.st_mtime, "tmin": str(info.tmin), "tmax": str(info.tmax), "n": info.n}
        infos.append(info)
    if use_cache:
        try:
            cache_path.write_text(json.dumps(fresh, indent=1), encoding="utf-8")
        except OSError:
            pass
    for z in sorted(hourly_dir.rglob("*.zip")):
        log.warning("%s is a zip file and was not read: unzip it first (choose 'Unarchived' on the CDS form)", z.name)
    return infos


def iter_hourly(info: FileInfo, spec, lo: np.datetime64, hi: np.datetime64, chunk: int = CHUNK_HOURS
                ) -> Iterator[Tuple[np.ndarray, Dict[str, np.ndarray]]]:
    """Yield (times, {TEMP, RH, PRES} each (n, H, W) float32) for the hours of the file inside [lo, hi], one chunk at a
    time, cut to the spec grid with latitude ascending."""
    with _open(info.path) as ds:
        tdim, times = _time_dim(ds)
        ilat, ilon = _grid_index(ds, spec, info.path.name)
        order = np.argsort(times, kind="stable")
        keep = order[(times[order] >= lo) & (times[order] <= hi)]
        for a in range(0, keep.size, chunk):
            rows = keep[a:a + chunk]
            raw = {}
            for v in ("t2m", "d2m", "sp"):
                da = ds[v]
                if "expver" in da.dims:                                  # ERA5 / ERA5T mix in recent months: take whichever is present
                    da = da.max("expver", skipna=True)
                if "number" in da.dims:
                    da = da.isel(number=0)
                da = da.transpose(tdim, "latitude", "longitude").isel({tdim: rows})
                raw[v] = da.values[:, ilat][:, :, ilon].astype(np.float32)
            t_c, td_c = raw["t2m"] - 273.15, raw["d2m"] - 273.15
            yield times[rows], {"TEMP": t_c, "RH": relative_humidity(t_c, td_c).astype(np.float32), "PRES": raw["sp"] / 100.0}


# ---------------------------------------------------------------------------------------------- inventory

def inventory(hourly_dir: Path, spec) -> Dict:
    """What the downloaded files cover: per file its span and whether it has gaps; per year the hours covered in each month
    against the hours the month has."""
    infos = scan(hourly_dir, spec)
    files = [{"file": str(i.path.relative_to(hourly_dir)), "first": str(i.tmin), "last": str(i.tmax), "hours": i.n,
              "gaps": not i.regular} for i in infos]
    covered: Dict[str, int] = {}
    for i in infos:
        if not i.regular:
            continue
        t = i.tmin + np.arange(int((i.tmax - i.tmin) / HOUR) + 1) * HOUR
        for key in np.unique(t.astype("datetime64[M]")):
            covered[str(key)] = covered.get(str(key), 0) + int(((t.astype("datetime64[M]")) == key).sum())
    years: Dict[int, Dict[str, str]] = {}
    for key, n in sorted(covered.items()):
        y, m = int(key[:4]), int(key[5:7])
        want = ((dt.date(y + (m == 12), m % 12 + 1, 1) - dt.date(y, m, 1)).days) * 24
        years.setdefault(y, {})[f"{m:02d}"] = "ok" if n == want else (f"{n}/{want} h" if n < want else f"{n}/{want} h (DUPLICATE hours)")
    full = [y for y, ms in years.items() if len(ms) == 12 and all(v == "ok" for v in ms.values())]
    return {"files": files, "years": {y: years[y] for y in sorted(years)}, "complete_years": sorted(full)}


# ---------------------------------------------------------------------------------------------- daily build

@dataclass
class YearBuild:
    year: int
    days: int
    complete_days: int
    incomplete: List[str]
    files_used: List[str]
    incomplete_months: List[str]
    path: Optional[Path] = None


def build_year(infos: Sequence[FileInfo], year: int, spec, align: Alignment, stats: Dict[str, Sequence[str]]
               ) -> Tuple[Dict[str, np.ndarray], YearBuild]:
    """Daily fields of one label year, from whichever files cover it. Returns ({TEMP_MEAN: (D, H, W)...}, report)."""
    D = (dt.date(year, 12, 31) - dt.date(year, 1, 1)).days + 1
    H, W = spec.n_lat, spec.n_lon
    first = np.datetime64(f"{year}-01-01")
    lo, hi = first - np.timedelta64(2, "D"), first + np.timedelta64(D + 2, "D")            # every hour that can fall in this label year
    seen = np.zeros(int((hi - lo) / HOUR) + 1, bool)
    acc = {v: {"sum": np.zeros((D, H, W), np.float64), "min": np.full((D, H, W), np.inf, np.float32),
               "max": np.full((D, H, W), -np.inf, np.float32)} for v in VARS}
    cnt = np.zeros((D, H, W), np.int16)
    used: List[str] = []
    for info in infos:
        if info.tmax < lo or info.tmin > hi:
            continue
        for times, data in iter_hourly(info, spec, lo, hi):
            h = ((times - lo) / HOUR).astype(int)
            fresh = ~seen[h]                                                    # an hour present in two files counts once
            seen[h] = True
            day = (align.label(times) - first).astype(int)
            use = fresh & (day >= 0) & (day < D)
            if not use.any():
                continue
            if info.path.name not in used:
                used.append(info.path.name)
            ok_all = np.ones((int(use.sum()), H, W), bool)
            for v in VARS:
                ok_all &= np.isfinite(data[v][use])
            dsel = day[use]
            for d in np.unique(dsel):
                sel = np.nonzero(dsel == d)[0]
                ok = ok_all[sel]
                cnt[d] += ok.sum(axis=0).astype(np.int16)
                for v in VARS:
                    x = data[v][use][sel]
                    acc[v]["sum"][d] += np.where(ok, x, 0.0).sum(axis=0)
                    acc[v]["min"][d] = np.minimum(acc[v]["min"][d], np.where(ok, x, np.inf).min(axis=0))
                    acc[v]["max"][d] = np.maximum(acc[v]["max"][d], np.where(ok, x, -np.inf).max(axis=0))
    day_ok = (cnt == HOURS).all(axis=(1, 2))
    out: Dict[str, np.ndarray] = {}
    for v in VARS:
        for s in stats.get(v, ()):
            arr = (acc[v]["sum"] / np.maximum(cnt, 1)).astype(np.float32) if s == "mean" else acc[v][s].copy()
            out[f"{v}_{s.upper()}"] = np.where(day_ok[:, None, None], arr, np.nan).astype(np.float32)
    dates = first + np.arange(D)
    bad = dates[~day_ok]
    rep = YearBuild(year, D, int(day_ok.sum()), [str(d) for d in bad], used, sorted({str(d)[:7] for d in bad}))
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


def _year_complete(daily_dir: Path, year: int) -> bool:
    p = daily_path(daily_dir, year)
    if not p.is_file():
        return False
    with xr.open_dataset(p, engine="scipy") as ds:
        return not str(ds.attrs.get("incomplete_days", "x"))


def _deletable(info: FileInfo, align: Alignment, daily_dir: Path) -> bool:
    """A file can go once every label year its hours fall in has a complete daily file."""
    a = align.label(np.array([info.tmin]))[0].astype(object).year
    b = align.label(np.array([info.tmax]))[0].astype(object).year
    return all(_year_complete(daily_dir, y) for y in range(a, b + 1))


def build_daily(hourly_dir: Path, daily_dir: Path, years: Sequence[int], spec, align: Alignment,
                stats: Optional[Dict[str, Sequence[str]]] = None, delete_consumed: bool = False,
                overwrite: bool = False) -> List[YearBuild]:
    """Build ``ERA5D_<year>.nc`` for each year from whatever files cover it. Skips years already built and complete; an incomplete one is rebuilt.
    ``delete_consumed`` deletes a hourly file only when every year its hours fall in has a complete daily file, and
    only after the requested years were processed. Default: nothing is deleted."""
    stats = {**DEFAULT_STATS, **(stats or {})}
    daily_dir = Path(daily_dir)
    infos = scan(hourly_dir, spec)
    reports = []
    for year in sorted(years):
        path = daily_path(daily_dir, year)
        if path.is_file() and not overwrite and _year_complete(daily_dir, year):
            log.info("ERA5 daily %d exists and is complete", year)
            continue                                                   # an incomplete year is rebuilt: more hourly data may have arrived
        fields, rep = build_year(infos, year, spec, align, stats)
        if rep.complete_days == 0:
            log.warning("ERA5 %d: no complete day (files missing?)", year)
            reports.append(rep)
            continue
        rep.path = write_year(path, year, fields, spec, align, rep)
        reports.append(rep)
        log.info("ERA5 daily %d: %d of %d days complete", year, rep.complete_days, rep.days)
    if delete_consumed:
        for info in infos:
            if _deletable(info, align, daily_dir):
                for f in [info.path] + list(info.path.parent.glob(info.path.name + "*.idx")):
                    f.unlink()
                log.info("deleted hourly file %s", info.path.name)
        cache = Path(hourly_dir) / ".era5_index.json"
        if cache.is_file():
            cache.unlink()
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
