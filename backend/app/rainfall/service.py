"""Polling service: fetches the chosen Weather Union stations on a schedule that respects the daily call budget, keeps recent
history, writes a raw JSONL log of every reading (so the unconfirmed accumulation semantics can be checked against real rain),
and reports per-station status, today's total and the quality score."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections import deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Sequence

import httpx

from backend.app.rainfall.catalog import Station, load_catalog, neighbours as catalog_neighbours
from backend.app.rainfall.daily import DailyAccumulator, rain_day
from backend.app.rainfall.weather_union import BudgetExhausted, CallBudget, RainObservation, WeatherUnionClient
from backend.app.geo import haversine_distance_km
from backend.app.validation.adapters import reading_from_observation
from backend.app.validation.checks import run_reading_checks
from backend.app.validation.records import Reading

logger = logging.getLogger(__name__)

SECONDS_PER_DAY = 86400


def pick_cluster(city: str, n: int, catalog: Optional[Dict[str, Station]] = None) -> List[Station]:
    """The ``n`` stations of ``city`` closest to the city's median point, so that they are each other's neighbours."""
    cat = catalog if catalog is not None else load_catalog()
    stations = [s for s in cat.values() if s.city.lower() == city.lower()]
    if not stations:
        raise ValueError(f"no stations for city {city!r}")
    lat = sorted(s.latitude for s in stations)[len(stations) // 2]
    lon = sorted(s.longitude for s in stations)[len(stations) // 2]
    return sorted(stations, key=lambda s: haversine_distance_km(lat, lon, s.latitude, s.longitude))[:n]


def safe_interval_seconds(n_stations: int, budget: int, requested: float) -> float:
    """Poll interval that cannot exceed the daily budget: every station is read once per interval."""
    if n_stations <= 0:
        return requested
    return max(requested, math.ceil(SECONDS_PER_DAY * n_stations / max(budget, 1)))


class RainfallService:
    def __init__(self, client: WeatherUnionClient, stations: Sequence[Station], poll_interval_seconds: float = 900.0,
                 accumulation_mode: str = "cumulative", raw_log_path: Optional[str] = None, buddy_radius_km: float = 10.0,
                 history_len: int = 96) -> None:
        self.client = client
        self.stations = {s.locality_id: s for s in stations}
        self.interval = safe_interval_seconds(len(self.stations), client.budget.limit, poll_interval_seconds)
        self.mode = accumulation_mode
        self.acc = DailyAccumulator(accumulation_mode)
        self.raw_log = Path(raw_log_path) if raw_log_path else None
        self.buddy_radius_km = buddy_radius_km
        self.history: Dict[str, Deque[RainObservation]] = {sid: deque(maxlen=history_len) for sid in self.stations}
        self.last_error: Optional[str] = None
        self.last_poll_at: Optional[datetime] = None
        self._task: Optional[asyncio.Task] = None
        self._catalog = {s.locality_id: s for s in stations}
        self._scored_cache: Optional[tuple] = None
        self.on_poll: Optional[Callable[["RainfallService"], Awaitable[None]]] = None   # called after every poll cycle (live run refresh)

    # -- polling ---------------------------------------------------------------------------------------------------
    def _log_raw(self, obs: RainObservation) -> None:
        if not self.raw_log:
            return
        self.raw_log.parent.mkdir(parents=True, exist_ok=True)
        with self.raw_log.open("a", encoding="utf8") as f:
            f.write(json.dumps({"station_id": obs.station_id, "received_at": obs.observed_at.isoformat(), "status": obs.status,
                                "rain_intensity": obs.rain_intensity, "rain_accumulation": obs.rain_accumulation,
                                "device_type": obs.device_type}) + "\n")

    async def poll_once(self) -> int:
        """Reads every station once. Returns the number of readings stored. Stops early if the budget runs out."""
        stored = 0
        for sid in self.stations:
            try:
                obs = await self.client.fetch_locality(sid)
            except BudgetExhausted as e:
                self.last_error = f"daily call budget reached: {e}"
                logger.warning("[RAINFALL] %s", self.last_error)
                break
            except (httpx.HTTPError, ValueError) as e:
                self.last_error = f"{sid}: {e}"
                logger.warning("[RAINFALL] fetch failed for %s: %s", sid, e)
                continue
            self.history[sid].append(obs)
            self.acc.add(obs)
            self._log_raw(obs)
            stored += 1
        self.last_poll_at = datetime.now(timezone.utc)
        if stored:
            self.last_error = None if stored == len(self.stations) else self.last_error
        return stored

    async def _loop(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # keep the loop alive; the error is shown in the status
                self.last_error = f"poll failed: {e}"
                logger.exception("[RAINFALL] poll failed")
            if self.on_poll is not None:
                try:
                    await self.on_poll(self)
                except asyncio.CancelledError:
                    raise
                except Exception:   # a storage problem must not stop polling or be reported as a feed error
                    logger.exception("[RAINFALL] live run refresh failed")
            await asyncio.sleep(self.interval)

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.client.aclose()

    # -- reporting -------------------------------------------------------------------------------------------------
    def readings(self, day: Optional[date] = None) -> List[Reading]:
        """The held history as platform Reading records (source weather_union, time_basis received, units unconfirmed, with the
        station's catalogue coordinates). With `day`, only readings in that rain day. row_ref is station@time, stable across polls."""
        out: List[Reading] = []
        for sid, hist in self.history.items():
            st = self.stations[sid]
            for obs in hist:
                if day is not None and rain_day(obs.observed_at) != day:
                    continue
                out.append(reading_from_observation(obs, self.mode, f"{sid}@{obs.observed_at.isoformat()}", st.latitude, st.longitude))
        return out

    def _scored(self):
        """(readings, catalogue result, result by reading id), computed once per change of the held history and reused by every station
        report, so listing N stations scores the history once, not N times."""
        key = (self.last_poll_at, sum(len(h) for h in self.history.values()))
        if self._scored_cache is None or self._scored_cache[0] != key:
            readings = self.readings()
            cat = run_reading_checks(readings, self.interval / 60.0, self.buddy_radius_km)
            self._scored_cache = (key, readings, cat, {id(r): res for r, res in zip(readings, cat.results)})
        return self._scored_cache[1], self._scored_cache[2], self._scored_cache[3]

    def _quality(self, sid: str) -> Optional[Dict[str, Any]]:
        """The catalogue's verdict for the station's latest reading, scored with every polled station's history as potential neighbours."""
        readings, cat, by_id = self._scored()
        mine = [r for r in readings if r.station_id == sid and r.timestamp is not None]
        if not mine:
            return None
        last = max(mine, key=lambda r: r.timestamp)
        res = by_id[id(last)]
        n_nb = max((len(h.evidence.get("neighbours", [])) for h in res.hits), default=0)
        return {"assessment": res.verdict, "score": res.rule_score, "severity": res.severity, "score_kind": "rule score (uncalibrated)",
                "reasons": [{"check": h.check, "weight": h.weight, "detail": h.reason, "kind": h.kind} for h in res.hits],
                "neighbours_used": n_nb, "not_run": [n for n in cat.not_run if n.get("station_id") in (None, sid)], "method": cat.method}

    def station_report(self, sid: str, now: Optional[datetime] = None) -> Dict[str, Any]:
        st = self.stations[sid]
        hist = list(self.history[sid])
        now = now or datetime.now(timezone.utc)
        quality = self._quality(sid)
        total = self.acc.total(sid, rain_day(now), now=now)
        last = hist[-1] if hist else None
        return {
            "station_id": sid, "place": st.place, "city": st.city, "device": st.device_label,
            "latitude": st.latitude, "longitude": st.longitude,
            "last_reading": None if last is None else {
                "received_at": last.observed_at.isoformat(), "status": last.status,
                "rain_intensity": last.rain_intensity, "rain_accumulation": last.rain_accumulation},
            "today": {"rain_day": str(total.day), "rain_day_label": "date the 03-to-03 UTC rain day ends", "total_mm": total.total_mm, "n_readings": total.n_readings,
                      "n_resets": total.n_resets, "max_gap_minutes": total.max_gap_minutes, "complete": total.complete,
                      "mode": total.mode, "units_confirmed": total.units_confirmed},
            "quality": quality,
        }

    def status(self) -> Dict[str, Any]:
        return {
            "source": "Weather Union (Zomato), live rain gauges", "stations": len(self.stations),
            "poll_interval_seconds": self.interval, "calls_used_today": self.client.budget.used,
            "calls_remaining_today": self.client.budget.remaining, "last_poll_at": None if not self.last_poll_at else self.last_poll_at.isoformat(),
            "last_error": self.last_error, "accumulation_mode": self.mode,
            "caveats": ["rain_intensity / rain_accumulation units and period are NOT documented by the provider (assumed mm; mode is a setting)",
                        "the API gives no observation timestamp; times are when this service received the reading",
                        "quality score is rules + neighbour check, not a trained model"],
        }
