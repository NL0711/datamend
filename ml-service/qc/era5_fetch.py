"""Download ERA5 hourly fields from the Copernicus CDS, one year per request, and convert each year as it arrives.

Used by ``notebooks/datamend_era5_kaggle.local.ipynb`` (and usable anywhere ``cdsapi`` works). The client is passed
in, so no credential lives in this module and the logic can be tested with a fake client.

Request: dataset ``reanalysis-era5-single-levels``, product ``reanalysis``, variables 2 m temperature, 2 m dewpoint
temperature and surface pressure, every day and all 24 hours, area N 38.5, W 66.5, S 6.5, E 100.0 (the RF25 grid).
A year is requested at once; if the CDS says the request is too large it is split into months. Downloads run one at a time by default
(the CDS rejects further requests once a few of yours are queued), and each year is converted to daily fields in the calling thread as soon as
its download finishes, so only a few years of hourly files are on disk at a time. A year that fails after retries is
reported, never hidden, and does not stop the others.
"""

from __future__ import annotations

import calendar
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

log = logging.getLogger(__name__)
DATASET = "reanalysis-era5-single-levels"
VARIABLES = ["2m_temperature", "2m_dewpoint_temperature", "surface_pressure"]
AREA = [38.5, 66.5, 6.5, 100.0]                       # North, West, South, East
TOO_LARGE = ("too large", "cost limit", "cost limits", "request is too large", "exceed")
QUEUE_FULL = ("queued requests", "request data sequentially")      # the CDS allows only a few queued requests per user and dataset


def build_request(year: int, months: Sequence[int], fmt: str = "grib") -> Dict:
    days = max(calendar.monthrange(year, m)[1] for m in months)
    return {
        "product_type": ["reanalysis"],
        "variable": VARIABLES,
        "year": [str(year)],
        "month": [f"{m:02d}" for m in months],
        "day": [f"{d:02d}" for d in range(1, days + 1)],
        "time": [f"{h:02d}:00" for h in range(24)],
        "data_format": fmt,
        "download_format": "unarchived",
        "area": AREA,
    }


def _retrieve(client, request: Dict, target: Path, retries: int, wait: float, queue_wait: float = 180.0, queue_tries: int = 60) -> None:
    """One download. Ordinary errors are retried ``retries`` times. "Queue full" is waited out (``queue_wait`` seconds,
    up to ``queue_tries`` times) without using up the ordinary retries: the CDS rejects the new job at once, so waiting
    costs nothing and retrying fast only adds rejected jobs."""
    tmp = target.with_suffix(target.suffix + ".part")
    last: Optional[Exception] = None
    attempt = full = 0
    while True:
        try:
            client.retrieve(DATASET, request, str(tmp))
            tmp.replace(target)
            return
        except Exception as e:                                     # CDS and network errors come in many types
            last = e
            msg = str(e).lower()
            if any(k in msg for k in TOO_LARGE):
                raise
            if any(k in msg for k in QUEUE_FULL):
                full += 1
                if full > queue_tries:
                    raise
                log.warning("%s: the CDS queue for this dataset is full (other requests of yours are still queued, delete finished or stuck "
                            "ones under 'Your requests' on the CDS site); waiting %.0f s [%d/%d]", target.name, queue_wait, full, queue_tries)
                time.sleep(queue_wait)
                continue
            if attempt < retries:
                log.warning("%s: attempt %d failed (%s); retrying", target.name, attempt + 1, str(e)[:120])
                time.sleep(wait * (attempt + 1))
                attempt += 1
                continue
            raise last                                              # type: ignore[misc]


def fetch_year(client, hourly_dir: Path, year: int, fmt: str = "grib", retries: int = 2, wait: float = 30.0) -> List[Path]:
    """Hourly file(s) for one year: one file, or twelve monthly files if the CDS refuses the whole year. Files that
    already exist are kept, not downloaded again."""
    hourly_dir = Path(hourly_dir)
    hourly_dir.mkdir(parents=True, exist_ok=True)
    ext = "grib" if fmt == "grib" else "nc"
    whole = hourly_dir / f"era5_single_{year}.{ext}"
    months = [hourly_dir / f"era5_single_{year}_{m:02d}.{ext}" for m in range(1, 13)]
    if whole.is_file():
        return [whole]
    if all(f.is_file() for f in months):
        return months
    try:
        _retrieve(client, build_request(year, range(1, 13), fmt), whole, retries, wait)
        return [whole]
    except Exception as e:
        if not any(k in str(e).lower() for k in TOO_LARGE):
            raise
        log.info("%d: whole-year request refused as too large; requesting month by month", year)
    for m, f in zip(range(1, 13), months):
        if not f.is_file():
            _retrieve(client, build_request(year, [m], fmt), f, retries, wait)
    return months


def fetch_and_convert(client_factory: Callable[[], object], years: Sequence[int], hourly_dir: Path,
                      convert: Callable[[int], object], fmt: str = "grib", workers: int = 1, retries: int = 2,
                      wait: float = 30.0, skip: Callable[[int], bool] = lambda y: False) -> Dict[int, str]:
    """Download ``years`` (``workers`` at a time) and call ``convert(year)`` in this thread as each one arrives.
    ``skip(year)`` is true for years that are already done. Returns year -> 'done' | 'skipped' | 'failed: <reason>'."""
    status: Dict[int, str] = {}
    todo = []
    for y in years:
        if skip(y):
            status[y] = "skipped"
        else:
            todo.append(y)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fetch_year, client_factory(), hourly_dir, y, fmt, retries, wait): y for y in todo}
        for fut in as_completed(futures):
            y = futures[fut]
            try:
                fut.result()
            except Exception as e:
                status[y] = f"failed: download: {str(e)[:200]}"
                log.error("%d download failed: %s", y, e)
                continue
            try:
                convert(y)
                status[y] = "done"
            except Exception as e:
                status[y] = f"failed: convert: {str(e)[:200]}"
                log.error("%d conversion failed: %s", y, e)
    return dict(sorted(status.items()))
