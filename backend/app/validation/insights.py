"""Insights: five aggregate views of the stored rain days, computed on request from the runs database. Measured or derived numbers only.

Every chart is a pure function over ``Day`` tuples (station, day, mm, verdict) so it is tested without a database; ``load_days`` is the
only part that reads storage. A view that lacks the data to say anything answers ``{"enough": False, "reason": ...}`` instead of drawing a
guess. Bands and thresholds are assumed values chosen here (labelled ``assumed`` in the output), not learned or validated against labels.

Only rows with a daily total in mm are used (daily-profile runs: uploads of daily data, live rain days).
Reading-profile rows carry no daily total and are counted in ``rows_without_mm``.
"""
from __future__ import annotations

import calendar
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.validation.models import ValidationResult, ValidationRun

ROW_CAP = 600_000                    # more rows than this are cut (oldest runs first) and the response says so
MIN_HISTORY = 3                      # complete same-month (or same-year) periods needed before an anomaly is drawn
MIN_COMMON_DAYS = 30                 # days two stations must share before their correlation is shown
CORR_STATIONS = 30                   # the matrix shows the stations with the most days
MIN_DAYS_CLIMATE = 180               # observed days before a station gets a climate band
WET_DAY_MM = 1.0                     # a wet day (assumed, the common 1 mm convention)
HEAVY_PERCENTILE = 95                # heavy = at or above this percentile of the station's own wet days (assumed)
MIN_WET_DAYS_HEAVY = 20
SCATTER_CAP = 1500
BANDS = [("dry", 0.0, 500.0), ("moderate", 500.0, 1500.0), ("wet", 1500.0, float("inf"))]      # annual mm, assumed
FLAGGED = ("SUSPECT", "UNCERTAIN")
VERDICTS = ("OK", "SUSPECT", "UNCERTAIN", "NO_DATA")


@dataclass(frozen=True)
class Day:
    station: str
    day: str                          # YYYY-MM-DD
    mm: float
    verdict: str


def _none(reason: str) -> Dict[str, Any]:
    return {"enough": False, "reason": reason}


def _day(time_key: Optional[str]) -> Optional[str]:
    if not time_key or len(time_key) < 10:
        return None
    s = time_key[:10]
    try:
        date.fromisoformat(s)
    except ValueError:
        return None
    return s


def percentile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile of an already sorted, non-empty list."""
    k = (len(sorted_vals) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _stdev(xs: Sequence[float]) -> float:
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def by_station(days: Iterable[Day]) -> Dict[str, Dict[str, Day]]:
    out: Dict[str, Dict[str, Day]] = defaultdict(dict)
    for d in days:
        out[d.station][d.day] = d                     # a later run's value for the same station and day wins (days arrive oldest run first)
    return out


# 1. rainfall anomaly ---------------------------------------------------------------------------------------------------------------------

def anomaly(days: Iterable[Day], granularity: str = "month") -> Dict[str, Any]:
    """Each station's total per month (or year) against its own normal for the same calendar month (or the same year length), using only
    COMPLETE periods (every day present). The period itself is inside its own normal. Needs MIN_HISTORY complete same-month periods."""
    if granularity not in ("month", "year"):
        raise ValueError("granularity must be month or year")
    series: List[Dict[str, Any]] = []
    skipped: Dict[str, str] = {}
    for st, per_day in sorted(by_station(days).items()):
        tot: Dict[str, float] = defaultdict(float)
        cnt: Dict[str, int] = defaultdict(int)
        flagged: Dict[str, int] = defaultdict(int)
        for day, d in per_day.items():
            key = day[:7] if granularity == "month" else day[:4]
            tot[key] += d.mm
            cnt[key] += 1
            if d.verdict in FLAGGED:
                flagged[key] += 1

        def need(key: str) -> int:
            y, m = int(key[:4]), int(key[5:7]) if granularity == "month" else 0
            return calendar.monthrange(y, m)[1] if granularity == "month" else (366 if calendar.isleap(y) else 365)

        complete = {k: tot[k] for k in tot if cnt[k] == need(k)}
        groups: Dict[str, List[float]] = defaultdict(list)
        for k, v in complete.items():
            groups[k[5:7] if granularity == "month" else "all"].append(v)
        points = []
        for k in sorted(complete):
            g = groups[k[5:7] if granularity == "month" else "all"]
            if len(g) < MIN_HISTORY:
                continue
            normal = sum(g) / len(g)
            sd = _stdev(g)
            points.append({"period": k, "total_mm": round(complete[k], 1), "normal_mm": round(normal, 1), "anomaly_mm": round(complete[k] - normal, 1),
                           "z": round((complete[k] - normal) / sd, 2) if sd > 0 else None, "flagged_days": flagged[k], "history": len(g)})
        if points:
            series.append({"station": st, "points": points})
        else:
            skipped[st] = (f"fewer than {MIN_HISTORY} complete {granularity}s of history" if complete else f"no complete {granularity}")
    if not series:
        return {**_none(f"no station has {MIN_HISTORY} complete {granularity}s of history yet"), "skipped": skipped}
    return {"enough": True, "granularity": granularity, "min_history": MIN_HISTORY, "series": series, "skipped": skipped,
            "note": "the normal is the station's own mean for the same calendar " + ("month" if granularity == "month" else "year") +
                    " over complete periods only (derived); z is shown only when the spread is above zero"}


# 2. station similarity -------------------------------------------------------------------------------------------------------------------

def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)


def correlation(days: Iterable[Day]) -> Dict[str, Any]:
    """Pearson correlation of daily rain between stations over the days both reported. Pairs sharing fewer than MIN_COMMON_DAYS days are null."""
    per = by_station(days)
    names = [s for s, _ in sorted(per.items(), key=lambda kv: (-len(kv[1]), kv[0]))][:CORR_STATIONS]
    if len(names) < 2:
        return _none("needs at least two stations")
    matrix: List[List[Optional[float]]] = []
    common: List[List[int]] = []
    for a in names:
        row, crow = [], []
        for b in names:
            shared = sorted(set(per[a]) & set(per[b]))
            crow.append(len(shared))
            if a == b:
                row.append(1.0)
            elif len(shared) < MIN_COMMON_DAYS:
                row.append(None)
            else:
                r = _pearson([per[a][d].mm for d in shared], [per[b][d].mm for d in shared])
                row.append(None if r is None else round(r, 3))
        matrix.append(row)
        common.append(crow)
    if not any(v is not None and i != j for i, r in enumerate(matrix) for j, v in enumerate(r)):
        return {**_none(f"no two stations share {MIN_COMMON_DAYS} days"), "stations": names}
    return {"enough": True, "stations": names, "matrix": matrix, "common_days": common, "min_common_days": MIN_COMMON_DAYS,
            "truncated": len(per) > len(names), "total_stations": len(per),
            "note": "Pearson r of daily rain over shared days (derived); empty cell = fewer than the minimum shared days or no variation"}


# 3. station climate groups ---------------------------------------------------------------------------------------------------------------

def band_of(annual_mm: float) -> str:
    return next(name for name, lo, hi in BANDS if lo <= annual_mm < hi)


def climate(days: Iterable[Day]) -> Dict[str, Any]:
    """Fixed bands (not learned) on each station's rainfall per year, scaled from the days it reported, plus its wet-day share."""
    stations = []
    short: List[str] = []
    for st, per_day in sorted(by_station(days).items()):
        n = len(per_day)
        if n < MIN_DAYS_CLIMATE:
            short.append(st)
            continue
        total = sum(d.mm for d in per_day.values())
        annual = total / n * 365.25
        wet = sum(1 for d in per_day.values() if d.mm >= WET_DAY_MM) / n
        stations.append({"station": st, "days": n, "annual_mm": round(annual, 0), "wet_day_share": round(wet, 3), "band": band_of(annual)})
    if not stations:
        return {**_none(f"no station has {MIN_DAYS_CLIMATE} observed days yet"), "too_short": short}
    return {"enough": True, "stations": stations, "too_short": short, "wet_day_mm": WET_DAY_MM,
            "bands": [{"name": n, "from_mm": lo, "to_mm": None if hi == float("inf") else hi} for n, lo, hi in BANDS],
            "note": "bands are fixed values we chose (assumed), not learned; annual mm is the station's mean per reported day times 365.25 (derived)"}


# 4. verdict mix over time ----------------------------------------------------------------------------------------------------------------

def verdict_mix(days: Iterable[Day], granularity: str = "month") -> Dict[str, Any]:
    if granularity not in ("month", "year"):
        raise ValueError("granularity must be month or year")
    width = 7 if granularity == "month" else 4
    counts: Dict[str, Counter] = defaultdict(Counter)
    for d in days:
        counts[d.day[:width]][d.verdict] += 1
    if not counts:
        return _none("no rows in this selection")
    periods = []
    for k in sorted(counts):
        c, n = counts[k], sum(counts[k].values())
        periods.append({"period": k, "rows": n, **{v: c.get(v, 0) for v in VERDICTS}, **{f"share_{v}": round(c.get(v, 0) / n, 4) for v in VERDICTS}})
    return {"enough": True, "granularity": granularity, "periods": periods,
            "note": "share of stored rows by check verdict; a rising SUSPECT share means the data looks worse, not that the weather changed"}


# 5. large rain against the verdict -------------------------------------------------------------------------------------------------------

def heavy_rain(days: Iterable[Day]) -> Dict[str, Any]:
    """Heavy days = at or above the station's own HEAVY_PERCENTILE of its wet days. Their verdicts are counted next to every other wet day.
    A heavy day that was not flagged is 'not flagged', never 'confirmed' or 'genuine': magnitude alone is not evidence of either."""
    stations, points = [], []
    heavy_v: Counter = Counter()
    other_v: Counter = Counter()
    short: List[str] = []
    for st, per_day in sorted(by_station(days).items()):
        wet = sorted(d.mm for d in per_day.values() if d.mm >= WET_DAY_MM)
        if len(wet) < MIN_WET_DAYS_HEAVY:
            short.append(st)
            continue
        thr = percentile(wet, HEAVY_PERCENTILE)
        h = Counter()
        for d in per_day.values():
            if d.mm < WET_DAY_MM:
                continue
            is_heavy = d.mm >= thr
            (heavy_v if is_heavy else other_v)[d.verdict] += 1
            if is_heavy:
                h[d.verdict] += 1
            points.append({"station": st, "day": d.day, "mm": round(d.mm, 1), "verdict": d.verdict, "heavy": is_heavy})
        n_h = sum(h.values())
        stations.append({"station": st, "threshold_mm": round(thr, 1), "heavy_days": n_h, "flagged": sum(h.get(v, 0) for v in FLAGGED),
                         "not_flagged": n_h - sum(h.get(v, 0) for v in FLAGGED)})
    if not stations:
        return {**_none(f"no station has {MIN_WET_DAYS_HEAVY} wet days yet"), "too_short": short}
    points.sort(key=lambda p: (-p["mm"], p["station"], p["day"]))
    return {"enough": True, "stations": stations, "too_short": short, "percentile": HEAVY_PERCENTILE, "wet_day_mm": WET_DAY_MM,
            "heavy_verdicts": {v: heavy_v.get(v, 0) for v in VERDICTS}, "other_wet_verdicts": {v: other_v.get(v, 0) for v in VERDICTS},
            "points": points[:SCATTER_CAP], "points_truncated": len(points) > SCATTER_CAP,
            "note": f"heavy = at or above the station's own {HEAVY_PERCENTILE}th percentile of wet days (assumed); 'not flagged' is not 'confirmed': "
                    "no one has said these days are genuine"}


# loading ---------------------------------------------------------------------------------------------------------------------------------

async def load_days(session: AsyncSession, run_id: Optional[int] = None, include_synthetic: bool = False, stations: Optional[Sequence[str]] = None,
                    start: Optional[str] = None, end: Optional[str] = None) -> Tuple[List[Day], Dict[str, Any]]:
    """Daily rows of one run (``run_id``) or of every non-failed run (real ones only unless ``include_synthetic``), oldest run first."""
    base = select(ValidationResult.run_id, ValidationResult.station_id, ValidationResult.time_key, ValidationResult.mm, ValidationResult.verdict) \
        .join(ValidationRun, ValidationRun.id == ValidationResult.run_id).where(ValidationRun.status != "failed")
    if run_id is not None:
        base = base.where(ValidationResult.run_id == run_id)
    elif not include_synthetic:
        base = base.where(ValidationRun.synthetic.is_(False))
    if stations:
        base = base.where(ValidationResult.station_id.in_(list(stations)))
    if start:
        base = base.where(ValidationResult.time_key >= start)
    if end:
        base = base.where(ValidationResult.time_key <= end + "~")          # "~" sorts after any time of that date
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    without_mm = (await session.execute(select(func.count()).select_from(base.where(ValidationResult.mm.is_(None)).subquery()))).scalar_one()
    rows = (await session.execute(base.where(ValidationResult.mm.is_not(None)).order_by(ValidationResult.run_id, ValidationResult.id).limit(ROW_CAP))).all()
    days: List[Day] = []
    for _run, st, tk, mm, verdict in rows:
        d = _day(tk)
        if d is not None and mm is not None and mm >= 0 and math.isfinite(mm):
            days.append(Day(st, d, float(mm), verdict))
    synthetic_runs = 0
    if run_id is not None:
        run = await session.get(ValidationRun, run_id)
        synthetic_runs = 1 if run is not None and run.synthetic else 0
    elif include_synthetic:
        synthetic_runs = (await session.execute(select(func.count()).select_from(ValidationRun).where(ValidationRun.synthetic.is_(True)))).scalar_one()
    meta = {"rows": total, "rows_used": len(days), "rows_without_mm": int(without_mm), "stations": len({d.station for d in days}),
            "first_day": min((d.day for d in days), default=None), "last_day": max((d.day for d in days), default=None),
            "truncated": len(rows) >= ROW_CAP, "synthetic": bool(synthetic_runs), "run_id": run_id,
            "scope": f"run {run_id}" if run_id is not None else ("every run, synthetic included" if include_synthetic else "every real run")}
    return days, meta


async def build(session: AsyncSession, run_id: Optional[int] = None, include_synthetic: bool = False, stations: Optional[Sequence[str]] = None,
                start: Optional[str] = None, end: Optional[str] = None, granularity: str = "month") -> Dict[str, Any]:
    days, meta = await load_days(session, run_id, include_synthetic, stations, start, end)
    if run_id is not None and not days and meta["rows"] == 0:
        meta["note"] = "this run has no rows (or the filters match none)"
    return {"selection": {**meta, "granularity": granularity, "start": start, "end": end}, "anomaly": anomaly(days, granularity),
            "correlation": correlation(days), "climate": climate(days), "verdict_mix": verdict_mix(days, granularity), "heavy_rain": heavy_rain(days)}
