"""The live feed with Open-Meteo behind it (mocked transport): repeated polls do not double count, readings and status say 'model, not a gauge',
the daily total is the sum of the hourly values, and the gauge-only score file refuses it."""
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from backend.app.rainfall.catalog import Station
from backend.app.rainfall.gauges import gauge_file
from backend.app.rainfall.providers import OpenMeteoProvider
from backend.app.rainfall.service import RainfallService
from backend.app.rainfall.weather_union import CallBudget

UTC = timezone.utc
STATIONS = [Station("ZWL001", "Mumbai", "Bandra", 19.0596, 72.8295, 2), Station("ZWL002", "Mumbai", "Dadar", 19.0178, 72.8478, 2)]


class Sky:
    """A fake Open-Meteo: a clock and an hourly series per station (mm of the hour ending at each stamp)."""

    def __init__(self, now: datetime):
        self.now, self.calls, self.per_hour = now, 0, 0.5

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls += 1
        past = int(req.url.params["past_hours"])
        end = self.now.replace(minute=0, second=0, microsecond=0)
        stamps = [end - timedelta(hours=past - i) for i in range(past + 1)]            # past_hours back up to the current hour
        return httpx.Response(200, json={"hourly": {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in stamps], "precipitation": [self.per_hour] * len(stamps)}})


def service(sky: Sky, **kw) -> RainfallService:
    prov = OpenMeteoProvider("", "https://api.open-meteo.com", "https://customer-api.open-meteo.com", CallBudget(1000), past_hours=6,
                             clock=lambda: sky.now, transport=httpx.MockTransport(sky.handler))
    return RainfallService(prov, STATIONS, 900.0, "cumulative", **kw)


@pytest.mark.asyncio
async def test_a_poll_stores_the_hours_and_a_repeat_adds_nothing():
    sky = Sky(datetime(2026, 3, 6, 10, 20, tzinfo=UTC))
    svc = service(sky)
    first = await svc.poll_once()
    assert first == 2 * 7                                                              # 7 complete hours per station (the 04:00 .. 10:00 stamps)
    assert len(svc.history["ZWL001"]) == 7
    assert await svc.poll_once() == 0 and len(svc.history["ZWL001"]) == 7              # the same hours again: nothing new
    sky.now = datetime(2026, 3, 6, 11, 5, tzinfo=UTC)                                  # the next hour arrives
    assert await svc.poll_once() == 2 and len(svc.history["ZWL001"]) == 8
    assert svc.last_error is None


@pytest.mark.asyncio
async def test_the_mode_is_forced_per_reading_and_the_interval_is_at_least_half_an_hour():
    svc = service(Sky(datetime(2026, 3, 6, 10, 20, tzinfo=UTC)))
    assert svc.mode == "per_reading" and svc.interval >= 1800.0
    assert svc.reading_minutes == 60.0


@pytest.mark.asyncio
async def test_readings_say_model_hourly_confirmed_units_and_the_poll_budget_is_counted():
    sky = Sky(datetime(2026, 3, 6, 10, 20, tzinfo=UTC))
    svc = service(sky)
    await svc.poll_once()
    rs = svc.readings()
    assert len(rs) == 14 and all(r.source == "open_meteo" and r.time_basis == "observed" and r.units_confirmed is True and r.accumulation_mode == "per_reading" for r in rs)
    assert sky.calls == 2 and svc.provider.budget.used == 2
    st = svc.status()
    assert "Open-Meteo" in st["source"] and st["provider"] == "open_meteo" and st["kind"] == "model"
    assert any("not a gauge" in c for c in st["caveats"]) and st["accumulation_mode"] == "per_reading"


@pytest.mark.asyncio
async def test_the_daily_total_is_the_sum_of_the_hours_and_a_full_day_is_complete():
    sky = Sky(datetime(2026, 3, 6, 3, 10, tzinfo=UTC))                                 # just after the rain day ending 2026-03-06 closed
    sky.per_hour = 0.5
    svc = service(sky)
    for h in range(0, 24, 6):                                                          # polls every six hours cover the whole day
        sky.now = datetime(2026, 3, 5, 3, 10, tzinfo=UTC) + timedelta(hours=h + 6)
        await svc.poll_once()
    sky.now = datetime(2026, 3, 6, 3, 10, tzinfo=UTC)
    await svc.poll_once()
    rep = svc.station_report("ZWL001", now=sky.now)
    # the rain day ending 2026-03-06 is open again at 03:10, so ask for the closed one directly
    t = svc.acc.total("ZWL001", date(2026, 3, 6), now=sky.now)
    assert t.n_readings == 24 and t.total_mm == 12.0 and t.complete is True and t.mode == "per_reading"
    assert rep["device"] == "model point (Open-Meteo)" and rep["last_reading"]["status"] == "OK"


@pytest.mark.asyncio
async def test_a_failed_station_is_reported_and_the_rest_still_stored():
    sky = Sky(datetime(2026, 3, 6, 10, 20, tzinfo=UTC))
    calls = {"n": 0}

    def flaky(req):
        calls["n"] += 1
        return httpx.Response(500, json={"error": True, "reason": "boom"}) if calls["n"] == 1 else sky.handler(req)

    prov = OpenMeteoProvider("", "https://api.open-meteo.com", "https://customer-api.open-meteo.com", CallBudget(100), clock=lambda: sky.now, transport=httpx.MockTransport(flaky))
    svc = RainfallService(prov, STATIONS, 900.0)
    n = await svc.poll_once()
    assert n == 7 and svc.last_error and "ZWL001" in svc.last_error and len(svc.history["ZWL001"]) == 0 and len(svc.history["ZWL002"]) == 7


@pytest.mark.asyncio
async def test_the_gauge_file_refuses_a_model_provider():
    svc = service(Sky(datetime(2026, 3, 6, 10, 20, tzinfo=UTC)))
    await svc.poll_once()
    with pytest.raises(ValueError, match="not gauge"):
        await gauge_file(svc, days=5)
