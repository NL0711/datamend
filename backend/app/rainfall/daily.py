"""Daily rainfall totals from a stream of Weather Union readings.

The rain day is 03 UTC to 03 UTC (08:30 to 08:30 IST), the same day definition as the IMD/RF25 daily grids, so a station's total
is comparable with a grid cell's.

Because the provider does not document what ``rain_accumulation`` is, the accumulation MODE is an explicit setting, and every
result carries ``units_confirmed=False`` until someone verifies it (the raw log written by service.py exists for that):
  * ``cumulative``  : the value is a running total since some reset. Day total = sum of increases between consecutive readings;
                      a drop is treated as a counter reset, after which the new value counts as rain since the reset.
  * ``per_reading`` : the value is the amount since the previous reading. Day total = sum of readings.
Units are ASSUMED to be millimetres in both modes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from backend.app.rainfall.weather_union import RainObservation

MODES = ("cumulative", "per_reading")
DAY_OFFSET = timedelta(hours=3)


def rain_day(ts: datetime) -> date:
    """The 03 UTC to 03 UTC rain day a UTC timestamp belongs to, labelled by the date it ENDS on (the IMD convention, and the
    label used by ml-service/qc/station.py): 2026-11-19 02:59 UTC is in rain day 2026-11-19, 03:00 UTC is in 2026-11-20."""
    if ts.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return (ts.astimezone(timezone.utc) - DAY_OFFSET).date() + timedelta(days=1)


def rain_day_bounds(day: date) -> Tuple[datetime, datetime]:
    """[start, end) in UTC of the rain day labelled `day`: 03 UTC on the previous date up to 03 UTC on `day`."""
    end = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + DAY_OFFSET
    return end - timedelta(days=1), end


@dataclass(frozen=True)
class DayTotal:
    station_id: str
    day: date
    total_mm: Optional[float]      # None when there is no usable reading
    n_readings: int
    n_resets: int
    max_gap_minutes: float
    complete: bool                 # readings cover the whole rain day without a gap longer than max_gap_ok
    mode: str
    units_confirmed: bool = False  # always False until the provider's units/period are verified


def total_for_day(station_id: str, day: date, samples: List[Tuple[datetime, float]], mode: str,
                  max_gap_ok_minutes: float = 60.0, edge_ok_minutes: float = 30.0, now: Optional[datetime] = None) -> DayTotal:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    pts = sorted((t, v) for t, v in samples if v is not None and v == v and v >= 0)
    if not pts:
        return DayTotal(station_id, day, None, 0, 0, 0.0, False, mode)
    total, resets = 0.0, 0
    if mode == "per_reading":
        total = sum(v for _, v in pts)
    else:
        for (_, a), (_, b) in zip(pts, pts[1:]):
            if b >= a:
                total += b - a
            else:
                resets += 1
                total += b
    gaps = [(b[0] - a[0]).total_seconds() / 60.0 for a, b in zip(pts, pts[1:])]
    max_gap = max(gaps, default=0.0)
    start, end = rain_day_bounds(day)
    horizon = min(end, now) if now else end
    complete = (
        (pts[0][0] - start).total_seconds() / 60.0 <= edge_ok_minutes
        and (horizon - pts[-1][0]).total_seconds() / 60.0 <= edge_ok_minutes
        and max_gap <= max_gap_ok_minutes
        and (now is None or now >= end)
    )
    return DayTotal(station_id, day, round(total, 3), len(pts), resets, round(max_gap, 1), complete, mode)


class DailyAccumulator:
    """Keeps recent readings per station and rain day (3 days) and reports totals."""

    def __init__(self, mode: str = "cumulative", keep_days: int = 3, edge_ok_minutes: float = 30.0) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.mode = mode
        self.keep_days = keep_days
        self.edge_ok_minutes = edge_ok_minutes        # a provider with hourly readings needs 60: its last reading of a day starts an hour before the end
        self._samples: Dict[Tuple[str, date], List[Tuple[datetime, float]]] = {}

    def add(self, obs: RainObservation) -> None:
        if obs.rain_accumulation is None or obs.status != "OK":
            return
        key = (obs.station_id, rain_day(obs.observed_at))
        self._samples.setdefault(key, []).append((obs.observed_at, obs.rain_accumulation))
        newest = max(d for _, d in self._samples)
        for k in [k for k in self._samples if (newest - k[1]).days >= self.keep_days]:
            del self._samples[k]

    def total(self, station_id: str, day: date, now: Optional[datetime] = None) -> DayTotal:
        return total_for_day(station_id, day, self._samples.get((station_id, day), []), self.mode, edge_ok_minutes=self.edge_ok_minutes, now=now)

    def days(self, station_id: str) -> List[date]:
        return sorted(d for s, d in self._samples if s == station_id)
