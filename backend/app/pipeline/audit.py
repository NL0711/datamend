"""The audit sample: a random draw of UNFLAGGED station-days that the reviewer checks, so that missed faults can be estimated.

Without it a model retrained on the reviewer's labels only learns to agree with the flags it was shown. Simple random sampling without
replacement: each unflagged day has the same inclusion probability n/N, so its weight is N/n. The estimate of the missed-fault rate is a
weighted proportion with a Wilson interval; it is an estimate for the sampled run, not a property of the checks in general.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pipeline.models import AuditItem
from backend.app.validation.models import ValidationResult, ValidationRun

DECISIONS = ("ok", "missed_fault", "unsure")
MAX_SAMPLE = 500


def audit_dict(a: AuditItem) -> Dict[str, Any]:
    return {"id": a.id, "run_id": a.run_id, "row_ref": a.row_ref, "station_id": a.station_id, "inclusion_probability": a.inclusion_probability,
            "weight": a.weight, "decision": a.decision, "note": a.note, "reviewer": a.reviewer,
            "decided_at": a.decided_at.isoformat() if a.decided_at else None}


async def draw(session: AsyncSession, run_id: int, n: int, seed: Optional[int] = None) -> List[AuditItem]:
    """Draw n unflagged days (verdict OK) that are not already in the sample. The seed makes a draw reproducible."""
    run = await session.get(ValidationRun, run_id)
    if run is None or run.source != "pipeline":
        raise ValueError("the audit sample is drawn from pipeline runs only")
    n = max(1, min(int(n), MAX_SAMPLE))
    existing = list((await session.execute(select(AuditItem).where(AuditItem.run_id == run_id))).scalars())
    taken = {a.row_ref for a in existing}
    ok_rows = [(r.row_ref, r.station_id) for r in (await session.execute(
        select(ValidationResult).where(ValidationResult.run_id == run_id, ValidationResult.verdict == "OK"))).scalars()]
    pool = [x for x in ok_rows if x[0] not in taken]
    if not pool:
        raise ValueError("no unflagged rows left to sample in this run")
    k = min(n, len(pool))
    chosen = random.Random(seed).sample(pool, k)
    items = [AuditItem(run_id=run_id, row_ref=ref, station_id=sid, inclusion_probability=1.0, weight=1.0) for ref, sid in chosen]
    session.add_all(items)
    # Draws without replacement one after another add up to ONE simple random sample of every item drawn so far, so every item (old and new)
    # has the same inclusion probability: all drawn / all unflagged rows. Without this a second draw would carry a wrong weight.
    p = (len(existing) + k) / len(ok_rows)
    for a in existing + items:
        a.inclusion_probability, a.weight = p, 1.0 / p
    await session.commit()
    return items


async def decide(session: AsyncSession, item_id: int, decision: str, reviewer: Optional[str], note: Optional[str] = None) -> AuditItem:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}")
    a = await session.get(AuditItem, item_id)
    if a is None:
        raise LookupError("no such audit item")
    a.decision, a.reviewer, a.note = decision, (reviewer or "").strip()[:60] or None, (note or "").strip()[:1000] or None
    a.decided_at = datetime.now(timezone.utc)
    await session.commit()
    return a


def wilson(k: float, n: float, z: float = 1.96) -> List[float]:
    if n <= 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


async def estimate(session: AsyncSession, run_id: int) -> Dict[str, Any]:
    """The weighted share of audited unflagged days that the reviewer called a missed fault ("unsure" is left out and counted)."""
    items = list((await session.execute(select(AuditItem).where(AuditItem.run_id == run_id))).scalars())
    decided = [a for a in items if a.decision in ("ok", "missed_fault")]
    n = len(decided)
    wsum = sum(a.weight for a in decided)
    wmiss = sum(a.weight for a in decided if a.decision == "missed_fault")
    rate = (wmiss / wsum) if wsum else None
    return {"run_id": run_id, "drawn": len(items), "decided": n, "unsure": sum(1 for a in items if a.decision == "unsure"),
            "missed_faults": sum(1 for a in decided if a.decision == "missed_fault"), "missed_fault_rate": rate,
            "interval_95": wilson(sum(1 for a in decided if a.decision == "missed_fault"), n) if n else None,
            "note": "Estimate for this run only, from a random sample of days the checks called OK, judged by one reviewer. Not ground truth."}
