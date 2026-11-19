"""The admin review loop: a reviewer works through flagged rows and records a decision on each (spec: reviews are stored separately).

A review NEVER changes a verdict, rule score or evidence; it is one person's judgement, kept with a note. Reviews are keyed by (run,
row_ref), so they survive a live run re-scoring its rows. The summary is explicit about what the counts are not: they cover only the rows
someone chose to review, so they are neither precision nor recall, and they are not ground truth.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.validation.models import Review, ValidationCheckHit, ValidationResult, ValidationRun

DECISIONS = ("confirmed_fault", "false_alarm", "genuine_extreme", "needs_followup")
FLAGGED = ("SUSPECT", "UNCERTAIN")
PAGE = 50
SUMMARY_CAP = 5000
CAVEAT = ("Reviewer decisions on the rows someone chose to review. Not ground truth, not a random sample, so these counts are not "
          "precision or recall and say nothing about how accurate the checks are on real data.")


def review_dict(r: Review) -> Dict[str, Any]:
    return {"id": r.id, "run_id": r.run_id, "row_ref": r.row_ref, "station_id": r.station_id, "decision": r.decision, "note": r.note,
            "reviewer": r.reviewer, "verdict_at_review": r.verdict_at_review, "created_at": r.created_at.isoformat() if r.created_at else None}


async def add_review(session: AsyncSession, row: ValidationResult, decision: str, note: Optional[str], reviewer: Optional[str]) -> Review:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}")
    if row.verdict not in FLAGGED:
        raise ValueError("only flagged rows (SUSPECT or UNCERTAIN) are reviewed")
    rev = Review(run_id=row.run_id, row_ref=row.row_ref, station_id=row.station_id, decision=decision, note=(note or "").strip()[:1000] or None,
                 reviewer=(reviewer or "").strip()[:60] or None, verdict_at_review=row.verdict)
    session.add(rev)
    await session.commit()
    return rev


async def reviews_for_row(session: AsyncSession, run_id: int, row_ref: str) -> List[Review]:
    return list((await session.execute(select(Review).where(Review.run_id == run_id, Review.row_ref == row_ref).order_by(Review.id))).scalars())


async def latest_by_key(session: AsyncSession, keys: List[tuple]) -> Dict[tuple, Review]:
    """The newest review of each (run_id, row_ref)."""
    if not keys:
        return {}
    out: Dict[tuple, Review] = {}
    runs = {k[0] for k in keys}
    refs = {k[1] for k in keys}
    for r in (await session.execute(select(Review).where(Review.run_id.in_(runs), Review.row_ref.in_(refs)).order_by(Review.id))).scalars():
        out[(r.run_id, r.row_ref)] = r                                  # ascending id, so the last one wins
    return {k: v for k, v in out.items() if k in set(keys)}


async def queue(session: AsyncSession, page: int = 1, page_size: int = PAGE, status: str = "unreviewed", verdict: Optional[str] = None,
                check: Optional[str] = None, run_id: Optional[int] = None, synthetic: Optional[bool] = None) -> Dict[str, Any]:
    """Flagged rows across every run (not rejected uploads), highest rule score first, with their review state. status is
    unreviewed (default), reviewed or all."""
    page_size, page = max(1, min(page_size, PAGE)), max(1, page)
    has_review = exists(select(Review.id).where(Review.run_id == ValidationResult.run_id, Review.row_ref == ValidationResult.row_ref))
    q = (select(ValidationResult, ValidationRun.label, ValidationRun.synthetic, ValidationRun.source)
         .join(ValidationRun, ValidationRun.id == ValidationResult.run_id)
         .where(ValidationRun.status != "failed", ValidationResult.verdict.in_(FLAGGED)))
    if verdict:
        q = q.where(ValidationResult.verdict == verdict)
    if run_id is not None:
        q = q.where(ValidationResult.run_id == run_id)
    if synthetic is not None:
        q = q.where(ValidationRun.synthetic == synthetic)
    if status == "unreviewed":
        q = q.where(~has_review)
    elif status == "reviewed":
        q = q.where(has_review)
    if check:
        q = q.where(ValidationResult.id.in_(select(ValidationCheckHit.result_id).where(ValidationCheckHit.check == check)))
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await session.execute(q.order_by(ValidationResult.rule_score.desc(), ValidationResult.run_id.desc(), ValidationResult.position)
                                  .limit(page_size).offset((page - 1) * page_size))).all()
    names: Dict[int, List[str]] = defaultdict(list)
    if rows:
        for rid, name in (await session.execute(select(ValidationCheckHit.result_id, ValidationCheckHit.check).where(
                ValidationCheckHit.result_id.in_([r[0].id for r in rows])))).all():
            names[rid].append(name)
    latest = await latest_by_key(session, [(r[0].run_id, r[0].row_ref) for r in rows])
    items = []
    for res, label, syn, source in rows:
        rev = latest.get((res.run_id, res.row_ref))
        items.append({"id": res.id, "run_id": res.run_id, "run_label": label, "synthetic": syn, "source": source, "row_ref": res.row_ref,
                      "station_id": res.station_id, "time": res.time_key, "verdict": res.verdict, "rule_score": res.rule_score,
                      "severity": res.severity, "checks": names.get(res.id, []), "review": review_dict(rev) if rev else None})
    return {"page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size, "status": status, "rows": items}


async def summary(session: AsyncSession) -> Dict[str, Any]:
    flagged = (await session.execute(select(func.count()).select_from(ValidationResult).join(ValidationRun, ValidationRun.id == ValidationResult.run_id)
                                     .where(ValidationRun.status != "failed", ValidationResult.verdict.in_(FLAGGED)))).scalar_one()
    revs = list((await session.execute(select(Review).order_by(Review.id.desc()).limit(SUMMARY_CAP))).scalars())
    latest: Dict[tuple, Review] = {}
    for r in revs:                                                       # newest first: keep the first seen per row
        latest.setdefault((r.run_id, r.row_ref), r)
    by_decision = Counter(r.decision for r in latest.values())
    by_check: Dict[str, Counter] = defaultdict(Counter)
    if latest:
        keys = set(latest)
        rows = (await session.execute(select(ValidationResult.id, ValidationResult.run_id, ValidationResult.row_ref)
                                      .where(ValidationResult.run_id.in_({k[0] for k in keys})))).all()
        rid_to_key = {rid: (run, ref) for rid, run, ref in rows if (run, ref) in keys}
        if rid_to_key:
            for rid, check in (await session.execute(select(ValidationCheckHit.result_id, ValidationCheckHit.check)
                                                     .where(ValidationCheckHit.result_id.in_(list(rid_to_key))))).all():
                by_check[check][latest[rid_to_key[rid]].decision] += 1
    return {"flagged_rows": flagged, "reviewed_rows": len(latest), "unreviewed_rows": max(0, flagged - len(latest)),
            "by_decision": {d: by_decision.get(d, 0) for d in DECISIONS},
            "by_check": {c: {d: cnt.get(d, 0) for d in DECISIONS} for c, cnt in sorted(by_check.items())},
            "truncated": len(revs) >= SUMMARY_CAP, "caveat": CAVEAT}
