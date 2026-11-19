"""Dashboard settings: Weather Union feed and AI narrator (editing needs ADMIN_TOKEN). No real API call is ever made: the feed test uses a
mocked transport and the feed restart is replaced by a recorder."""
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

TOKEN = "t" * 32
KEY = "wu-secret-key-1234567890"
H = {"X-Admin-Token": TOKEN}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(tmp_path / "rt.json"))
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "WEATHER_UNION_API_KEY", "")
    monkeypatch.setattr(settings, "WEATHER_UNION_CITY", "")
    monkeypatch.setattr(settings, "NARRATOR_URL", "")
    monkeypatch.setattr(settings, "NARRATOR_TOKEN", "")
    monkeypatch.setenv("NARRATOR_ALLOW_PRIVATE", "true")        # most tests use a made-up host; the private-address guard has its own tests
    settings_api._failures.clear()
    restarts = []

    async def fake_restart():
        restarts.append(1)
        return True
    monkeypatch.setattr(rainfall_api, "restart_rainfall_service", fake_restart)
    monkeypatch.setattr(settings_api, "_TEST_TRANSPORT", None)
    yield restarts


# ---------------------------------------------------------------- reading
@pytest.mark.asyncio
async def test_get_shows_state_without_any_secret(async_client: AsyncClient):
    st = (await async_client.get("/api/settings")).json()
    assert st["editing_enabled"] is True and "Mumbai" in st["cities"] and st["accumulation_modes"] == ["cumulative", "per_reading"]
    assert st["weather_union"]["enabled"] is False and st["weather_union"]["api_key_set"] is False and st["narrator"]["connected"] is False


@pytest.mark.asyncio
async def test_editing_is_disabled_without_an_admin_token_in_the_environment(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
    assert (await async_client.get("/api/settings")).json()["editing_enabled"] is False
    r = await async_client.put("/api/settings", json={"weather_union_city": "Mumbai"}, headers=H)
    assert r.status_code == 403 and "ADMIN_PASSWORD" in r.text
    assert (await async_client.post("/api/settings/feed/test", headers=H)).status_code == 403
    assert not Path(os.environ["RUNTIME_SETTINGS_PATH"]).exists()


@pytest.mark.asyncio
async def test_wrong_or_missing_token_is_refused_and_repeated_guessing_is_throttled(async_client: AsyncClient):
    assert (await async_client.put("/api/settings", json={"weather_union_city": "Mumbai"})).status_code == 401
    assert (await async_client.put("/api/settings", json={"weather_union_city": "Mumbai"}, headers={"X-Admin-Token": "x" * 32})).status_code == 401
    for _ in range(settings_api.MAX_FAILURES):
        await async_client.put("/api/settings", json={"weather_union_city": "Mumbai"}, headers={"X-Admin-Token": "nope"})
    blocked = await async_client.put("/api/settings", json={"weather_union_city": "Mumbai"}, headers=H)
    assert blocked.status_code == 429                                     # even the right token waits out the window
    assert not Path(os.environ["RUNTIME_SETTINGS_PATH"]).exists()


# ---------------------------------------------------------------- saving
@pytest.mark.asyncio
async def test_saving_the_feed_settings_applies_them_restarts_the_feed_and_never_echoes_the_key(async_client: AsyncClient, _isolated):
    r = await async_client.put("/api/settings", headers=H, json={
        "weather_union_api_key": KEY, "weather_union_city": "mumbai", "weather_union_poll_interval_seconds": 1200, "weather_union_accumulation_mode": "per_reading"})
    assert r.status_code == 200, r.text
    assert KEY not in r.text and KEY not in (await async_client.get("/api/settings")).text
    wu = r.json()["weather_union"]
    assert wu == {"api_key_set": True, "api_key_source": "runtime", "city": "Mumbai", "city_source": "runtime", "poll_interval_seconds": 1200.0,
                  "poll_interval_source": "runtime", "accumulation_mode": "per_reading", "accumulation_mode_source": "runtime", "enabled": True}
    assert sorted(r.json()["saved"]) == ["weather_union_accumulation_mode", "weather_union_api_key", "weather_union_city", "weather_union_poll_interval_seconds"]
    assert len(_isolated) == 1                                            # the feed was restarted once
    assert json.loads(Path(os.environ["RUNTIME_SETTINGS_PATH"]).read_text())["weather_union_api_key"] == KEY      # stored, just never returned


@pytest.mark.asyncio
async def test_saved_settings_build_the_feed_service_from_them():
    rs.save_update({"weather_union_api_key": KEY, "weather_union_city": "Mumbai", "weather_union_poll_interval_seconds": 1800.0,
                    "weather_union_accumulation_mode": "per_reading"})
    svc = rainfall_api.build_service_from_settings()                      # built, NOT started: nothing is polled
    try:
        assert svc is not None and svc.mode == "per_reading" and svc.interval >= 1800.0 and all(s.city == "Mumbai" for s in svc.stations.values())
    finally:
        await svc.client.aclose()
    rs.save_update({"weather_union_city": None})
    assert rainfall_api.build_service_from_settings() is None             # no city: the feed is off


@pytest.mark.asyncio
async def test_a_change_that_does_not_touch_the_feed_does_not_restart_it(async_client: AsyncClient, _isolated):
    r = await async_client.put("/api/settings", headers=H, json={"narrator_url": "https://narrator.example.org/explain", "narrator_token": "n" * 16})
    assert r.status_code == 200 and r.json()["narrator"] == {"url": "https://narrator.example.org/explain", "url_source": "runtime",
                                                                "token_set": True, "token_source": "runtime", "connected": True}
    assert _isolated == [] and "n" * 16 not in r.text


@pytest.mark.asyncio
async def test_clear_removes_an_override_and_the_environment_value_applies_again(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_UNION_CITY", "Pune")
    await async_client.put("/api/settings", headers=H, json={"weather_union_city": "Mumbai"})
    assert rs.effective().weather_union_city == "Mumbai"
    r = await async_client.put("/api/settings", headers=H, json={"clear": ["weather_union_city"]})
    assert r.json()["weather_union"]["city"] == "Pune" and r.json()["weather_union"]["city_source"] == "environment"


@pytest.mark.asyncio
async def test_a_feed_that_fails_to_restart_is_reported_not_a_500(async_client: AsyncClient, monkeypatch):
    async def boom():
        raise RuntimeError("x")
    monkeypatch.setattr(rainfall_api, "restart_rainfall_service", boom)
    r = await async_client.put("/api/settings", headers=H, json={"weather_union_city": "Mumbai"})
    assert r.status_code == 200 and "could not be restarted" in r.json()["feed_error"]


# ---------------------------------------------------------------- validation
@pytest.mark.asyncio
@pytest.mark.parametrize("body,msg", [
    ({"weather_union_city": "Atlantis"}, "unknown city"),
    ({"weather_union_poll_interval_seconds": 5}, "between"),
    ({"weather_union_poll_interval_seconds": 10 ** 9}, "between"),
    ({"weather_union_api_key": "short"}, "8 to 300"),
    ({"weather_union_api_key": "has a space in it 123"}, "no spaces"),
    ({"narrator_token": "bad\ntoken-1234567"}, "no spaces"),
    ({"narrator_url": "ftp://narrator.example.org"}, "http://"),
    ({"narrator_url": "file:///etc/passwd"}, "http://"),
    ({"narrator_url": "https://user:pw@narrator.example.org/x"}, "credentials"),
    ({"clear": ["admin_token"]}, "unknown setting"),
    ({}, "nothing to change"),
])
async def test_invalid_values_are_refused_and_nothing_is_saved(async_client: AsyncClient, body, msg):
    r = await async_client.put("/api/settings", headers=H, json=body)
    assert r.status_code == 422 and msg in r.text
    assert not Path(os.environ["RUNTIME_SETTINGS_PATH"]).exists()


@pytest.mark.asyncio
async def test_bad_accumulation_mode_is_refused(async_client: AsyncClient):
    assert (await async_client.put("/api/settings", headers=H, json={"weather_union_accumulation_mode": "daily"})).status_code == 422


@pytest.mark.parametrize("url", ["http://127.0.0.1:9000/x", "http://localhost/x", "http://10.0.0.5/x", "http://169.254.169.254/latest/meta-data",
                                 "http://192.168.1.10:8080", "http://[::1]/x", "http://0.0.0.0/x"])
def test_private_loopback_and_metadata_addresses_are_blocked_by_default(url):
    with pytest.raises(rs.SettingsError, match="private or reserved"):
        rs.check_narrator_url(url, allow_private=False)
    assert rs.check_narrator_url(url, allow_private=True) == url         # the explicit opt-in works


@pytest.mark.asyncio
async def test_the_private_address_guard_applies_to_the_api(async_client: AsyncClient, monkeypatch):
    monkeypatch.delenv("NARRATOR_ALLOW_PRIVATE")
    r = await async_client.put("/api/settings", headers=H, json={"narrator_url": "http://169.254.169.254/latest"})
    assert r.status_code == 422 and "NARRATOR_ALLOW_PRIVATE" in r.text and not Path(os.environ["RUNTIME_SETTINGS_PATH"]).exists()


def test_a_corrupt_settings_file_counts_as_no_overrides():
    Path(os.environ["RUNTIME_SETTINGS_PATH"]).write_text("{not json")
    assert rs.load_overrides() == {} and rs.effective().sources["weather_union_city"] == "unset"
    Path(os.environ["RUNTIME_SETTINGS_PATH"]).write_text(json.dumps({"admin_token": "x", "weather_union_city": "Mumbai"}))
    assert rs.load_overrides() == {"weather_union_city": "Mumbai"}       # unknown fields are ignored


# ---------------------------------------------------------------- narrator picks the saved URL up
@pytest.mark.asyncio
async def test_the_narrator_status_follows_the_saved_url(async_client: AsyncClient):
    assert (await async_client.get("/api/validation/narrator")).json()["connected"] is False
    await async_client.put("/api/settings", headers=H, json={"narrator_url": "https://narrator.example.org/explain"})
    st = (await async_client.get("/api/validation/narrator")).json()
    assert st["connected"] is True and st["host"] == "narrator.example.org"
    await async_client.put("/api/settings", headers=H, json={"clear": ["narrator_url"]})
    assert (await async_client.get("/api/validation/narrator")).json()["connected"] is False


# ---------------------------------------------------------------- feed test (mocked transport, one call)
def _wu_payload(intensity=0.0, accum=0.0):
    return {"status": "200", "device_type": 2, "locality_weather_data": {"rain_intensity": intensity, "rain_accumulation": accum}}


@pytest.mark.asyncio
async def test_feed_test_needs_a_key_and_a_city_first(async_client: AsyncClient):
    r = await async_client.post("/api/settings/feed/test", headers=H)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_feed_test_reports_a_working_key_with_one_call_and_never_leaks_it(async_client: AsyncClient, monkeypatch):
    rs.save_update({"weather_union_api_key": KEY, "weather_union_city": "Mumbai"})
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.headers.get("x-zomato-api-key"), req.url.params["locality_id"]))
        return httpx.Response(200, json=_wu_payload(0.0, 0.0))
    monkeypatch.setattr(settings_api, "_TEST_TRANSPORT", httpx.MockTransport(handler))
    r = await async_client.post("/api/settings/feed/test", headers=H)
    assert r.status_code == 200 and r.json()["ok"] is True and "key works" in r.json()["message"]
    assert len(seen) == 1 and seen[0][0] == KEY                          # exactly one call, with the saved key
    assert KEY not in r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("make,msg", [
    (lambda r: httpx.Response(401), "rejected"), (lambda r: httpx.Response(403), "rejected"), (lambda r: httpx.Response(500), "HTTP 500"),
    (lambda r: httpx.Response(200, json={"status": "400"}), "reported an error"),
])
async def test_feed_test_failures_are_explained(async_client: AsyncClient, monkeypatch, make, msg):
    rs.save_update({"weather_union_api_key": KEY, "weather_union_city": "Mumbai"})
    monkeypatch.setattr(settings_api, "_TEST_TRANSPORT", httpx.MockTransport(make))
    r = await async_client.post("/api/settings/feed/test", headers=H)
    assert r.status_code == 200 and r.json()["ok"] is False and msg in r.json()["message"] and KEY not in r.text


@pytest.mark.asyncio
async def test_feed_test_network_error_is_reported(async_client: AsyncClient, monkeypatch):
    rs.save_update({"weather_union_api_key": KEY, "weather_union_city": "Mumbai"})

    def boom(req):
        raise httpx.ConnectTimeout("t")
    monkeypatch.setattr(settings_api, "_TEST_TRANSPORT", httpx.MockTransport(boom))
    r = await async_client.post("/api/settings/feed/test", headers=H)
    assert r.json()["ok"] is False and "could not reach" in r.json()["message"]
