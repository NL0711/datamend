"""The one internal record for every rainfall source (spec section 3).

Uploads, the Weather Union feed and the ISD replay are adapters that produce these records. The original row is kept untouched in
``raw``; nothing is overwritten or silently corrected. ``issues`` holds row-level input problems (never a reason to drop the row).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

SOURCES = ("upload", "weather_union", "isd_replay")
TIME_BASES = ("observed", "received")


@dataclass(frozen=True)
class RowIssue:
    code: str       # machine-readable, one of ISSUE_CODES
    message: str    # one plain sentence naming the row's problem


ISSUE_CODES = (
    "bad_timestamp", "bad_day", "missing_value", "non_numeric", "negative_value",
    "duplicate_timestamp", "duplicate_day", "out_of_order", "gap",
)


@dataclass
class Reading:
    """One reading from one gauge. ``timestamp`` is timezone-aware UTC, or None when the row's timestamp did not parse."""
    source: str
    station_id: str
    timestamp: Optional[datetime]
    accumulation: Optional[float]
    intensity: Optional[float]
    time_basis: str = "observed"
    accumulation_mode: Optional[str] = None   # "cumulative" | "per_reading" | None when the row has no accumulation value
    units_confirmed: bool = False
    row_ref: Union[int, str] = 0              # file row number (1 = first data row) or live sequence number
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    issues: List[RowIssue] = field(default_factory=list)


@dataclass
class DailyTotal:
    """One rain-day total for one gauge, in mm. ``day`` is the date the 03 UTC to 03 UTC rain day ENDS."""
    source: str
    station_id: str
    day: Optional[date]
    mm: Optional[float]
    complete: Optional[bool] = None           # None when the input says nothing about completeness (uploaded daily totals)
    units_confirmed: bool = False
    row_ref: Union[int, str] = 0
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    issues: List[RowIssue] = field(default_factory=list)
