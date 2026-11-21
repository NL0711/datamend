"""Weather providers behind the live feed: one small interface, two adapters.

  * ``WeatherUnionProvider``: Weather Union's rain-gauge stations (a key is required). One reading per call, timestamped when we receive it.
  * ``OpenMeteoProvider``: Open-Meteo's hourly precipitation at a point (no key needed; a commercial key switches to the customer endpoint).
    It is a MODEL product, not a gauge: every value is labelled so, and the gauge-only features (the score gauge file) refuse it.

Open-Meteo facts (checked against the public API on 2026-11-21): ``GET /v1/forecast?latitude=&longitude=&hourly=precipitation&timezone=UTC&past_hours=N``
answers ``hourly.time`` as 'YYYY-MM-DDTHH:MM' and ``hourly.precipitation`` in mm, each value the sum of the PRECEDING hour. An hour stamped t therefore
covers (t - 1 h, t]; its observation is stamped with the START of that hour so it falls in the right 03-to-03 UTC rain day. Hours after now are
forecasts and are dropped. A missing value stays missing (never zero).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol

import httpx

from backend.app.rainfall.catalog import Station
from backend.app.rainfall.weather_union import CallBudget, RainObservation, WeatherUnionClient

PROVIDERS = ("weather_union", "open_meteo")


class RainProvider(Protocol):
    name: str
    label: str                       # the source line shown on the status
    kind: str                        # "gauge" (a physical rain gauge) or "model" (a model estimate at a point)
    budget: CallBudget
    time_basis: str                  # "received" (time of receipt) or "observed" (a time the provider states)
    units_confirmed: bool
    forced_mode: Optional[str]       # the accumulation mode the provider's values have, or None to use the setting
    reading_minutes: Optional[float]  # the readings' own step in minutes, or None to use the poll interval
    min_poll_seconds: float
    edge_ok_minutes: float           # how far from a rain day's edges the first and last reading may be and the day still count complete
    caveats: List[str]

    async def fetch(self, station: Station) -> List[RainObservation]: ...
    async def aclose(self) -> None: ...


class WeatherUnionProvider:
    name = "weather_union"
    label = "Weather Union (Zomato), live rain gauges"
    kind = "gauge"
    time_basis = "received"
    units_confirmed = False
    forced_mode: Optional[str] = None
    reading_minutes: Optional[float] = None
    min_poll_seconds = 0.0
    edge_ok_minutes = 30.0
    caveats = ["rain_intensity / rain_accumulation units and period are NOT documented by the provider (assumed mm; mode is a setting)",
               "the API gives no observation timestamp; times are when this service received the reading",
               "quality score is rules + neighbour check, not a trained model"]

    def __init__(self, client: WeatherUnionClient) -> None:
        self.client = client
        self.budget = client.budget

    async def fetch(self, station: Station) -> List[RainObservation]:
        return [await self.client.fetch_locality(station.locality_id)]

    async def aclose(self) -> None:
        await self.client.aclose()


class OpenMeteoError(ValueError):
    """Open-Meteo answered with an HTTP error. ``reason`` is the API's own words (it answers {"error": true, "reason": "..."}). Checked against
    customer-api.open-meteo.com on 2026-11-21: no key gives 401 ("API key required"), a wrong key gives 400 ("The supplied API key is invalid")."""

    def __init__(self, status: int, reason: str) -> None:
        super().__init__(f"Open-Meteo answered HTTP {status}" + (f": {reason}" if reason else ""))
        self.status, self.reason = status, reason

    @property
    def key_problem(self) -> bool:
        return self.status in (401, 403) or (self.status == 400 and "key" in self.reason.lower())


class OpenMeteoProvider:
    name = "open_meteo"
    label = "Open-Meteo, hourly precipitation (model estimate, not a gauge)"
    kind = "model"
    time_basis = "observed"
    units_confirmed = True                       # the API states mm
    forced_mode = "per_reading"                  # each hourly value is the rain of that hour
    reading_minutes = 60.0
    min_poll_seconds = 1800.0                    # new values appear hourly; polling faster only repeats the same hours
    edge_ok_minutes = 60.0                       # hourly values: the last hour of a day starts 60 minutes before the day's end
    caveats = ["Open-Meteo precipitation is a weather model estimate at the point, not a gauge reading",
               "each value is the sum of the preceding hour, stamped here with the start of that hour (UTC)",
               "quality score is rules + neighbour check, not a trained model"]

    def __init__(self, api_key: str, base_url: str, customer_base_url: str, budget: CallBudget, past_hours: int = 6, timeout: float = 15.0,
                 transport: Optional[httpx.AsyncBaseTransport] = None, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.api_key = api_key.strip()
        self.url = (customer_base_url if self.api_key else base_url).rstrip("/") + "/v1/forecast"
        self.budget, self.past_hours, self._clock = budget, max(2, min(int(past_hours), 48)), clock
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)
        self.last_latency_ms: Optional[float] = None

    async def aclose(self) -> None:
        await self._client.aclose()

    def _params(self, station: Station) -> Dict[str, Any]:
        q: Dict[str, Any] = {"latitude": f"{station.latitude:.4f}", "longitude": f"{station.longitude:.4f}", "hourly": "precipitation",
                             "timezone": "UTC", "past_hours": self.past_hours, "forecast_hours": 1}
        if self.api_key:
            q["apikey"] = self.api_key
        return q

    async def fetch(self, station: Station) -> List[RainObservation]:
        """One call; the last ``past_hours`` complete hours as observations, oldest first. Raises BudgetExhausted before sending if the allowance
        is used up, httpx errors on a failed request, and ValueError when the answer is not the documented shape."""
        self.budget.take()
        t0 = time.perf_counter()
        r = await self._client.get(self.url, params=self._params(station))
        self.last_latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        if r.status_code >= 400:
            try:
                reason = str(r.json().get("reason", ""))[:160]
            except Exception:
                reason = ""
            raise OpenMeteoError(r.status_code, reason or r.reason_phrase)
        try:
            body = r.json()
        except ValueError:
            raise ValueError("Open-Meteo did not return JSON")
        return self._parse(station.locality_id, body, self._clock())

    @staticmethod
    def _parse(station_id: str, body: Any, now: datetime) -> List[RainObservation]:
        if not isinstance(body, dict):
            raise ValueError("Open-Meteo answer is not an object")
        if body.get("error"):
            raise ValueError(f"Open-Meteo reported an error: {str(body.get('reason', 'unknown'))[:160]}")
        hourly = body.get("hourly")
        times, values = (hourly or {}).get("time"), (hourly or {}).get("precipitation")
        if not isinstance(times, list) or not isinstance(values, list) or len(times) != len(values):
            raise ValueError("Open-Meteo answer has no matching hourly time and precipitation lists")
        out: List[RainObservation] = []
        for stamp, v in zip(times, values):
            try:
                hour_end = datetime.strptime(str(stamp), "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
            except ValueError:
                raise ValueError(f"Open-Meteo hour {stamp!r} is not YYYY-MM-DDTHH:MM")
            if hour_end > now:                                    # a forecast, not yet a value
                continue
            mm = None if v is None or isinstance(v, bool) else _finite_nonneg(v)
            raw = {"provider": "open_meteo", "hour_end_utc": hour_end.isoformat(), "precipitation_mm": v, "model": "best_match"}
            when = hour_end - timedelta(hours=1)
            out.append(RainObservation(station_id, when, None, mm, mm, "OK", raw) if mm is not None
                       else RainObservation(station_id, when, None, None, None, "NO_RAIN_FIELDS", raw))
        return out


def _finite_nonneg(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and 0.0 <= x < 1e4 else None


def provider_info() -> List[Dict[str, Any]]:
    """What the Settings page may show about each provider."""
    return [
        {"id": "weather_union", "label": "Weather Union", "kind": "gauge", "key_required": True, "mode_setting": True,
         "note": "Rain gauges in Indian cities. Needs a free key from weatherunion.com."},
        {"id": "open_meteo", "label": "Open-Meteo", "kind": "model", "key_required": False, "mode_setting": False,
         "note": "Hourly model precipitation at each station's coordinates. Free without a key; a commercial key is optional. A model estimate, not a gauge."},
    ]
