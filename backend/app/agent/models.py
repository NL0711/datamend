"""Tables of the agent (PROTOTYPE): the append-only event log, the task record, and the proposals a human accepts.

`agent_events` is written only by `SqlEventLog.append` (no update, no delete anywhere in the code). `agent_proposals` holds what the agent's
allowlisted actions produced; nothing in it changes a verdict, score, evidence or raw data. A proposed label becomes a `reviews` row only when an
admin accepts it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentEvent(Base):
    """One structured record per graph step (APPEND-ONLY)."""
    __tablename__ = "agent_events"
    __table_args__ = (Index("ix_agent_events_task_step", "task_id", "step"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64))
    step: Mapped[int] = mapped_column(Integer)
    node: Mapped[str] = mapped_column(String(24))
    record: Mapped[Dict[str, Any]] = mapped_column(JSON)                  # the redacted step record (inputs by reference, no secrets)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    station_id: Mapped[str] = mapped_column(String(64), index=True)
    request: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24))
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)     # graph.result_view: generated text is marked generated
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentProposal(Base):
    __tablename__ = "agent_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(32))
    station_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    row_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    args: Mapped[Dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="proposed")   # proposed | accepted | dismissed
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # the reviews row an accepted label created
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
