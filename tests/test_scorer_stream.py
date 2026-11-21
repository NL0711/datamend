"""Keras scorer inside the stream's ReadingProcessor: stored provider block, model-only events are UNCERTAIN and never faults, the checks'
verdict and rule score stay theirs, and the platform runs with the scorer absent. httpx.MockTransport stub with known errors; real SQLite."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from backend.app.db import database
from backend.app.scorer.client import ScorerClient
from backend.app.scorer.service import ModelScorer
from backend.app.scorer.threshold import ThresholdStore
from backend.app.scorer.window import WINDOW
from backend.app.stream.models import StreamEvent, StreamReadingRow
from backend.app.stream.service import ReadingProcessor, anomaly_detail
from backend.app.stream.types import StreamReading
from tests.test_scorer_unit import Stub

T0 = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def smooth(i, rh=True):
    return StreamReading("SC-1", T0 + timedelta(minutes=i), "fake", temperature_c=24.0 + 0.01 * i, pressure_hpa=1000.0 - 0.01 * i,
                         humidity_pct=60.0 - 0.02 * i if rh else None)


@pytest_asyncio.fixture
async def clean_db(async_client: AsyncClient):
    async with database.async_session_factory() as s:
        await s.execute(delete(StreamEvent))
        await s.execute(delete(StreamReadingRow))
        await s.commit()


async def warm(proc, n):
    out = None
    for i in range(n):
        out = await proc(smooth(i))
    return out


def processor(stub):
    return ReadingProcessor(scorer=ModelScorer(ScorerClient("http://scorer", "k", 2.0, stub.transport), thresholds=ThresholdStore(0.2, 3)))


@pytest.mark.asyncio
async def test_a_model_flag_alone_is_an_uncertain_model_flag_event_with_the_checks_rule_score(clean_db):
    stub = Stub(error=0.1)
    proc = processor(stub)
    pre = await warm(proc, WINDOW - 1)
    assert pre["provider"]["variables"]["temperature"]["reason"].startswith("not run: need 288 readings")
    for i in range(WINDOW - 1, WINDOW + 4):
        out = await proc(smooth(i))
        assert out["validation_status"] == "OK" and out["model_flagged"] is False
    stub.error = 7.0
    out = await proc(smooth(WINDOW + 4))
    assert out["validation_status"] == "OK" and out["is_anomaly"] is False        # the checks' verdict is untouched
    assert out["model_flagged"] is True and out["provider_score_kind"] == "model reconstruction error, not validated"
    assert out["provider"]["variables"]["temperature"]["flagged"] is True and out["anomaly_score"] == 0.0
    async with database.async_session_factory() as s:
        ev = (await s.execute(select(StreamEvent))).scalars().all()
        rows = (await s.execute(select(StreamReadingRow).order_by(StreamReadingRow.id.desc()).limit(1))).scalars().all()
    assert len(ev) == 1 and ev[0].verdict == "UNCERTAIN" and ev[0].classification == "model_flag" and ev[0].is_fault is False and ev[0].hits == []
    assert ev[0].rule_score == 0.0 and ev[0].provider["variables"]["temperature"]["flagged"] is True
    assert rows[0].check_status == "OK" and rows[0].provider["variables"]["temperature"]["error"] == 7.0 and "window" not in rows[0].provider["variables"]["temperature"]


@pytest.mark.asyncio
async def test_when_the_checks_flag_the_provider_is_attached_to_their_event_and_the_api_carries_it(clean_db, async_client: AsyncClient):
    stub = Stub(error=0.1)
    proc = processor(stub)
    await warm(proc, WINDOW + 3)
    stub.error = 7.0
    gone = await proc(smooth(WINDOW + 3, rh=False))                          # humidity vanishes: the dropout check is a fault
    assert gone["validation_status"] == "SUSPECT"
    an = (await async_client.get("/api/anomalies?station_id=SC-1")).json()
    assert an["total"] == 1
    ev = an["items"][0]
    assert ev["classification"] == "dropout" and ev["score_kind"] == "uncalibrated rule score" and ev["provider_score_kind"] == "model reconstruction error, not validated"
    assert ev["provider"]["validated"] is False and ev["provider"]["variables"]["temperature"]["error"] == 7.0
    detail = (await async_client.get(f"/api/anomalies/{ev['id']}")).json()
    assert detail["provider"]["model_id"] == "keras-io/timeseries-anomaly-detection"
    obs = (await async_client.get("/api/observations?station_id=SC-1&limit=1")).json()["items"][0]
    assert obs["provider"]["variables"]["humidity"]["status"] == "not_run" and obs["check_status"] == "SUSPECT"


@pytest.mark.asyncio
async def test_a_scorer_outage_does_not_stall_or_change_the_stream(clean_db):
    stub = Stub(status=503)
    proc = processor(stub)
    out = await warm(proc, WINDOW)
    assert out["validation_status"] == "OK" and out["stored"] is True
    assert out["provider"]["variables"]["temperature"]["status"] == "unavailable" and out["provider"]["variables"]["temperature"]["error"] is None
    n = len(stub.requests)
    out = await proc(smooth(WINDOW))
    assert len(stub.requests) == n and out["stored"] is True               # backing off: no further calls
    async with database.async_session_factory() as s:
        assert (await s.execute(select(StreamEvent))).scalars().all() == []


@pytest.mark.asyncio
async def test_a_restart_rebuilds_the_windows_from_stored_readings(clean_db):
    stub = Stub(error=0.1)
    first = processor(stub)
    await warm(first, WINDOW)
    second = processor(stub)                                                # new process: empty windows, same database
    out = await second(smooth(WINDOW))
    assert out["provider"]["variables"]["temperature"]["status"] == "scored"


@pytest.mark.asyncio
async def test_with_no_scorer_there_is_no_provider_and_nothing_else_changes(clean_db, monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "SCORER_URL", "")
    proc = ReadingProcessor()
    out = await proc(smooth(0))
    assert "provider" not in out and out["validation_status"] in ("OK", "NO_CHECKS", "NO_DATA", "UNCERTAIN")
    async with database.async_session_factory() as s:
        assert (await s.execute(select(StreamReadingRow))).scalars().all()[0].provider is None
