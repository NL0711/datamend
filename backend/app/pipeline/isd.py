"""Adapter for NOAA ISD fixed-width files (one file per station and year, usually gzip), read from an S3 link or a Kaggle dataset.

Format facts (docs/research/noaa-isd-rainfall-facts.md): the mandatory section is 105 characters (station USAF 5-10, WBAN 11-15, date 16-23,
time 24-27, latitude 29-34 and longitude 35-41 in thousandths of a degree); liquid precipitation groups AA1..AA4 follow, each ``AAn`` + period
(hours, 2 digits) + depth (tenths of mm, 9999 = missing) + condition (1) + quality (1).

OVERLAP RULE (no double counting). Every AA group is an accumulation over ``period`` whole hours ending at the record time (rounded UP to the
next full hour). Per station, groups are taken in order of period (1 hour first, then 2, 3, 6, 12, 24 ...), then good quality before the
rest, then file order. A group is KEPT only if none of the hours it covers is already covered by a kept group; otherwise it is dropped and
listed as a problem row ("overlaps ..."). So a 24-hour total is kept only for a day on which no finer group was kept inside it, and two reports
of the same hour never both count. A kept group is stored as ONE value stamped at the START of the LAST hour of its period (a 24-hour total
ending 03:00 UTC is stamped 02:00 UTC, inside the rain day it ends); a multi-hour value is NOT spread over its hours (that would invent hourly
values) and is listed as a warning. Missing depth (9999) is skipped, never zero; quality 3 and 7 (erroneous) are not stored; 2 and 6 (suspect)
are stored with a warning.

Non-US ISD data is subject to WMO Resolution 40 and must not be redistributed: it is fetched at run time only and never committed.
"""
from __future__ import annotations

import gzip
import re
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

SOURCE = "isd"
omits_zero_values = False      # a real zero is reported as depth 0000, so a missing hour is not assumed dry but is not hidden zeros either
MANDATORY_LEN = 105
MISSING_DEPTH = "9999"
GOOD_QUALITY = frozenset("15")
BAD_QUALITY = frozenset("37")            # erroneous: not stored
SUSPECT_QUALITY = frozenset("26")        # suspect: stored with a warning
MAX_TEXT_BYTES = 3_000_000_000           # after decompression: a guard against a decompression bomb
MAX_LINE = 8192
_GROUP = re.compile(r"AA([1-4])(\d{2})(\d{4})(\w)(\w)")
ASSUMPTIONS = {
    "time_zone": "UTC (ISD time stamps are UTC)",
    "units": "ISD depth is tenths of a millimetre; 9999 means missing and is skipped, never zero",
    "overlap_rule": "per station the groups with the shortest period are kept first; a longer group is kept only if none of its hours is already covered, so "
                    "no rain is counted twice. A multi-hour total is stored as one value at the last hour of its period (not spread over its hours)",
    "time_stamp": "a record time is rounded up to the next full hour; a value is stamped at the start of the last hour it covers",
    "quality": "ISD quality 3 and 7 (erroneous) are not stored; 2 and 6 (suspect) are stored with a warning",
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


def split_id(isd_id: str) -> Tuple[str, str]:
    usaf, _, wban = isd_id.partition("-")
    if len(usaf) != 6 or len(wban) != 5 or not (usaf + wban).isalnum():
        raise ValueError("not an ISD station id (USAF-WBAN)")
    return usaf, wban


def parse_line(line: str) -> Optional[Tuple[str, datetime, List[Tuple[int, Optional[float], str, str]]]]:
    """One ISD record -> (USAF-WBAN, UTC time, [(period_hours, mm or None, condition, quality), ...]); None for a malformed record."""
    if len(line) < MANDATORY_LEN:
        return None
    s = line[4:15].strip()
    if len(s) != 11:
        return None
    try:
        when = datetime.strptime(line[15:23] + line[23:27], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    groups = []
    for m in _GROUP.finditer(line[MANDATORY_LEN:]):
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


def looks_like_isd(line: str) -> bool:
    return parse_line(line.rstrip("\r\n")) is not None and line[27:28].isalnum()


def _ceil_hour(t: datetime) -> datetime:
    floor = t.replace(minute=0, second=0, microsecond=0)
    return floor if floor == t else floor + timedelta(hours=1)


def _lines(path: str) -> Iterator[Tuple[int, str]]:
    """Lines of a plain or gzip file, never more than MAX_TEXT_BYTES decompressed, never a line longer than MAX_LINE kept."""
    total = 0
    try:
        with open(path, "rb") as raw:
            magic = raw.read(2)
            raw.seek(0)
            f = gzip.GzipFile(fileobj=raw) if magic == b"\x1f\x8b" else raw
            n = 0
            while True:
                chunk = f.readline(MAX_LINE)
                if not chunk:
                    break
                n += 1
                total += len(chunk)
                while not chunk.endswith(b"\n") and len(chunk) == MAX_LINE:          # an over-long line: keep its start, drain the rest
                    more = f.readline(MAX_LINE)
                    total += len(more)
                    if total > MAX_TEXT_BYTES:
                        raise IsdFormatError("the decompressed ISD file is larger than the safety limit")
                    if not more or more.endswith(b"\n"):
                        break
                if total > MAX_TEXT_BYTES:
                    raise IsdFormatError("the decompressed ISD file is larger than the safety limit")
                yield n, chunk.decode("ascii", errors="replace")
    except (gzip.BadGzipFile, EOFError, zlib.error):
        raise IsdFormatError("the gzip file is damaged") from None


def _name_lookup() -> Dict[str, Dict[str, Any]]:
    from backend.app.places import imd
    return {s["id"]: s for s in imd.stations()}


def read_rows(path: str) -> Iterator[IsdRow]:
    """Stream the rows of an ISD file. Raises IsdFormatError before the first row when the first record is not an ISD record."""
    imd_by_id = _name_lookup()
    seen_first = False
    pos: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    groups_by: Dict[str, List[Tuple[int, datetime, int, float, str, str]]] = {}
    for n, line in _lines(path):
        if not line.strip():
            continue
        rec = parse_line(line.rstrip("\r\n"))
        if not seen_first:
            if rec is None:
                raise IsdFormatError("not an NOAA ISD file: the first record is not in the ISD fixed-width layout")
            seen_first = True
        if rec is None:
            yield IsdRow(n, "", "", None, None, None, None, None, None, problem="malformed ISD record")
            continue
        sid, when, groups = rec
        key = f"isd:{sid}"
        if key not in pos:
            pos[key] = parse_position(line)
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
    if not seen_first:
        raise IsdFormatError("the file is empty")
    for key in sorted(groups_by):
        sid = key[4:]
        meta = imd_by_id.get(sid)
        lat, lon = pos.get(key, (None, None))
        if lat is None and meta:
            lat, lon = meta["latitude"], meta["longitude"]
        name = (meta["name"] if meta else f"ISD {sid}")
        state = meta["state"] if meta else None
        fields = dict(station_key=key, name=name, state=state, district=None, latitude=lat, longitude=lon)
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
    return {"station_key": row.station_key, "source": SOURCE, "name": row.name[:128], "state": row.state[:64] if row.state else None,
            "district": None, "latitude": row.latitude, "longitude": row.longitude}
