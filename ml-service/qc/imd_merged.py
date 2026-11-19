"""Reader for the IMD/NCMRWF merged GPM daily rainfall grid (the product behind the live-input candidate) and its orientation check.

STATUS: written from the page's control file and three sample files (15 Jul 2016, 10 Jan 2017, 2 Sep 2016, fetched 2026-11-18); tested on
generated files and, once, by hand on those three files. Source page: https://imdpune.gov.in/cmpg/Realtimedata/gpm/Rain_Download.html

What is established (from the control file and the files):
  * GrADS-style description: ``XDEF 241 LINEAR 50.0 0.25``, ``YDEF 281 LINEAR -30.0 0.25``, undefined value -999.0, one variable ``rf``.
  * Each file is exactly 241 * 281 * 4 bytes: little-endian float32 (read as big-endian it gives values near 1e38).
  * RF25 (6.5-38.5 N, 66.5-100 E, 0.25 degree) is an exact sub-window of this grid.
What is NOT established and is therefore never guessed:
  * the ROW ORDER of the binary file. A control file without ``options yrev`` means south-first in GrADS, but IMD's separate 0/1 map grid
    is north-first, and three sample days gave conflicting hints. ``read_grd`` therefore needs ``row_order`` and ``verify_orientation``
    decides it by comparing the product with RF25 on the same dates; ``run_bridge`` callers must run it first.
  * the units (assumed mm per day) and the day the value belongs to (03 UTC to 03 UTC per the paper's landing page, unverified).
  * licence and automated-download terms: none found. Do not download in bulk until they are known.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Sequence

import numpy as np

ROW_ORDERS = ("south_first", "north_first")


@dataclass(frozen=True)
class MergedGrid:
    nx: int
    ny: int
    x0: float
    y0: float
    dx: float
    dy: float
    undef: float
    var: str

    @property
    def nbytes(self) -> int:
        return self.nx * self.ny * 4


def parse_control(text: str) -> MergedGrid:
    """Parse the GrADS-style control text of the merged grid. Only the fields the product uses are read; anything else is refused."""
    u = {}
    for line in text.splitlines():
        t = line.strip()
        if not t:
            continue
        key = t.split()[0].upper()
        u[key] = t
    for need in ("XDEF", "YDEF", "UNDEF", "VARS"):
        if need not in u:
            raise ValueError(f"control text has no {need} line")
    xm = re.match(r"XDEF\s+(\d+)\s+LINEAR\s+([-\d.]+)\s+([-\d.]+)", u["XDEF"], re.I)
    ym = re.match(r"YDEF\s+(\d+)\s+LINEAR\s+([-\d.]+)\s+([-\d.]+)", u["YDEF"], re.I)
    if not xm or not ym:
        raise ValueError("only LINEAR XDEF and YDEF definitions are supported")
    if "OPTIONS" in u:
        raise ValueError(f"unsupported control option line: {u['OPTIONS']!r} (row order and byte order would change)")
    names = re.findall(r"^\s*(\w+)\s+\d+\s+\d+\s+", text, re.M)
    names = [n for n in names if n.upper() not in ("XDEF", "YDEF", "ZDEF", "TDEF", "DSET", "TITLE", "UNDEF", "VARS", "ENDVARS")]
    if len(names) != 1:
        raise ValueError(f"expected exactly one variable, found {names}")
    return MergedGrid(int(xm.group(1)), int(ym.group(1)), float(xm.group(2)), float(ym.group(2)), float(xm.group(3)),
                      float(ym.group(3)), float(u["UNDEF"].split()[1]), names[0])


def read_grd(path: Path, grid: MergedGrid, row_order: str) -> np.ndarray:
    """One day as (ny, nx) float32 mm with row 0 the SOUTHERNMOST row (latitude ascending, like RF25). Undefined values are NaN.
    ``row_order`` says how the file is laid out: ``south_first`` (row 0 of the file is the most southern) or ``north_first``."""
    if row_order not in ROW_ORDERS:
        raise ValueError(f"row_order must be one of {ROW_ORDERS}; it has to be established with verify_orientation, not guessed")
    raw = Path(path).read_bytes()
    if len(raw) != grid.nbytes:
        raise ValueError(f"{path} has {len(raw)} bytes, expected {grid.nbytes} (= {grid.nx} x {grid.ny} x 4, little-endian float32)")
    a = np.frombuffer(raw, dtype="<f4").reshape(grid.ny, grid.nx).astype(np.float32)
    if not np.isfinite(a).all() or np.abs(a[a != grid.undef]).max(initial=0.0) > 1e5:
        raise ValueError(f"{path} does not look like little-endian float32 rainfall (non-finite or enormous values)")
    a = np.where(a == grid.undef, np.nan, a)
    return a[::-1] if row_order == "north_first" else a


def rf25_window(grid: MergedGrid, lat0: float = 6.5, lon0: float = 66.5, n_lat: int = 129, n_lon: int = 135, step: float = 0.25):
    """Row and column slices of the merged grid (south-first) that cover the RF25 grid exactly."""
    if abs(grid.dx - step) > 1e-9 or abs(grid.dy - step) > 1e-9:
        raise ValueError("the merged grid and RF25 have different spacing")
    r, c = (lat0 - grid.y0) / step, (lon0 - grid.x0) / step
    if abs(r - round(r)) > 1e-6 or abs(c - round(c)) > 1e-6:
        raise ValueError("RF25 is not an exact sub-window of the merged grid")
    r, c = int(round(r)), int(round(c))
    if r < 0 or c < 0 or r + n_lat > grid.ny or c + n_lon > grid.nx:
        raise ValueError("the RF25 grid does not fit inside the merged grid")
    return slice(r, r + n_lat), slice(c, c + n_lon)


def verify_orientation(file_days: Sequence[np.ndarray], rf25_days: Sequence[np.ndarray], grid: MergedGrid, land: np.ndarray,
                       min_corr: float = 0.3, min_margin: float = 0.1, **window) -> Dict:
    """Decide the row order of the files by comparing them with RF25 on the SAME dates. ``file_days`` are (ny, nx) arrays exactly as stored
    (row 0 = first row of the file); ``rf25_days`` are (H, W) mm with row 0 the southernmost row; ``land`` is the RF25 land mask (H, W).
    For each candidate row order the pooled correlation over land cells is computed; the order is accepted only if its correlation is at
    least ``min_corr`` and beats the other by ``min_margin``. Raises otherwise: an unverified orientation would put every cell in the
    wrong place. Use several days with rain in them."""
    if len(file_days) != len(rf25_days) or not file_days:
        raise ValueError("need the same, non-zero number of file days and RF25 days")
    rs, cs = rf25_window(grid, **window)
    corr = {}
    for order in ROW_ORDERS:
        xs, ys = [], []
        for f, r in zip(file_days, rf25_days):
            a = f[::-1] if order == "north_first" else f
            a = np.where(a == grid.undef, np.nan, a)[rs, cs]
            m = land & np.isfinite(a) & np.isfinite(r)
            xs.append(a[m])
            ys.append(r[m])
        x, y = np.concatenate(xs), np.concatenate(ys)
        corr[order] = float(np.corrcoef(x, y)[0, 1]) if x.size > 10 and x.std() > 0 and y.std() > 0 else float("nan")
    best = max(ROW_ORDERS, key=lambda k: -np.inf if np.isnan(corr[k]) else corr[k])
    other = [k for k in ROW_ORDERS if k != best][0]
    if np.isnan(corr[best]) or corr[best] < min_corr or (not np.isnan(corr[other]) and corr[best] - corr[other] < min_margin):
        raise ValueError(f"the row order could not be established from RF25: correlations {corr}; use more days with rain")
    return {"row_order": best, "correlation": corr, "days": len(file_days)}
