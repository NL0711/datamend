"""Proposals: suggested corrections for flagged station-days, and the reviewer's decision on each.

A proposal is generated text plus a suggested value. It changes nothing. Accepting it stores a correction (the original value stays beside
it, observations are never touched) and records the reviewer's decision as a label; rejecting it only closes the proposal. The baseline
proposer is rule based. The LLM proposer is the narrator team's service and is NOT IMPLEMENTED here: it would be a second ``Proposer``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pipeline.models import Correction, Proposal
from backend.app.validation import checks
from backend.app.validation.models import Review, ValidationCheckHit, ValidationResult, ValidationRun
from backend.app.validation.review import FLAGGED

BASELINE = "baseline-rules"


class Proposer(Protocol):
    name: str

    def propose(self, result: ValidationResult, hits: List[ValidationCheckHit]) -> List[Dict[str, Any]]: ...


class BaselineProposer:
    """Plain rules, no model. Each proposal says what it is based on."""
    name = BASELINE

    def propose(self, result: ValidationResult, hits: List[ValidationCheckHit]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        names = {h.check for h in hits}
        mm = result.mm
        if "impossible_value" in names:
            out.append({"kind": "exclude_value", "original_mm": mm, "proposed_mm": None,
                        "text": f"The daily total of {mm:g} mm is outside what is physically possible (0 to {checks.DAILY_MAX_MM:g} mm). Suggested: treat it as no data. "
                                "The original value is kept."})
        peak = (result.original_row or {}).get("max_hour_mm")
        if isinstance(peak, (int, float)) and peak > checks.INTENSITY_CEILING:
            out.append({"kind": "review_peak", "original_mm": mm, "proposed_mm": None,
                        "text": f"One hour of this day is {peak:g} mm, above the {checks.INTENSITY_CEILING:g} mm per hour ceiling used for readings. "
                                "Check the gauge and the neighbouring stations; if it is a transmission error, exclude the value."})
        if "repeated_value" in names:
            out.append({"kind": "review_repeat", "original_mm": mm, "proposed_mm": None,
                        "text": "The same positive total repeats on consecutive days, which can mean a stuck or re-sent value. Check the source before accepting it."})
        return out


PROPOSERS: Dict[str, Proposer] = {BASELINE: BaselineProposer()}


def proposal_dict(p: Proposal) -> Dict[str, Any]:
    return {"id": p.id, "run_id": p.run_id, "row_ref": p.row_ref, "station_id": p.station_id, "kind": p.kind, "original_mm": p.original_mm,
            "proposed_mm": p.proposed_mm, "text": p.text, "generator": p.generator, "generated": True, "label": "generated, not a decision",
            "status": p.status, "decided_by": p.decided_by, "decided_at": p.decided_at.isoformat() if p.decided_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None}


async def generate(session: AsyncSession, run_id: int, generator: str = BASELINE) -> List[Proposal]:
    """Create proposals for the flagged rows of a run. Repeating it never duplicates a proposal (same row and kind)."""
    run = await session.get(ValidationRun, run_id)
    if run is None or run.source != "pipeline":
        raise ValueError("proposals are made for pipeline runs only")
    if generator not in PROPOSERS:
        raise ValueError(f"unknown generator {generator!r}; available: {sorted(PROPOSERS)} (the LLM proposer is NOT IMPLEMENTED)")
    proposer = PROPOSERS[generator]
    existing = {(p.row_ref, p.kind) for p in (await session.execute(select(Proposal).where(Proposal.run_id == run_id))).scalars()}
    rows = (await session.execute(select(ValidationResult).where(ValidationResult.run_id == run_id, ValidationResult.verdict.in_(FLAGGED)))).scalars().all()
    made: List[Proposal] = []
    for r in rows:
        hits = list((await session.execute(select(ValidationCheckHit).where(ValidationCheckHit.result_id == r.id))).scalars())
        for d in proposer.propose(r, hits):
            if (r.row_ref, d["kind"]) in existing:
                continue
            p = Proposal(run_id=run_id, row_ref=r.row_ref, station_id=r.station_id, generator=generator, **d)
            session.add(p)
            made.append(p)
    await session.commit()
    return made


async def decide(session: AsyncSession, proposal_id: int, accept: bool, reviewer: Optional[str], note: Optional[str] = None,
                 corrected_mm: Optional[float] = None) -> Proposal:
    """Accept or reject a pending proposal. Accepting an ``exclude_value`` stores a correction (corrected value None = excluded) and a
    'confirmed_fault' decision (so does accepting with an explicit corrected value); accepting a review_* proposal only closes it: it suggests
    no value and is NOT a fault label."""
    p = await session.get(Proposal, proposal_id)
    if p is None:
        raise LookupError("no such proposal")
    if p.status != "pending":
        raise ValueError(f"proposal already {p.status}")
    p.status = "accepted" if accept else "rejected"
    p.decided_by = (reviewer or "").strip()[:60] or None
    p.decided_at = datetime.now(timezone.utc)
    if accept:
        result = (await session.execute(select(ValidationResult).where(ValidationResult.run_id == p.run_id, ValidationResult.row_ref == p.row_ref))).scalars().first()
        if p.kind == "exclude_value" or corrected_mm is not None:
            session.add(Correction(run_id=p.run_id, row_ref=p.row_ref, station_id=p.station_id, original_mm=p.original_mm,
                                   corrected_mm=corrected_mm, proposal_id=p.id, reviewer=p.decided_by, note=(note or "")[:1000] or None))
        # only a proposal that removes or replaces the value confirms a fault; 'review_peak' and 'review_repeat' only say "check this"
        confirms_fault = p.kind == "exclude_value" or corrected_mm is not None
        if confirms_fault and result is not None and result.verdict in FLAGGED:
            session.add(Review(run_id=p.run_id, row_ref=p.row_ref, station_id=p.station_id, decision="confirmed_fault",
                               note=f"accepted proposal {p.id} ({p.kind})", reviewer=p.decided_by, verdict_at_review=result.verdict))
    await session.commit()
    return p


async def effective_mm(session: AsyncSession, run_id: int) -> Dict[str, Optional[float]]:
    """row_ref -> the value to use after accepted corrections (None = excluded). Rows without a correction are absent."""
    out: Dict[str, Optional[float]] = {}
    for c in (await session.execute(select(Correction).where(Correction.run_id == run_id).order_by(Correction.id))).scalars():
        out[c.row_ref] = c.corrected_mm
    return out
