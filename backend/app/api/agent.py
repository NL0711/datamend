"""The agent's API (PROTOTYPE of a sandboxed, bounded decision-support agent). Routes only call the services in `backend/app/agent/service.py`.

  * ``GET  /api/agent/status``               connected or "agent not connected", provider, model, limits.
  * ``POST /api/agent/tasks``                ask about a station (admin): runs the graph once, returns the generated answer and what was proposed.
  * ``GET  /api/agent/tasks``                recent tasks (optionally one station).
  * ``GET  /api/agent/tasks/{id}/events``    the append-only event log of one task (the "why" view).
  * ``GET  /api/agent/proposals``            proposals the agent's actions recorded; ``POST .../{id}/accept|dismiss`` (admin) is the human decision.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import mcp_gateway as gw
from backend.app.agent import service
from backend.app.agent.models import AgentEvent, AgentProposal, AgentTask
from backend.app.api.settings import require_admin
from backend.app.db.database import get_db
from backend.app.validation import review as review_svc, runs as runs_svc

router = APIRouter(prefix="/api/agent", tags=["agent"])


class TaskRequest(BaseModel):
    station_id: str = Field(min_length=1, max_length=64)
    request: str = Field(min_length=1, max_length=1000)
    scope: Literal["run", "live"] = "run"       # run: the newest stored run of the station (default); live: the current live feed of the station
    window: Optional[int] = Field(None, ge=1, le=288)       # live only: how many of the newest readings to read (default 60)


def _proposal(p: AgentProposal) -> Dict[str, Any]:
    return {"id": p.id, "task_id": p.task_id, "action": p.action, "station_id": p.station_id, "run_id": p.run_id, "row_ref": p.row_ref, "args": p.args,
            "status": p.status, "review_id": p.review_id, "created_at": p.created_at.isoformat() if p.created_at else None,
            "decided_at": p.decided_at.isoformat() if p.decided_at else None, "generated": True,
            "note": "proposed by the agent (generated); it takes effect only when a human accepts it"}


@router.get("/status")
async def agent_status() -> Dict[str, Any]:
    return service.agent_status()


@router.post("/tasks", dependencies=[Depends(require_admin)])
async def create_task(body: TaskRequest, request: Request, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    if not gw.AVAILABLE:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "the MCP service files (mcp-service/) are not installed; the agent reads only through MCP")
    if body.scope == "live":
        view = await service.run_live_task(request.app, body.station_id.strip(), body.request.strip(), window=body.window or 60)
        return {**view, "proposals": []}
    view = await service.run_task(request.app, body.station_id.strip(), body.request.strip())
    props = (await session.execute(select(AgentProposal).where(AgentProposal.task_id == view["task_id"]).order_by(AgentProposal.id))).scalars()
    return {**view, "proposals": [_proposal(p) for p in props]}


@router.get("/tasks")
async def list_tasks(station_id: Optional[str] = Query(None, max_length=64), limit: int = Query(10, ge=1, le=50), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    q = select(AgentTask).order_by(AgentTask.created_at.desc()).limit(limit)
    if station_id:
        q = q.where(AgentTask.station_id == station_id)
    return {"tasks": [{"task_id": t.task_id, "station_id": t.station_id, "request": t.request, "status": t.status, "created_at": t.created_at.isoformat(), "result": t.result}
                      for t in (await session.execute(q)).scalars()]}


@router.get("/tasks/{task_id}/events")
async def task_events(task_id: str, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    rows = list((await session.execute(select(AgentEvent).where(AgentEvent.task_id == task_id).order_by(AgentEvent.step, AgentEvent.id))).scalars())
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no events for task {task_id}")
    return {"task_id": task_id, "append_only": True, "events": [{"id": e.id, **e.record} for e in rows]}


@router.get("/proposals")
async def list_proposals(station_id: Optional[str] = Query(None, max_length=64), task_id: Optional[str] = Query(None, max_length=64),
                         session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    q = select(AgentProposal).order_by(AgentProposal.id.desc()).limit(100)
    if station_id:
        q = q.where(AgentProposal.station_id == station_id)
    if task_id:
        q = q.where(AgentProposal.task_id == task_id)
    return {"proposals": [_proposal(p) for p in (await session.execute(q)).scalars()]}


async def _open_proposal(session: AsyncSession, proposal_id: int) -> AgentProposal:
    p = await session.get(AgentProposal, proposal_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"proposal {proposal_id} not found")
    if p.status != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, f"proposal {proposal_id} is already {p.status}")
    return p


@router.post("/proposals/{proposal_id}/accept", dependencies=[Depends(require_admin)])
async def accept_proposal(proposal_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """A human accepts a proposal. A proposed label becomes a review (a separate record: no verdict, score or evidence changes); the others are marked accepted."""
    p = await _open_proposal(session, proposal_id)
    if p.action == "propose_reviewer_label":
        row = await runs_svc.get_row(session, int(p.run_id), int(p.row_ref)) if p.run_id is not None and p.row_ref is not None else None
        if row is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "the row of this proposal no longer exists")
        try:
            rev = await review_svc.add_review(session, row, str(p.args["label"]), p.args.get("note"), "agent proposal, accepted by admin")
        except ValueError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
        p.review_id = rev.id
    p.status, p.decided_at = "accepted", datetime.now(timezone.utc)
    await session.commit()
    return _proposal(p)


@router.post("/proposals/{proposal_id}/dismiss", dependencies=[Depends(require_admin)])
async def dismiss_proposal(proposal_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    p = await _open_proposal(session, proposal_id)
    p.status, p.decided_at = "dismissed", datetime.now(timezone.utc)
    await session.commit()
    return _proposal(p)
