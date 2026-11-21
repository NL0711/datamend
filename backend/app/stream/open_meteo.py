"""The Open-Meteo telemetry source: temperature, relative humidity and surface pressure at the stations' coordinates, KEYLESS.

Open-Meteo's ``current`` values are the output of a weather MODEL at the point, not a measurement: every reading carries source ``open_meteo``,
and the stored source says so (no on-screen badge, by owner decision). The station's coordinates are the catalogue gauge's (or the configured
external point's); the model snaps them to its grid.

One poll is ONE multi-location request (``latitude=a,b,c&longitude=x,y,z&current=...``). The model refreshes ``current`` about every 15 minutes
(ASSUMED from its documentation, not measured here), so the default cadence is 15 minutes and a value whose model time was already stored for the
station is not stored again (a repeated value would look like a frozen sensor). A failed poll or an answer of the wrong shape emits nothing and
marks the source disconnected; a variable the model leaves null stays None. Rain is NOT taken from here (the rain feed has its own Open-Meteo
provider for hourly precipitation).

The key that Settings holds for the weather feed is never sent here: this source is keyless on purpose.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from backend.app.config import settings
from backend.app.rainfall.providers import OpenMeteoError
from backend.app.rainfall.weather_union import BudgetExhausted, CallBudget, _num
from backend.app.stream.polling import PollingSource
from backend.app.stream.source import Emit
from backend.app.stream.types import SourceStartFailed, StationInfo, StreamReading

CURRENT_VARIABLES = "temperature_2m,relative_humidity_2m,surface_pressure"
MAX_LOCATIONS = 50          # ASSUMED cap per request (keeps the URL short and the call weight small); not a documented limit
DEFAULT_INTERVAL_S = 900.0


def parse_current(body: Any, stations: Sequence[StationInfo]) -> Tuple[List[StreamReading], List[str]]:
    """Open-Meteo's answer -> readings, and a note per station that gave nothing. One location answers an object, several answer a list in request
    order. A null value stays None; a station with none of the three values gives no reading. Raises ValueError for any other shape."""
    items = body if isinstance(body, list) else [body]
    if any(isinstance(i, dict) and i.get("error") for i in items):
        reason = next(str(i.get("reason", "unknown")) for i in items if isinstance(i, dict) and i.get("error"))
        raise ValueError(f"Open-Meteo reported an error: {reason[:160]}")
    if len(items) != len(stations) or not all(isinstance(i, dict) for i in items):
        raise ValueError(f"Open-Meteo answered {len(items)} location(s) for {len(stations)} requested")
    readings: List[StreamReading] = []
    notes: List[str] = []
    for st, item in zip(stations, items):
        cur = item.get("current")
        if not isinstance(cur, dict) or "time" not in cur:
            notes.append(f"{st.station_id}: no current values")
            continue
        try:
            when = datetime.fromisoformat(str(cur["time"]))
        except ValueError:
            raise ValueError(f"Open-Meteo time {cur['time']!r} is not an ISO time")
        when = when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)      # timezone=UTC is requested
        t, rh, p = _num(cur.get("temperature_2m")), _num(cur.get("relative_humidity_2m")), _num(cur.get("surface_pressure"))
        if t is None and rh is None and p is None:
            notes.append(f"{st.station_id}: all current values null")
            continue
        readings.append(StreamReading(st.station_id, when, "open_meteo", temperature_c=t, pressure_hpa=p, humidity_pct=rh))
    return readings, notes


class OpenMeteoSource(PollingSource):
    source_id = "open_meteo"
    source_type = "EXTERNAL_API"
    name = "Open-Meteo"
    description = ("Temperature, humidity and surface pressure from the Open-Meteo weather model at the station coordinates (keyless). "
                   "MODEL ESTIMATES, not measurements.")

    def __init__(self, *, transport: Optional[httpx.AsyncBaseTransport] = None, budget: Optional[CallBudget] = None, base_url: Optional[str] = None,
                 timeout: float = 15.0, **kw: Any) -> None:
        super().__init__(**kw)
        self._transport, self._timeout = transport, timeout
        self.budget = budget or CallBudget(settings.OPEN_METEO_DAILY_CALL_BUDGET)
        self._url = (base_url or settings.OPEN_METEO_BASE_URL).rstrip("/") + "/v1/forecast"
        self._stations: List[StationInfo] = []
        self._interval = DEFAULT_INTERVAL_S
        self._config_error: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._last_time: Dict[str, datetime] = {}
        self.last_latency_ms: Optional[float] = None

    # -- configuration
    def configure(self, stations: Sequence[StationInfo], interval_s: float, error: Optional[str] = None) -> None:
        self._stations, self._interval, self._config_error = list(stations), interval_s, error

    @property
    def interval_s(self) -> float:
        return self._interval

    def stations(self) -> Sequence[StationInfo]:
        return list(self._stations)

    def extra_metadata(self) -> Dict[str, Any]:
        return {"model_estimates": True, "calls_used_today": self.budget.used, "calls_remaining_today": self.budget.remaining,
                "assumed_model_refresh_minutes": 15}

    # -- transport
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout, transport=self._transport)
        return self._client

    async def fetch_current(self, stations: Optional[Sequence[StationInfo]] = None) -> Tuple[List[StreamReading], List[str]]:
        """ONE request for all ``stations`` (default: the configured set). Raises BudgetExhausted before sending, OpenMeteoError on an HTTP error,
        httpx errors on a failed request and ValueError on an answer of the wrong shape. Never invents a value."""
        sts = list(stations if stations is not None else self._stations)
        if not sts:
            raise ValueError("no stations to read")
        if len(sts) > MAX_LOCATIONS:
            raise ValueError(f"{len(sts)} stations is more than one Open-Meteo request is allowed here ({MAX_LOCATIONS}); choose a smaller station set")
        if self.budget.remaining < len(sts):
            raise BudgetExhausted(f"{self.budget.used}/{self.budget.limit} calls used today (one per location)")
        for _ in sts:
            self.budget.take()         # a multi-location request counts one call per location (ASSUMED weighting, the safe side)
        params = {"latitude": ",".join(f"{s.latitude:.4f}" for s in sts), "longitude": ",".join(f"{s.longitude:.4f}" for s in sts),
                  "current": CURRENT_VARIABLES, "timezone": "UTC"}
        t0 = time.perf_counter()
        r = await self._http().get(self._url, params=params)
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
        return parse_current(body, sts)

    # -- the polling loop
    async def prepare(self) -> None:
        if self._config_error:
            raise SourceStartFailed(self._config_error)
        if not self._stations:
            raise SourceStartFailed("no stations are configured for Open-Meteo")
        if len(self._stations) > MAX_LOCATIONS:
            raise SourceStartFailed(f"{len(self._stations)} stations is more than one Open-Meteo request is allowed here ({MAX_LOCATIONS}); choose a smaller station set")
        self._last_time.clear()

    async def release(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def poll_once(self, emit: Emit) -> Optional[str]:
        readings, notes = await self.fetch_current()
        for rd in readings:
            if self._last_time.get(rd.station_id) is not None and rd.timestamp <= self._last_time[rd.station_id]:
                continue                     # the model has not produced a new value yet: not stored twice
            self._last_time[rd.station_id] = rd.timestamp
            await emit(rd)
        return "; ".join(notes)[:300] if notes else None
