"""Training snapshots: a frozen, time-cut export of labelled station-days for ONE offline training run.

Rules (docs/mlops-feedback-loop-spec.md section 9, docs/qc-evaluation-protocol.md):
- nothing after the cut day is in the snapshot (training earlier, validation later, never the future);
- the locked test years 2018 to 2025 are EXCLUDED by default, because those years are scored once at the end; including them needs an explicit
  override and is recorded in the manifest;
- only reviewer decisions are labels. Unreviewed rows are never treated as clean, and proposals never are labels;
- audit items carry their sampling weight; flagged rows reviewed by choice carry weight 1 and are NOT a random sample;
- the content is stored with its hash, so it cannot change after the fact.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings as app_settings
from backend.app.pipeline.models import AuditItem, Correction, PipelineStation, TrainingSnapshot
from backend.app.validation.models import Review, ValidationCheckHit, ValidationResult, ValidationRun

LOCKED_TEST_YEARS = tuple(range(2018, 2026))
LABEL_OF = {"confirmed_fault": "fault", "false_alarm": "clean", "genuine_extreme": "genuine_extreme"}      # needs_followup is not a label
AUDIT_LABEL_OF = {"ok": "clean", "missed_fault": "fault"}                                               # unsure is not a label


async def build(session: AsyncSession, cut: date, exclude_years: Optional[Sequence[int]] = None, allow_test_years: bool = False) -> TrainingSnapshot:
    years = tuple(exclude_years) if exclude_years is not None else (() if allow_test_years else LOCKED_TEST_YEARS)
    runs = (await session.execute(select(ValidationRun.id, ValidationRun.settings).where(ValidationRun.source == "pipeline", ValidationRun.status != "failed"))).all()
    stations = {s.station_key: s for s in (await session.execute(select(PipelineStation))).scalars()}
    rows: List[Dict[str, Any]] = []
    skipped = {"after_cut": 0, "excluded_year": 0, "no_label": 0}
    for run_id, run_settings in runs:
        results = {r.row_ref: r for r in (await session.execute(select(ValidationResult).where(ValidationResult.run_id == run_id))).scalars()}
        corr = {c.row_ref: c for c in (await session.execute(select(Correction).where(Correction.run_id == run_id).order_by(Correction.id))).scalars()}
        hits_by_result: Dict[int, List[str]] = {}
        for rid, chk in (await session.execute(select(ValidationCheckHit.result_id, ValidationCheckHit.check).where(ValidationCheckHit.run_id == run_id))).all():
            hits_by_result.setdefault(rid, []).append(chk)
        labels: Dict[str, Dict[str, Any]] = {}
        for rev in (await session.execute(select(Review).where(Review.run_id == run_id).order_by(Review.id))).scalars():     # newest wins
            if rev.decision in LABEL_OF:
                labels[rev.row_ref] = {"label": LABEL_OF[rev.decision], "weight": 1.0, "label_source": "review", "random_sample": False}
            else:
                labels.pop(rev.row_ref, None)
        for a in (await session.execute(select(AuditItem).where(AuditItem.run_id == run_id, AuditItem.decision.in_(list(AUDIT_LABEL_OF))))).scalars():
            labels[a.row_ref] = {"label": AUDIT_LABEL_OF[a.decision], "weight": a.weight, "label_source": "audit", "random_sample": True}
        for ref, lab in labels.items():
            r = results.get(ref)
            if r is None or not r.time_key:
                continue
            day = date.fromisoformat(r.time_key[:10])
            if day > cut:
                skipped["after_cut"] += 1
                continue
            if day.year in years:
                skipped["excluded_year"] += 1
                continue
            hits = hits_by_result.get(r.id, [])
            st = stations.get(r.station_id)
            c = corr.get(ref)
            rows.append({"run_id": run_id, "row_ref": ref, "station_id": r.station_id, "day": r.time_key[:10],
                         "latitude": st.latitude if st else None, "longitude": st.longitude if st else None,
                         "mm_original": r.mm, "mm_effective": (c.corrected_mm if c is not None else r.mm), "excluded_by_correction": bool(c is not None and c.corrected_mm is None),
                         "verdict": r.verdict, "rule_score": r.rule_score, "checks": sorted(hits), **lab, "label_tier": "real_reviewer"})
    rows.sort(key=lambda x: (x["run_id"], int(x["row_ref"]) if str(x["row_ref"]).isdigit() else 0))
    content = "\n".join(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rows)
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    manifest = {"cut_day": cut.isoformat(), "rows": len(rows), "excluded_years": list(years), "test_years_override": bool(allow_test_years and exclude_years is None),
                "skipped": skipped, "label_counts": {k: sum(1 for r in rows if r["label"] == k) for k in sorted({r["label"] for r in rows})},
                "random_sample_rows": sum(1 for r in rows if r["random_sample"]), "platform_version": app_settings.VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "notes": ["labels are one reviewer's judgements, not ground truth", "reviewed flagged rows are chosen, not random; only audit rows are a random sample",
                          "unreviewed rows are not labelled and are never treated as clean", "station values are derived from hourly observations (sum of reported hours)"]}
    snap = TrainingSnapshot(cut_day=cut.isoformat(), n_rows=len(rows), sha256=sha, manifest=manifest, content=content)
    session.add(snap)
    await session.commit()
    return snap


def snapshot_dict(s: TrainingSnapshot) -> Dict[str, Any]:
    return {"id": s.id, "created_at": s.created_at.isoformat() if s.created_at else None, "cut_day": s.cut_day, "n_rows": s.n_rows, "sha256": s.sha256, "manifest": s.manifest}
