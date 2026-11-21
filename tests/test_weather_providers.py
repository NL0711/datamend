"""Weather providers behind the live feed: Open-Meteo (hourly model precipitation) and Weather Union, through a mocked transport only.
No real API, no quota. The Open-Meteo response shape was checked once against the public API: hourly.time as 'YYYY-MM-DDTHH:MM' in UTC (timezone=UTC),
hourly.precipitation in mm, each value the sum of the PRECEDING hour."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.app.rainfall.catalog import Station
from backend.app.rainfall.daily import DailyAccumulator, rain_day
from backend.app.rainfall.providers import OpenMeteoError, OpenMeteoProvider, WeatherUnionProvider, provider_info
from backend.app.rainfall.weather_union import BudgetExhausted, CallBudget, WeatherUnionClient

UTC = timezone.utc
ST = Station("ZWL001", "Mumbai", "Bandra", 19.0596, 72.8295, 2)
NOW = datetime(2026, 3, 6, 10, 20, tzinfo=UTC)                       # the hour stamped 10:00 is the last complete one


def payload(times, values):
    return {"latitude": 19.06, "longitude": 72.83, "hourly_units": {"time": "iso8601", "precipitation": "mm"}, "hourly": {"time": times, "precipitation": values}}


def provider(handler, key="", **kw):
    return OpenMeteoProvider(key, "https://api.open-meteo.com", "https://customer-api.open-meteo.com", CallBudget(100), clock=lambda: NOW,
                             transport=httpx.MockTransport(handler), **kw)


@pytest.mark.asyncio
async def test_open_meteo_sends_the_coordinates_utc_and_no_key_by_default():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["q"] = str(req.url), dict(req.url.params)
        return httpx.Response(200, json=payload(["2026-03-06T09:00", "2026-03-06T10:00"], [0.2, 1.4]))

    obs = await provider(handler).fetch(ST)
    assert seen["url"].startswith("https://api.open-meteo.com/v1/forecast?")
    assert seen["q"]["latitude"] == "19.0596" and seen["q"]["longitude"] == "72.8295" and seen["q"]["timezone"] == "UTC"
    assert seen["q"]["hourly"] == "precipitation" and "apikey" not in seen["q"] and "past_hours" in seen["q"]
    assert len(obs) == 2


@pytest.mark.asyncio
async def test_a_key_switches_to_the_customer_endpoint():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["host"], seen["key"] = req.url.host, req.url.params.get("apikey")
        return httpx.Response(200, json=payload(["2026-03-06T09:00"], [0.0]))

    await provider(handler, key="my-commercial-key").fetch(ST)
    assert seen == {"host": "customer-api.open-meteo.com", "key": "my-commercial-key"}


@pytest.mark.asyncio
@pytest.mark.parametrize("status,reason,key_problem", [
    (401, "API key required. Please add &apikey= to the URL.", True),               # what customer-api.open-meteo.com answers with no key (checked 2026-11-21)
    (400, "The supplied API key is invalid.", True),                                # ... and with a wrong key
    (403, "", True), (400, "Latitude must be in range of -90 to 90", False), (500, "boom", False)])
async def test_a_key_problem_is_told_apart_from_other_errors(status, reason, key_problem):
    with pytest.raises(OpenMeteoError) as e:
        await provider(lambda req: httpx.Response(status, json={"error": True, "reason": reason} if reason else {}), key="a-key-123456").fetch(ST)
    assert e.value.key_problem is key_problem and e.value.status == status


@pytest.mark.asyncio
async def test_each_value_becomes_an_observation_stamped_with_the_start_of_the_hour_it_covers():
    def handler(req):
        return httpx.Response(200, json=payload(["2026-03-06T08:00", "2026-03-06T09:00", "2026-03-06T10:00"], [0.0, 2.5, 1.0]))

    obs = await provider(handler).fetch(ST)
    assert [o.observed_at for o in obs] == [datetime(2026, 3, 6, 7, tzinfo=UTC), datetime(2026, 3, 6, 8, tzinfo=UTC), datetime(2026, 3, 6, 9, tzinfo=UTC)]
    assert [o.rain_accumulation for o in obs] == [0.0, 2.5, 1.0] and [o.rain_intensity for o in obs] == [0.0, 2.5, 1.0]     # mm in the hour = mm per hour
    assert all(o.station_id == "ZWL001" and o.status == "OK" and o.raw["provider"] == "open_meteo" for o in obs)


@pytest.mark.asyncio
async def test_future_hours_are_forecasts_and_are_dropped():
    def handler(req):
        return httpx.Response(200, json=payload(["2026-03-06T10:00", "2026-03-06T11:00", "2026-03-06T12:00"], [1.0, 9.9, 9.9]))

    obs = await provider(handler).fetch(ST)
    assert len(obs) == 1 and obs[0].rain_accumulation == 1.0                         # 11:00 and 12:00 are after 'now' (10:20)


@pytest.mark.asyncio
async def test_a_missing_value_is_kept_as_no_data_not_as_zero():
    def handler(req):
        return httpx.Response(200, json=payload(["2026-03-06T08:00", "2026-03-06T09:00"], [None, 0.4]))

    obs = await provider(handler).fetch(ST)
    assert obs[0].status == "NO_RAIN_FIELDS" and obs[0].rain_accumulation is None and obs[1].rain_accumulation == 0.4


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"error": True, "reason": "Latitude must be in range of -90 to 90"}),
    httpx.Response(200, json={"hourly": {"time": ["2026-03-06T08:00"], "precipitation": []}}),
    httpx.Response(200, json={"hourly": {"time": "x", "precipitation": [1]}}),
    httpx.Response(200, content=b"not json"),
])
async def test_a_bad_answer_raises_value_error_and_is_never_turned_into_rain(response):
    with pytest.raises(ValueError):
        await provider(lambda req: response).fetch(ST)


@pytest.mark.asyncio
async def test_http_errors_carry_the_apis_own_reason_and_the_budget_is_counted_before_the_call():
    with pytest.raises(OpenMeteoError) as e:
        await provider(lambda req: httpx.Response(429, json={"error": True, "reason": "too many"})).fetch(ST)
    assert e.value.status == 429 and e.value.reason == "too many" and not e.value.key_problem and str(e.value) == "Open-Meteo answered HTTP 429: too many"
    with pytest.raises(OpenMeteoError) as e:
        await provider(lambda req: httpx.Response(502, content=b"<html>bad gateway</html>")).fetch(ST)
    assert e.value.status == 502 and e.value.reason                                      # a non-JSON body falls back to the HTTP reason phrase
    p = OpenMeteoProvider("", "https://api.open-meteo.com", "https://customer-api.open-meteo.com", CallBudget(1), clock=lambda: NOW,
                          transport=httpx.MockTransport(lambda req: httpx.Response(200, json=payload([], []))))
    await p.fetch(ST)
    with pytest.raises(BudgetExhausted):
        await p.fetch(ST)


def test_provider_facts_are_stated_not_assumed():
    om = provider(lambda r: httpx.Response(200))
    assert (om.name, om.kind, om.units_confirmed, om.forced_mode, om.reading_minutes, om.time_basis) == ("open_meteo", "model", True, "per_reading", 60.0, "observed")
    assert om.min_poll_seconds >= 900 and any("model" in c and "not a gauge" in c for c in om.caveats)
    wu = WeatherUnionProvider(WeatherUnionClient("k" * 12, "https://x.example", CallBudget(5), transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    assert (wu.name, wu.kind, wu.units_confirmed, wu.forced_mode, wu.reading_minutes, wu.time_basis) == ("weather_union", "gauge", False, None, None, "received")
    info = {p["id"]: p for p in provider_info()}
    assert info["open_meteo"]["key_required"] is False and info["weather_union"]["key_required"] is True and info["open_meteo"]["kind"] == "model"


@pytest.mark.asyncio
async def test_weather_union_provider_wraps_the_existing_client_unchanged():
    def handler(req):
        return httpx.Response(200, json={"status": "200", "device_type": 2, "locality_weather_data": {"rain_intensity": 0.2, "rain_accumulation": 3.0}})

    wu = WeatherUnionProvider(WeatherUnionClient("k" * 12, "https://x.example", CallBudget(5), transport=httpx.MockTransport(handler)))
    (o,) = await wu.fetch(ST)
    assert o.station_id == "ZWL001" and o.rain_accumulation == 3.0 and wu.budget.used == 1


def test_a_full_open_meteo_rain_day_is_complete_and_totals_the_hourly_values():
    """24 hourly values from 03:00 to 02:00 UTC (the hour that ends 04:00 .. 03:00 next day) make one complete rain day."""
    from backend.app.rainfall.weather_union import RainObservation
    day_start = datetime(2026, 3, 5, 3, tzinfo=UTC)
    acc = DailyAccumulator("per_reading", edge_ok_minutes=60.0)
    for h in range(24):
        acc.add(RainObservation("ZWL001", day_start + timedelta(hours=h), None, 0.5, 0.5))
    day = rain_day(day_start)
    assert str(day) == "2026-03-06"
    t = acc.total("ZWL001", day, now=datetime(2026, 3, 6, 9, tzinfo=UTC))
    assert t.total_mm == 12.0 and t.n_readings == 24 and t.complete is True
    strict = DailyAccumulator("per_reading")                                         # the 30 minute default calls the last hour 'too far from the end'
    for h in range(24):
        strict.add(RainObservation("ZWL001", day_start + timedelta(hours=h), None, 0.5, 0.5))
    assert strict.total("ZWL001", day, now=datetime(2026, 3, 6, 9, tzinfo=UTC)).complete is False
