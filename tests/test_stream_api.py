"""Telemetry stream through the app (slice S3a): stations, observations, anomalies, data sources, simulation control and the /ws/live WebSocket, with
storage in the throwaway test database (tests/conftest.py pins SQLite) and the sign-in. The simulator is the only real source here, seeded and fast;
rain readings are pushed through the real processor by hand (the simulator has no rain)."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.api import auth as auth_api
from backend.app.config import settings
from backend.app.db import database
from backend.app.main import app
from backend.app.rainfall.catalog import load_catalog
from backend.app.stream import runtime
from backend.app.stream.manager import StreamManager
from backend.app.stream.models import StreamEvent, StreamReadingRow
from backend.app.stream.service import ReadingProcessor
from backend.app.stream.sim_physics import SIM_STATIONS
from backend.app.stream.simulator import SimulatorSource
from backend.app.stream.types import StreamReading
from tests.test_stream_fakes import FakeSource

EMAIL, PW = "admin@admin.com", "admin"
FAST = {"interval_seconds": 0.05, "noise_level": 0.0}


def fast_manager() -> StreamManager:
    m = StreamManager(processor=ReadingProcessor(), watch_interval_s=0.05)
    m.register(SimulatorSource(interval_seconds=0.05))
    return m


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
    monkeypatch.setattr(settings, "ADMIN_EMAIL", EMAIL)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", PW)
    auth_api._sessions.clear()
    auth_api._failures.clear()
    auth_api._token_failures.clear()


@pytest_asyncio.fixture
async def manager():
    async with database.async_session_factory() as s:
        await s.execute(delete(StreamEvent))
        await s.execute(delete(StreamReadingRow))
        await s.commit()
    m = fast_manager()
    runtime.set_manager(m)
    yield m
    await m.shutdown()
    runtime.set_manager(None)


async def admin_headers(c: AsyncClient):
    r = await c.post("/api/auth/login", json={"email": EMAIL, "password": PW})
    assert r.status_code == 200
    return {"X-Admin-Token": r.json()["token"]}


async def wait_until(check, timeout=8.0):
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        got = await check()
        if got:
            return got
        await asyncio.sleep(0.03)
    raise AssertionError("condition not reached in time")


async def stored(station=None):
    async with database.async_session_factory() as s:
        q = select(StreamReadingRow).order_by(StreamReadingRow.timestamp)
        if station:
            q = q.where(StreamReadingRow.station_id == station)
        return list((await s.execute(q)).scalars())


# ---------------------------------------------------------------------------------------------------- stations
@pytest.mark.asyncio
async def test_station_list_merges_the_gauge_catalogue_and_simulator_stations_with_no_label(async_client: AsyncClient, manager):
    body = (await async_client.get("/api/stations")).json()
    n_gauges = len(load_catalog())
    assert body["total"] == len(body["items"]) == n_gauges + len(SIM_STATIONS)
    by_id = {s["station_id"]: s for s in body["items"]}
    sim, gauge = by_id["KTLX"], by_id[next(iter(load_catalog()))]
    assert set(sim) == set(gauge)                                              # same shape: nothing marks a simulated station
    assert not any("source" in s or "simulated" in str(s).lower() or "synthetic" in str(s).lower() for s in (sim, gauge))
    assert sim["name"] == "Oklahoma City, OK" and sim["elevation"] == 370.0 and gauge["elevation"] is None   # an unknown elevation stays unknown
    assert len({s["id"] for s in body["items"]}) == len(body["items"])
    assert body["items"][-1]["station_id"] == SIM_STATIONS[-1].station_id
    assert (await async_client.get("/api/stations?status=active")).json()["total"] == 0      # nothing has reported yet
    one = await async_client.get("/api/stations/KOKX")
    assert one.status_code == 200 and one.json()["station_id"] == "KOKX" and one.json()["latitude"] == pytest.approx(40.8656)
    assert (await async_client.get("/api/stations/NOPE")).status_code == 404


# ---------------------------------------------------------------------------------------------------- data sources
@pytest.mark.asyncio
async def test_data_source_list_status_and_select(async_client: AsyncClient, manager):
    h = await admin_headers(async_client)
    d = (await async_client.get("/api/data-sources")).json()
    assert d["active_source"] is None and d["active_source_id"] is None            # nothing is selected until someone selects it
    by_type = {s["source_type"]: s for s in d["sources"]}
    assert by_type["SIMULATED"]["is_available"] is True and by_type["SIMULATED"]["status"] == "STOPPED"
    for t in ("EXTERNAL_API", "WEATHER_UNION", "PHYSICAL_AWS"):
        assert by_type[t]["is_available"] is False and "NOT IMPLEMENTED" in by_type[t]["description"] and by_type[t]["status"] == "STOPPED"
    assert (await async_client.get("/api/data-sources/status")).status_code == 404

    assert (await async_client.post("/api/data-sources/select", json={"source_type": "SIMULATED"})).status_code == 401      # a change needs the admin
    assert (await async_client.post("/api/data-sources/select", json={"source_type": "WEATHER_UNION"}, headers=h)).status_code == 501
    assert (await async_client.post("/api/data-sources/select", json={"source_type": "NOPE"}, headers=h)).status_code == 422
    r = await async_client.post("/api/data-sources/select", json={"source_type": "SIMULATED"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "RUNNING" and r.json()["is_active"] is True and r.json()["source_id"] == "simulator"
    d = (await async_client.get("/api/data-sources")).json()
    assert d["active_source"] == "SIMULATED" and (await async_client.get("/api/data-sources/status")).json()["is_active"] is True


# ---------------------------------------------------------------------------------------------------- simulation, storage, injection
@pytest.mark.asyncio
async def test_start_stream_store_inject_and_stop(async_client: AsyncClient, manager):
    h = await admin_headers(async_client)
    assert (await async_client.post("/api/simulation/start", json=FAST)).status_code == 401           # no admin session
    assert (await async_client.post("/api/simulate/inject", json={"anomaly_type": "SPIKE"})).status_code == 401
    assert (await async_client.post("/api/simulate/inject", json={"anomaly_type": "SPIKE"}, headers=h)).status_code == 409   # not running yet
    assert (await async_client.get("/api/simulation/status")).json()["running"] is False

    bad = await async_client.post("/api/simulation/start", json={**FAST, "station_ids": ["KTLX", "NOPE"]}, headers=h)
    assert bad.status_code == 404 and "NOPE" in bad.json()["detail"]
    assert (await async_client.post("/api/simulation/start", json={**FAST, "scenario": "monsoon"}, headers=h)).status_code == 422

    r = await async_client.post("/api/simulation/start", json={**FAST, "station_ids": ["KTLX", "KOKX"]}, headers=h)
    assert r.status_code == 200 and r.json()["running"] is True and r.json()["active_stations"] == ["KTLX", "KOKX"]
    again = await async_client.post("/api/simulate/start", json=FAST, headers=h)                      # the original path still works
    assert again.json()["running"] is True and "already" in again.json()["message"]

    async def two_each():
        rows = await stored()
        return rows if sum(r.station_id == "KTLX" for r in rows) >= 3 and sum(r.station_id == "KOKX" for r in rows) >= 3 else None
    await wait_until(two_each)
    obs = (await async_client.get("/api/observations?station_id=KTLX&limit=5")).json()
    assert obs["total"] >= 3 and len(obs["items"]) <= 5
    first = obs["items"][0]
    assert first["source"] == "simulator" and first["station_id"] == "KTLX" and isinstance(first["temperature"], float)
    assert first["rain_mm"] is None and first["validation_status"] == "NO_CHECKS" and first["rule_score"] is None and first["injected_fault"] is None
    ts = [o["timestamp"] for o in obs["items"]]
    assert ts == sorted(ts, reverse=True)                                                              # newest first
    st = (await async_client.get("/api/stations?status=active")).json()
    assert {s["station_id"] for s in st["items"]} == {"KTLX", "KOKX"}                                  # active means a reading was stored

    inj = await async_client.post("/api/simulate/inject", json={"anomaly_type": "SPIKE", "station_id": "KTLX", "parameter": "temperature",
                                                                 "magnitude": 25.0, "duration_steps": 2}, headers=h)
    assert inj.status_code == 200 and inj.json()["success"] is True and inj.json()["injection_id"]
    assert (await async_client.post("/api/simulate/inject", json={"anomaly_type": "SPIKE", "station_id": "KATX"}, headers=h)).status_code == 404
    assert (await async_client.post("/api/simulate/inject", json={"anomaly_type": "TELEPORT"}, headers=h)).status_code == 422

    async def spiked():
        return [r for r in await stored("KTLX") if r.injected_fault == "SPIKE"] or None
    hit = await wait_until(spiked)
    rows = await stored("KTLX")
    clean = [r.temperature_c for r in rows if r.injected_fault is None]
    assert hit[0].temperature_c - clean[-1] > 15.0                       # the spike is in the stored raw value, as sent
    assert all(r.injected_fault is None for r in await stored("KOKX"))   # only the targeted station

    # no checks exist for temperature, pressure and humidity: no detection and no score, however big the spike
    assert (await async_client.get("/api/anomalies")).json()["total"] == 0
    stats = (await async_client.get("/api/anomalies/stats")).json()
    assert stats["total_anomalies"] == 0 and stats["meteorological_extremes"] == 0 and stats["sensor_faults"] == 0
    assert (await async_client.get("/api/anomalies/alerts/active")).json() == []
    assert all(r.check_status == "NO_CHECKS" and r.rule_score is None for r in await stored())

    s = await async_client.post("/api/simulation/stop", headers=h)
    assert s.json()["running"] is False
    n = len(await stored())
    await asyncio.sleep(0.3)
    assert len(await stored()) == n                                       # stopped: no more readings, nothing fabricated for the gap
    assert (await async_client.get("/api/data-sources")).json()["sources"][0]["status"] == "STOPPED"


@pytest.mark.asyncio
async def test_injection_never_affects_another_source(async_client: AsyncClient, manager):
    h = await admin_headers(async_client)
    other = FakeSource("other")
    manager.register(other)
    await manager.select("other")                                         # a different source is the active one
    r = await async_client.post("/api/simulate/inject", json={"anomaly_type": "SPIKE", "station_id": "KTLX"}, headers=h)
    assert r.status_code == 409 and "not the running source" in r.json()["detail"]
    assert manager.source("simulator").pending_injections == 0
    st = (await async_client.get("/api/simulation/status")).json()
    assert st["running"] is False


@pytest.mark.asyncio
async def test_starting_the_simulator_replaces_the_active_source(async_client: AsyncClient, manager):
    h = await admin_headers(async_client)
    other = FakeSource("other")
    manager.register(other)
    await manager.select("other")
    r = await async_client.post("/api/simulation/start", json=FAST, headers=h)
    assert r.json()["running"] is True and other.state == "stopped" and manager.active.source_id == "simulator"
    await async_client.post("/api/simulation/stop", headers=h)


# ---------------------------------------------------------------------------------------------------- rainfall through the stream
@pytest.mark.asyncio
async def test_rain_readings_are_checked_stored_raw_and_flagged_only_when_a_check_fires(async_client: AsyncClient, manager):
    proc = ReadingProcessor()
    t = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    good = await proc(StreamReading("RG-1", t, "fake", rain_mm=0.4))
    assert good["validation_status"] == "OK" and good["checks_run"] is True and good["is_anomaly"] is False and good["stored"] is True
    bad = await proc(StreamReading("RG-1", t + timedelta(minutes=5), "fake", temperature_c=21.0, rain_mm=-3.0))
    assert bad["validation_status"] == "SUSPECT" and bad["is_anomaly"] is True and bad["is_fault"] is True and bad["classification"] == "negative_value"
    assert {"temperature", "neighbour"} <= {n["check"] for n in bad["not_run"]}      # the temperature check does not exist yet and says so
    await proc(StreamReading("RG-1", t + timedelta(minutes=10), "fake", rain_mm=0.0))

    raw = [r for r in await stored("RG-1")]
    assert [r.rain_mm for r in raw] == [0.4, -3.0, 0.0]                                # the impossible value is stored as sent
    assert [r.check_status for r in raw] == ["OK", "SUSPECT", "OK"]

    obs = (await async_client.get("/api/observations?station_id=RG-1")).json()["items"]
    assert {o["validation_status"] for o in obs} == {"QC_PASSED", "QC_FLAGGED"}
    an = (await async_client.get("/api/anomalies?station_id=RG-1")).json()
    assert an["total"] == 1 and an["page"] == 1
    ev = an["items"][0]
    assert ev["station_id"] == "RG-1" and ev["severity"] == "HIGH" and ev["is_fault"] is True and ev["classification"] == "negative_value"
    assert ev["score_kind"] == "uncalibrated rule score" and ev["anomaly_score"] > 0.9 and ev["raw_values"] == {"rain_mm": -3.0}
    assert ev["evidence"][0]["check"] == "negative_value" and "confidence" not in ev          # no confidence: the platform has none
    assert (await async_client.get("/api/anomalies?severity=low")).json()["total"] == 0
    assert (await async_client.get("/api/anomalies?classification=negative")).json()["total"] == 1
    detail = (await async_client.get(f"/api/anomalies/{ev['id']}")).json()
    assert detail["observation"]["rain_mm"] == -3.0 and detail["station"] is None            # RG-1 is not in the station list
    assert (await async_client.get("/api/anomalies/999999")).status_code == 404
    stats = (await async_client.get("/api/anomalies/stats?hours=8760")).json()
    assert stats["total_anomalies"] == 1 and stats["by_severity"] == {"HIGH": 1} and stats["sensor_faults"] == 1
    # the alert list only shows the last 24 hours; this reading is from 2026-08-01
    async with database.async_session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(StreamEvent))).scalar_one() == 1


# ---------------------------------------------------------------------------------------------------- WebSocket (fake client = starlette's test client)
def _login(c: TestClient):
    r = c.post("/api/auth/login", json={"email": EMAIL, "password": PW})
    assert r.status_code == 200
    return r


def test_websocket_streams_readings_and_an_injected_spike_appears():
    runtime.set_manager(fast_manager())
    with TestClient(app) as c:
        h = {"X-Admin-Token": _login(c).json()["token"]}
        with c.websocket_connect("/ws/live") as ws:                               # REQUIRE_LOGIN is off in the test environment
            first = ws.receive_json()
            assert first["type"] == "status" and first["data"]["state"] == "stopped" and "station_id" not in first
            assert c.post("/api/simulation/start", json={**FAST, "station_ids": ["KTLX"]}, headers=h).status_code == 200
            seen, spiked = [], None
            injected = False
            for _ in range(200):
                f = ws.receive_json()
                if f["type"] != "observation":
                    continue
                seen.append(f)
                if len(seen) == 3 and not injected:
                    assert c.post("/api/simulate/inject", json={"anomaly_type": "SPIKE", "station_id": "KTLX", "magnitude": 25.0, "duration_steps": 1},
                                  headers=h).status_code == 200
                    injected = True
                if injected and f["data"]["temperature"] - seen[0]["data"]["temperature"] > 15:
                    spiked = f
                    break
            assert spiked is not None
            f0 = seen[0]
            assert f0["station_id"] == f0["data"]["station_id"] == "KTLX" and isinstance(f0["data"]["temperature"], float)
            assert f0["data"]["validation_status"] == "NO_CHECKS" and f0["data"]["checks_run"] is False and f0["data"]["stored"] is True
            assert not {"anomaly_score", "is_anomaly", "severity"} & set(f0["data"])    # no invented verdict on T/P/RH
            assert "source" not in f0 and "source" not in f0["data"]                   # the label is on stored readings only
            c.post("/api/simulation/stop", headers=h)
            seen_states = []
            for _ in range(50):
                f = ws.receive_json()
                if f["type"] == "status":
                    seen_states.append(f["data"]["state"])
                    if f["data"]["state"] == "stopped":
                        break
            assert seen_states and seen_states[-1] == "stopped"


def test_two_websocket_clients_get_the_same_readings():
    runtime.set_manager(fast_manager())
    with TestClient(app) as c:
        h = {"X-Admin-Token": _login(c).json()["token"]}
        with c.websocket_connect("/ws/live") as a, c.websocket_connect("/ws/live") as b:
            assert a.receive_json()["type"] == "status" and b.receive_json()["type"] == "status"
            c.post("/api/simulation/start", json={**FAST, "station_ids": ["KAMX"]}, headers=h)

            def obs(ws, n):
                out = []
                while len(out) < n:
                    f = ws.receive_json()
                    if f["type"] == "observation":
                        out.append(f["data"]["timestamp"])
                return out
            ta, tb = obs(a, 3), obs(b, 3)
            assert ta == tb
            c.post("/api/simulation/stop", headers=h)


# ---------------------------------------------------------------------------------------------------- auth
def test_rest_routes_are_behind_the_sign_in_and_writes_need_the_admin(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_LOGIN", True)
    runtime.set_manager(fast_manager())
    with TestClient(app) as c:
        for url in ("/api/stations", "/api/stations/KTLX", "/api/observations", "/api/anomalies", "/api/anomalies/stats", "/api/data-sources",
                    "/api/data-sources/status", "/api/simulation/status", "/api/simulate/status"):
            assert c.get(url).status_code == 401, url
        for url in ("/api/simulation/start", "/api/simulation/stop", "/api/simulate/inject", "/api/data-sources/select"):
            assert c.post(url, json={}).status_code == 401, url
        tok = _login(c).json()["token"]
        assert c.get("/api/stations", headers={"X-Admin-Token": tok}).status_code == 200
        assert c.get("/api/simulation/status", headers={"X-Admin-Token": tok}).json()["running"] is False
        # the cookie the sign-in sets opens the WebSocket only; an HTTP route ignores it
        assert c.get("/api/stations", headers={"cookie": f"{auth_api.SESSION_COOKIE}={tok}"}).status_code == 401


def test_websocket_auth_header_cookie_origin_and_refusals(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_LOGIN", True)
    runtime.set_manager(fast_manager())
    with TestClient(app) as c:
        login = _login(c)
        tok = login.json()["token"]
        assert f"{auth_api.SESSION_COOKIE}=" in login.headers["set-cookie"] and "HttpOnly" in login.headers["set-cookie"]
        cookie = {"cookie": f"{auth_api.SESSION_COOKIE}={tok}"}
        c.cookies.clear()                                                                   # the client's own jar must not sign the later attempts in

        def refused(headers=None):
            with pytest.raises(WebSocketDisconnect) as e:
                with c.websocket_connect("/ws/live", headers=headers or {}) as ws:
                    ws.receive_json()
            return e.value.code

        assert refused() == 1008                                                            # nobody signed in
        assert refused({"X-Admin-Token": "wrong"}) == 1008
        assert refused({**cookie, "origin": "http://evil.example"}) == 1008                 # a cookie from a foreign page is refused
        with c.websocket_connect("/ws/live", headers={"X-Admin-Token": tok}) as ws:         # scripts: the header
            assert ws.receive_json()["type"] == "status"
        with c.websocket_connect("/ws/live", headers={**cookie, "origin": "http://localhost:5173"}) as ws:     # browsers: cookie from an allowed origin
            assert ws.receive_json()["type"] == "status"
        with c.websocket_connect("/ws/live", headers=cookie) as ws:                         # no Origin header: not a browser
            assert ws.receive_json()["type"] == "status"
        c.post("/api/auth/logout", headers={"X-Admin-Token": tok})
        assert refused(cookie) == 1008                                                      # the session is gone


def test_websocket_admin_token_header_works_for_scripts(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_LOGIN", True)
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "script-token-for-tests")
    runtime.set_manager(fast_manager())
    with TestClient(app) as c:
        with c.websocket_connect("/ws/live", headers={"X-Admin-Token": "script-token-for-tests"}) as ws:
            assert ws.receive_json()["type"] == "status"
