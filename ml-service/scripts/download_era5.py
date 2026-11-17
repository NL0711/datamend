"""Download ERA5 hourly single-level fields for the RF25 box from the Copernicus Climate Data Store.

Variables: 2m temperature, 2m dewpoint temperature, surface pressure (all hourly, all 24 UTC hours).
Area: the RF25 grid, 6.5-38.5 N and 66.5-100 E. One file per month, so an interrupted run can restart.

The CDS key is read from the CDSAPI_KEY environment variable or from `ml-service/.env`. It is never
written to disk or printed. Create a free account and find the key on your CDS profile page. You must also
accept the dataset's licence once on its Download tab, or the request is refused.

  python scripts/download_era5.py --year 2016 --month 1          # small test: one month
  python scripts/download_era5.py --years 2013 2017 --dry-run    # list what would be requested

Output: $DATAMEND_DATA_DIR/era5/era5_single_<year>_<month>.<ext>  (default ml-service/data/era5/)
Dataset DOI: 10.24381/cds.adbb2d47. Licence shown on the download form: CC-BY.
"""
from __future__ import annotations

import argparse
import calendar
import os
import sys
from pathlib import Path

ML_SERVICE = Path(__file__).resolve().parent.parent
DATASET = "reanalysis-era5-single-levels"
URL = "https://cds.climate.copernicus.eu/api"
VARIABLES = ["2m_temperature", "2m_dewpoint_temperature", "surface_pressure"]
AREA = [38.5, 66.5, 6.5, 100.0]          # North, West, South, East (CDS order)


def read_env_file(path: Path) -> dict:
    out = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def get_key() -> str:
    key = os.environ.get("CDSAPI_KEY") or read_env_file(ML_SERVICE / ".env").get("CDSAPI_KEY")
    if not key:
        sys.exit("error: set CDSAPI_KEY in the environment or in ml-service/.env (see .env.example)")
    return key


def out_dir() -> Path:
    root = os.environ.get("DATAMEND_DATA_DIR")
    return (Path(root) if root else ML_SERVICE / "data") / "era5"


def build_request(year: int, month: int, fmt: str) -> dict:
    days = calendar.monthrange(year, month)[1]
    return {
        "product_type": ["reanalysis"],
        "variable": VARIABLES,
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "day": [f"{d:02d}" for d in range(1, days + 1)],
        "time": [f"{h:02d}:00" for h in range(24)],
        "data_format": fmt,
        "download_format": "unarchived",
        "area": AREA,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--year", type=int)
    ap.add_argument("--month", type=int, help="1-12; with --year, a single month")
    ap.add_argument("--years", type=int, nargs=2, metavar=("FIRST", "LAST"), help="every month of these years")
    ap.add_argument("--format", choices=["grib", "netcdf"], default="grib")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.years:
        jobs = [(y, m) for y in range(args.years[0], args.years[1] + 1) for m in range(1, 13)]
    elif args.year and args.month:
        jobs = [(args.year, args.month)]
    else:
        ap.error("give --year and --month, or --years FIRST LAST")
    ext = "grib" if args.format == "grib" else "nc"
    dest = out_dir()
    todo = [(y, m, dest / f"era5_single_{y}_{m:02d}.{ext}") for y, m in jobs]
    todo = [t for t in todo if not t[2].is_file()]
    print(f"{len(todo)} of {len(jobs)} monthly files to download into {dest}")
    if args.dry_run or not todo:
        return 0
    import cdsapi
    client = cdsapi.Client(url=URL, key=get_key(), quiet=False)   # prints queue state; the key is not printed
    dest.mkdir(parents=True, exist_ok=True)
    for y, m, path in todo:
        tmp = path.with_suffix(path.suffix + ".part")
        print(f"requesting {y}-{m:02d} ...", flush=True)
        client.retrieve(DATASET, build_request(y, m, args.format), str(tmp))
        tmp.replace(path)
        print(f"  saved {path.name} ({path.stat().st_size / 1e6:.1f} MB)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
