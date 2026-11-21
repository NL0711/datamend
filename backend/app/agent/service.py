"""Agent services (PROTOTYPE of a sandboxed, bounded decision-support agent): the real adapters behind the graph's interfaces, and `run_task`.

  * `McpToolBox`      reads the platform ONLY through the in-process MCP server (read-only tools; the server itself reads the platform with
                      the process-internal READ-ONLY token, never admin credentials) and adapts each result into the shape the graph needs.
  * `SqlEvidenceLookup` the CURRENT evidence hash, computed from the database with the same digest the evidence API uses.
  * `SqlExecutor`     the only writer: it records an allowlisted action as an `agent_proposals` row. It changes no verdict, score, evidence,
                      raw data or setting. Accepting a proposal (a human, admin-gated) is a separate step in the API.
  * `SqlEventLog`     the append-only `agent_events` table (records are redacted first).

The graph is synchronous and runs in a worker thread; these adapters hand their database work back to the event loop (`Bridge`).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Mapping, Optional

from sqlalchemy import select

from backend.app import mcp_gateway as gw
from backend.app.agent import events, policy
from backend.app.agent.gemini_model import AgentNotConnected, GeminiAgentModel
from backend.app.agent.graph import build_agent_graph, result_view
from backend.app.agent.models import AgentEvent, AgentProposal, AgentTask
from backend.app.agent.state import STATUS_ABSTAINED, new_state
from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.validation import narrate, review as review_svc, runs as runs_svc
from backend.app.validation.checks import CATALOGUE
from backend.app.validation.evidence import digest
from backend.app.validation.explain import BaselineExplainer
from backend.app.validation.models import ValidationResult, ValidationRun

logger = logging.getLogger(__name__)
FLAGGED = ("SUSPECT", "UNCERTAIN")
PROTOTYPE_NOTE = "PROTOTYPE of a sandboxed, bounded decision-support agent. It proposes; a human accepts. It never changes a verdict, score, evidence or raw data."


class Bridge:
    """Runs a coroutine on the app's event loop from the graph's worker thread."""
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def run(self, coro: Any, timeout: float = 30.0) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=timeout)


# ------------------------------------------------------------------------------------------------ evidence hashes
def run_hash(run: Mapping[str, Any]) -> str:
    """Hash of the run-level facts the agent reads from a run summary (id, status, rows, stations). A live run that gets new rows changes it."""
    return digest({"id": run.get("id"), "status": run.get("status"), "n_rows": run.get("n_rows"), "n_stations": run.get("n_stations")})


class SqlEvidenceLookup:
    """EvidenceLookup: (station, run, row_ref) -> the hash the evidence has NOW, or None when it no longer exists."""
    def __init__(self, bridge: Bridge) -> None:
        self.bridge = bridge

    def __call__(self, station_id: Any, run_id: Any, row_ref: Any) -> Optional[str]:
        return self.bridge.run(self._hash(run_id, row_ref))

    @staticmethod
    async def _hash(run_id: Any, row_ref: Any) -> Optional[str]:
        if run_id is None:
            return None
        async with async_session_factory() as s:
            run = await s.get(ValidationRun, int(run_id))
            if run is None:
                return None
            if row_ref is None:
                return run_hash({"id": run.id, "status": run.status, "n_rows": run.n_rows, "n_stations": run.n_stations})
            row = await runs_svc.get_row(s, run.id, int(row_ref))
            if row is None:
                return None
            return digest(await narrate.evidence_for_row(s, run, row))


# ------------------------------------------------------------------------------------------------ tools
class McpToolBox:
    """ToolBox over the MCP server (`client.call_tool(name, args) -> {is_error, text, structured}`). Results are adapted for the graph:
    run_id, row_ref, station_id, evidence_hash, source_status ("live" = the run is current: completed or open) and checks."""
    def __init__(self, client: Any, station_id: str) -> None:
        self.client, self.station_id = client, station_id

    def call(self, name: str, args: Mapping[str, Any]) -> Any:
        r = self.client.call_tool(name, dict(args))
        if r.get("is_error"):
            raise RuntimeError(f"MCP tool {name} failed: {r.get('text', '')[:200]}")
        structured = r.get("structured")
        data = structured.get("data") if isinstance(structured, dict) else None
        if data is None:
            try:
                data = json.loads(r.get("text", "")).get("data")
            except ValueError:
                data = None
        if data is None:
            raise RuntimeError(f"MCP tool {name} returned no data")
        return self.adapt(name, args, data)

    def adapt(self, name: str, args: Mapping[str, Any], data: Any) -> dict:
        if name == "get_run_summary" and isinstance(data, dict):
            ok = data.get("status") in ("completed", "open")
            return {**data, "run_id": data.get("id", args.get("run_id")), "row_ref": None, "station_id": self.station_id, "evidence_hash": run_hash(data),
                    "source_status": "live" if ok else str(data.get("status")), "checks": {}}
        if name == "get_evidence_v1" and isinstance(data, dict):
            evs = data.get("evidence") or []
            station = ((evs[0].get("row") or {}).get("station_id") if evs else None) or self.station_id
            return {**data, "run_id": args.get("run_id"), "row_ref": args.get("row_id"), "station_id": station, "evidence_hash": data.get("evidence_hash"),
                    "source_status": "live", "checks": {e.get("check"): "ran" for e in evs if e.get("check")}}
        return data if isinstance(data, dict) else {"value": data}


# ------------------------------------------------------------------------------------------------ the only writer
class SqlExecutor:
    """ActionExecutor: records an allowlisted action as a proposal for a human. Returns {"status": success|refused, "detail"}; a database
    failure raises, which the graph records as an error. Never assumes success."""
    def __init__(self, bridge: Bridge, task_id: str) -> None:
        self.bridge, self.task_id = bridge, task_id

    def execute(self, action: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.bridge.run(self._execute(action, dict(args)))

    async def _execute(self, action: str, args: dict) -> dict:
        pol = policy.check_action(action, args)
        if not pol.ok:
            return {"status": "refused", "detail": f"executor policy check: {pol.reason}"}
        row_ref = None
        async with async_session_factory() as s:
            if action in ("propose_reviewer_label", "add_review_note", "request_checks_rerun"):
                run = await s.get(ValidationRun, int(args["run_id"]))
                if run is None:
                    return {"status": "refused", "detail": f"run {args['run_id']} does not exist"}
                if "row_ref" in args:
                    row = await runs_svc.get_row(s, run.id, int(args["row_ref"]))
                    if row is None or row.station_id != str(args["station_id"]):
                        return {"status": "refused", "detail": "that row is not in the run for that station"}
                    if row.verdict not in FLAGGED:
                        return {"status": "refused", "detail": "only flagged rows (SUSPECT or UNCERTAIN) are reviewed"}
                    row_ref = str(args["row_ref"])
            if action == "propose_reviewer_label" and args["label"] not in review_svc.DECISIONS:
                return {"status": "refused", "detail": f"label must be one of {review_svc.DECISIONS}"}
            p = AgentProposal(task_id=self.task_id, action=action, station_id=str(args["station_id"]) if "station_id" in args else None,
                              run_id=int(args["run_id"]) if "run_id" in args else None, row_ref=row_ref, args=args, status="proposed")
            s.add(p)
            await s.commit()
            return {"status": "success", "detail": f"recorded proposal {p.id} ({action}) for a human to accept; nothing else was changed"}


# ------------------------------------------------------------------------------------------------ event log
class SqlEventLog:
    """EventLog over `agent_events`: insert only. Records are redacted before they are written."""
    def __init__(self, bridge: Bridge, extra_secrets: tuple = ()) -> None:
        self.bridge, self._extra = bridge, extra_secrets

    def append(self, record: dict) -> None:
        clean = events.redact(json.loads(json.dumps(record, default=str)), self._extra)
        self.bridge.run(self._insert(clean))

    @staticmethod
    async def _insert(clean: dict) -> None:
        async with async_session_factory() as s:
            s.add(AgentEvent(task_id=str(clean["task_id"]), step=int(clean["step"]), node=str(clean["node"]), record=clean))
            await s.commit()

    def read_all(self) -> list[dict]:
        async def _all() -> list[dict]:
            async with async_session_factory() as s:
                return [e.record for e in (await s.execute(select(AgentEvent).order_by(AgentEvent.id))).scalars()]
        return self.bridge.run(_all())


async def append_event(record: dict) -> None:
    """Append one record from async code (the not-connected path, a timeout)."""
    await SqlEventLog._insert(events.redact(json.loads(json.dumps(record, default=str)), (settings.GEMINI_API_KEY,)))


# ------------------------------------------------------------------------------------------------ model
def build_model() -> GeminiAgentModel:
    """The configured model, or AgentNotConnected (no provider, no key, package missing). Tests replace this function."""
    provider = settings.AGENT_PROVIDER.strip().lower()
    if provider in ("", "none", "off"):
        raise AgentNotConnected("AGENT_PROVIDER is not set (agent switched off)")
    if provider != "gemini":
        raise AgentNotConnected(f"AGENT_PROVIDER '{provider}' is not supported (only gemini)")
    return GeminiAgentModel(api_key=settings.GEMINI_API_KEY.strip(), model=(settings.AGENT_MODEL.strip() or settings.GEMINI_MODEL.strip()),
                            timeout=min(60.0, settings.AGENT_TIMEOUT_SECONDS), token_budget=settings.AGENT_TOKEN_BUDGET)


def agent_status() -> dict:
    try:
        m = build_model()
        return {"connected": True, "provider": settings.AGENT_PROVIDER, "model": m.model_id, "prototype": True, "note": PROTOTYPE_NOTE, **limits()}
    except AgentNotConnected as e:
        return {"connected": False, "provider": settings.AGENT_PROVIDER, "model": None, "reason": f"agent not connected: {e}", "prototype": True,
                "note": PROTOTYPE_NOTE, **limits()}


def limits() -> dict:
    return {"max_tool_calls": settings.AGENT_MAX_TOOL_CALLS, "token_budget": settings.AGENT_TOKEN_BUDGET, "timeout_seconds": settings.AGENT_TIMEOUT_SECONDS}


# ------------------------------------------------------------------------------------------------ one task
async def pick_target(station_id: str) -> tuple[Optional[int], Optional[int]]:
    """(run id, row id): the newest run that has this station, and its highest-scored flagged row for the station (None when it has none)."""
    async with async_session_factory() as s:
        run_id = (await s.execute(select(ValidationResult.run_id).where(ValidationResult.station_id == station_id).order_by(ValidationResult.run_id.desc()).limit(1))).scalar()
        if run_id is None:
            return None, None
        row_id = (await s.execute(select(ValidationResult.id).where(ValidationResult.run_id == run_id, ValidationResult.station_id == station_id,
                                                                   ValidationResult.verdict.in_(FLAGGED)).order_by(ValidationResult.rule_score.desc()).limit(1))).scalar()
        return int(run_id), (int(row_id) if row_id is not None else None)


async def baseline_text(run_id: Optional[int], row_id: Optional[int]) -> Optional[str]:
    """The rule-based explanation of the first fired check of the row (works with no agent provider)."""
    if run_id is None or row_id is None:
        return None
    async with async_session_factory() as s:
        run, row = await s.get(ValidationRun, run_id), await runs_svc.get_row(s, run_id, row_id)
        if run is None or row is None:
            return None
        evs = await narrate.evidence_for_row(s, run, row)
    return BaselineExplainer.text(evs[0]) if evs else None


async def _save(task_id: str, station_id: str, request: str, view: dict) -> None:
    async with async_session_factory() as s:
        s.add(AgentTask(task_id=task_id, station_id=station_id, request=request, status=str(view.get("status")), result=json.loads(json.dumps(view, default=str))))
        await s.commit()


async def run_task(app: Any, station_id: str, request: str, *, model_factory: Optional[Callable[[], Any]] = None) -> dict:
    """One agent turn for a station. Returns the view the UI shows. The graph runs in a worker thread; this function only wires and stores."""
    import uuid

    from fastapi.concurrency import run_in_threadpool
    task_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    bridge = Bridge(loop)
    run_id, row_id = await pick_target(station_id)
    try:
        model = (model_factory or build_model)()
    except AgentNotConnected as e:
        base = await baseline_text(run_id, row_id)
        reason = f"agent not connected: {e}"
        await append_event(events.step_record(task_id=task_id, step=1, node="input", inputs=[{"station_id": station_id, "run_id": run_id, "row_ref": row_id}], model_id=None,
                                              tool_calls=[], decision={"abstain": reason}, rejected=[], gate_result=None, outcome={"status": "agent_not_connected", "detail": reason},
                                              note="no provider; the rule-based baseline is shown instead"))
        view = {"prototype": True, "note": PROTOTYPE_NOTE, "task_id": task_id, "status": "agent_not_connected", "agent_connected": False, "abstain_reason": reason,
                "explanation": None, "explanation_generated": False, "baseline_explanation": base, "baseline_generator": "baseline-rules" if base else None,
                "selected": None, "rejected_alternatives": [], "gate_result": None, "outcome": None, "tool_call_count": 0}
        await _save(task_id, station_id, request, view)
        return view

    server = gw.get_server(app, loop)
    toolbox = McpToolBox(gw.InProcessMcpClient(server), station_id)
    log = SqlEventLog(bridge, (settings.GEMINI_API_KEY,))
    lookup = SqlEvidenceLookup(bridge)
    graph = build_agent_graph(model, toolbox, SqlExecutor(bridge, task_id), lookup, log, known_checks=tuple(CATALOGUE))
    plan: list = []
    if run_id is not None:
        plan.append(("get_run_summary", {"run_id": run_id}))
        if row_id is not None:
            plan.append(("get_evidence_v1", {"run_id": run_id, "row_id": row_id}))
    state = new_state(request, station_id=station_id, run_id=run_id, row_ref=row_id, max_tool_calls=settings.AGENT_MAX_TOOL_CALLS, perception_plan=plan, task_id=task_id)
    try:
        out = await asyncio.wait_for(run_in_threadpool(graph.invoke, state), timeout=settings.AGENT_TIMEOUT_SECONDS)
        view = {**result_view(out), "note": PROTOTYPE_NOTE, "agent_connected": True, "model_id": getattr(model, "model_id", None)}
    except asyncio.TimeoutError:
        reason = f"timeout after {settings.AGENT_TIMEOUT_SECONDS:g} s; the turn stopped waiting (a step already running may still finish; its events are logged)"
        await append_event(events.step_record(task_id=task_id, step=99, node="timeout", inputs=[], model_id=getattr(model, "model_id", None), tool_calls=[], decision={"abstain": reason},
                                              rejected=[], gate_result=None, outcome={"status": STATUS_ABSTAINED, "detail": reason}, note=reason))
        view = {"prototype": True, "note": PROTOTYPE_NOTE, "task_id": task_id, "status": STATUS_ABSTAINED, "agent_connected": True, "abstain_reason": reason, "explanation": None,
                "explanation_generated": False, "selected": None, "rejected_alternatives": [], "gate_result": None, "outcome": None, "tool_call_count": 0}
    await _save(task_id, station_id, request, view)
    return view
