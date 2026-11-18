"""Station rainfall lane: NOAA ISD daily totals and a causal one-station scorer.

Facts used (docs/research/noaa-isd-rainfall-facts.md, docs/qc-multires-pipeline-spec.md section 7):
  - fixed-width mandatory section is 105 characters: station USAF 5-10, WBAN 11-15, date 16-23, time 24-27;
  - liquid precipitation groups AA1..AA4 follow, each `AAn` + period (2 digits, hours) + depth (4 digits,
    tenths of mm, 9999 = missing) + condition (1) + quality (1);
  - in Indian files the 24-hour total is stamped on the 03 UTC observation (measured, not documented).

Scope and limits. This is a REPLAY lane: ISD has no data after Aug 2025. The scorer uses only a station's own
earlier days (causal). Its scores are NOT calibrated against any false-alarm budget; the RF25 budgets of
docs/qc-evaluation-protocol.md do not apply to them. ISD data of non-US stations must not be redistributed
(WMO Resolution 40): nothing here writes ISD values anywhere.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import numpy as np

_GROUP = re.compile(r"AA([1-4])(\d{2})(\d{4})(\w)(\w)")
MANDATORY_LEN = 105
MISSING_DEPTH = "9999"
GOOD_QUALITY = frozenset(["1", "5"])   # ISD: 1 = passed all checks, 5 = passed, source with limited checks
# every other code (2, 3, 6, 7, 0, ...) is kept and passed through, never silently dropped
DAY_STAMP_HOUR_UTC = 3


@dataclass(frozen=True)
class DailyTotal:
    station: str
    day: date              # the date of the 03 UTC stamp (the day ends at 03 UTC = 08:30 IST)
    mm: float
    quality: str
    condition: str


def parse_line(line: str) -> Optional[Tuple[str, datetime, List[Tuple[int, Optional[float], str, str]]]]:
    """One ISD record -> (station, UTC time, [(period_hours, mm or None, condition, quality), ...]).
    Returns None for a malformed or too-short record. Never raises on bad data."""
    if len(line) < MANDATORY_LEN:
        return None
    station = line[4:15].strip()
    try:
        when = datetime.strptime(line[15:23] + line[23:27], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    groups = []
    for m in _GROUP.finditer(line[MANDATORY_LEN:]):
        depth = None if m.group(3) == MISSING_DEPTH else int(m.group(3)) / 10.0
        groups.append((int(m.group(2)), depth, m.group(4), m.group(5)))
    return station, when, groups


def daily_totals(lines: Iterable[str]) -> List[DailyTotal]:
    """24-hour totals stamped in the 03 UTC hour, one per station and day, sorted by time.
    Other accumulation periods are ignored (not usable as daily totals). Missing depths are skipped, not zero.
    If a day has several 24-hour groups, the one with the best quality code wins; a tie keeps the first."""
    best: Dict[Tuple[str, date], DailyTotal] = {}
    for line in lines:
        rec = parse_line(line)
        if rec is None:
            continue
        station, when, groups = rec
        if when.hour != DAY_STAMP_HOUR_UTC:
            continue
        for period, mm, cond, qual in groups:
            if period != 24 or mm is None:
                continue
            key = (station, when.date())
            cand = DailyTotal(station, when.date(), mm, qual, cond)
            old = best.get(key)
            if old is None or (qual in GOOD_QUALITY and old.quality not in GOOD_QUALITY):
                best[key] = cand
    return sorted(best.values(), key=lambda d: (d.station, d.day))


@dataclass(frozen=True)
class StationScore:
    day: date
    mm: float
    rules: float          # 1.0 if physically impossible, else 0.0
    repeat: float         # 0..1, share of the stuck-value run length reached
    climatology: float    # -log10 upper-tail probability under the station's own wet-day gamma, 0 if no history
    isd_quality: str      # the source's own quality code, passed through
    n_history_wet: int    # wet days behind the climatology (0 = no judgement possible)

    @property
    def score(self) -> float:
        """Max of the components, each on its own scale. UNCALIBRATED."""
        return max(self.rules * 10.0, self.repeat, self.climatology)


class StationScorer:
    """Causal one-station scorer: the score of day t uses only days before t.

    rules        total < 0 or > max_mm (default 1,000 mm in a day, above any recorded Indian 24-hour total).
    repeat       the same positive value on consecutive days; reaches 1.0 at `repeat_days` in a row.
    climatology  upper tail of a gamma fitted (method of moments) to the station's earlier WET days within
                 +/- `window_days` of the same day of year, years pooled; needs `min_wet` wet days or it is 0.
    """

    def __init__(self, wet_mm: float = 0.1, window_days: int = 15, min_wet: int = 30,
                 max_mm: float = 1000.0, repeat_days: int = 3, max_score: float = 8.0) -> None:
        self.wet_mm, self.window, self.min_wet = wet_mm, window_days, min_wet
        self.max_mm, self.repeat_days, self.max_score = max_mm, repeat_days, max_score
        self._wet_days: List[Tuple[int, float]] = []   # (day of year, mm) of earlier wet days
        self._last: Optional[Tuple[date, float]] = None
        self._run = 1

    def _clim(self, doy: int, mm: float) -> Tuple[float, int]:
        from scipy.stats import gamma
        near = [v for d, v in self._wet_days if min(abs(d - doy), 366 - abs(d - doy)) <= self.window]
        if len(near) < self.min_wet or mm < self.wet_mm:
            return 0.0, len(near)
        x = np.asarray(near, dtype=float)
        mean, var = x.mean(), x.var()
        if var <= 0:
            return 0.0, len(near)
        shape, scale = mean * mean / var, var / mean
        tail = float(gamma.sf(mm, a=shape, scale=scale))
        return float(min(self.max_score, -np.log10(max(tail, 10.0 ** -self.max_score)))), len(near)

    def score(self, total: DailyTotal) -> StationScore:
        """Score one day, then add it to the history. Days must arrive in time order."""
        if self._last is not None and total.day <= self._last[0]:
            raise ValueError(f"days must be strictly increasing: {total.day} after {self._last[0]}")
        rules = 1.0 if (total.mm < 0 or total.mm > self.max_mm) else 0.0
        if self._last is not None and total.mm > 0 and total.mm == self._last[1] and (total.day - self._last[0]).days == 1:
            self._run += 1
        else:
            self._run = 1
        repeat = min(1.0, (self._run - 1) / max(1, self.repeat_days - 1)) if self._run > 1 else 0.0
        clim, n = self._clim(total.day.timetuple().tm_yday, total.mm)
        out = StationScore(total.day, total.mm, rules, repeat, clim, total.quality, n)
        self._last = (total.day, total.mm)
        if rules == 0.0 and total.mm >= self.wet_mm:
            self._wet_days.append((total.day.timetuple().tm_yday, total.mm))
        return out


def replay(totals: Iterable[DailyTotal], scorer_factory=StationScorer) -> Iterator[Tuple[DailyTotal, StationScore]]:
    """Replay daily totals in global time order, one scorer per station, labelled by the caller as REPLAY.
    Yields (total, score). Stations are interleaved by day so that a day is emitted for all stations first."""
    scorers: Dict[str, StationScorer] = {}
    for t in sorted(totals, key=lambda d: (d.day, d.station)):
        s = scorers.setdefault(t.station, scorer_factory())
        yield t, s.score(t)
