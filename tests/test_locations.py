"""Locations feature: grid mapping, normals, weather anomaly, data-QC checks, score plug-in, service and REST API.

The API and service tests run against an in-memory database and a mocked Open-Meteo (httpx MockTransport): no network,
no real data is touched. The mock generates series from a known seasonal cycle, so every assertion has a derivable answer.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone

import httpx
import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.api import locations as locations_api
from backend.app.db.database import Base, get_db
from backend.app.locations import anomaly, grid, qc
from backend.app.locations.models import CellNormals, Location
from backend.app.locations.normals import NormalsError, build_normals, doy_index
from backend.app.locations.openmeteo import OpenMeteoClient
from backend.app.locations.scores import FileScoreProvider, model_block
from backend.app.locations.service import LocationService
from backend.app.main import app


# ---------------------------------------------------------------------------------------------- grid

def test_mumbai_is_four_land_cells_in_the_held_out_region():
    cells = grid.cells_for(19.0760, 72.8777, 15.0)
    assert [(grid.lat_of(r), grid.lon_of(c)) for r, c in cells] == [(19.0, 72.75), (19.0, 73.0), (19.25, 72.75), (19.25, 73.0)]
    for r, c in cells:
        d = grid.describe_cell(r, c)
        assert d["is_land"] is True and d["client"] == 6 and d["held_out"] is True


def test_cell_of_uses_the_southernmost_row_as_row_zero_and_rejects_points_outside():
    assert grid.cell_of(6.5, 66.5) == (0, 0)
    assert grid.cell_of(38.5, 100.0) == (128, 134)
    assert grid.cell_of(19.07, 72.88) == (50, 26)
    for lat, lon in ((5.0, 70.0), (20.0, 120.0), (45.0, 80.0)):
        with pytest.raises(grid.GridError, match="outside the grid"):
            grid.cell_of(lat, lon)


def test_a_point_always_includes_its_own_cell_and_huge_areas_are_refused():
    assert grid.cells_for(19.0, 72.75, 0.0) == [(50, 25)]
    with pytest.raises(grid.GridError, match="at most"):
        grid.cells_for(19.0, 73.0, 100.0)
    with pytest.raises(grid.GridError):
        grid.cells_for(19.0, 73.0, -1.0)


def test_sea_cells_are_marked_not_land():
    r, c = grid.cell_of(19.0, 72.5)                                   # Arabian Sea west of Mumbai
    assert grid.describe_cell(r, c)["is_land"] is False and grid.describe_cell(r, c)["client"] is None


# ---------------------------------------------------------------------------------------------- normals and anomaly

def _history(years=range(1991, 2021), seed=0, rain=True):
    rng = np.random.default_rng(seed)
    days = [date(y, 1, 1) + timedelta(days=i) for y in years for i in range(366 if y % 4 == 0 else 365)]
    doy = np.array([d.timetuple().tm_yday for d in days])
    ang = 2 * np.pi * doy / 365.25
    return {"time": [d.isoformat() for d in days],
            "temperature": list(27 + 3 * np.sin(ang) + rng.normal(0, 1.0, len(days))),
            "humidity": list(70 + 10 * np.sin(ang) + rng.normal(0, 5.0, len(days))),
            "pressure": list(1008 + 2 * np.sin(ang) + rng.normal(0, 2.0, len(days))),
            "precipitation": list(np.where(rng.random(len(days)) < 0.3, rng.gamma(0.7, 12.0, len(days)), 0.0)) if rain else [0.0] * len(days)}


def test_normals_recover_the_seasonal_cycle_and_spread():
    h = _history()
    n = build_normals(h)
    i = doy_index(date(2021, 4, 1))
    expect = 27 + 3 * np.sin(2 * np.pi * (i + 1) / 365.25)
    assert abs(n["temperature"]["mean"][i] - expect) < 0.4
    assert 0.8 < n["temperature"]["sd"][i] < 1.25
    assert len(n["humidity"]["mean"]) == 366 and all(math.isfinite(x) for x in n["pressure"]["sd"])
    assert 0 < n["rain"]["wet_p95"] < n["rain"]["wet_p99"] and 0.2 < n["rain"]["wet_fraction"][100] < 0.4
    json.dumps(n)                                                      # JSON-safe: it is stored in a JSON column


def test_too_little_history_gives_no_normals_instead_of_made_up_ones():
    with pytest.raises(NormalsError, match="at least"):
        build_normals(_history(years=range(2015, 2020)))


def test_weather_anomaly_levels_and_rain_classes():
    n = build_normals(_history())
    d = date(2025, 6, 15)
    mean = n["temperature"]["mean"][doy_index(d)]
    sd = n["temperature"]["sd"][doy_index(d)]
    a = anomaly.weather_anomaly({"temperature": mean + 2.5 * sd, "humidity": n["humidity"]["mean"][doy_index(d)], "pressure": n["pressure"]["mean"][doy_index(d)] - 3.5 * n["pressure"]["sd"][doy_index(d)],
                                 "precipitation": 0.0}, n, d)
    assert a["temperature"]["level"] == "unusual" and a["temperature"]["direction"] == "above" and abs(a["temperature"]["z"] - 2.5) < 0.05
    assert a["humidity"]["level"] == "normal"
    assert a["pressure"]["level"] == "extreme" and a["pressure"]["direction"] == "below"
    assert a["precipitation"]["level"] == "dry"
    p95, p99 = n["rain"]["wet_p95"], n["rain"]["wet_p99"]
    assert anomaly.rain_anomaly(p95 * 1.01, n, d)["level"] == "heavy"
    assert anomaly.rain_anomaly(p99 * 1.01, n, d)["level"] == "very_heavy"
    assert anomaly.rain_anomaly(1.0, n, d)["level"] == "normal"
    assert anomaly.weather_anomaly({"temperature": None}, n, d)["temperature"]["level"] == "unavailable"
    assert anomaly.anomaly_strength(a) == 2


# ---------------------------------------------------------------------------------------------- QC checks

def _hours(n=168):
    t0 = datetime(2026, 11, 1, 0)
    return [(t0 + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(n)]


def _smooth(n=168, base=28.0, amp=3.0):
    return [base + amp * math.sin(2 * math.pi * (i % 24) / 24) + 0.02 * ((i * 7) % 5) for i in range(n)]


def test_clean_smooth_series_has_no_findings():
    t = _hours()
    for v, vals in (("temperature", _smooth()), ("humidity", [70 + 5 * math.sin(i / 3) for i in range(168)]), ("pressure", [1008 + 0.3 * math.sin(i / 12) for i in range(168)])):
        assert qc.check_series(v, vals, t) == [], v


def test_stuck_step_range_and_missing_are_each_found():
    t, x = _hours(), _smooth()
    stuck = x[:100] + [30.0] * 8 + x[108:]
    assert [f["check"] for f in qc.check_series("temperature", stuck, t)] == ["stuck"]
    step = x[:80] + [v + 12.0 for v in x[80:]]
    assert any(f["check"] == "step" for f in qc.check_series("temperature", step, t))
    assert any(f["check"] == "range" for f in qc.check_series("humidity", [50.0] * 100 + [130.0] + [50.0] * 67, t))
    holes = [None if 20 < i < 80 else v for i, v in enumerate(x)]
    assert any(f["check"] == "missing" for f in qc.check_series("temperature", holes, t))
    assert qc.check_series("precipitation", [0.0] * 168, t) == []                     # zeros in rainfall are normal


def test_buddy_check_needs_enough_neighbours_and_names_the_odd_cell():
    z = {"a": {"temperature": 0.1}, "b": {"temperature": -0.2}, "c": {"temperature": 0.0}, "d": {"temperature": 5.0}}
    out = qc.buddy_check(z)
    assert out["d"] and "temperature" in out["d"][0]["detail"] and not out["a"] and not out["b"] and not out["c"]
    assert all(not v for v in qc.buddy_check({"a": {"temperature": 0.0}, "b": {"temperature": 9.0}}).values())     # one other cell: not enough


def test_classification_separates_a_coherent_event_from_a_single_cell_fault():
    assert qc.classify(0, [], [], 0, 3)["label"] == "consistent"
    assert qc.classify(2, [], [], 3, 3)["label"] == "genuine_event_likely"
    assert qc.classify(2, [], [{"detail": "x"}], 0, 3)["label"] == "possible_data_fault"
    assert qc.classify(0, [{"check": "stuck", "detail": "d"}], [], 0, 3)["label"] == "possible_data_fault"
    assert qc.classify(2, [], [], 0, 1)["label"] == "uncertain"                       # too few cells to compare
    assert qc.classify(2, [], [], 1, 3)["label"] == "uncertain"


# ---------------------------------------------------------------------------------------------- score plug-in

def test_model_scores_are_never_invented(tmp_path):
    day = date(2026, 11, 16)
    assert model_block(None, 50, 25, day)["status"] == "not_available"
    prov = FileScoreProvider(tmp_path)
    assert model_block(prov, 50, 25, day)["status"] == "not_available"
    (tmp_path / "50_25.json").write_text(json.dumps({"model": "fusion_max", "version": "t", "label_tier": "synthetic faults",
                                                       "scores": {"2026-11-16": {"temperature": 1.2, "fused": 1.9, "flag": "none"}}}))
    got = model_block(prov, 50, 25, day)
    assert got["status"] == "ok" and got["scores"]["fused"] == 1.9 and got["label_tier"] == "synthetic faults"
    assert model_block(prov, 50, 25, date(2026, 11, 17))["status"] == "not_available"
    (tmp_path / "50_26.json").write_text("not json")
    assert model_block(prov, 50, 26, day)["status"] == "not_available"


# ---------------------------------------------------------------------------------------------- mocked Open-Meteo

class Feed:
    """A mock Open-Meteo. ``mode`` changes the recent series; the history (normals) always comes from _history()."""

    def __init__(self):
        self.mode = "normal"
        self.calls = {"archive": 0, "forecast": 0, "geocode": 0}
        self.down = False

    def hourly(self, now: datetime, cell_index: int):
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=6)           # includes future hours that must be dropped
        times, t, rh, p, pr = [], [], [], [], []
        h = start
        while h <= end:
            doy = h.timetuple().tm_yday
            ang = 2 * np.pi * doy / 365.25
            diurnal = 2.0 * math.sin(2 * math.pi * (h.hour - 9) / 24)
            temp = 27 + 3 * np.sin(ang) + diurnal
            if self.mode == "hot" or (self.mode == "single_hot" and cell_index == 1):
                temp += 6.0
            if self.mode == "stuck" and cell_index == 0 and h > now - timedelta(hours=14):
                temp = 30.0
            times.append(h.strftime("%Y-%m-%dT%H:%M"))
            t.append(float(temp)); rh.append(float(70 + 10 * np.sin(ang) + 3 * math.sin(2 * math.pi * h.hour / 24)))
            p.append(float(1008 + 2 * np.sin(ang) + 0.3 * math.sin(2 * math.pi * h.hour / 12))); pr.append(0.0)
            h += timedelta(hours=1)
        return times, t, rh, p, pr

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(503, text="down")
        q = dict(request.url.params)
        url = str(request.url)
        if "geocoding" in url:
            self.calls["geocode"] += 1
            return httpx.Response(200, json={"results": [{"name": "Pune", "latitude": 18.5196, "longitude": 73.8553, "country": "India", "admin1": "Maharashtra"}]}
                                  if q["name"].lower() == "pune" else {})
        lats, lons = q["latitude"].split(","), q["longitude"].split(",")
        items = []
        for i, (la, lo) in enumerate(zip(lats, lons)):
            base = {"latitude": float(la) + 0.0158, "longitude": float(lo) + 0.12, "elevation": 3.0}
            if "archive" in url:
                h = _history(seed=i)
                items.append({**base, "daily": {"time": h["time"], "temperature_2m_mean": h["temperature"], "relative_humidity_2m_mean": h["humidity"],
                                                "surface_pressure_mean": h["pressure"], "precipitation_sum": h["precipitation"]}})
            else:
                times, t, rh, p, pr = self.hourly(datetime.now(timezone.utc).replace(tzinfo=None), i)
                items.append({**base, "hourly": {"time": times, "temperature_2m": t, "relative_humidity_2m": rh, "surface_pressure": p, "precipitation": pr}})
        self.calls["archive" if "archive" in url else "forecast"] += 1
        return httpx.Response(200, json=items if len(items) > 1 else items[0])


@pytest.fixture
def feed():
    return Feed()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture
async def api(db, feed, monkeypatch):
    om_http = httpx.AsyncClient(transport=httpx.MockTransport(feed.handler))
    monkeypatch.setattr(locations_api, "_client", OpenMeteoClient(client=om_http, retries=0, backoff=0))
    monkeypatch.setattr(locations_api, "_scores", None)

    async def override():
        async with db() as session:
            yield session
            await session.commit()
    app.dependency_overrides[get_db] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    await om_http.aclose()


async def _mumbai(api: AsyncClient) -> int:
    r = await api.post("/api/locations", json={"name": "Mumbai", "latitude": 19.076, "longitude": 72.8777, "radius_km": 15})
    assert r.status_code == 201, r.text
    assert len(r.json()["cells"]) == 4
    return r.json()["id"]


# ---------------------------------------------------------------------------------------------- service and API

@pytest.mark.asyncio
async def test_presets_seed_mumbai_only_when_there_are_no_locations(db):
    async with db() as s:
        await LocationService(s).ensure_presets()
        await s.commit()
    async with db() as s:
        await LocationService(s).ensure_presets()                       # second call adds nothing
        locs = await LocationService(s).list()
    assert [(l.name, l.preset, len(l.cells)) for l in locs] == [("Mumbai", True, 4)]


@pytest.mark.asyncio
async def test_add_by_coordinates_by_name_and_validation(api, feed):
    mid = await _mumbai(api)
    got = (await api.get(f"/api/locations/{mid}")).json()
    assert {(c["lat"], c["lon"]) for c in got["cells"]} == {(19.0, 72.75), (19.0, 73.0), (19.25, 72.75), (19.25, 73.0)}
    assert all(c["held_out"] and c["client"] == 6 for c in got["cells"])
    r = await api.post("/api/locations", json={"name": "Pune"})                      # looked up by name
    assert r.status_code == 201 and r.json()["name"].startswith("Pune") and feed.calls["geocode"] == 1 and r.json()["cells"]
    assert (await api.post("/api/locations", json={"name": "Nowhereville"})).status_code == 404
    assert (await api.post("/api/locations", json={"name": "Paris", "latitude": 48.85, "longitude": 2.35})).status_code == 422      # outside the grid
    assert (await api.post("/api/locations", json={"name": "x", "latitude": 19.0})).status_code == 422                              # one coordinate only
    assert (await api.post("/api/locations", json={"name": "Big", "latitude": 19.0, "longitude": 73.0, "radius_km": 100})).status_code == 422
    assert (await api.get("/api/locations")).json()["total"] == 2
    assert (await api.delete(f"/api/locations/{mid}")).status_code == 200
    assert (await api.get(f"/api/locations/{mid}")).status_code == 404


@pytest.mark.asyncio
async def test_normal_weather_is_consistent_and_everything_is_labelled(api, feed):
    mid = await _mumbai(api)
    r = await api.get(f"/api/locations/{mid}/status")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["source"]["provider"] == "open_meteo" and "not station observations" in s["source"]["kind"] and s["stale"] is False
    assert len(s["limitations"]) >= 3 and s["summary"] == {"consistent": 4}
    for c in s["cells"]:
        assert c["status"] == "ok" and c["classification"]["label"] == "consistent"
        assert c["model"]["status"] == "not_available" and "reason" in c["model"]                      # no invented model scores
        assert c["qc"]["method"] == "rules+statistics v0" and c["qc"]["findings"] == []
        assert abs(c["grid_point"]["lat"] - (c["cell"]["lat"] + 0.0158)) < 1e-6                         # the point actually used is reported
        w = c["weather_anomaly"]
        assert w["status"] == "ok" and w["normals_period"] == "1991-2020"
        assert all(w[v]["level"] == "normal" for v in ("temperature", "humidity", "pressure"))
        assert datetime.fromisoformat(c["current"]["time"]) <= datetime.now(timezone.utc).replace(tzinfo=None)     # no forecast hours as "current"
    assert feed.calls["archive"] == 1 and feed.calls["forecast"] == 1                                    # one batched call each
    await api.get(f"/api/locations/{mid}/status")
    assert feed.calls["archive"] == 1 and feed.calls["forecast"] == 1                                    # normals stored, series cached


@pytest.mark.asyncio
async def test_a_hot_spell_seen_by_every_cell_is_a_likely_genuine_event(api, feed):
    feed.mode = "hot"
    mid = await _mumbai(api)
    s = (await api.get(f"/api/locations/{mid}/status")).json()
    assert s["summary"] == {"genuine_event_likely": 4}
    c = s["cells"][0]
    assert c["weather_anomaly"]["temperature"]["level"] == "extreme" and c["weather_anomaly"]["temperature"]["direction"] == "above"
    assert c["qc"]["findings"] == [] and "other cells together" in c["classification"]["reasons"][0]


@pytest.mark.asyncio
async def test_the_same_spell_in_one_cell_only_is_a_possible_data_fault(api, feed):
    feed.mode = "single_hot"
    mid = await _mumbai(api)
    s = (await api.get(f"/api/locations/{mid}/status")).json()
    labels = [c["classification"]["label"] for c in s["cells"]]
    assert labels.count("possible_data_fault") == 1 and labels.count("consistent") == 3
    odd = next(c for c in s["cells"] if c["classification"]["label"] == "possible_data_fault")
    assert odd["qc"]["neighbour_findings"] and "temperature" in odd["classification"]["reasons"][0]


@pytest.mark.asyncio
async def test_a_stuck_sensor_series_is_flagged_with_the_reason(api, feed):
    feed.mode = "stuck"
    mid = await _mumbai(api)
    s = (await api.get(f"/api/locations/{mid}/status")).json()
    c = s["cells"][0]
    assert c["classification"]["label"] == "possible_data_fault"
    assert any(f["check"] == "stuck" and f["variable"] == "temperature" for f in c["qc"]["findings"])


@pytest.mark.asyncio
async def test_series_endpoint_returns_hourly_values_and_todays_normals(api):
    mid = await _mumbai(api)
    r = await api.get(f"/api/locations/{mid}/series?days=2")
    assert r.status_code == 200
    s = r.json()
    assert len(s["cells"]) == 4 and 24 <= len(s["cells"][0]["time"]) <= 72
    assert set(s["normals_today"]["50_25"]) == {"temperature", "humidity", "pressure"}
    assert (await api.get(f"/api/locations/{mid}/series?days=30")).status_code == 422


@pytest.mark.asyncio
async def test_service_down_gives_a_plain_502_cold_and_stale_data_when_warm(db, feed, monkeypatch):
    http = httpx.AsyncClient(transport=httpx.MockTransport(feed.handler))
    om = OpenMeteoClient(client=http, retries=0, backoff=0)
    clock = {"now": datetime.now(timezone.utc)}
    async with db() as s:
        svc = LocationService(s, om=om, now=lambda: clock["now"], cache_seconds=60)
        loc = await svc.create("Mumbai", 19.076, 72.8777, 15.0)
        feed.down = True
        from backend.app.locations.openmeteo import OpenMeteoError
        with pytest.raises(OpenMeteoError):
            await svc.status(loc.id)                                                    # nothing cached yet
        feed.down = False
        first = await svc.status(loc.id)
        assert first["stale"] is False
        clock["now"] += timedelta(minutes=5)                                            # cache expired, service goes down
        feed.down = True
        second = await svc.status(loc.id)
        assert second["stale"] is True and second["as_of"] == first["as_of"]            # last good data, marked stale
    await http.aclose()


@pytest.mark.asyncio
async def test_missing_normals_are_reported_not_replaced_with_guesses(db, feed):
    http = httpx.AsyncClient(transport=httpx.MockTransport(feed.handler))
    om = OpenMeteoClient(client=http, retries=0, backoff=0)
    real = feed.handler

    def no_history(request):
        return httpx.Response(503) if "archive" in str(request.url) else real(request)
    om2 = OpenMeteoClient(client=httpx.AsyncClient(transport=httpx.MockTransport(no_history)), retries=0, backoff=0)
    async with db() as s:
        svc = LocationService(s, om=om2)
        loc = await svc.create("Mumbai", 19.076, 72.8777, 15.0)
        st = await svc.status(loc.id)
    for c in st["cells"]:
        assert c["weather_anomaly"]["status"] == "unavailable" and "history could not be fetched" in c["weather_anomaly"]["reason"]
        assert c["current"] is not None                                                   # current values still shown
    await http.aclose()
