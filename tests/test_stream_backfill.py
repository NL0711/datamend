"""Startup backfill of the simulator (stream/backfill.py): earlier SYNTHETIC readings go through the live ReadingProcessor in time order, the
scorer is a httpx.MockTransport stub with known errors (labelled fake), nothing touches the network. Storage is the throwaway SQLite of conftest."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from backend.app.config import settings
from backend.app.db import database
from backend.app.scorer.client import ScorerClient
from backend.app.scorer.service import MODEL_ID, ModelScorer
from backend.app.scorer.threshold import ThresholdStore
from backend.app.scorer.window import WINDOW
from backend.app.stream import backfill, control, service
from backend.app.stream.manager import StreamManager
from backend.app.stream.models import StreamEvent, StreamReadingRow
from backend.app.stream.service import ReadingProcessor
from backend.app.stream.sim_physics import SIM_STATIONS
from backend.app.stream.simulator import SimulatorSource

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
STEP = 30.0
N = WINDOW + 12            # 12 scored readings per station


class FakeScorer:
    """Fake scorer service: /health answers ``health``; /score gives every window the error ``error`` (or the status ``score_status``)."""
    def __init__(self, error=0.1, health=200, score_status=200):
        self.error, self.health, self.score_status, self.scores, self.health_calls = error, health, score_status, 0, 0
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            self.health_calls += 1
            return httpx.Response(self.health, json={"status": "ok"})
        if self.score_status != 200:
            return httpx.Response(self.score_status, json={"detail": "x"})
        self.scores += 1
        n = len(json.loads(req.content)["windows"])
        return httpx.Response(200, json={"errors": [self.error] * n, "model": {"id": MODEL_ID, "revision": "abc", "format": "onnx"}})


def processor(fake):
    return ReadingProcessor(scorer=ModelScorer(ScorerClient("http://scorer", "k", 2.0, fake.transport), thresholds=ThresholdStore(0.2, 5)))


def sim(n_stations=2, interval=STEP):
    return SimulatorSource(SIM_STATIONS[:n_stations], interval_seconds=interval)


@pytest_asyncio.fixture
async def clean_db():
    async def wipe():
        async with database.async_session_factory() as s:
            await s.execute(delete(StreamEvent))
            await s.execute(delete(StreamReadingRow))
            await s.commit()
    await wipe()
    yield
    await wipe()


async def rows(station_id):
    async with database.async_session_factory() as s:
        return list((await s.execute(select(StreamReadingRow).where(StreamReadingRow.station_id == station_id)
                                     .order_by(StreamReadingRow.timestamp, StreamReadingRow.id))).scalars())


def aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@pytest.mark.asyncio
async def test_backfill_stores_n_ordered_simulator_readings_with_full_windows_and_a_threshold(clean_db):
    fake = FakeScorer()
    s = sim(2)
    st = await backfill.run_backfill(s, processor(fake), readings=N, now=NOW)
    assert st.status == "done" and st.readings_done == 2 * N and st.stations_done == 2 and st.scorer == "awake" and fake.health_calls == 1
    for sid in ("KTLX", "KOKX"):
        rs = await rows(sid)
        assert len(rs) == N
        ts = [aware(r.timestamp) for r in rs]
        assert ts[-1] == NOW - timedelta(seconds=STEP) and all(b - a == timedelta(seconds=STEP) for a, b in zip(ts, ts[1:]))     # oldest first, one cadence apart
        assert {r.source for r in rs} == {"simulator"} and all(r.injected_fault is None for r in rs)                               # labelled, fault-free
        assert rs[0].provider["variables"]["temperature"]["status"] == "not_run"
        last = rs[-1].provider["variables"]
        assert all(last[v]["status"] == "scored" and last[v]["error"] == 0.1 for v in ("temperature", "pressure", "humidity"))      # windows full, real client answered
        assert last["temperature"]["threshold"] == 0.1                                                                              # 5 clean scores earlier: a threshold exists
        assert rs[WINDOW].provider["variables"]["temperature"].get("threshold") is None                                              # the first scored reading has none yet
    d = st.as_dict()
    assert d["status"] == "done" and d["synthetic"] is True and d["readings_total"] == 2 * N


@pytest.mark.asyncio
async def test_a_second_run_adds_nothing(clean_db):
    fake = FakeScorer()
    await backfill.run_backfill(sim(1), processor(fake), readings=40, now=NOW)
    before = len(await rows("KTLX"))
    st = await backfill.run_backfill(sim(1), processor(fake), readings=40, now=NOW + timedelta(hours=1))
    assert before == 40 and st.status == "skipped" and st.readings_done == 0 and len(await rows("KTLX")) == 40


@pytest.mark.asyncio
async def test_a_station_with_some_readings_gets_only_the_missing_ones_after_the_stored_ones(clean_db):
    await backfill.run_backfill(sim(1), processor(FakeScorer()), readings=10, now=NOW)
    await backfill.run_backfill(sim(1), processor(FakeScorer()), readings=25, now=NOW + timedelta(seconds=STEP * 100))
    rs = await rows("KTLX")
    ts = [aware(r.timestamp) for r in rs]
    assert len(rs) == 25 and ts == sorted(ts) and len(set(ts)) == 25


@pytest.mark.asyncio
async def test_scorer_absent_still_stores_readings_and_checks(clean_db):
    st = await backfill.run_backfill(sim(1), ReadingProcessor(scorer=ModelScorer(None)), readings=30, now=NOW)
    rs = await rows("KTLX")
    assert st.status == "done" and st.scorer == "absent" and len(rs) == 30
    assert all(r.provider is None and r.check_status for r in rs)


@pytest.mark.asyncio
async def test_a_scorer_that_never_wakes_leaves_a_provider_block_that_says_so(clean_db, monkeypatch):
    monkeypatch.setattr(backfill, "WAKE_MAX_S", 0.0)
    fake = FakeScorer(health=503, score_status=503)
    st = await backfill.run_backfill(sim(1), processor(fake), readings=WINDOW + 3, now=NOW)
    rs = await rows("KTLX")
    assert st.status == "done" and st.scorer == "not_awake" and len(rs) == WINDOW + 3
    v = rs[-1].provider["variables"]["temperature"]
    assert v["status"] == "unavailable" and v.get("error") is None and "scorer not available" in v["reason"]


@pytest.mark.asyncio
async def test_a_station_cap_limits_the_stations(clean_db):
    st = await backfill.run_backfill(sim(3), ReadingProcessor(scorer=ModelScorer(None)), readings=5, stations=2, now=NOW)
    assert st.stations_total == 2 and len(await rows("KTLX")) == 5 and len(await rows("KOKX")) == 5 and await rows("KAMX") == []


@pytest.mark.asyncio
async def test_zero_disables_it(clean_db):
    st = await backfill.run_backfill(sim(1), ReadingProcessor(scorer=ModelScorer(None)), readings=0, now=NOW)
    assert st.status == "skipped" and await rows("KTLX") == []
    assert target_with(settings, 0) == 0


def target_with(cfg, value):
    old = cfg.STREAM_BACKFILL_READINGS
    cfg.STREAM_BACKFILL_READINGS = value
    try:
        return backfill.target_per_station()
    finally:
        cfg.STREAM_BACKFILL_READINGS = old


def test_the_default_depends_on_the_scorer(monkeypatch):
    monkeypatch.setattr(settings, "STREAM_BACKFILL_READINGS", -1)
    monkeypatch.setattr(settings, "SCORER_URL", "")
    assert backfill.target_per_station() == 300
    monkeypatch.setattr(settings, "SCORER_URL", "http://scorer")
    assert backfill.target_per_station() == 1300
    monkeypatch.setattr(settings, "STREAM_BACKFILL_READINGS", 0)
    assert backfill.enabled() is False


@pytest.mark.asyncio
async def test_the_live_simulator_continues_after_the_backfill_without_overlap(clean_db):
    s = sim(1, interval=0.05)
    manager = StreamManager(processor=ReadingProcessor(scorer=ModelScorer(None)))
    manager.register(s)
    st = await backfill.run_backfill(s, manager.processor, readings=20)
    backfilled = await rows("KTLX")
    n = len(backfilled)
    assert st.status == "done" and n >= 20             # 20, plus the steps that real time added while they were processed (0.05 s cadence here)
    await manager.select("simulator")                         # the live start continues the timeline instead of resetting the models
    try:
        for _ in range(200):
            if len(await rows("KTLX")) >= n + 4:
                break
            await asyncio.sleep(0.05)
    finally:
        await manager.stop()
    rs = await rows("KTLX")
    ts = [aware(r.timestamp) for r in rs]
    assert len(rs) >= n + 4 and ts == sorted(ts) and len(set(ts)) == len(ts)
    assert ts[n] > ts[n - 1] and abs(rs[n].temperature_c - rs[n - 1].temperature_c) < 2.0   # a continuation, not a restart from the seed
    assert s.step_count >= n + 4                                                               # the step counter kept counting


def test_catch_up_continues_the_timeline_up_to_the_present_without_a_gap():
    s = sim(1)
    hist = s.generate_history(5, NOW)
    assert hist[-1][0].timestamp == NOW - timedelta(seconds=STEP) and s.catch_up(NOW) == []        # nothing is due yet
    extra = s.catch_up(NOW + timedelta(seconds=STEP * 4))
    ts = [step[0].timestamp for step in hist + extra]
    assert [b - a for a, b in zip(ts, ts[1:])] == [timedelta(seconds=STEP)] * (len(ts) - 1)
    assert ts[-1] == NOW + timedelta(seconds=STEP * 3) and s.step_count == 5 + len(extra)


@pytest.mark.asyncio
async def test_autostart_backfills_in_the_background_then_starts_the_simulator_and_reports_the_state(clean_db, monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(tmp_path / "rt.json"))
    monkeypatch.setattr(settings, "STREAM_AUTOSTART_SIMULATOR", True)
    monkeypatch.setattr(settings, "STREAM_BACKFILL_READINGS", 15)
    monkeypatch.setattr(settings, "STREAM_BACKFILL_STATIONS", 1)
    manager = StreamManager(processor=ReadingProcessor(scorer=ModelScorer(None)))
    manager.register(sim(2, interval=0.05))
    assert await control.autostart(manager) is None
    assert manager.active is None and backfill.state.status == "running"                 # returned at once; the backfill is a background task
    assert service.active_source_status(manager)["backfill"]["status"] == "running"      # no source is active yet, the status still answers
    try:
        for _ in range(200):
            if manager.active is not None:
                break
            await asyncio.sleep(0.05)
        assert manager.active is not None and manager.active.source_id == "simulator"
        listing = service.source_list(manager)
        assert listing["backfill"]["status"] == "done" and listing["backfill"]["readings_done"] >= 15      # plus any steps real time added (0.05 s cadence)
        assert service.active_source_status(manager)["backfill"]["status"] == "done"
    finally:
        await backfill.cancel()
        await manager.stop()


@pytest.mark.asyncio
async def test_autostart_with_the_backfill_off_starts_the_simulator_at_once(clean_db, monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(tmp_path / "rt.json"))
    monkeypatch.setattr(settings, "STREAM_AUTOSTART_SIMULATOR", True)
    monkeypatch.setattr(settings, "STREAM_BACKFILL_READINGS", 0)
    manager = StreamManager(processor=ReadingProcessor(scorer=ModelScorer(None)))
    manager.register(sim(1, interval=0.05))
    assert await control.autostart(manager) is None
    try:
        assert manager.active is not None and backfill.state.status == "skipped"
    finally:
        await manager.stop()
