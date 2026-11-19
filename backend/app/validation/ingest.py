"""Parse an uploaded rainfall file into Reading or DailyTotal records (spec section 3).

File-level problems REJECT the whole upload (InputRejected, with a clear message). Row-level problems keep the row, untouched in
``raw``, with an issue and a reason; no row is dropped and no value is silently fixed. Rows stay in file order; ``sorted_for_scoring``
orders them only after ``flag_integrity`` has reported any disorder.

Formats: CSV and JSON. Parquet is NOT IMPLEMENTED. Units: mm (mm per hour for intensity); unit conversion is NOT IMPLEMENTED.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from backend.app.validation.records import DailyTotal, Reading, RowIssue

MAX_BYTES = 10 * 1024 * 1024          # about 200,000 rows
PROFILES = ("reading", "daily")
FORMATS = ("csv", "json")
ACCUMULATION_MODES = ("cumulative", "per_reading")
MM_UNITS = ("mm", "mm/h", "mm/hr", "mm_per_hour", "mm per hour")
GAP_FACTOR = 1.5                      # a gap is a step larger than this many declared intervals (design choice, uncalibrated)

REQUIRED = {"reading": ("timestamp", "station_id"), "daily": ("day", "station_id", "mm")}
OPTIONAL = {"reading": ("accumulation", "intensity", "latitude", "longitude", "unit"),
            "daily": ("latitude", "longitude", "unit")}

# Documented header aliases. Every rename is reported back in ParsedInput.renamed, never silent.
ALIASES: Dict[str, Tuple[str, ...]] = {
    "timestamp": ("time", "datetime", "date_time", "timestamp_utc", "observed_at"),
    "station_id": ("station", "stationid", "gauge_id", "gauge", "id"),
    "accumulation": ("rain_accumulation", "cumulative_rain", "accum"),
    "intensity": ("rain_intensity", "intensity_mm_h"),
    "day": ("date", "rain_day"),
    "mm": ("rain_mm", "rainfall_mm", "precip_mm", "total_mm", "rainfall"),
    "latitude": ("lat",),
    "longitude": ("lon", "lng", "long"),
    "unit": ("units",),
}
_ALIAS_TO_CANON = {a: c for c, al in ALIASES.items() for a in al}


class InputRejected(ValueError):
    """The whole file is rejected (file-level problem)."""


@dataclass
class UploadOptions:
    profile: str                              # "reading" or "daily", chosen by the user
    fmt: str = "csv"                          # "csv" or "json"
    accumulation_mode: Optional[str] = None   # REQUIRED when the file has an accumulation column; no default
    timezone: Optional[str] = None            # declared zone for timestamps without one: "UTC", "+05:30" or an IANA name
    interval_minutes: Optional[float] = None  # declared reading interval; without it the gap check is "not run"


@dataclass
class ParsedInput:
    profile: str
    records: List[Union[Reading, DailyTotal]]
    renamed: Dict[str, str] = field(default_factory=dict)       # original header -> canonical name
    not_run: List[Dict[str, str]] = field(default_factory=list)  # checks that could not run, with the reason
    issue_counts: Dict[str, int] = field(default_factory=dict)
    out_of_order: bool = False


# ------------------------------------------------------------------------------------------------ helpers

def _norm(h: str) -> str:
    return re.sub(r"[\s\-]+", "_", str(h).strip().lower())


def _zone(name: str) -> timezone:
    s = name.strip()
    if s.upper() in ("UTC", "Z"):
        return timezone.utc
    m = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", s)
    if m:
        off = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
        return timezone(off if m.group(1) == "+" else -off)
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(s)  # type: ignore[return-value]
    except Exception:
        raise InputRejected(f"unknown time zone {name!r}: use 'UTC', an offset such as '+05:30', or an IANA name")


def _parse_ts(value: Any, declared: Optional[timezone]) -> Tuple[Optional[datetime], bool]:
    """-> (UTC datetime or None, was_naive). Never guesses a zone."""
    if value is None or str(value).strip() == "":
        return None, False
    s = str(value).strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None, False
    if dt.tzinfo is None:
        if declared is None:
            return dt, True
        dt = dt.replace(tzinfo=declared)
    return dt.astimezone(timezone.utc), False


def _parse_day(value: Any) -> Optional[date]:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _num(value: Any) -> Tuple[Optional[float], Optional[str]]:
    """-> (value, problem). problem is None, 'missing' or 'non_numeric'. A negative number is returned as is (flagged later)."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None, "missing"
    if isinstance(value, bool):
        return None, "non_numeric"
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None, "non_numeric"
    if not math.isfinite(x):
        return None, "non_numeric"
    return x, None


def _read_rows(content: bytes, fmt: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputRejected("the file is not valid UTF-8 text")
    if fmt == "csv":
        reader = csv.DictReader(io.StringIO(text))
        headers = [h for h in (reader.fieldnames or []) if h is not None]
        if not headers:
            raise InputRejected("the file has no header row")
        rows = []
        for r in reader:
            r = {k: v for k, v in r.items() if k is not None}
            rows.append(r)
        return headers, rows
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise InputRejected(f"the file is not valid JSON ({e.msg} at line {e.lineno})")
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        data = data["rows"]
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise InputRejected("JSON input must be a list of row objects (or an object with a 'rows' list)")
    headers: List[str] = []
    for r in data:
        for k in r:
            if k not in headers:
                headers.append(k)
    return headers, data


def _map_columns(headers: Sequence[str], profile: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """-> (canonical -> original header, original -> canonical for the renamed ones). Rejects duplicates and missing columns."""
    canon_to_orig: Dict[str, str] = {}
    renamed: Dict[str, str] = {}
    for h in headers:
        n = _norm(h)
        c = n if n in ALIASES else _ALIAS_TO_CANON.get(n)
        if c is None:
            continue                                   # unknown extra column: ignored, kept in raw
        if c in canon_to_orig:
            raise InputRejected(f"two columns map to '{c}' ({canon_to_orig[c]!r} and {h!r}); keep one")
        canon_to_orig[c] = h
        if h != c:
            renamed[h] = c
    missing = [c for c in REQUIRED[profile] if c not in canon_to_orig]
    if missing:
        raise InputRejected(f"missing required column(s) for the {profile} profile: {', '.join(missing)}")
    if profile == "reading" and not ({"accumulation", "intensity"} & set(canon_to_orig)):
        raise InputRejected("the reading profile needs an 'accumulation' and/or an 'intensity' column")
    return canon_to_orig, renamed


# ------------------------------------------------------------------------------------------------ parse

def parse_upload(content: bytes, opts: UploadOptions) -> ParsedInput:
    if opts.profile not in PROFILES:
        raise InputRejected(f"profile must be one of {PROFILES}")
    if opts.fmt not in FORMATS:
        raise InputRejected(f"format {opts.fmt!r} is not supported (csv or json; parquet is NOT IMPLEMENTED)")
    if not content or not content.strip():
        raise InputRejected("the file is empty")
    if len(content) > MAX_BYTES:
        raise InputRejected(f"the file is larger than {MAX_BYTES // (1024 * 1024)} MB")
    if opts.interval_minutes is not None and not (isinstance(opts.interval_minutes, (int, float)) and math.isfinite(opts.interval_minutes)
                                                  and opts.interval_minutes > 0):
        raise InputRejected("interval_minutes must be a number greater than 0")
    if opts.accumulation_mode is not None and opts.accumulation_mode not in ACCUMULATION_MODES:
        raise InputRejected(f"accumulation_mode must be one of {ACCUMULATION_MODES}")

    headers, rows = _read_rows(content, opts.fmt)
    if not rows:
        raise InputRejected("the file has a header but no data rows")
    cols, renamed = _map_columns(headers, opts.profile)

    if "unit" in cols:
        bad = sorted({str(r.get(cols["unit"])).strip() for r in rows
                      if str(r.get(cols["unit"]) or "").strip().lower() not in MM_UNITS + ("",)})
        if bad:
            raise InputRejected(f"unsupported unit(s) {bad}: only mm (mm per hour for intensity) is accepted; unit conversion is NOT IMPLEMENTED")

    if opts.profile == "reading":
        if "accumulation" in cols and opts.accumulation_mode is None:
            raise InputRejected("the file has an accumulation column: declare accumulation_mode as 'cumulative' or 'per_reading' (there is no default)")
        parsed = _parse_readings(rows, cols, opts)
    else:
        parsed = _parse_daily(rows, cols)
    parsed.renamed = renamed
    flag_integrity(parsed, opts.interval_minutes)
    return parsed


def _get(row: Dict[str, Any], cols: Dict[str, str], key: str) -> Any:
    return row.get(cols[key]) if key in cols else None


def _coord(row, cols, key) -> Optional[float]:
    v, prob = _num(_get(row, cols, key))
    return v if prob is None else None


def _parse_readings(rows: List[Dict[str, Any]], cols: Dict[str, str], opts: UploadOptions) -> ParsedInput:
    declared = _zone(opts.timezone) if opts.timezone else None
    out: List[Reading] = []
    n_naive = n_ok = 0
    for i, row in enumerate(rows, start=1):
        issues: List[RowIssue] = []
        ts, naive = _parse_ts(_get(row, cols, "timestamp"), declared)
        if naive:
            n_naive += 1
            ts = None
        elif ts is not None:
            n_ok += 1
        if ts is None and not naive:
            issues.append(RowIssue("bad_timestamp", "the timestamp is missing or is not ISO 8601"))
        vals: Dict[str, Optional[float]] = {}
        for key in ("accumulation", "intensity"):
            if key not in cols:
                vals[key] = None
                continue
            v, prob = _num(_get(row, cols, key))
            vals[key] = v
            if prob == "non_numeric":
                issues.append(RowIssue("non_numeric", f"{key} is not a finite number"))
            elif v is not None and v < 0:
                issues.append(RowIssue("negative_value", f"{key} is negative ({v:g}); the value is kept as given"))
        if all(vals[k] is None for k in ("accumulation", "intensity")) and not any(x.code == "non_numeric" for x in issues):
            issues.append(RowIssue("missing_value", "the row has no accumulation or intensity value"))
        out.append(Reading(
            source="upload", station_id=str(_get(row, cols, "station_id") or "").strip(), timestamp=ts,
            accumulation=vals["accumulation"], intensity=vals["intensity"], time_basis="observed",
            accumulation_mode=opts.accumulation_mode if vals["accumulation"] is not None else None,
            units_confirmed=True, row_ref=i, latitude=_coord(row, cols, "latitude"), longitude=_coord(row, cols, "longitude"),
            raw=dict(row), issues=issues))
    if n_naive:
        raise InputRejected(f"{n_naive} timestamp(s) have no time zone: add an offset (for example +05:30 or Z) or declare one zone for the whole file")
    if n_ok == 0:
        raise InputRejected("no timestamp in the file parses as ISO 8601")
    return ParsedInput("reading", out)


def _parse_daily(rows: List[Dict[str, Any]], cols: Dict[str, str]) -> ParsedInput:
    out: List[DailyTotal] = []
    n_ok = 0
    for i, row in enumerate(rows, start=1):
        issues: List[RowIssue] = []
        d = _parse_day(_get(row, cols, "day"))
        if d is None:
            issues.append(RowIssue("bad_day", "the day is missing or is not a YYYY-MM-DD date"))
        else:
            n_ok += 1
        v, prob = _num(_get(row, cols, "mm"))
        if prob == "non_numeric":
            issues.append(RowIssue("non_numeric", "mm is not a finite number"))
        elif prob == "missing":
            issues.append(RowIssue("missing_value", "mm is empty"))
        elif v is not None and v < 0:
            issues.append(RowIssue("negative_value", f"mm is negative ({v:g}); the value is kept as given"))
        out.append(DailyTotal(source="upload", station_id=str(_get(row, cols, "station_id") or "").strip(), day=d, mm=v,
                              complete=None, units_confirmed=True, row_ref=i,
                              latitude=_coord(row, cols, "latitude"), longitude=_coord(row, cols, "longitude"),
                              raw=dict(row), issues=issues))
    if n_ok == 0:
        raise InputRejected("no day in the file parses as a YYYY-MM-DD date")
    return ParsedInput("daily", out)


# ------------------------------------------------------------------------------------------------ input integrity

def flag_integrity(parsed: ParsedInput, interval_minutes: Optional[float] = None) -> None:
    """Add duplicate, out-of-order and gap issues in place. Never drops, reorders or edits a row."""
    daily = parsed.profile == "daily"
    key = (lambda r: r.day) if daily else (lambda r: r.timestamp)
    dup_code = "duplicate_day" if daily else "duplicate_timestamp"
    by_station: Dict[str, List[Any]] = defaultdict(list)
    for r in parsed.records:
        if key(r) is not None:
            by_station[r.station_id].append(r)

    for recs in by_station.values():
        # out of order: a row earlier than the latest one already seen for the same station (file order)
        latest = None
        for r in recs:
            k = key(r)
            if latest is not None and k < latest:
                r.issues.append(RowIssue("out_of_order", f"row {r.row_ref} is earlier than a row above it for this station"))
                parsed.out_of_order = True
            latest = k if latest is None or k > latest else latest
        # duplicates: every row of a repeated station + time
        groups: Dict[Any, List[Any]] = defaultdict(list)
        for r in recs:
            groups[key(r)].append(r)
        for k, g in groups.items():
            if len(g) > 1:
                for r in g:
                    r.issues.append(RowIssue(dup_code, f"{len(g)} rows share this station and {'day' if daily else 'timestamp'}"))
        # gaps: between consecutive distinct times
        times = sorted(groups)
        if daily:
            for a, b in zip(times, times[1:]):
                if (b - a).days > 1:
                    groups[b][0].issues.append(RowIssue("gap", f"{(b - a).days - 1} day(s) missing before this day"))
        elif interval_minutes:
            limit = GAP_FACTOR * interval_minutes
            for a, b in zip(times, times[1:]):
                mins = (b - a).total_seconds() / 60.0
                if mins > limit:
                    groups[b][0].issues.append(RowIssue("gap", f"{mins:g} minutes since the previous reading (declared interval {interval_minutes:g})"))

    if not daily and not interval_minutes:
        parsed.not_run.append({"check": "gap", "reason": "no interval_minutes declared for this upload"})
    parsed.issue_counts = dict(Counter(i.code for r in parsed.records for i in r.issues))


def sorted_for_scoring(parsed: ParsedInput) -> List[Union[Reading, DailyTotal]]:
    """Records with a usable time, ordered by station then time (stable). Call only after flag_integrity has reported disorder."""
    daily = parsed.profile == "daily"
    usable = [r for r in parsed.records if (r.day if daily else r.timestamp) is not None]
    return sorted(usable, key=lambda r: (r.station_id, r.day if daily else r.timestamp))
