"""NOAA ISD India replay: real station rainfall from NOAA's Integrated Surface Database, shown as a REPLAY (never as live).

What it is. For a handful of Indian stations it fetches the year's ISD file (NOAA's public bucket noaa-isd-pds), keeps the 24-hour
precipitation totals stamped at 03 UTC (the end of the rain day, 08:30 IST) and stores them as ONE daily-profile run, source 'replay'.
The station ids are the ISD ids (USAF-WBAN), the same ids as the IMD station list on the map, so the map's IMD stations show their state.

What it is not. ISD has no data after about 24 to 25 August 2025 for these stations, so this is a replay of the past, not a live feed.
Non-US ISD data is subject to WMO Resolution 40 and must not be redistributed: nothing here is committed to git, the data is fetched
when the replay is started (by an administrator, or at startup when ISD_REPLAY_ON_START is set), and every screen labels it REPLAY.

Format facts (docs/research/noaa-isd-rainfall-facts.md, checked against real files): the mandatory section is 105 characters (station
USAF 5-10, WBAN 11-15, date 16-23, time 24-27); liquid precipitation groups AA1..AA4 follow, each `AAn` + period (hours, 2 digits) + depth
(tenths of mm, 9999 = missing) + condition (1) + quality (1). Condition and quality codes are passed through in the row, never dropped.
"""
from __future__ import annotations

import asyncio
import logging
import re
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

from backend.app.places import imd
from backend.app.validation.records import DailyTotal

logger = logging.getLogger(__name__)

URL = "https://noaa-isd-pds.s3.amazonaws.com/data/{year}/{usaf}-{wban}-{year}.gz"
YEAR = 2025
MAX_DOWNLOAD_BYTES = 2_000_000            # per station file (the largest 2025 India file is about 334 KB compressed)
MAX_TEXT_BYTES = 20_000_000               # after decompression: a guard against a decompression bomb
MANDATORY_LEN = 105
DAY_STAMP_HOUR_UTC = 3
MISSING_DEPTH = "9999"
GOOD_QUALITY = frozenset("15")            # ISD: 1 passed all checks, 5 passed (NCEI source); every other code is kept and passed through
_GROUP = re.compile(r"AA([1-4])(\d{2})(\d{4})(\w)(\w)")

# Large-city IMD stations that have 2025 files (checked with header requests on 2026-11-19). About 2 MB in all.
DEFAULT_STATIONS: Tuple[str, ...] = (
    "421820-99999",   # Safdarjung (Delhi)
    "430570-99999",   # Bombay / Colaba
    "430630-99999",   # Pune
    "432790-99999",   # Chennai Intl
    "431280-99999",   # Begumpet Airport / Hyderabad
    "432950-99999",   # Bangalore
    "426470-99999",   # Ahmedabad
    "423480-99999",   # Jaipur
    "423690-99999",   # Lucknow
    "426670-99999",   # Bhopal
    "424100-99999",   # Guwahati
    "433710-99999",   # Thiruvananthapuram
    "431940-99999",   # Goa Intl
    "432840-99999",   # Mangalore
)

NOTE = ("REPLAY of real NOAA ISD observations, not live: ISD has no data after about 24 August 2025. Non-US ISD data is subject to WMO "
        "Resolution 40 and must not be redistributed.")


def split_id(isd_id: str) -> Tuple[str, str]:
    usaf, _, wban = isd_id.partition("-")
    if len(usaf) != 6 or len(wban) != 5 or not (usaf + wban).isalnum():
        raise ValueError(f"not an ISD station id (USAF-WBAN): {isd_id!r}")
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


def daily_totals(lines: Iterable[str], positions: Optional[Dict[str, Tuple[float, float]]] = None) -> List[DailyTotal]:
    """24-hour totals stamped in the 03 UTC hour, one per station and day (the date of the stamp = the day the rain day ENDS), sorted by
    station and day. Other accumulation periods are ignored; a missing depth is skipped, never zero. Of several 24-hour groups on one day
    the one with a good quality code wins, a tie keeps the first."""
    best: Dict[Tuple[str, Any], Tuple[DailyTotal, str]] = {}
    for line in lines:
        rec = parse_line(line)
        if rec is None:
            continue
        sid, when, groups = rec
        if when.hour != DAY_STAMP_HOUR_UTC:
            continue
        for period, mm, cond, qual in groups:
            if period != 24 or mm is None:
                continue
            lat, lon = (positions or {}).get(sid, (None, None))
            cand = DailyTotal(source="isd_replay", station_id=sid, day=when.date(), mm=mm, complete=True, units_confirmed=True,
                              latitude=lat, longitude=lon,
                              raw={"isd_period_hours": 24, "isd_condition": cond, "isd_quality": qual, "stamped_utc": when.isoformat(),
                                   "latitude": lat, "longitude": lon})
            key = (sid, when.date())
            old = best.get(key)
            if old is None or (qual in GOOD_QUALITY and old[1] not in GOOD_QUALITY):
                best[key] = (cand, qual)
    out = sorted((v[0] for v in best.values()), key=lambda d: (d.station_id, d.day))
    for i, d in enumerate(out, start=1):
        d.row_ref = i
    return out


def gunzip_capped(data: bytes, limit: int = MAX_TEXT_BYTES) -> str:
    """Decompress a gzip file, refusing more than ``limit`` bytes of output."""
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    text = d.decompress(data, limit)
    if d.unconsumed_tail:
        raise ValueError("the decompressed ISD file is larger than the safety limit")
    return text.decode("ascii", errors="replace")


async def fetch_station(client: httpx.AsyncClient, isd_id: str, year: int = YEAR) -> str:
    usaf, wban = split_id(isd_id)
    r = await client.get(URL.format(year=year, usaf=usaf, wban=wban))
    r.raise_for_status()
    if len(r.content) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"the ISD file is larger than {MAX_DOWNLOAD_BYTES} bytes")
    return gunzip_capped(r.content)


@dataclass
class ReplayResult:
    records: List[DailyTotal]
    stations: List[Dict[str, Any]]
    year: int
    fetched_at: str
    note: str = NOTE


async def build(ids: Sequence[str] = DEFAULT_STATIONS, year: int = YEAR, transport: Optional[httpx.AsyncBaseTransport] = None,
                timeout: float = 30.0) -> ReplayResult:
    """Fetch the stations one after another (polite to NOAA) and parse their 24-hour totals. A station that fails is reported and skipped."""
    by_id = {s["id"]: s for s in imd.stations()}
    positions = {i: (s["latitude"], s["longitude"]) for i, s in by_id.items()}
    records: List[DailyTotal] = []
    stations: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=timeout, transport=transport, follow_redirects=True) as client:
        for isd_id in ids:
            name = by_id.get(isd_id, {}).get("name")
            try:
                got = daily_totals(((await fetch_station(client, isd_id, year)).splitlines()), positions)
                got = [d for d in got if d.station_id == isd_id]
                records.extend(got)
                stations.append({"id": isd_id, "name": name, "ok": True, "totals": len(got), "error": None})
            except (httpx.HTTPError, ValueError, zlib.error) as e:
                logger.warning("[ISD REPLAY] %s skipped: %s", isd_id, e)
                stations.append({"id": isd_id, "name": name, "ok": False, "totals": 0, "error": str(e)[:160]})
    for i, d in enumerate(records, start=1):
        d.row_ref = i
    return ReplayResult(records, stations, year, datetime.now(timezone.utc).isoformat())


@dataclass
class ReplayJob:
    """The replay's state for the status endpoint. One job at a time."""
    state: str = "idle"                      # idle | running | done | failed
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    run_id: Optional[int] = None
    stations: List[Dict[str, Any]] = field(default_factory=list)
    message: Optional[str] = None
    _task: Optional["asyncio.Task[None]"] = None

    def status(self) -> Dict[str, Any]:
        return {"state": self.state, "started_at": self.started_at, "finished_at": self.finished_at, "run_id": self.run_id,
                "stations": self.stations, "stations_ok": sum(1 for s in self.stations if s["ok"]), "message": self.message,
                "default_stations": len(DEFAULT_STATIONS), "year": YEAR, "note": NOTE}

    @property
    def running(self) -> bool:
        return self.state == "running"


JOB = ReplayJob()
