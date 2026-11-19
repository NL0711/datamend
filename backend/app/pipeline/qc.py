"""Checking the raw store: hourly observations are rolled up to rain-day totals (03 UTC to 03 UTC) per station and run through the
validation platform's daily checks, so the existing run, row, evidence, review and explanation views apply unchanged.

What the roll-up does NOT know: the CWC files list only non-zero hours, so a total is the sum of the hours that were reported and a day
with no rows is neither dry nor missing. Totals are therefore left with ``complete = None`` (the input says nothing about completeness),
and the run's settings say so. The hourly peak of each day is kept in the row's original data so a reviewer sees a 423 mm hour.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings as app_settings
from backend.app.pipeline import cwc
from backend.app.pipeline.models import IngestJob, Observation, PipelineStation
from backend.app.rainfall.daily import rain_day, rain_day_bounds
from backend.app.validation import checks
from backend.app.validation.records import DailyTotal
from backend.app.validation.models import ValidationRun
from backend.app.validation.runs import _store_rows, build_report, check_settings, git_commit, prune_runs

import time


NEIGHBOUR_NOT_TRUSTED = ("the neighbour checks cannot be trusted on this source: it lists only non-zero hours, so a neighbour with no row is not known to be dry "
                         "(neighbour votes of 'dry' are missing for most days, and a wet station can look isolated)")


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo is not None else t.replace(tzinfo=timezone.utc)      # SQLite hands back naive datetimes; they are stored as UTC


async def daily_totals(session: AsyncSession, source: str, start: Optional[date] = None, end: Optional[date] = None) -> List[DailyTotal]:
    """Roll the hourly observations of a source up to rain-day totals, one record per station and day, ordered by station and day."""
    stations = (await session.execute(select(PipelineStation).where(PipelineStation.source == source).order_by(PipelineStation.station_key))).scalars().all()
    out: List[DailyTotal] = []
    for st in stations:
        q = select(Observation.observed_at, Observation.value_mm).where(Observation.source == source, Observation.station_key == st.station_key)
        if start is not None:                                   # the period filter is done in SQL, on the rain-day bounds
            q = q.where(Observation.observed_at >= rain_day_bounds(start)[0])
        if end is not None:
            q = q.where(Observation.observed_at < rain_day_bounds(end)[1])
        rows = (await session.execute(q.order_by(Observation.observed_at))).all()
        days: Dict[date, List[float]] = defaultdict(list)
        for t, v in rows:
            d = rain_day(_utc(t))
            if (start is None or d >= start) and (end is None or d <= end):
                days[d].append(float(v))
        for d in sorted(days):
            vs = days[d]
            out.append(DailyTotal(
                source="pipeline", station_id=st.station_key, day=d, mm=round(sum(vs), 3), complete=None, units_confirmed=False,
                row_ref=str(len(out) + 1), latitude=st.latitude, longitude=st.longitude,
                raw={"hours_reported": len(vs), "max_hour_mm": max(vs), "source": source, "name": st.name, "state": st.state,
                     "note": "sum of the non-zero hours the source listed"}))
    return out


async def run_qc(session: AsyncSession, source: str, job: Optional[IngestJob] = None, start: Optional[date] = None, end: Optional[date] = None) -> ValidationRun:
    """Check the stored observations of a source as ONE daily-profile run (source 'pipeline'). Raises ValueError when there is nothing to check."""
    t0 = time.perf_counter()
    records = await daily_totals(session, source, start, end)
    if not records:
        raise ValueError("no stored observations to check for this source and period")
    cat = checks.run_checks(records, "daily", None)
    if source == "cwc":
        cat.not_run.append({"check": "neighbour", "reason": NEIGHBOUR_NOT_TRUSTED})      # before build_report, so the report carries it too
    report = build_report("daily", records, cat, None)
    st = check_settings("daily", None, None)
    st["pipeline"] = {"source": source, "assumptions": dict(cwc.ASSUMPTIONS) if source == "cwc" else {}, "start": start.isoformat() if start else None,
                      "end": end.isoformat() if end else None, "job_id": job.id if job else None,
                      "roll_up": "rain day 03 UTC to 03 UTC, sum of the reported hours, completeness unknown"}
    if source == "cwc":                                    # a source that omits zero hours
        st["pipeline"]["neighbour_checks"] = NEIGHBOUR_NOT_TRUSTED
    days = sorted({r.day for r in records})
    label = f"pipeline {source}: {len({r.station_id for r in records})} stations, {days[0]} to {days[-1]}"
    run = ValidationRun(profile="daily", source="pipeline", label=label, platform_version=app_settings.VERSION, git_commit=git_commit(), settings=st,
                        status="completed", n_rows=len(records), n_stations=len({r.station_id for r in records}), not_run=list(cat.not_run),
                        report=report, issue_counts=dict(Counter(i.code for r in records for i in r.issues)))
    session.add(run)
    await session.flush()
    await _store_rows(session, run, records, cat)
    run.duration_ms = (time.perf_counter() - t0) * 1000
    if job is not None:
        job.run_id = run.id
    await prune_runs(session)
    await session.commit()
    return run
