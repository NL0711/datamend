"""The agent's real adapters and API, with a FAKE model (no network, no key). Tools are the real in-process MCP server over a throwaway SQLite
database; the data is a small SYNTHETIC upload."""
import asyncio
import io
import time

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, func, select

from backend.app import mcp_gateway
from backend.app.agent import service
from backend.app.agent.gemini_model import AgentNotConnected, GeminiAgentModel, TokenBudgetExceeded
from backend.app.agent.models import AgentEvent, AgentProposal, AgentTask
from backend.app.agent.service import McpToolBox, SqlEventLog, run_hash
from backend.app.agent.state import Candidate
from backend.app.api import auth as auth_api
from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.validation.models import Review
from tests.test_agent_fakes import FakeModel

ADMIN = "a" * 32
H = {"X-Admin-Token": ADMIN}
DAILY = "station_id,day,mm\n" + "\n".join(f"S1,2026-03-{d:02d},{0.0 if d != 5 else -1.0}" for d in range(1, 11)) + "\n"      # SYNTHETIC; a negative day is flagged


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", ADMIN)
    monkeypatch.setattr(settings, "MCP_AUDIT_LOG", str(tmp_path / "mcp_audit.jsonl"))
    auth_api._token_failures.clear()
    mcp_gateway.reset()


@pytest_asyncio.fixture(autouse=True)
async def _clean():
    async with async_session_factory() as s:
        for t in (AgentEvent, AgentTask, AgentProposal):
            await s.execute(delete(t))
        await s.commit()


async def upload(c: AsyncClient) -> tuple[int, int]:
    r = await c.post("/api/validation/runs", data={"profile": "daily", "synthetic": "true"}, files={"file": ("d.csv", io.BytesIO(DAILY.encode()), "text/csv")}, headers=H)
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    rows = (await c.get(f"/api/validation/runs/{run_id}/rows")).json()["rows"]
    assert rows, "the synthetic upload should have a flagged row"
    return run_id, rows[0]["id"]


def label_model(run_id: int, row_id: int, label: str = "false_alarm") -> FakeModel:
    cand = Candidate("propose_reviewer_label", {"run_id": run_id, "row_ref": row_id, "station_id": "S1", "label": label}, "the negative value is an impossible reading")
    return FakeModel([cand], text=f"Run {run_id} row {row_id} at station S1 was flagged; a reviewer label is proposed for a human to accept.")


async def ask(c: AsyncClient, monkeypatch, model, station="S1") -> dict:
    monkeypatch.setattr(service, "build_model", lambda: model)
    r = await c.post("/api/agent/tasks", json={"station_id": station, "request": "Why is the latest flag at this station there?"}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- the adapter
def test_toolbox_adapts_run_summary_and_evidence():
    class C:
        def call_tool(self, name, args):
            if name == "get_run_summary":
                d = {"id": 3, "status": "completed", "n_rows": 10, "n_stations": 1, "not_run": [{"check": "neighbour", "reason": "x"}]}
            else:
                d = {"schema": "evidence-v1", "evidence": [{"check": "impossible_value", "row": {"station_id": "S1"}}], "evidence_hash": "h" * 64}
            return {"is_error": False, "text": "", "structured": {"data": d}}
    box = McpToolBox(C(), "S1")
    s = box.call("get_run_summary", {"run_id": 3})
    assert s["run_id"] == 3 and s["station_id"] == "S1" and s["source_status"] == "live" and s["evidence_hash"] == run_hash({"id": 3, "status": "completed", "n_rows": 10, "n_stations": 1})
    e = box.call("get_evidence_v1", {"run_id": 3, "row_id": 9})
    assert e["row_ref"] == 9 and e["evidence_hash"] == "h" * 64 and e["checks"] == {"impossible_value": "ran"} and e["station_id"] == "S1"


def test_toolbox_raises_on_an_mcp_error_and_never_invents_a_result():
    class C:
        def call_tool(self, name, args):
            return {"is_error": True, "text": "the DataMend platform said: run 9 not found", "structured": None}
    with pytest.raises(RuntimeError, match="not found"):
        McpToolBox(C(), "S1").call("get_run_summary", {"run_id": 9})


# ---------------------------------------------------------------- the API, end to end
@pytest.mark.asyncio
async def test_task_proposes_a_label_logs_every_step_and_a_human_accepts(async_client: AsyncClient, monkeypatch):
    run_id, row_id = await upload(async_client)
    async with async_session_factory() as s:
        before = (await s.execute(select(func.count()).select_from(Review))).scalar_one()
    out = await ask(async_client, monkeypatch, label_model(run_id, row_id))
    assert out["status"] == "completed" and out["prototype"] is True and out["agent_connected"] is True
    assert out["explanation_generated"] is True and out["explanation"]["generated"] is True
    assert out["outcome"]["status"] == "success" and out["gate_result"]["ok"] is True
    assert len(out["proposals"]) == 1 and out["proposals"][0]["status"] == "proposed" and out["proposals"][0]["generated"] is True
    async with async_session_factory() as s:
        assert (await s.execute(select(func.count()).select_from(Review))).scalar_one() == before      # nothing reached the review records yet

    ev = (await async_client.get(f"/api/agent/tasks/{out['task_id']}/events")).json()
    assert ev["append_only"] is True and [e["node"] for e in ev["events"]] == ["perceive", "reason", "decide", "explain", "gate", "act"]
    perceive = ev["events"][0]
    assert [c["tool"] for c in perceive["tool_calls"]] == ["get_run_summary", "get_evidence_v1"] and all(c["ok"] for c in perceive["tool_calls"])

    pid = out["proposals"][0]["id"]
    assert (await async_client.post(f"/api/agent/proposals/{pid}/accept")).status_code in (401, 403)       # a human decision needs the admin sign-in
    acc = await async_client.post(f"/api/agent/proposals/{pid}/accept", headers=H)
    assert acc.status_code == 200 and acc.json()["status"] == "accepted" and acc.json()["review_id"]
    async with async_session_factory() as s:
        rev = await s.get(Review, acc.json()["review_id"])
        assert rev.decision == "false_alarm" and rev.run_id == run_id
    assert (await async_client.post(f"/api/agent/proposals/{pid}/accept", headers=H)).status_code == 409


@pytest.mark.asyncio
async def test_a_verdict_word_is_not_a_label_policy_rejects_it(async_client: AsyncClient, monkeypatch):
    run_id, row_id = await upload(async_client)
    out = await ask(async_client, monkeypatch, label_model(run_id, row_id, label="SUSPECT"))      # what a real model first answered in the live check
    assert out["status"] == "abstained" and "label must be one of" in out["rejected_alternatives"][0]["reason"]
    assert (await async_client.get("/api/agent/proposals")).json()["proposals"] == []


@pytest.mark.asyncio
async def test_executor_refuses_a_missing_run_and_records_the_refusal_as_real_outcome(async_client: AsyncClient, monkeypatch):
    run_id, row_id = await upload(async_client)
    ex = service.SqlExecutor(service.Bridge(asyncio.get_running_loop()), "t-exec")
    res = await asyncio.get_running_loop().run_in_executor(None, ex.execute, "propose_reviewer_label", {"run_id": 999999, "row_ref": 1, "station_id": "S1", "label": "false_alarm"})
    assert res["status"] == "refused" and "does not exist" in res["detail"]
    res = await asyncio.get_running_loop().run_in_executor(None, ex.execute, "change_verdict", {"run_id": run_id})
    assert res["status"] == "refused"
    assert (await async_client.get("/api/agent/proposals?task_id=t-exec")).json()["proposals"] == []


@pytest.mark.asyncio
async def test_forbidden_action_is_rejected_by_policy_and_nothing_is_written(async_client: AsyncClient, monkeypatch):
    run_id, row_id = await upload(async_client)
    model = FakeModel([Candidate("change_verdict", {"run_id": run_id, "row_ref": row_id, "station_id": "S1", "verdict": "OK"}, "x")])
    out = await ask(async_client, monkeypatch, model)
    assert out["status"] == "abstained" and out["outcome"] is None
    assert [e["node"] for e in (await async_client.get(f"/api/agent/tasks/{out['task_id']}/events")).json()["events"]][-1] == "abstain"
    assert out["rejected_alternatives"] and "verdict" in out["rejected_alternatives"][0]["reason"]
    assert (await async_client.get("/api/agent/proposals")).json()["proposals"] == []


@pytest.mark.asyncio
async def test_station_with_no_run_asks_for_clarification(async_client: AsyncClient, monkeypatch):
    out = await ask(async_client, monkeypatch, FakeModel([Candidate("ask_user", {"question": "Which file should I look at?"}, "no data")]), station="NOSUCH-STATION")
    assert out["status"] == "needs_clarification" and "no evidence" in out["abstain_reason"]


@pytest.mark.asyncio
async def test_no_provider_says_agent_not_connected_and_the_baseline_still_explains(async_client: AsyncClient, monkeypatch):
    run_id, row_id = await upload(async_client)
    monkeypatch.setattr(settings, "AGENT_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    st = (await async_client.get("/api/agent/status")).json()
    assert st["connected"] is False and "agent not connected" in st["reason"] and st["prototype"] is True and st["max_tool_calls"] == 6
    r = await async_client.post("/api/agent/tasks", json={"station_id": "S1", "request": "explain"}, headers=H)
    out = r.json()
    assert r.status_code == 200 and out["status"] == "agent_not_connected" and out["agent_connected"] is False
    assert out["baseline_generator"] == "baseline-rules" and "S1" in out["baseline_explanation"] and out["explanation"] is None
    ev = (await async_client.get(f"/api/agent/tasks/{out['task_id']}/events")).json()["events"]
    assert ev[0]["outcome"]["status"] == "agent_not_connected"


@pytest.mark.asyncio
async def test_provider_none_is_not_connected(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_PROVIDER", "none")
    with pytest.raises(AgentNotConnected):
        service.build_model()


@pytest.mark.asyncio
async def test_task_needs_the_admin_sign_in(async_client: AsyncClient):
    r = await async_client.post("/api/agent/tasks", json={"station_id": "S1", "request": "x"})
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_turn_timeout_is_recorded(async_client: AsyncClient, monkeypatch):
    run_id, row_id = await upload(async_client)

    class Slow(FakeModel):
        def propose(self, state, tools):
            time.sleep(0.6)
            return super().propose(state, tools)
    monkeypatch.setattr(settings, "AGENT_TIMEOUT_SECONDS", 0.15)
    out = await ask(async_client, monkeypatch, Slow([Candidate("ask_user", {"question": "q?"}, "r")]))
    assert out["status"] == "abstained" and "timeout" in out["abstain_reason"]
    await asyncio.sleep(1.0)                                    # let the abandoned worker finish its writes before the next test
    nodes = [e["node"] for e in (await async_client.get(f"/api/agent/tasks/{out['task_id']}/events")).json()["events"]]
    assert "timeout" in nodes


# ---------------------------------------------------------------- the event log
@pytest.mark.asyncio
async def test_sql_event_log_is_insert_only_and_redacts():
    log = SqlEventLog(service.Bridge(asyncio.get_running_loop()), ("my-real-secret-value",))
    assert not any(hasattr(log, n) for n in ("update", "delete", "remove", "clear"))
    await log.bridge.loop.run_in_executor(None, log.append, {"task_id": "t1", "step": 1, "node": "perceive", "note": "leak my-real-secret-value AIzaSyA1234567890abcdefghijklmnopqrstuv", "api_key": "zzz"})
    async with async_session_factory() as s:
        rec = (await s.execute(select(AgentEvent).where(AgentEvent.task_id == "t1"))).scalars().one().record
    assert "my-real-secret-value" not in str(rec) and "AIza" not in str(rec) and "zzz" not in str(rec)


# ---------------------------------------------------------------- token budget
def test_token_budget_refuses_oversized_evidence_instead_of_cutting_it():
    m = GeminiAgentModel(api_key="test-key-not-real-0000", model="made-up-model-name", token_budget=50)
    state = {"objective": "x", "constraints": {}, "evidence": [{"ref_id": "ev1", "result": {"text": "y" * 2000}}]}
    with pytest.raises(TokenBudgetExceeded):
        m.propose(state, None)
