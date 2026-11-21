"""Weather Union (Zomato) client for live rain-gauge readings.

Documented facts (https://www.weatherunion.com/dashboard/, read 2026-11-19):
  * Base URL https://www.weatherunion.com/gw/weather/external/v0, header ``x-zomato-api-key``.
  * GET /get_locality_weather_data?locality_id=...  and  GET /get_weather_data?latitude=..&longitude=..
  * Response: status, message, device_type, locality_weather_data{temperature, humidity, wind_speed, wind_direction,
    rain_intensity, rain_accumulation, aqi_pm_2_point_5, aqi_pm_10}. Rain-gauge stations return only the rain fields.
  * Free key limit: 1000 calls per day, reset after 12 AM.

NOT DOCUMENTED, therefore never assumed silently:
  * the UNITS of rain_intensity and rain_accumulation,
  * the PERIOD of rain_accumulation (since a midnight reset? since the last reading? rolling?),
  * the observation TIME (the response has no timestamp; ``observed_at`` is the time WE received it).
Observations carry the raw values untouched. Conversion to a daily total is in daily.py with an explicit, labelled mode.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))  # India has no daylight saving time


class BudgetExhausted(RuntimeError):
    """The free key's daily call allowance is used up; no request was sent."""


class CallBudget:
    """Counts calls per IST calendar day and refuses to exceed ``limit`` (the provider allows 1000)."""

    def __init__(self, limit: int = 900, clock=lambda: datetime.now(IST)) -> None:
        self.limit = limit
        self._clock = clock
        self._day: Optional[date] = None
        self.used = 0

    def _roll(self) -> None:
        today = self._clock().date()
        if today != self._day:
            self._day, self.used = today, 0

    def take(self) -> None:
        self._roll()
        if self.used >= self.limit:
            raise BudgetExhausted(f"{self.used}/{self.limit} calls used for {self._day}")
        self.used += 1

    @property
    def remaining(self) -> int:
        self._roll()
        return self.limit - self.used


_shared_budget: Optional[CallBudget] = None


def shared_budget(limit: int = 900) -> CallBudget:
    """THE process-wide counter of the one Weather Union key: the rain feed and the telemetry stream source both count against it, and a restart
    of either does not reset it within the day (the key allows 1000 calls a day in total)."""
    global _shared_budget
    if _shared_budget is None:
        _shared_budget = CallBudget(limit)
    else:
        _shared_budget.limit = limit
    return _shared_budget


@dataclass(frozen=True)
class RainObservation:
    station_id: str
    observed_at: datetime                 # UTC; = time received (the API gives no timestamp)
    device_type: Optional[int]
    rain_intensity: Optional[float]       # raw, unit UNCONFIRMED
    rain_accumulation: Optional[float]    # raw, unit and period UNCONFIRMED
    status: str = "OK"                    # OK | NO_RAIN_FIELDS (station offline / all null) | API_ERROR
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_rain_fields(self) -> bool:
        return self.rain_intensity is not None or self.rain_accumulation is not None


def _num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def parse_response(station_id: str, payload: Dict[str, Any], received_at: datetime) -> RainObservation:
    """Normalise one API response. Never invents values: missing or non-numeric rain fields stay None."""
    if str(payload.get("status")) != "200":
        return RainObservation(station_id, received_at, None, None, None, "API_ERROR", payload)
    data = payload.get("locality_weather_data") or {}
    obs = RainObservation(station_id, received_at, int(payload["device_type"]) if str(payload.get("device_type", "")).isdigit() else None,
                          _num(data.get("rain_intensity")), _num(data.get("rain_accumulation")), "OK", payload)
    if not obs.has_rain_fields:
        return RainObservation(station_id, received_at, obs.device_type, None, None, "NO_RAIN_FIELDS", payload)
    return obs


class WeatherUnionClient:
    def __init__(self, api_key: str, base_url: str, budget: Optional[CallBudget] = None, timeout: float = 15.0,
                 transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        if not api_key:
            raise ValueError("WEATHER_UNION_API_KEY is not set")
        self.base_url = base_url.rstrip("/")
        self.budget = budget or CallBudget()
        self._client = httpx.AsyncClient(timeout=timeout, headers={"x-zomato-api-key": api_key}, transport=transport)
        self.last_latency_ms: Optional[float] = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_locality(self, locality_id: str) -> RainObservation:
        """One call. Raises BudgetExhausted before sending if the allowance is used up; HTTP errors propagate."""
        self.budget.take()
        t0 = time.perf_counter()
        r = await self._client.get(f"{self.base_url}/get_locality_weather_data", params={"locality_id": locality_id})
        self.last_latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        r.raise_for_status()
        return parse_response(locality_id, r.json(), datetime.now(timezone.utc))
