"""Adapter for the Central Water Commission hourly telemetry rainfall CSVs (National Water Data Portal, one file per state and period).

Shape measured on one real file (Tripura 2021-2025, wayfinder ticket "What does one real CWC file look like?"): columns Station, State,
District, Latitude, Longitude, ``Data Acquisition Time`` (dd-mm-yyyy hh:mm) and ``Telemetry Hourly Rainfall (mm)``. Only NON-ZERO hours are
present in that file, so a missing hour is neither dry nor missing; the roll-up says so. The time zone is not stated by the source: IST
(UTC+05:30) is ASSUMED and recorded on every job. The licence is "Other (Open)" with no name; derived-flag storage is unconfirmed.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, Optional

SOURCE = "cwc"
ASSUMED_OFFSET = timedelta(hours=5, minutes=30)
ASSUMPTIONS = {
    "time_zone": "Asia/Kolkata (IST, UTC+05:30) ASSUMED: the source does not state it",
    "zero_hours": "the source file lists only non-zero hours: a missing hour is not known to be dry",
    "units": "mm per hour as the column name says (not otherwise confirmed)",
    "licence": "portal says 'Other (Open)' with no licence name; storing derived flags is unconfirmed",
}
COLUMNS = {"station": "Station", "state": "State", "district": "District", "lat": "Latitude", "lon": "Longitude",
           "time": "Data Acquisition Time", "mm": "Telemetry Hourly Rainfall (mm)"}
TIME_FORMATS = ("%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


class CwcFormatError(ValueError):
    """The file is not a CWC hourly rainfall CSV (a file-level problem: the whole file is rejected)."""


@dataclass
class CwcRow:
    row_number: int
    station_key: str
    name: str
    state: Optional[str]
    district: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    observed_at: Optional[datetime]
    value_mm: Optional[float]
    problem: Optional[str] = None           # set when the row cannot be stored; the row is counted and listed, never silently dropped


def _num(s: Optional[str]) -> Optional[float]:
    try:
        return float(str(s).strip()) if s is not None and str(s).strip() != "" else None
    except ValueError:
        return None


def parse_time(s: str) -> Optional[datetime]:
    for fmt in TIME_FORMATS:
        try:
            return (datetime.strptime(s.strip(), fmt) - ASSUMED_OFFSET).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def station_key(state: Optional[str], name: str) -> str:
    """A stable id of at most 64 characters (the width of the validation tables); a longer one is cut and given a short hash."""
    base = f"cwc:{(state or '-').strip().lower()}:{name.strip().lower()}"
    if len(base) <= 64:
        return base
    return base[:55] + "~" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]


def read_rows(path: str) -> Iterator[CwcRow]:
    """Stream the rows of a CWC file. Raises CwcFormatError before the first row when required columns are missing."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for k, c in COLUMNS.items() if k in ("station", "lat", "lon", "time", "mm") and c not in (reader.fieldnames or [])]
        if missing:
            raise CwcFormatError("not a CWC hourly rainfall file; missing columns: " + ", ".join(missing))
        for i, r in enumerate(reader, start=1):
            name = (r.get(COLUMNS["station"]) or "").strip()
            state = (r.get(COLUMNS["state"]) or "").strip() or None
            row = CwcRow(i, station_key(state, name) if name else "", name, state, (r.get(COLUMNS["district"]) or "").strip() or None,
                         _num(r.get(COLUMNS["lat"])), _num(r.get(COLUMNS["lon"])), None, None)
            if not name:
                row.problem = "no station name"
            else:
                row.observed_at = parse_time(r.get(COLUMNS["time"]) or "")
                row.value_mm = _num(r.get(COLUMNS["mm"]))
                if row.observed_at is None:
                    row.problem = f"time not understood: {(r.get(COLUMNS['time']) or '')[:30]!r}"
                elif row.value_mm is None:
                    row.problem = f"rainfall not a number: {(r.get(COLUMNS['mm']) or '')[:30]!r}"
            yield row


def station_record(row: CwcRow) -> Dict[str, Any]:
    return {"station_key": row.station_key, "source": SOURCE, "name": row.name, "state": row.state, "district": row.district,
            "latitude": row.latitude, "longitude": row.longitude}
