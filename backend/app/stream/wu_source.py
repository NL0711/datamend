"""The Weather Union telemetry source: temperature, humidity and rain of the polled stations, from the LIVE RESPONSE of each one.

It does not duplicate the existing integration: it uses the same client (``rainfall.weather_union.WeatherUnionClient``) and the same daily call
counter (``shared_budget``: one counter for the rain feed and this source, 900 of the key's 1000 calls a day). When the rain feed is running with
Weather Union, its client is shared outright; otherwise this source opens its own client on the same counter. The existing rain feed
(rainfall/service.py, its history and its per-station rain checks) is left as it is; it is NOT wrapped, because it keeps only rain fields and
its own schedule. What this source adds is the temperature and humidity that the feed drops.

What a response holds decides what is stored (the catalogue ``device_type`` is unreliable, 4 of 13 sampled stations disagreed with their live
answer): type 1 stations answer temperature, humidity, wind and rain, type 2 rain only, any field can be null. A field that is missing or null is
stored as None, NOT filled (it is "not run" for the checks). There is NO pressure field. Wind is read by the client but the stream has no wind
column, so it is not stored. The API gives no observation time, so a reading is stamped with the time it was received.

Rain: ``rain_accumulation`` has unconfirmed units and period (see rainfall/weather_union.py). The stream stores rain of one reading interval:
in ``per_reading`` mode the value itself, in ``cumulative`` mode the increase since the previous poll of the station (a drop counts as a reset;
the first poll of a run has nothing to subtract from and stores no rain). The mode is the rain feed's own setting; mm is ASSUMED.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import httpx

from backend.app.config import settings
from backend.app.rainfall.service import safe_interval_seconds
from backend.app.rainfall.weather_union import BudgetExhausted, WeatherUnionClient, _num, shared_budget
from backend.app.stream.polling import PollingSource
from backend.app.stream.source import Emit
from backend.app.stream.types import SourceStartFailed, StationInfo, StreamReading

DEFAULT_INTERVAL_S = 900.0


def default_client(api_key: str) -> Tuple[WeatherUnionClient, bool]:
    """(client, owned). The running rain feed's client when it uses Weather Union (not ours to close), else a new one on the shared counter."""
    from backend.app.api import rainfall as rainfall_api
    from backend.app.rainfall.providers import WeatherUnionProvider
    svc = rainfall_api.rainfall_service()
    if svc is not None and isinstance(svc.provider, WeatherUnionProvider):
        return svc.provider.client, False
    return WeatherUnionClient(api_key, settings.WEATHER_UNION_BASE_URL, shared_budget(settings.WEATHER_UNION_DAILY_CALL_BUDGET)), True


class WeatherUnionSource(PollingSource):
    source_id = "weather_union"
    source_type = "WEATHER_UNION"
    name = "Weather Union"
    description = ("Live temperature, humidity and rain of Weather Union stations in Indian cities, as each station answers (a missing field is "
                   "not filled; there is no pressure).")

    def __init__(self, *, client_factory: Callable[[str], Tuple[Any, bool]] = default_client, **kw: Any) -> None:
        super().__init__(**kw)
        self._client_factory = client_factory
        self._client: Any = None
        self._owned = False
        self._stations: List[StationInfo] = []
        self._requested_interval = DEFAULT_INTERVAL_S
        self._interval = DEFAULT_INTERVAL_S
        self._api_key = ""
        self._mode = "cumulative"
        self._config_error: Optional[str] = None
        self._prev_acc: Dict[str, float] = {}
        self.last_fields: Dict[str, List[str]] = {}       # station -> the fields its last answer really held

    def configure(self, stations: Sequence[StationInfo], interval_s: float, api_key: str, rain_mode: str, error: Optional[str] = None) -> None:
        self._stations, self._requested_interval, self._api_key, self._mode, self._config_error = list(stations), interval_s, api_key, rain_mode, error
        self._interval = interval_s

    @property
    def interval_s(self) -> float:
        return self._interval

    def stations(self) -> Sequence[StationInfo]:
        return list(self._stations)

    def extra_metadata(self) -> Dict[str, Any]:
        b = self._client.budget if self._client is not None else shared_budget(settings.WEATHER_UNION_DAILY_CALL_BUDGET)
        return {"calls_used_today": b.used, "calls_remaining_today": b.remaining, "daily_call_budget": b.limit, "requested_interval_seconds": self._requested_interval,
                "last_fields": self.last_fields, "rain_mode": self._mode, "pressure": "never reported by Weather Union"}

    async def prepare(self) -> None:
        if self._config_error:
            raise SourceStartFailed(self._config_error)
        if not self._api_key:
            raise SourceStartFailed("no Weather Union key is set (Settings or WEATHER_UNION_API_KEY)")
        if not self._stations:
            raise SourceStartFailed("no stations are configured for Weather Union")
        from backend.app.rainfall.catalog import load_catalog
        cat = load_catalog()
        missing = [s.station_id for s in self._stations if s.station_id not in cat]
        if missing:
            raise SourceStartFailed(f"not Weather Union stations: {', '.join(missing[:5])}")
        self._client, self._owned = self._client_factory(self._api_key)
        # every station is read once per interval: never an interval whose calls would exceed the daily budget
        self._interval = safe_interval_seconds(len(self._stations), self._client.budget.limit, self._requested_interval)
        self._prev_acc.clear()

    async def release(self) -> None:
        client, owned, self._client = self._client, self._owned, None
        if client is not None and owned:
            await client.aclose()

    def _rain(self, station_id: str, acc: Optional[float]) -> Optional[float]:
        if acc is None:
            return None
        if self._mode == "per_reading":
            return acc
        prev, self._prev_acc[station_id] = self._prev_acc.get(station_id), acc
        if prev is None:
            return None                       # nothing to subtract from: not run, not zero
        return acc - prev if acc >= prev else acc

    async def poll_once(self, emit: Emit) -> Optional[str]:
        """One round: each station is read once (one call each, counted on the shared budget). The round fails as a whole only when no station
        answered; otherwise the reasons of the stations that did not answer are returned as a note."""
        answered, problems = 0, []
        for st in self._stations:
            try:
                obs = await self._client.fetch_locality(st.station_id)
            except BudgetExhausted as e:
                problems.append(f"daily call budget reached: {e}")
                break
            except httpx.HTTPStatusError as e:
                problems.append(f"{st.station_id}: HTTP {e.response.status_code}")
                continue
            except (httpx.HTTPError, ValueError) as e:
                problems.append(f"{st.station_id}: {type(e).__name__}")
                continue
            if obs.status == "API_ERROR":
                problems.append(f"{st.station_id}: the API reported an error")
                continue
            answered += 1
            data = (obs.raw.get("locality_weather_data") or {}) if isinstance(obs.raw, dict) else {}
            temp, hum = _num(data.get("temperature")), _num(data.get("humidity"))
            rain = self._rain(st.station_id, obs.rain_accumulation)
            self.last_fields[st.station_id] = [n for n, v in (("temperature", temp), ("humidity", hum), ("rain_accumulation", obs.rain_accumulation),
                                                             ("rain_intensity", obs.rain_intensity)) if v is not None]
            if temp is None and hum is None and rain is None:
                continue                      # nothing usable in the answer (an offline station, or the first rain value of a run): no reading
            await emit(StreamReading(st.station_id, obs.observed_at, "weather_union", temperature_c=temp, humidity_pct=hum, rain_mm=rain))
        if answered == 0 and problems:
            raise RuntimeError("; ".join(problems[:3]))
        return "; ".join(problems[:3])[:300] if problems else None
