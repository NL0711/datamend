"""Polling service: fetches the chosen Weather Union stations on a schedule that respects the daily call budget, keeps recent
history, writes a raw JSONL log of every reading (so the unconfirmed accumulation semantics can be checked against real rain),
and reports per-station status, today's total and the quality score."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Sequence

import httpx

from backend.app.rainfall.catalog import Station, load_catalog, neighbours as catalog_neighbours
from backend.app.rainfall.daily import DailyAccumulator, rain_day
from backend.app.rainfall.scorer import score_reading
from backend.app.rainfall.weather_union import BudgetExhausted, CallBudget, RainObservation, WeatherUnionClient
from backend.app.rainfall.geo import haversine_distance_km

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
    def decision_evidence(self, sid: str):
        from backend.app.rainfall.evidence import build_evidence
        hist = list(self.history[sid])
        if not hist:
            raise ValueError("No reading has been received for this station")
        st = self.stations[sid]
        nb = {n.locality_id: list(self.history[n.locality_id])
              for n in catalog_neighbours(st, self.buddy_radius_km, self._catalog)}
        return build_evidence(st, hist, nb, self.stations, score_reading(hist, nb, self.mode), self.mode, self.buddy_radius_km)

    def station_report(self, sid: str, now: Optional[datetime] = None) -> Dict[str, Any]:
        st = self.stations[sid]
        hist = list(self.history[sid])
        now = now or datetime.now(timezone.utc)
        nb = {n.locality_id: list(self.history[n.locality_id])
              for n in catalog_neighbours(st, self.buddy_radius_km, self._catalog) if n.locality_id in self.history}
        score = score_reading(hist, nb, self.mode) if hist else None
        total = self.acc.total(sid, rain_day(now), now=now)
        last = hist[-1] if hist else None
        return {
            "station_id": sid, "place": st.place, "city": st.city, "device": st.device_label,
            "latitude": st.latitude, "longitude": st.longitude,
            "last_reading": None if last is None else {
                "received_at": last.observed_at.isoformat(), "status": last.status,
                "rain_intensity": last.rain_intensity, "rain_accumulation": last.rain_accumulation},
            "today": {"rain_day_utc_start": str(total.day), "total_mm": total.total_mm, "n_readings": total.n_readings,
                      "n_resets": total.n_resets, "max_gap_minutes": total.max_gap_minutes, "complete": total.complete,
                      "mode": total.mode, "units_confirmed": total.units_confirmed},
            "quality": None if score is None else {"assessment": score.assessment, "score": score.score, "reasons": score.reasons,
                                                   "neighbours_used": score.n_neighbours_used, "method": score.method},
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
