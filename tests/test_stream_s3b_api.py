"""Slice S3b through the app: the real sources registered with the manager (mocked transports only), select/start/stop, the virtual packet, the
external point and preview, the stream settings (validation, write-only secrets, restarts) and the admin gate. Storage is the throwaway SQLite
database of tests/conftest.py; the real APIs and brokers are never called."""
import asyncio
import collections
import json

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from backend.app.config import settings
from backend.app.api import settings as settings_api
from backend.app.db import database
from backend.app.rainfall.catalog import load_catalog
from backend.app.stream import control, runtime
from backend.app.stream.esp32 import Esp32Source
from backend.app.stream.manager import StreamManager
from backend.app.stream.models import StreamEvent, StreamReadingRow
from backend.app.stream.open_meteo import OpenMeteoSource
from backend.app.stream.service import ReadingProcessor
from backend.app.stream.simulator import SimulatorSource
from backend.app.stream.wu_source import WeatherUnionSource
from tests.test_stream_sources import FakeTransport, OmServer, WuServer, wu_answer

TOKEN = "t" * 32
H = {"X-Admin-Token": TOKEN}
PASSWORD = "mqtt-pass-s3cret-xyz"


async def until(check, timeout=8.0):
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        got = await check()
        if got:
            return got
        await asyncio.sleep(0.03)
    raise AssertionError("condition not reached in time")


async def stored(source=None):
    async with database.async_session_factory() as s:
        q = select(StreamReadingRow).order_by(StreamReadingRow.id)
        if source:
            q = q.where(StreamReadingRow.source == source)
        return list((await s.execute(q)).scalars())


class Env:
    pass


@pytest_asyncio.fixture
async def env(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(tmp_path / "rt.json"))
    for name, value in (("ADMIN_TOKEN", TOKEN), ("WEATHER_UNION_API_KEY", "k" * 12), ("WEATHER_UNION_CITY", ""), ("WEATHER_PROVIDER", "weather_union"),
                        ("MQTT_HOST", ""), ("MQTT_PASSWORD", "")):
        monkeypatch.setattr(settings, name, value)
    monkeypatch.delenv("MQTT_ALLOW_PRIVATE", raising=False)
    settings_api._failures.clear()
    async with database.async_session_factory() as s:
        await s.execute(delete(StreamEvent))
        await s.execute(delete(StreamReadingRow))
        await s.commit()
    e = Env()
    e.om = OmServer()
    e.wu = WuServer(collections.defaultdict(lambda: wu_answer(22.0, 70.0, acc=0.0, inten=0.0)))
    FakeTransport.instances = []
    m = StreamManager(processor=ReadingProcessor(), watch_interval_s=0.05)
    m.register(SimulatorSource(interval_seconds=0.05))
    m.register(OpenMeteoSource(transport=e.om.transport()))
    m.register(WeatherUnionSource(client_factory=lambda key: (e.wu.client(), True)))
    m.register(Esp32Source(transport_factory=FakeTransport, retry_s=0.05))
    control.configure_sources(m)
    runtime.set_manager(m)
    e.manager = m
    yield e
    await m.shutdown()
    runtime.set_manager(None)


def entry(body, source_id):
    return next(s for s in body["sources"] if s["source_id"] == source_id)


# ---------------------------------------------------------------------------------------------------- listing and selecting
@pytest.mark.asyncio
async def test_all_four_sources_are_listed_as_available(async_client: AsyncClient, env):
    body = (await async_client.get("/api/data-sources")).json()
    types = {s["source_type"]: s for s in body["sources"]}
    assert set(types) == {"SIMULATED", "EXTERNAL_API", "WEATHER_UNION", "PHYSICAL_AWS"} and all(s["is_available"] for s in types.values())
    assert "MODEL ESTIMATES" in types["EXTERNAL_API"]["description"] and "NOT verified" in types["PHYSICAL_AWS"]["description"]
    assert entry(body, "open_meteo")["metadata"]["station_set"] == {"mode": "city", "city": "Bengaluru", "cap": 5}
    assert len(entry(body, "open_meteo")["metadata"]["station_ids"]) == 5 and body["active_source"] is None


@pytest.mark.asyncio
async def test_selecting_open_meteo_stores_model_estimates_with_source_open_meteo(async_client: AsyncClient, env):
    r = await async_client.post("/api/data-sources/select", json={"source_type": "EXTERNAL_API"}, headers=H)
    assert r.status_code == 200 and r.json()["is_active"] and r.json()["metadata"]["model_estimates"] is True
    rows = await until(lambda: _rows("open_meteo", 5))
    assert {x.source for x in rows} == {"open_meteo"}
    assert all(x.temperature_c == 24.1 and x.rain_mm is None for x in rows), [(x.temperature_c, x.rain_mm, x.check_status) for x in rows]
    assert len(env.om.requests) == 1                                  # ONE multi-location request for the five stations
    st = (await async_client.get("/api/data-sources/status")).json()
    assert st["source_id"] == "open_meteo" and st["status"] == "RUNNING" and st["packet_count"] == 5 and len(st["metadata"]["station_ids"]) == 5
    obs = (await async_client.get("/api/observations", params={"station_id": rows[0].station_id})).json()["items"][0]
    assert obs["source"] == "open_meteo" and obs["pressure"] == 912.4
    stopped = await async_client.post("/api/simulation/stop", headers=H)                  # stopping the simulator never touches another source
    assert stopped.status_code == 200 and env.manager.active.source_id == "open_meteo"


async def _rows(source, n):
    rows = await stored(source)
    return rows if len(rows) >= n else None


@pytest.mark.asyncio
async def test_a_failing_open_meteo_is_disconnected_in_the_api_and_stores_nothing(async_client: AsyncClient, env):
    env.om.status = 500
    await async_client.post("/api/data-sources/select", json={"source_type": "EXTERNAL_API"}, headers=H)

    async def down():
        st = (await async_client.get("/api/data-sources/status")).json()
        return st if st["status"] == "DISCONNECTED" else None
    st = await until(down)
    assert "boom" in st["error_message"] and st["packet_count"] == 0 and await stored("open_meteo") == []


@pytest.mark.asyncio
async def test_selecting_weather_union_stores_only_the_fields_the_answers_hold(async_client: AsyncClient, env):
    r = await async_client.post("/api/data-sources/select", json={"source_type": "WEATHER_UNION"}, headers=H)
    assert r.status_code == 200
    rows = await until(lambda: _rows("weather_union", 5))
    assert all(x.temperature_c == 22.0 and x.humidity_pct == 70.0 and x.pressure_hpa is None and x.source == "weather_union" for x in rows)
    assert len(env.wu.requests) == 5
    st = (await async_client.get("/api/data-sources/status")).json()
    assert st["metadata"]["calls_used_today"] >= 0 and st["metadata"]["daily_call_budget"] == 900


@pytest.mark.asyncio
async def test_weather_union_without_a_key_does_not_start(async_client: AsyncClient, env, monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_UNION_API_KEY", "")
    control.configure_sources(env.manager)
    r = await async_client.post("/api/data-sources/select", json={"source_type": "WEATHER_UNION"}, headers=H)
    assert r.status_code == 502 and "key" in r.json()["detail"]


# ---------------------------------------------------------------------------------------------------- ESP32 and the virtual packet
@pytest.mark.asyncio
async def test_virtual_packet_needs_the_esp32_source_running_then_stores_a_reading_as_esp32(async_client: AsyncClient, env):
    packet = {"station_id": "ESP32-001", "temperature_c": 27.5, "humidity_pct": None, "pressure_hpa": 1004.0}
    r = await async_client.post("/api/data-sources/physical/virtual-packet", json=packet, headers=H)
    assert r.status_code == 409                                                       # nothing selected
    assert (await async_client.post("/api/data-sources/select", json={"source_type": "PHYSICAL_AWS"}, headers=H)).status_code == 200
    r = await async_client.post("/api/data-sources/physical/virtual-packet", json=packet, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] and r.json()["source"] == "esp32" and r.json()["verified_on_real_device"] is False
    row = (await stored("esp32"))[0]
    assert (row.station_id, row.temperature_c, row.humidity_pct, row.pressure_hpa) == ("ESP32-001", 27.5, None, 1004.0)
    assert (await async_client.post("/api/data-sources/physical/virtual-packet", json={"station_id": "ESP32-001"}, headers=H)).status_code == 422
    assert (await async_client.post("/api/data-sources/physical/virtual-packet", json={"station_id": "X", "temperature_c": 1}, headers=H)).status_code == 404
    st = (await async_client.get("/api/data-sources/status")).json()
    assert st["metadata"]["virtual_packets"] == 1 and st["metadata"]["mqtt"]["configured"] is False and st["metadata"]["verified_on_real_device"] is False


@pytest.mark.asyncio
async def test_esp32_over_the_fake_transport_through_the_api(async_client: AsyncClient, env):
    r = await async_client.put("/api/settings", headers=H, json={"stream_mqtt_host": "93.184.216.34", "stream_mqtt_username": "dev",
                                                                 "stream_mqtt_password": PASSWORD, "stream_esp32_station_ids": ["ESP32-009"]})
    assert r.status_code == 200, r.text
    await async_client.post("/api/data-sources/select", json={"source_type": "PHYSICAL_AWS"}, headers=H)
    await until(lambda: _fake_ready())
    t = FakeTransport.instances[0]
    assert t.connected_with == ("93.184.216.34", 1883, "dev", PASSWORD, False)
    t.deliver("skyguard/aws/ESP32-009/telemetry", {"temperature_c": 19.0, "humidity_pct": 80.0})
    rows = await until(lambda: _rows("esp32", 1))
    assert rows[0].station_id == "ESP32-009" and rows[0].pressure_hpa is None


async def _fake_ready():
    return bool(FakeTransport.instances and FakeTransport.instances[0].filters)


# ---------------------------------------------------------------------------------------------------- the admin gate
@pytest.mark.asyncio
@pytest.mark.parametrize("method,url,body", [
    ("post", "/api/data-sources/select", {"source_type": "EXTERNAL_API"}),
    ("post", "/api/data-sources/physical/virtual-packet", {"temperature_c": 1}),
    ("post", "/api/data-sources/external/configure", {"latitude": 1.0, "longitude": 2.0}),
    ("get", "/api/data-sources/external/preview", None),
])
async def test_changing_or_calling_a_source_needs_the_admin_sign_in(async_client: AsyncClient, env, method, url, body):
    kw = {"json": body} if body is not None else {}
    assert (await getattr(async_client, method)(url, **kw)).status_code == 401
    assert (await getattr(async_client, method)(url, headers={"X-Admin-Token": "wrong" * 8}, **kw)).status_code == 401
    assert env.om.requests == [] and env.wu.requests == []                          # nothing was called


# ---------------------------------------------------------------------------------------------------- external point and preview
@pytest.mark.asyncio
async def test_external_configure_sets_the_open_meteo_point_and_restarts_the_running_source(async_client: AsyncClient, env):
    await async_client.post("/api/data-sources/select", json={"source_type": "EXTERNAL_API"}, headers=H)
    await until(lambda: _rows("open_meteo", 5))
    before = len(env.om.requests)
    body = {"latitude": 18.5204, "longitude": 73.8567, "station_id": "PUNE-EXT-001", "station_name": "Pune"}
    r = await async_client.post("/api/data-sources/external/configure", json=body, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["metadata"]["station_ids"] == ["PUNE-EXT-001"] and r.json()["coordinates"] == {"latitude": 18.5204, "longitude": 73.8567}
    assert r.json()["metadata"]["station_set"] == {"mode": "point", "station_id": "PUNE-EXT-001"}
    await until(lambda: _rows("open_meteo", 6))
    last = env.om.requests[-1].url.params
    assert len(env.om.requests) > before and last["latitude"] == "18.5204" and last["longitude"] == "73.8567"
    stations = (await async_client.get("/api/stations/PUNE-EXT-001")).json()
    assert stations["name"] == "Pune" and stations["latitude"] == 18.5204
    clash = next(iter(load_catalog()))
    assert (await async_client.post("/api/data-sources/external/configure", headers=H,
                                    json={"latitude": 1.0, "longitude": 2.0, "station_id": clash})).status_code == 422
    assert (await async_client.post("/api/data-sources/external/configure", headers=H, json={"latitude": 91.0, "longitude": 2.0})).status_code == 422


@pytest.mark.asyncio
async def test_external_preview_makes_one_call_for_one_station_and_stores_nothing(async_client: AsyncClient, env):
    r = await async_client.get("/api/data-sources/external/preview", headers=H)
    assert r.status_code == 200, r.text
    t = r.json()["telemetry"]
    assert r.json()["success"] and len(env.om.requests) == 1 and len(env.om.requests[0].url.params["latitude"].split(",")) == 1
    assert (t["temperature"], t["humidity"], t["pressure"], t["source"], t["model_estimate"]) == (24.1, 61.0, 912.4, "open_meteo", True)
    assert await stored() == []
    env.om.status = 500
    assert (await async_client.get("/api/data-sources/external/preview", headers=H)).status_code == 502


# ---------------------------------------------------------------------------------------------------- settings
@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"stream_active_source": "accuweather"},
    {"stream_station_mode": "nearby"},
    {"stream_city": "Atlantis"},
    {"stream_station_ids": ["ZWL005764", "NOT-A-STATION"]},
    {"stream_station_cap": 0},
    {"stream_station_cap": 51},
    {"stream_open_meteo_interval_seconds": 10},
    {"stream_open_meteo_interval_seconds": 10**7},
    {"stream_weather_union_interval_seconds": 5},
    {"stream_simulator_interval_seconds": 0.001},
    {"stream_esp32_interval_seconds": 100000},
    {"stream_mqtt_host": "127.0.0.1"},
    {"stream_mqtt_host": "mqtt://broker.example"},
    {"stream_mqtt_host": "10.1.2.3"},
    {"stream_mqtt_port": 70000},
    {"stream_mqtt_topic_prefix": "skyguard/#"},
    {"stream_mqtt_password": "bad\npassword"},
    {"stream_esp32_station_ids": ["bad id"]},
    {"stream_esp32_station_ids": ["KTLX"]},
    {"stream_esp32_latitude": 120},
])
async def test_stream_settings_validation(async_client: AsyncClient, env, payload):
    r = await async_client.put("/api/settings", headers=H, json=payload)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_a_private_mqtt_host_is_allowed_only_with_the_environment_opt_in(async_client: AsyncClient, env, monkeypatch):
    assert (await async_client.put("/api/settings", headers=H, json={"stream_mqtt_host": "192.168.1.20"})).status_code == 422
    monkeypatch.setenv("MQTT_ALLOW_PRIVATE", "true")
    r = await async_client.put("/api/settings", headers=H, json={"stream_mqtt_host": "192.168.1.20"})
    assert r.status_code == 200 and r.json()["stream"]["mqtt"]["host"] == "192.168.1.20"


@pytest.mark.asyncio
async def test_the_mqtt_password_is_write_only(async_client: AsyncClient, env):
    r = await async_client.put("/api/settings", headers=H, json={"stream_mqtt_password": PASSWORD, "stream_mqtt_username": "dev"})
    assert r.status_code == 200
    for text in (r.text, (await async_client.get("/api/settings")).text, (await async_client.get("/api/data-sources")).text,
                 (await async_client.get("/api/data-sources/status")).text if env.manager.active else ""):
        assert PASSWORD not in text
    mq = (await async_client.get("/api/settings")).json()["stream"]["mqtt"]
    assert mq["password_set"] is True and mq["password_origin"] == "runtime" and "password" not in mq and mq["username"] == "dev"
    r = await async_client.put("/api/settings", headers=H, json={"clear": ["stream_mqtt_password"]})
    assert r.json()["stream"]["mqtt"]["password_set"] is False
    assert (await async_client.put("/api/settings", json={"stream_mqtt_password": PASSWORD})).status_code == 401      # writing needs the admin


@pytest.mark.asyncio
async def test_station_set_modes_city_ids_and_all(async_client: AsyncClient, env):
    r = await async_client.put("/api/settings", headers=H, json={"stream_station_mode": "city", "stream_city": "mumbai", "stream_station_cap": 3})
    assert r.json()["stream"]["station_set"]["city"] == "Mumbai"
    ids = [i for i in entry((await async_client.get("/api/data-sources")).json(), "open_meteo")["metadata"]["station_ids"]]
    assert len(ids) == 3 and all(load_catalog()[i].city == "Mumbai" for i in ids)
    r = await async_client.put("/api/settings", headers=H, json={"stream_station_mode": "ids", "stream_station_ids": ["ZWL005764", "KTLX"]})
    assert r.status_code == 200, r.text
    body = (await async_client.get("/api/data-sources")).json()
    assert entry(body, "open_meteo")["metadata"]["station_ids"] == ["ZWL005764", "KTLX"]       # a catalogue gauge and a simulator station
    assert entry(body, "weather_union")["metadata"]["station_ids"] == ["ZWL005764"]             # Weather Union only has its own gauges
    await async_client.put("/api/settings", headers=H, json={"stream_station_mode": "all"})
    body = (await async_client.get("/api/data-sources")).json()
    assert len(entry(body, "weather_union")["metadata"]["station_ids"]) == len(load_catalog())
    r = await async_client.post("/api/data-sources/select", json={"source_type": "EXTERNAL_API"}, headers=H)
    assert r.status_code == 502 and "more than one Open-Meteo request" in r.json()["detail"]    # too many for one request: refused, not truncated
    assert env.om.requests == []


@pytest.mark.asyncio
async def test_changing_a_setting_restarts_the_active_source_and_the_status_reports_it(async_client: AsyncClient, env):
    await async_client.post("/api/data-sources/select", json={"source_type": "EXTERNAL_API"}, headers=H)
    await until(lambda: _rows("open_meteo", 5))
    st = (await async_client.get("/api/settings")).json()["stream"]["status"]
    assert st["source_id"] == "open_meteo" and st["state"] == "running" and st["expected_interval_seconds"] == 900.0
    before = len(env.om.requests)
    r = await async_client.put("/api/settings", headers=H, json={"stream_station_mode": "city", "stream_city": "Mumbai", "stream_station_cap": 2,
                                                                 "stream_open_meteo_interval_seconds": 600})
    assert r.status_code == 200 and "stream_error" not in r.json()
    assert r.json()["stream"]["status"]["expected_interval_seconds"] == 600.0 and r.json()["stream"]["status"]["state"] == "running"
    await until(lambda: asyncio.sleep(0, len(env.om.requests) > before))
    ids = (await async_client.get("/api/data-sources/status")).json()["metadata"]["station_ids"]
    assert len(ids) == 2 and all(load_catalog()[i].city == "Mumbai" for i in ids)
    assert len(env.om.requests[-1].url.params["latitude"].split(",")) == 2                       # the restart used the new station set


@pytest.mark.asyncio
async def test_the_active_source_setting_selects_and_clearing_it_stops(async_client: AsyncClient, env):
    r = await async_client.put("/api/settings", headers=H, json={"stream_active_source": "esp32"})
    assert r.status_code == 200 and r.json()["stream"]["active_source"] == "esp32" and env.manager.active.source_id == "esp32"
    assert r.json()["stream"]["status"]["source_id"] == "esp32"
    r = await async_client.put("/api/settings", headers=H, json={"stream_active_source": ""})
    assert r.json()["stream"]["active_source"] == "" and env.manager.status().state == "stopped"
    r = await async_client.put("/api/settings", headers=H, json={"stream_active_source": "weather_union"})
    assert r.status_code == 200 and env.manager.active.source_id == "weather_union"


@pytest.mark.asyncio
async def test_autostart_starts_the_simulator_when_nothing_is_saved(env, monkeypatch):
    monkeypatch.setattr(settings, "STREAM_AUTOSTART_SIMULATOR", True)
    assert await control.autostart(env.manager) is None
    assert env.manager.active is not None and env.manager.active.source_id == "simulator"


@pytest.mark.asyncio
async def test_autostart_starts_only_a_saved_active_source(env, monkeypatch):
    assert await control.autostart(env.manager) is None and env.manager.active is None            # nothing saved: nothing starts
    import backend.app.runtime_settings as rs
    rs.save_update({"stream_active_source": "esp32"})
    await control.autostart(env.manager)
    assert env.manager.active.source_id == "esp32" and env.manager.status().state == "running"
    rs.save_update({"stream_active_source": "weather_union"})
    monkeypatch.setattr(settings, "WEATHER_UNION_API_KEY", "")
    control.configure_sources(env.manager)
    assert "key" in (await control.autostart(env.manager) or "")                                  # a start that fails is reported, not raised


@pytest.mark.asyncio
async def test_settings_keep_working_for_the_existing_fields(async_client: AsyncClient, env):
    r = await async_client.put("/api/settings", headers=H, json={"weather_union_city": "Pune"})
    assert r.status_code == 200 and r.json()["weather_union"]["city"] == "Pune"
    doc = json.loads(open(__import__("os").environ["RUNTIME_SETTINGS_PATH"], encoding="utf-8").read())
    assert doc == {"weather_union_city": "Pune"}
