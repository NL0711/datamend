"""The gauge file: Weather Union daily totals with their coordinates, in the form the ml-service ``score-gauges`` command reads.

Totals come from the same rain-day rule as the live runs (03 UTC to 03 UTC, ``daily.total_for_day``) over the stored feed history (90 days
by default, ``FEED_HISTORY_RETENTION_DAYS``). Only COMPLETE rain days are written: a day with a long gap or a missing start or end is biased
low, and a low total would read as a fault to a network that was trained on full days. The accumulation mode is the configured one and the
units are ASSUMED millimetres (``units_confirmed`` false), exactly as everywhere else in the feed.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.app.rainfall.daily import rain_day, total_for_day
from backend.app.rainfall.weather_union import RainObservation

READINGS_PER_DAY = 300                         # an upper guess (one reading every five minutes) for how many to fetch per requested day


def gauge_days(observations: Sequence[RainObservation], mode: str, now: datetime, keep_days: int) -> Tuple[Dict[str, float], Dict[str, int]]:
    """{rain day (ISO): mm} of the complete rain days among the newest ``keep_days`` that hold a usable reading, and a count of what was left out."""
    by_day: Dict[date, List[Tuple[datetime, float]]] = defaultdict(list)
    for o in observations:
        if o.rain_accumulation is None or o.status != "OK":
            continue
        by_day[rain_day(o.observed_at)].append((o.observed_at, o.rain_accumulation))
    out: Dict[str, float] = {}
    left = {"incomplete_days": 0, "no_usable_reading": 0}
    for day in sorted(by_day)[-keep_days:]:
        t = total_for_day("", day, by_day[day], mode, now=now)
        if t.total_mm is None:
            left["no_usable_reading"] += 1
        elif not t.complete:
            left["incomplete_days"] += 1
        else:
            out[day.isoformat()] = t.total_mm
    return out, left


async def gauge_file(service, days: int = 90, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The gauge file of a running RainfallService. Stations without a complete day are listed under ``left_out`` with their counts."""
    if getattr(getattr(service, "provider", None), "kind", "gauge") != "gauge":
        raise ValueError(f"the {service.provider.name} feed is a model estimate, not gauge observations: a gauge file is made from gauges only")
    now = now or datetime.now(timezone.utc)
    gauges: List[Dict[str, Any]] = []
    left_out: Dict[str, Dict[str, int]] = {}
    for sid, st in service.stations.items():
        if service.store is not None:
            obs = await service.store.recent(sid, days * READINGS_PER_DAY)
        else:
            obs = list(service.history.get(sid, []))
        got, left = gauge_days(obs, service.mode, now, days)
        if got:
            gauges.append({"station": sid, "place": st.place, "city": st.city, "lat": st.latitude, "lon": st.longitude, "days": got})
        if left["incomplete_days"] or left["no_usable_reading"] or not got:
            left_out[sid] = left
    return {"source": "Weather Union (Zomato), live rain gauges", "generated_at": now.isoformat(), "rain_day": "03 UTC to 03 UTC, labelled by the date it ends",
            "accumulation_mode": service.mode, "units": "mm, ASSUMED (units_confirmed false)", "days_requested": days,
            "stations_polled": len(service.stations), "stations_with_days": len(gauges), "left_out": left_out,
            "history_kept": None if service.store is None else service.store.state().as_dict(),
            "gauges": gauges}
