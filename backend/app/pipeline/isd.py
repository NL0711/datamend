"""Import FILE FORMAT for NOAA ISD hourly files (one file per station and year, fixed-width ``.gz`` or the NCEI CSV), read from an S3 link or a
Kaggle dataset and turned into ordinary rainfall readings through the normal ingest job path (``jobs.SOURCES['isd']``).

This is a reader only. There is no replay, no station list and no ISD-specific page: a station's name is ``ISD <usaf>-<wban>`` and its position is
the one in the file's own header fields (fixed-width: latitude and longitude in thousandths of a degree; CSV: LATITUDE and LONGITUDE), or none.

Format facts (docs/research/noaa-isd-rainfall-facts.md): the mandatory section of a fixed-width record is 105 characters (station USAF 5-10, WBAN
11-15, date 16-23, time 24-27, latitude 29-34 and longitude 35-41 in thousandths of a degree); liquid precipitation groups AA1..AA4 follow, each
``AAn`` + period (hours, 2 digits) + depth (tenths of mm, 9999 = missing) + condition (1) + quality (1). Remarks (REM) and element-quality (EQD)
sections are cut off before the groups are read, so text inside them is never taken for a group. The CSV layout has one column per group
(``AA1``..``AA4``) holding ``period,depth,condition,quality``.

OVERLAP RULE (no double counting). Every AA group is an accumulation over ``period`` whole hours ending at the record time (rounded UP to the
next full hour). Per station, groups are taken in order of period (1 hour first, then 2, 3, 6, 12, 24 ...), then good quality before the
rest, then file order. A group is KEPT only if none of the hours it covers is already covered by a kept group; otherwise it is dropped and
listed as a problem row ("overlaps ..."). So a 24-hour total is kept only for a day on which no finer group was kept inside it, and two reports
of the same hour never both count. A kept group is stored as ONE value stamped at the START of the LAST hour of its period (a 24-hour total
ending 03:00 UTC is stamped 02:00 UTC, inside the rain day it ends); a multi-hour value is NOT spread over its hours (that would invent hourly
values) and is listed as a warning. Missing depth (9999) is skipped, never zero; quality 3 and 7 (erroneous) are not stored; 2 and 6 (suspect)
are stored with a warning. A record with no AA group says nothing about rain and adds no row.

Non-US ISD data is subject to WMO Resolution 40 and must not be redistributed: it is fetched at run time only and never committed.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

SOURCE = "isd"
omits_zero_values = False      # a real zero is reported as depth 0000, so a missing hour is not assumed dry, and zeros are present
MANDATORY_LEN = 105
MISSING_DEPTH = "9999"
GOOD_QUALITY = frozenset("15")
BAD_QUALITY = frozenset("37")            # erroneous: not stored
SUSPECT_QUALITY = frozenset("26")        # suspect: stored with a warning
MAX_LINE = 8192
_GROUP = re.compile(r"AA([1-4])(\d{2})(\d{4})(\w)(\w)")
_CSV_GROUP = re.compile(r"\s*(\d{1,2})\s*,\s*(\d{1,4})\s*,\s*(\w?)\s*,\s*(\w?)\s*")
_AA_COLUMN = re.compile(r"AA[1-4]")
ASSUMPTIONS = {
    "time_zone": "UTC (ISD time stamps are UTC)",
    "units": "ISD depth is tenths of a millimetre; 9999 means missing and is skipped, never zero",
    "overlap_rule": "per station the groups with the shortest period are kept first; a longer group is kept only if none of its hours is already covered, so "
                    "no rain is counted twice. A multi-hour total is stored as one value at the last hour of its period (not spread over its hours)",
    "time_stamp": "a record time is rounded up to the next full hour; a value is stamped at the start of the last hour it covers",
    "quality": "ISD quality 3 and 7 (erroneous) are not stored; 2 and 6 (suspect) are stored with a warning",
    "position": "latitude and longitude come from the file's own header fields; a station without them has no position",
    "licence": "non-US ISD data is subject to WMO Resolution 40: fetched at run time only, never committed or redistributed",
}


class IsdFormatError(ValueError):
    """The file is not an NOAA ISD file (a file-level problem: the whole file is rejected)."""


FormatError = IsdFormatError


@dataclass
class IsdRow:
    row_number: int
    station_key: str
    name: str
    state: Optional[str]
    district: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    observed_at: Optional[datetime]
    value_mm: Optional[float]
    problem: Optional[str] = None
    warning: Optional[str] = None


Group = Tuple[int, Optional[float], str, str]          # period hours, mm or None, condition, quality


# ------------------------------------------------------------------------------------------------ record parsing
def parse_line(line: str) -> Optional[Tuple[str, datetime, List[Group]]]:
    """One fixed-width ISD record -> (USAF-WBAN, UTC time, [(period_hours, mm or None, condition, quality), ...]); None for a malformed record."""
    if len(line) < MANDATORY_LEN:
        return None
    s = line[4:15].strip()
    if len(s) != 11:
        return None
    try:
        when = datetime.strptime(line[15:23] + line[23:27], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    additional = line[MANDATORY_LEN:]
    for marker in ("REM", "EQD"):                        # text in remarks or element-quality sections is never a precipitation group
        cut = additional.find(marker)
        if cut >= 0:
            additional = additional[:cut]
    groups: List[Group] = []
    for m in _GROUP.finditer(additional):
        depth = None if m.group(3) == MISSING_DEPTH else int(m.group(3)) / 10.0
        groups.append((int(m.group(2)), depth, m.group(4), m.group(5)))
    return f"{s[:6]}-{s[6:]}", when, groups


def parse_position(line: str) -> Tuple[Optional[float], Optional[float]]:
    """Latitude and longitude from the mandatory section (+99999 / +999999 mean missing)."""
    try:
        lat, lon = int(line[28:34]), int(line[34:41])
    except ValueError:
        return None, None
    if abs(lat) == 99999 or abs(lon) == 999999 or abs(lat) > 90000 or abs(lon) > 180000:
        return None, None
    return lat / 1000.0, lon / 1000.0


def looks_like_fixed_width(line: str) -> bool:
    line = line.rstrip("\r\n")
    return parse_line(line) is not None and line[27:28].isalnum()


def looks_like_csv_header(line: str) -> bool:
    """The NCEI ISD CSV header: quoted or plain STATION and DATE columns and at least one AA1..AA4 precipitation column."""
    cols = {c.strip().strip('"').upper() for c in line.strip().split(",")}
    return {"STATION", "DATE"} <= cols and any(_AA_COLUMN.fullmatch(c) for c in cols)


def sniff_layout(first_line: str) -> Optional[str]:
    """'fixed' or 'csv' when the first line is an ISD record or header, else None."""
    if looks_like_fixed_width(first_line):
        return "fixed"
    if looks_like_csv_header(first_line):
        return "csv"
    return None


def _ceil_hour(t: datetime) -> datetime:
    floor = t.replace(minute=0, second=0, microsecond=0)
    return floor if floor == t else floor + timedelta(hours=1)


def _lines(path: str) -> Iterator[Tuple[int, str]]:
    """Lines of a plain text file (gzip is unpacked by ``importers.prepare``), never a line longer than MAX_LINE kept."""
    with open(path, "rb") as f:
        n = 0
        while True:
            chunk = f.readline(MAX_LINE)
            if not chunk:
                break
            n += 1
            while not chunk.endswith(b"\n") and len(chunk) == MAX_LINE:          # an over-long line: keep its start, drain the rest
                more = f.readline(MAX_LINE)
                if not more or more.endswith(b"\n"):
                    break
            yield n, chunk.decode("ascii", errors="replace")


Record = Tuple[int, str, datetime, List[Group], Optional[float], Optional[float]]        # line, USAF-WBAN, time, groups, latitude, longitude
Malformed = Tuple[int, str]


def _fixed_records(path: str) -> Iterator[Any]:
    seen_first = False
    for n, line in _lines(path):
        if not line.strip():
            continue
        rec = parse_line(line.rstrip("\r\n"))
        if not seen_first:
            if rec is None:
                raise IsdFormatError("not an NOAA ISD file: the first record is not in the ISD fixed-width layout")
            seen_first = True
        if rec is None:
            yield (n, "malformed ISD record")
            continue
        sid, when, groups = rec
        lat, lon = parse_position(line)
        yield (n, sid, when, groups, lat, lon)
    if not seen_first:
        raise IsdFormatError("the file is empty")


def _csv_coord(v: Optional[str], limit: float) -> Optional[float]:
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if abs(x) <= limit else None


def _csv_records(path: str) -> Iterator[Any]:
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        names = {(c or "").strip().upper(): c for c in (reader.fieldnames or [])}
        aa = [names[k] for k in sorted(names) if _AA_COLUMN.fullmatch(k)]
        if "STATION" not in names or "DATE" not in names or not aa:
            raise IsdFormatError("not an NOAA ISD CSV: needs the columns STATION, DATE and at least one of AA1..AA4")
        seen = False
        for i, r in enumerate(reader, start=2):
            seen = True
            station = (r.get(names["STATION"]) or "").strip()
            if len(station) != 11 or not station.isalnum():
                yield (i, "station is not an ISD id (USAF + WBAN, 11 characters)")
                continue
            try:
                when = datetime.fromisoformat((r.get(names["DATE"]) or "").strip()).replace(tzinfo=timezone.utc)
            except ValueError:
                yield (i, "malformed ISD record")
                continue
            groups: List[Group] = []
            bad = False
            for col in aa:
                text = (r.get(col) or "").strip()
                if not text:
                    continue
                m = _CSV_GROUP.fullmatch(text)
                if not m:
                    bad = True
                    continue
                depth = None if m.group(2).zfill(4) == MISSING_DEPTH else int(m.group(2)) / 10.0
                groups.append((int(m.group(1)), depth, m.group(3) or "9", m.group(4) or "9"))
            if bad and not groups:
                yield (i, "malformed ISD record")
                continue
            lat = _csv_coord(r.get(names["LATITUDE"]), 90.0) if "LATITUDE" in names else None
            lon = _csv_coord(r.get(names["LONGITUDE"]), 180.0) if "LONGITUDE" in names else None
            if lat is None or lon is None:
                lat = lon = None
            yield (i, f"{station[:6]}-{station[6:]}", when, groups, lat, lon)
        if not seen:
            raise IsdFormatError("the file has a header but no records")


def _layout_of(path: str) -> str:
    for _n, line in _lines(path):
        if line.strip():
            layout = sniff_layout(line)
            if layout is None:
                raise IsdFormatError("not an NOAA ISD file: the first line is neither an ISD fixed-width record nor an ISD CSV header")
            return layout
    raise IsdFormatError("the file is empty")


def read_rows(path: str) -> Iterator[IsdRow]:
    """Stream the rows of an ISD file. Raises IsdFormatError before the first row when the file is not ISD."""
    records = _csv_records(path) if _layout_of(path) == "csv" else _fixed_records(path)
    pos: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    groups_by: Dict[str, List[Tuple[int, datetime, int, float, str, str]]] = {}
    for rec in records:
        if len(rec) == 2:
            n, why = rec
            yield IsdRow(n, "", "", None, None, None, None, None, None, problem=why)
            continue
        n, sid, when, groups, lat, lon = rec
        key = f"isd:{sid}"
        if pos.get(key, (None, None)) == (None, None):
            pos[key] = (lat, lon)
        for period, mm, cond, qual in groups:
            base = dict(row_number=n, station_key=key, name="", state=None, district=None, latitude=None, longitude=None)
            if period == 0:
                yield IsdRow(**base, observed_at=None, value_mm=None, problem="precipitation period of 0 hours")
            elif mm is None:
                yield IsdRow(**base, observed_at=None, value_mm=None, problem="precipitation depth missing (9999), skipped, not zero")
            elif qual in BAD_QUALITY:
                yield IsdRow(**base, observed_at=None, value_mm=None, problem=f"source quality code {qual} (erroneous), not stored")
            else:
                groups_by.setdefault(key, []).append((n, when, period, mm, cond, qual))
    for key in sorted(groups_by):
        lat, lon = pos.get(key, (None, None))
        fields = dict(station_key=key, name=f"ISD {key[4:]}", state=None, district=None, latitude=lat, longitude=lon)
        covered: set = set()
        kept: List[IsdRow] = []
        order = sorted(groups_by[key], key=lambda g: (g[2], 0 if g[5] in GOOD_QUALITY else 1, g[1], g[0]))
        for n, when, period, mm, cond, qual in order:
            end = _ceil_hour(when)
            last = end - timedelta(hours=1)
            hours = {int((last - timedelta(hours=i)).timestamp() // 3600) for i in range(period)}
            if hours & covered:
                yield IsdRow(row_number=n, observed_at=None, value_mm=None, **fields,
                             problem=f"{period}-hour group overlaps hours already kept from a finer group, dropped to avoid double counting")
                continue
            covered |= hours
            warn = None
            if period > 1:
                warn = f"{period}-hour total stored as one value at the last hour of its period (not spread over the hours)"
            if qual in SUSPECT_QUALITY:
                warn = (warn + "; " if warn else "") + f"source quality code {qual} (suspect)"
            kept.append(IsdRow(row_number=n, observed_at=last, value_mm=mm, warning=warn, **fields))
        kept.sort(key=lambda r: r.observed_at)
        yield from kept


def station_record(row: IsdRow) -> Dict[str, Any]:
    return {"station_key": row.station_key, "source": SOURCE, "name": row.name[:128], "state": None, "district": None,
            "latitude": row.latitude, "longitude": row.longitude}
