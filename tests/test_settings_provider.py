"""Settings: the weather provider (Weather Union or Open-Meteo) and the one weather API key. Mocked transport only; the feed restart is a recorder."""
import json
import os
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient

from backend.app import runtime_settings as rs
from backend.app.api import rainfall as rainfall_api
from backend.app.api import settings as settings_api
from backend.app.config import settings
from backend.app.rainfall.providers import OpenMeteoProvider, WeatherUnionProvider

TOKEN = "t" * 32
KEY = "om-commercial-key-123456"
H = {"X-Admin-Token": TOKEN}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(tmp_path / "rt.json"))
    for name, value in (("ADMIN_TOKEN", TOKEN), ("WEATHER_UNION_API_KEY", ""), ("WEATHER_UNION_CITY", ""), ("WEATHER_PROVIDER", "weather_union")):
        monkeypatch.setattr(settings, name, value)
    settings_api._failures.clear()
    restarts = []

    async def fake_restart():
        restarts.append(1)
        return True
    monkeypatch.setattr(rainfall_api, "restart_rainfall_service", fake_restart)
    monkeypatch.setattr(settings_api, "_TEST_TRANSPORT", None)
    yield restarts


@pytest.mark.asyncio
async def test_the_state_lists_the_providers_and_defaults_to_weather_union(async_client: AsyncClient):
    st = (await async_client.get("/api/settings")).json()
    ids = {p["id"]: p for p in st["providers"]}
    assert set(ids) == {"weather_union", "open_meteo"} and ids["open_meteo"]["key_required"] is False and ids["weather_union"]["key_required"] is True
    wu = st["weather_union"]
    assert wu["provider"] == "weather_union" and wu["key_required"] is True and wu["enabled"] is False


@pytest.mark.asyncio
async def test_open_meteo_is_enabled_with_a_city_and_no_key_while_weather_union_still_needs_one(async_client: AsyncClient, _isolated):
    r = await async_client.put("/api/settings", headers=H, json={"weather_provider": "open_meteo", "weather_union_city": "Mumbai"})
    assert r.status_code == 200, r.text
    wu = r.json()["weather_union"]
    assert wu["provider"] == "open_meteo" and wu["api_key_set"] is False and wu["key_required"] is False and wu["enabled"] is True
    assert sorted(r.json()["saved"]) == ["weather_provider", "weather_union_city"] and _isolated == [1]            # the feed was restarted once
    r = await async_client.put("/api/settings", headers=H, json={"weather_provider": "weather_union"})
    assert r.json()["weather_union"]["enabled"] is False                                                           # a key is required again


@pytest.mark.asyncio
async def test_an_unknown_provider_is_refused(async_client: AsyncClient):
    assert (await async_client.put("/api/settings", headers=H, json={"weather_provider": "accuweather"})).status_code == 422
    with pytest.raises(rs.SettingsError):
        rs.validate_update({"weather_provider": "accuweather"}, [])


@pytest.mark.asyncio
async def test_a_hand_edited_unknown_provider_falls_back_instead_of_breaking(async_client: AsyncClient):
    Path(os.environ["RUNTIME_SETTINGS_PATH"]).write_text(json.dumps({"weather_provider": "nonsense", "weather_union_city": "Mumbai"}))
    eff = rs.effective()
    assert eff.weather_provider == "weather_union" and eff.sources["weather_provider"] == "unset"


def test_the_environment_can_choose_the_provider(monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_PROVIDER", "open_meteo")
    monkeypatch.setattr(settings, "WEATHER_UNION_CITY", "Pune")
    eff = rs.effective()
    assert eff.weather_provider == "open_meteo" and eff.sources["weather_provider"] == "environment" and rs.feed_enabled(eff)
    monkeypatch.setattr(settings, "WEATHER_PROVIDER", "")                       # blank (as in the test environment) means the default
    assert rs.effective().weather_provider == "weather_union"


def test_the_provider_is_built_from_the_effective_settings(monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_UNION_CITY", "Mumbai")
    assert rainfall_api.build_provider(rs.effective()) is None                                       # Weather Union without a key
    monkeypatch.setattr(settings, "WEATHER_UNION_API_KEY", KEY)
    assert isinstance(rainfall_api.build_provider(rs.effective()), WeatherUnionProvider)
    monkeypatch.setattr(settings, "WEATHER_UNION_API_KEY", "")
    monkeypatch.setattr(settings, "WEATHER_PROVIDER", "open_meteo")
    p = rainfall_api.build_provider(rs.effective())
    assert isinstance(p, OpenMeteoProvider) and p.url.startswith("https://api.open-meteo.com") and p.budget.limit == settings.OPEN_METEO_DAILY_CALL_BUDGET
    monkeypatch.setattr(settings, "WEATHER_UNION_API_KEY", KEY)
    assert rainfall_api.build_provider(rs.effective()).url.startswith("https://customer-api.open-meteo.com")      # a key selects the commercial endpoint
    monkeypatch.setattr(settings, "WEATHER_UNION_CITY", "")
    assert rainfall_api.build_provider(rs.effective()) is None                                       # no city: nothing to poll


def _om_payload(v):
    return {"hourly": {"time": ["2026-03-06T08:00", "2026-03-06T09:00"], "precipitation": [0.0, v]}}


@pytest.mark.asyncio
async def test_the_feed_test_for_open_meteo_makes_one_keyless_call(async_client: AsyncClient, monkeypatch):
    rs.save_update({"weather_provider": "open_meteo", "weather_union_city": "Mumbai"})
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.url.host, req.url.params.get("apikey")))
        return httpx.Response(200, json=_om_payload(0.7))
    monkeypatch.setattr(settings_api, "_TEST_TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr("backend.app.rainfall.providers.datetime", _FrozenDatetime)
    r = await async_client.post("/api/settings/feed/test", headers=H)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["rain_accumulation"] == 0.7
    assert seen == [("api.open-meteo.com", None)]


class _FrozenDatetime:
    """Stands in for datetime inside providers.py so 'now' is after the mocked hours."""
    from datetime import datetime as _dt, timezone as _tz

    @classmethod
    def strptime(cls, s, fmt):
        return cls._dt.strptime(s, fmt)

    @classmethod
    def now(cls, tz=None):
        return cls._dt(2026, 3, 6, 10, 0, tzinfo=cls._tz.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize("make,msg", [
    (lambda r: httpx.Response(401, json={}), "rejected"), (lambda r: httpx.Response(500, json={}), "HTTP 500"),
    (lambda r: httpx.Response(400, json={"error": True, "reason": "The supplied API key is invalid."}), "key was rejected (The supplied API key is invalid.)"),
    (lambda r: httpx.Response(200, json={"error": True, "reason": "bad"}), "could not read"),
])
async def test_open_meteo_failures_are_explained_and_the_key_is_never_leaked(async_client: AsyncClient, monkeypatch, make, msg):
    rs.save_update({"weather_provider": "open_meteo", "weather_union_city": "Mumbai", "weather_union_api_key": KEY})
    monkeypatch.setattr(settings_api, "_TEST_TRANSPORT", httpx.MockTransport(make))
    r = await async_client.post("/api/settings/feed/test", headers=H)
    assert r.status_code == 200 and r.json()["ok"] is False and msg in r.json()["message"] and KEY not in r.text


@pytest.mark.asyncio
async def test_the_feed_test_for_open_meteo_needs_only_a_city(async_client: AsyncClient):
    rs.save_update({"weather_provider": "open_meteo"})
    r = await async_client.post("/api/settings/feed/test", headers=H)
    assert r.status_code == 409 and "city" in r.json()["detail"]


@pytest.mark.asyncio
async def test_the_gauge_route_refuses_a_model_feed(async_client: AsyncClient, monkeypatch):
    class Svc:
        class provider:
            name, kind = "open_meteo", "model"
    monkeypatch.setattr(rainfall_api, "_service", Svc())
    r = await async_client.get("/api/rainfall/gauges", headers=H)
    assert r.status_code == 409 and "not gauge" in r.json()["detail"]
