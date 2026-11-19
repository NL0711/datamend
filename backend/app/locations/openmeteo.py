"""Open-Meteo client for the Locations feature: geocoding, recent hourly series, 30-year daily history.

Open-Meteo returns the value at ITS nearest model grid point, not the mean of a 0.25-degree cell. Every result carries the
point actually used (``grid_point``) so the UI can say so. Future hours (forecast values) are dropped from the "recent" series:
they are not observations.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from backend.app.config import settings

logger = logging.getLogger(__name__)

FORECAST_URL = settings.EXTERNAL_WEATHER_BASE_URL
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
HOURLY = ("temperature_2m", "relative_humidity_2m", "surface_pressure", "precipitation")
DAILY = ("temperature_2m_mean", "relative_humidity_2m_mean", "surface_pressure_mean", "precipitation_sum")
VAR_OF = {"temperature_2m": "temperature", "relative_humidity_2m": "humidity", "surface_pressure": "pressure", "precipitation": "precipitation",
          "temperature_2m_mean": "temperature", "relative_humidity_2m_mean": "humidity", "surface_pressure_mean": "pressure",
          "precipitation_sum": "precipitation"}
SOURCE = "open_meteo"


class OpenMeteoError(RuntimeError):
    """The external service could not be reached or returned something unusable."""


def _nan(x: Any) -> float:
    return float("nan") if x is None else float(x)


class OpenMeteoClient:
    def __init__(self, client: Optional[httpx.AsyncClient] = None, timeout: float = 15.0, retries: int = 2, backoff: float = 1.5) -> None:
        self._client = client
        self.timeout, self.retries, self.backoff = timeout, retries, backoff

    async def _get(self, url: str, params: Dict[str, Any]) -> Any:
        last: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                if self._client is not None:
                    r = await self._client.get(url, params=params, timeout=self.timeout)
                else:
                    async with httpx.AsyncClient() as c:
                        r = await c.get(url, params=params, timeout=self.timeout)
                if r.status_code == 429:
                    raise OpenMeteoError("Open-Meteo rate limit reached (HTTP 429); try again later")
                r.raise_for_status()
                return r.json()
            except OpenMeteoError:
                raise
            except Exception as e:                      # network, HTTP and JSON errors
                last = e
                if attempt < self.retries:
                    await asyncio.sleep(self.backoff * (attempt + 1))
        raise OpenMeteoError(f"Open-Meteo request failed: {last}")

    async def geocode(self, name: str, count: int = 5) -> List[Dict[str, Any]]:
        data = await self._get(GEOCODING_URL, {"name": name, "count": count, "language": "en"})
        return [{"name": r.get("name"), "latitude": r["latitude"], "longitude": r["longitude"], "country": r.get("country"),
                 "admin1": r.get("admin1")} for r in (data.get("results") or [])]

    @staticmethod
    def _as_list(data: Any, n: int) -> List[Dict[str, Any]]:
        items = data if isinstance(data, list) else [data]
        if len(items) != n:
            raise OpenMeteoError(f"expected {n} results, got {len(items)}")
        return items

    async def recent(self, points: Sequence[Tuple[float, float]], past_days: int = 7, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Hourly series for each point, up to the current hour (UTC). One batched call for all points."""
        now = now or datetime.now(timezone.utc)
        data = await self._get(FORECAST_URL, {
            "latitude": ",".join(f"{p[0]:.4f}" for p in points), "longitude": ",".join(f"{p[1]:.4f}" for p in points),
            "hourly": ",".join(HOURLY), "past_days": past_days, "forecast_days": 1, "timezone": "UTC"})
        out = []
        for item in self._as_list(data, len(points)):
            h = item.get("hourly") or {}
            times = h.get("time") or []
            keep = [i for i, t in enumerate(times) if datetime.fromisoformat(t).replace(tzinfo=timezone.utc) <= now]
            out.append({"grid_point": {"lat": item.get("latitude"), "lon": item.get("longitude")}, "elevation": item.get("elevation"),
                        "time": [times[i] for i in keep],
                        **{VAR_OF[k]: [_nan((h.get(k) or [None] * len(times))[i]) for i in keep] for k in HOURLY}})
        return out

    async def history(self, points: Sequence[Tuple[float, float]], start: str, end: str) -> List[Dict[str, Any]]:
        """Daily means (and rainfall sums) for each point, UTC days."""
        data = await self._get(ARCHIVE_URL, {
            "latitude": ",".join(f"{p[0]:.4f}" for p in points), "longitude": ",".join(f"{p[1]:.4f}" for p in points),
            "start_date": start, "end_date": end, "daily": ",".join(DAILY), "timezone": "UTC"})
        out = []
        for item in self._as_list(data, len(points)):
            d = item.get("daily") or {}
            n = len(d.get("time") or [])
            out.append({"grid_point": {"lat": item.get("latitude"), "lon": item.get("longitude")}, "time": d.get("time") or [],
                        **{VAR_OF[k]: [_nan(x) for x in (d.get(k) or [None] * n)] for k in DAILY}})
        return out
