"""Append-only explanation snapshots, separate from readings and verdicts."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base


class ExplanationRecord(Base):
    __tablename__ = "explanations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(100), index=True)
    row_ref: Mapped[str] = mapped_column(String(200), index=True)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict] = mapped_column(JSON)
    baseline: Mapped[dict] = mapped_column(JSON)
    narrator: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    narrator_status: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


async def save_explanation(session, evidence, baseline, narrator, status):
    record = ExplanationRecord(run_id=evidence.run_id, row_ref=evidence.row_ref,
                               evidence_hash=evidence.digest(), evidence=evidence.model_dump(),
                               baseline=baseline.model_dump(), narrator=narrator.model_dump() if narrator else None,
                               narrator_status=status)
    session.add(record)
    await session.flush()
    return record


def record_response(record):
    return {"id": record.id, "evidence_hash": record.evidence_hash, "evidence": record.evidence,
            "baseline": record.baseline, "narrator": record.narrator,
            "narrator_status": record.narrator_status, "created_at": record.created_at.isoformat()}
