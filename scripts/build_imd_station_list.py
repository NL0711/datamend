"""Build the list of Indian synoptic stations (IMD stations that report through NOAA's Integrated Surface Database) as a small CSV.

Source: NOAA NCEI station inventory, https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv (station METADATA only: names and coordinates;
no observations). IMD's own AWS/ARG station list is not public, so this is the closest open list of IMD stations. It is NOT IMD's list:
a station appears here only if it has reported to NOAA, and `last_data` shows when that stopped.

Usage:
    python scripts/build_imd_station_list.py isd-history.csv backend/app/places/data/imd_stations.csv

Kept: country IN, coordinates present and inside India's bounding box, not a placeholder ("BOGUS"). Output columns:
id (USAF-WBAN), name, state, icao, latitude, longitude, elevation_m, first_data, last_data (ISO dates).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, List

LAT_RANGE = (6.0, 38.0)
LON_RANGE = (66.0, 100.0)


def _date(s: str) -> str:
    s = (s or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else ""


def _num(s: str):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse(rows) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for r in rows:
        if (r.get("CTRY") or "").strip() != "IN":
            continue
        name = (r.get("STATION NAME") or "").strip()
        lat, lon = _num(r.get("LAT")), _num(r.get("LON"))
        if "BOGUS" in name.upper() or lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            continue
        if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
            continue
        elev = _num(r.get("ELEV(M)"))
        out.append({
            "id": f"{r['USAF'].strip()}-{r['WBAN'].strip()}", "name": name.title(), "state": (r.get("STATE") or "").strip(),
            "icao": (r.get("ICAO") or "").strip(), "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
            "elevation_m": "" if elev is None else f"{elev:.0f}", "first_data": _date(r.get("BEGIN")), "last_data": _date(r.get("END")),
        })
    if not out:
        raise ValueError("no Indian stations found; is this NOAA's isd-history.csv?")
    return sorted(out, key=lambda x: (x["name"], x["id"]))


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf8", errors="replace", newline="") as f:
        rows = parse(csv.DictReader(f))
    dst = Path(argv[2])
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} stations to {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
