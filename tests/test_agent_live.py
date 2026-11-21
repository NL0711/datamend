"""The agent's comment on the CURRENT LIVE FEED (scope=live): fake model, real in-process MCP server, SYNTHETIC rows seeded in SQLite. No network, no key."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from backend.app import mcp_gateway
from backend.app.agent import gate as gate_mod, live, service
from backend.app.agent.gemini_model import AgentNotConnected
from backend.app.agent.models import AgentEvent, AgentProposal, AgentTask
from backend.app.agent.policy import READ_ONLY_TOOLS
from backend.app.api import auth as auth_api
from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.stream import live_view, runtime
from backend.app.stream.manager import StreamStatus
from backend.app.stream.models import StreamEvent, StreamReadingRow

ADMIN = "a" * 32
H = {"X-Admin-Token": ADMIN}
ST = "LIVE-T1"
BASE = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
TEXT = ("Station LIVE-T1 is running with source simulator. The window holds 60 stored readings and 2 detections in the window, from the check frozen_value. "
        "The readings are simulated data. A Keras model score is present and it is not validated.")


class FakeSource:
    source_id = "simulator"

    def stations(self):
        return [SimpleNamespace(station_id=ST), SimpleNamespace(station_id="LIVE-BIG")]


class FakeManager:
    """Duck-typed stream manager: only what live_view.source_state reads. `state` can be changed while a task runs."""
    def __init__(self, state="running"):
        self.state, self.active = state, FakeSource()

    def status(self):
        return StreamStatus("simulator", "SIMULATED", self.state, BASE, None, 5.0, 0, None, None, 1.0, 0)


class FakeLiveModel:
    model_id = "fake-live-model"

    def __init__(self, text=TEXT, hook=None):
        self.text, self.hook = text, hook

    def comment(self, state):
        if self.hook:
            self.hook()
        return self.text


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", ADMIN)
    monkeypatch.setattr(settings, "MCP_AUDIT_LOG", str(tmp_path / "mcp_audit.jsonl"))
    auth_api._token_failures.clear()
    mcp_gateway.reset()
    fake = FakeManager()
    monkeypatch.setattr(runtime, "_manager", fake)
    return fake


@pytest.fixture
def manager(_env):
    return _env


async def seed(station=ST, n=80, start_id_hint=None, source="simulated"):
    """SYNTHETIC rows. Reading i of the station; readings 70 and 75 are SUSPECT with an event (75 also carries a Keras provider block)."""
    async with async_session_factory() as s:
        await s.execute(delete(StreamEvent).where(StreamEvent.station_id == station))
        await s.execute(delete(StreamReadingRow).where(StreamReadingRow.station_id == station))
        await s.commit()
        for i in range(n):
            await add_reading(s, station, i, source)
        await s.commit()


async def add_reading(s, station, i, source="simulated"):
    flagged = i in (70, 75)
    row = StreamReadingRow(station_id=station, timestamp=BASE + timedelta(seconds=i), temperature_c=20.0 + (i % 5) * 0.1, pressure_hpa=1012.0, humidity_pct=55.0, rain_mm=0.0,
                           source=source, injected_fault=("frozen" if flagged else None), check_status="SUSPECT" if flagged else "OK", rule_score=0.6 if flagged else 0.0,
                           provider={"model_id": "keras-io/timeseries-anomaly-detection", "revision": "r1", "calibrated": False,
                                     "variables": {"temperature": {"status": "ok", "error": 0.25, "flagged": False}}} if i == 75 else None)
    s.add(row)
    await s.flush()
    if flagged:
        s.add(StreamEvent(reading_id=row.id, station_id=station, timestamp=row.timestamp, variable="temperature", verdict="SUSPECT", rule_score=0.6, severity="medium",
                          classification="frozen_value", is_fault=True, reason="8 identical readings in a row",
                          hits=[{"check": "frozen_value", "layer": "rule", "kind": "fault", "weight": 0.6, "reason": "8 identical readings in a row", "evidence": {"run_length": 8}}],
                          not_run=[{"check": "level_shift", "reason": "needs 80 earlier readings"}], source=source, provider=row.provider))
    return row


@pytest_asyncio.fixture(autouse=True)
async def _clean():
    async with async_session_factory() as s:
        for t in (AgentEvent, AgentTask, AgentProposal):
            await s.execute(delete(t))
        await s.commit()


async def ask_live(c: AsyncClient, monkeypatch, model, station=ST, **extra) -> dict:
    monkeypatch.setattr(service, "build_model", lambda: model)
    r = await c.post("/api/agent/tasks", json={"station_id": station, "request": "Comment on the live feed", "scope": "live", **extra}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- happy path
@pytest.mark.asyncio
async def test_live_comment_happy_path_logs_perception_and_runs_no_action(async_client, monkeypatch):
    await seed()
    out = await ask_live(async_client, monkeypatch, FakeLiveModel())
    assert out["scope"] == "live" and out["status"] == "completed" and out["agent_connected"] is True and out["prototype"] is True
    assert out["comment"] == TEXT and out["explanation_generated"] is True and out["explanation"]["generated"] is True
    assert out["selected"] is None and out["outcome"] is None and out["proposals"] == []
    lv = out["live"]
    assert lv["feed_state_at_perception"] == "running" and lv["feed_state_at_gate"] == "running" and lv["n_readings"] == 60 and lv["detections_in_window"] == 2
    assert lv["last_verdict"] == "OK" and lv["model_score_present"] is True and lv["model_score_label"] == "not validated"
    assert lv["snapshot"]["cutoff_id"] and len(lv["snapshot"]["evidence_hash"]) == 64
    assert out["gate_result"]["ok"] is True and out["baseline_generator"] == "baseline-rules"
    ev = (await async_client.get(f"/api/agent/tasks/{out['task_id']}/events")).json()["events"]
    assert [e["node"] for e in ev] == ["perceive", "decide", "reason", "explain", "gate"]
    assert [c["tool"] for c in ev[0]["tool_calls"]] == ["get_station_stream_v1", "list_stream_detections_v1"] and all(c["ok"] for c in ev[0]["tool_calls"])
    assert ev[0]["tool_calls"][1]["args"]["up_to_id"] == lv["snapshot"]["cutoff_id"]       # detections are read at the same cutoff
    assert "readings" not in json.dumps(ev[0])                                              # the event holds references, not the data


@pytest.mark.asyncio
async def test_run_scope_is_still_the_default_and_a_bad_scope_is_refused(async_client, monkeypatch):
    r = await async_client.post("/api/agent/tasks", json={"station_id": ST, "request": "x", "scope": "everything"}, headers=H)
    assert r.status_code == 422
    monkeypatch.setattr(service, "build_model", lambda: FakeLiveModel())
    r = await async_client.post("/api/agent/tasks", json={"station_id": "NOSUCH", "request": "x"}, headers=H)
    assert r.status_code == 200 and r.json().get("scope") == "live"      # the default scope with no uploaded run for the station falls back to the live feed


@pytest.mark.asyncio
async def test_station_with_no_live_readings_asks_for_clarification(async_client, monkeypatch):
    out = await ask_live(async_client, monkeypatch, FakeLiveModel(), station="LIVE-EMPTY")
    assert out["status"] == "needs_clarification" and "no live readings" in out["abstain_reason"] and out["comment"] is None


# ---------------------------------------------------------------- the immutable snapshot
@pytest.mark.asyncio
async def test_snapshot_hash_is_stable_while_new_readings_arrive_after_the_cutoff(manager):
    await seed()
    async with async_session_factory() as s:
        first = await live_view.feed_view(s, manager, ST, 60)
        cutoff = first["snapshot"]["cutoff_id"]
        for i in range(80, 90):
            await add_reading(s, ST, i)
        await s.commit()
    async with async_session_factory() as s:
        again = await live_view.feed_view(s, manager, ST, 60, up_to_id=cutoff)
        newest = await live_view.feed_view(s, manager, ST, 60)
        dets = await live_view.detections_view(s, manager, ST, 20, cutoff, 60)
        digest = await live_view.snapshot_digest(s, ST, 60, cutoff)
    assert again["snapshot_hash"] == first["snapshot_hash"] == digest == dets["snapshot_hash"] and again["readings"] == first["readings"]
    assert newest["snapshot"]["cutoff_id"] > cutoff and newest["snapshot_hash"] != first["snapshot_hash"]


@pytest.mark.asyncio
async def test_a_reading_after_the_cutoff_does_not_make_the_gate_refuse(async_client, monkeypatch):
    await seed()

    def late():                                           # the feed moves between perception and the gate
        async def go():
            async with async_session_factory() as s:
                await add_reading(s, ST, 200)
                await s.commit()
        asyncio.run_coroutine_threadsafe(go(), loop).result(5)
    loop = asyncio.get_running_loop()
    out = await ask_live(async_client, monkeypatch, FakeLiveModel(hook=late))
    assert out["status"] == "completed" and out["gate_result"]["ok"] is True


def _state_with(feed, dets=None, **over):
    st = live.new_live_state("x", station_id=ST)
    from backend.app.agent.interfaces import evidence_ref_from_result
    from backend.app.agent.service import McpToolBox
    box = McpToolBox(None, ST)
    st["evidence"] = [evidence_ref_from_result("get_station_stream_v1", {"station_id": ST}, box.adapt("get_station_stream_v1", {"station_id": ST}, feed), "ev1")]
    if dets is not None:
        st["evidence"].append(evidence_ref_from_result("list_stream_detections_v1", {"station_id": ST}, box.adapt("list_stream_detections_v1", {"station_id": ST}, dets), "ev2"))
    st["tool_calls"] = [{"tool": e["tool"], "args": {}, "ok": True, "error": ""} for e in st["evidence"]]
    st.update(over)
    return st


FEED = {"station_id": ST, "feed_state": "running", "source_id": "simulator", "cadence_seconds": 1.0, "window": 60, "n_readings": 3, "snapshot": {"cutoff_id": 9, "cutoff_timestamp": "t"},
        "snapshot_hash": "h" * 64, "last_reading_at": "2026-11-21T10:00:02+00:00", "last_verdict": "OK", "counts_by_check_status": {"OK": 3}, "detections_in_window": 0,
        "checks_not_run": [], "model_score": {"present": False}, "readings": [[7, "t", 20.0, None, None, 0.0, "simulated", "OK", 0.0]]}


def test_gate_refuses_when_the_window_re_reads_differently():
    st = _state_with(FEED, status="running", explanation={"text": "x", "generated": True})
    ok = gate_mod.verify_live(st, lambda s, c, w: "h" * 64, lambda s: {"feed_state": "running"})
    assert ok.ok is True
    bad = gate_mod.verify_live(st, lambda s, c, w: "z" * 64, lambda s: {"feed_state": "running"})
    assert bad.ok is False and "fresh_hash" in bad.reason and "changed" in bad.reason
    gone = gate_mod.verify_live(st, lambda s, c, w: None, lambda s: {"feed_state": "running"})
    assert gone.ok is False and "no longer exists" in gone.reason


@pytest.mark.asyncio
async def test_gate_withholds_the_comment_when_the_source_goes_stale_after_perception(async_client, monkeypatch, manager):
    await seed()
    out = await ask_live(async_client, monkeypatch, FakeLiveModel(hook=lambda: setattr(manager, "state", "stale")))
    assert out["status"] == "needs_clarification" and "source_state" in out["abstain_reason"] and "stale" in out["abstain_reason"]
    assert out["comment"] is None and out["explanation"] is None and out["gate_result"]["ok"] is False
    assert out["live"]["feed_state_at_perception"] == "running" and out["live"]["feed_state_at_gate"] == "stale"
    ev = (await async_client.get(f"/api/agent/tasks/{out['task_id']}/events")).json()["events"]
    assert ev[-1]["node"] == "gate" and ev[-1]["gate_result"]["ok"] is False


@pytest.mark.asyncio
async def test_a_feed_that_was_already_stale_is_commented_as_stale(async_client, monkeypatch, manager):
    await seed()
    manager.state = "stale"
    text = "Station LIVE-T1 has a stale feed: no reading has arrived recently. The readings are simulated data. The window holds 60 stored readings."
    out = await ask_live(async_client, monkeypatch, FakeLiveModel(text=text))
    assert out["status"] == "completed" and out["live"]["feed_state_at_perception"] == "stale" and out["live"]["feed_state_at_gate"] == "stale"


# ---------------------------------------------------------------- the guard
@pytest.mark.asyncio
async def test_guard_refuses_an_invented_number_and_an_invented_station(async_client, monkeypatch):
    await seed()
    out = await ask_live(async_client, monkeypatch, FakeLiveModel(text=TEXT.replace("60 stored", "999 stored")))
    assert out["status"] == "explanation_refused" and "number 999" in out["abstain_reason"] and out["comment"] is None and out["gate_result"] is None
    out = await ask_live(async_client, monkeypatch, FakeLiveModel(text=TEXT.replace("LIVE-T1", "LIVE-T9")))
    assert out["status"] == "explanation_refused" and "LIVE-T9" in out["abstain_reason"]


def test_guard_refuses_no_checks_ran_when_readings_carry_verdicts():
    st = _state_with(FEED, status="running")
    bad = live.validate_live_text("Station LIVE-T1 is running and no checks ran in the window.", st)
    assert any("no checks ran" in p for p in bad)
    assert not any("no checks ran" in p for p in live.validate_live_text("Station LIVE-T1 is running. The list of checks that did not run is not available.", st))


def test_guard_refuses_a_model_score_that_is_not_there():
    st = _state_with(FEED, status="running")          # FEED holds no model score
    assert any("holds none" in p for p in live.validate_live_text("Station LIVE-T1 is running. A model score is present, but it is not validated.", st))
    st2 = _state_with({**FEED, "model_score": {"present": True}}, status="running")
    assert not any("holds none" in p for p in live.validate_live_text("Station LIVE-T1 is running. A model score is present, but it is not validated.", st2))


def test_guard_rules_for_simulated_data_and_the_model_score():
    st = _state_with({**FEED, "model_score": {"present": True}}, status="running")
    ok = "Station LIVE-T1 is running. The readings are simulated data. The model score is not validated."
    assert live.validate_live_text(ok, st) == []
    assert not any("does not say so" in p for p in live.validate_live_text("Station LIVE-T1 is running with 3 readings.", st))           # no forced 'simulated' label
    assert any("called real" in p for p in live.validate_live_text("The readings are simulated but these are real measurements.", st))
    assert live.validate_live_text("The readings are simulated, not real measurements.", st) == []
    assert any("not validated" in p for p in live.validate_live_text("The readings are simulated; the Keras model reports a high error.", st))
    assert any("verdict" in p for p in live.validate_live_text("The readings are simulated; the Keras model score is not validated yet confirms a fault verdict.", st))
    assert live.validate_live_text("The readings are simulated. The Keras score is not validated and is not a verdict.", st) == []


@pytest.mark.asyncio
async def test_a_failing_model_never_becomes_a_made_up_comment(async_client, monkeypatch):
    await seed()

    def boom():
        raise RuntimeError("provider down")
    out = await ask_live(async_client, monkeypatch, FakeLiveModel(hook=boom))
    assert out["status"] == "abstained" and "model unavailable" in out["abstain_reason"] and out["comment"] is None


# ---------------------------------------------------------------- no provider
@pytest.mark.asyncio
async def test_no_provider_returns_a_deterministic_rule_based_summary(async_client, monkeypatch):
    await seed()
    monkeypatch.setattr(settings, "AGENT_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    r = await async_client.post("/api/agent/tasks", json={"station_id": ST, "request": "Comment on the live feed", "scope": "live"}, headers=H)
    out = r.json()
    assert r.status_code == 200 and out["status"] == "agent_not_connected" and out["agent_connected"] is False and "agent not connected" in out["agent_not_connected_reason"]
    assert out["comment"] is None and out["explanation"] is None and out["baseline_generator"] == "baseline-rules"
    b = out["baseline_explanation"]
    assert "2 detections in the window" in b and "frozen_value" in b and "feed is running" in b and "simulated" in b and "not validated" in b and "verdict is OK" in b
    ev = (await async_client.get(f"/api/agent/tasks/{out['task_id']}/events")).json()["events"]
    assert [e["node"] for e in ev][0] == "perceive" and ev[2]["model_id"] == "baseline-rules"
    with pytest.raises(AgentNotConnected):
        service.build_model()


# ---------------------------------------------------------------- the MCP tools
def test_tools_are_read_only_bounded_and_pinned():
    from datamend_mcp import security as sec
    from datamend_mcp.tools import ArgumentError, Registry, validate_args
    reg = Registry()
    names = {t["name"] for t in reg.listing()}
    assert {"get_station_stream_v1", "list_stream_detections_v1"} <= names and names == set(READ_ONLY_TOOLS)
    for n in ("get_station_stream_v1", "list_stream_detections_v1"):
        tool = reg.get(n)
        assert tool.annotations["readOnlyHint"] is True and tool.annotations["destructiveHint"] is False and tool.schema["additionalProperties"] is False
        assert sec.scan_definition(tool.listing()) == []
    feed, dets = reg.get("get_station_stream_v1"), reg.get("list_stream_detections_v1")
    assert validate_args(feed.schema, {"station_id": ST})["window"] == 60 and validate_args(dets.schema, {"station_id": ST})["limit"] == 20
    for bad in ({"station_id": ST, "window": 289}, {"station_id": ST, "window": 0}, {"window": 5}, {"station_id": ST, "write": True}, {"station_id": "x" * 65}):
        with pytest.raises(ArgumentError):
            validate_args(feed.schema, bad)
    with pytest.raises(ArgumentError):
        validate_args(dets.schema, {"station_id": ST, "limit": 51})
    sec.verify_manifest(reg.listing(), sec.load_lock(str(mcp_gateway.LOCK_PATH)))      # the pinned lock matches the definitions
    assert {"get_station_stream_v1", "list_stream_detections_v1"} <= set(sec.load_lock(str(mcp_gateway.LOCK_PATH)))


@pytest.mark.asyncio
async def test_tools_through_the_real_mcp_server_are_bounded_audited_and_read_only(async_client, tmp_path):
    await seed("LIVE-BIG", n=300)
    from backend.app.main import app
    server = mcp_gateway.get_server(app, asyncio.get_running_loop())
    client = mcp_gateway.InProcessMcpClient(server)
    loop = asyncio.get_running_loop()
    r = await loop.run_in_executor(None, client.call_tool, "get_station_stream_v1", {"station_id": "LIVE-BIG", "window": 288})
    assert not r["is_error"]
    d = r["structured"]["data"]
    assert d["n_readings"] == 288 == len(d["readings"]) and d["columns"][0] == "id" and "injected_fault" not in json.dumps(d)         # the synthetic label is never shown
    assert len(r["text"].encode()) < 48 * 1024
    big = await loop.run_in_executor(None, client.call_tool, "get_station_stream_v1", {"station_id": "LIVE-BIG", "window": 289})
    assert big["is_error"] and "invalid arguments" in big["text"]
    dd = await loop.run_in_executor(None, client.call_tool, "list_stream_detections_v1", {"station_id": ST, "limit": 5})
    assert not dd["is_error"] and dd["structured"]["data"]["returned"] <= 5
    assert not (await async_client.post("/api/validation/stream/feed", params={"station_id": ST})).status_code == 200      # GET only
    audit = [json.loads(line) for line in open(settings.MCP_AUDIT_LOG, encoding="utf-8")]
    assert any(a.get("tool") == "get_station_stream_v1" and a.get("ok") is True for a in audit) and any(a.get("reason") == "bad_arguments" for a in audit)


@pytest.mark.asyncio
async def test_the_endpoints_bound_their_parameters(async_client):
    assert (await async_client.get("/api/validation/stream/feed", params={"station_id": ST, "window": 289})).status_code == 422
    assert (await async_client.get("/api/validation/stream/detections", params={"station_id": ST, "limit": 51})).status_code == 422
    assert (await async_client.get("/api/validation/stream/feed")).status_code == 422
