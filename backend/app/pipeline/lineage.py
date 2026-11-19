"""The lineage of everything the platform stores, as a graph: ingest job -> checking run -> snapshot -> training job -> model (with its gate).

Read-only and built from the tables that already exist, so it can never disagree with them. Row-level lineage (a flagged day -> its evidence ->
the raw hours -> its proposal and label) stays in the run view; this graph is the stage-level story.
"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pipeline.models import AuditItem, Correction, IngestJob, ModelVersion, Proposal, TrainingJob, TrainingSnapshot
from backend.app.validation.models import Review, ValidationResult, ValidationRun

COLUMNS = ("job", "run", "snapshot", "train", "model")


async def _count(session: AsyncSession, model, *where) -> int:
    return (await session.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def build(session: AsyncSession) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []

    def edge(a: str, b: str) -> None:
        edges.append({"from": a, "to": b})

    jobs = (await session.execute(select(IngestJob).order_by(IngestJob.id))).scalars().all()
    for j in jobs:
        nodes.append({"id": f"job:{j.id}", "kind": "job", "label": j.filename, "status": j.status,
                      "facts": {"source": j.source, "rows stored": j.rows_inserted, "already stored": j.rows_duplicate, "bad rows": j.rows_bad, "stations": j.stations}})
    runs = (await session.execute(select(ValidationRun).where(ValidationRun.source == "pipeline").order_by(ValidationRun.id))).scalars().all()
    for r in runs:
        flagged = await _count(session, ValidationResult, ValidationResult.run_id == r.id, ValidationResult.verdict.in_(("SUSPECT", "UNCERTAIN")))
        nodes.append({"id": f"run:{r.id}", "kind": "run", "label": f"run {r.id}", "status": r.status, "run_id": r.id,
                      "facts": {"station-days": r.n_rows, "flagged": flagged, "proposals": await _count(session, Proposal, Proposal.run_id == r.id),
                                "corrections": await _count(session, Correction, Correction.run_id == r.id), "reviews": await _count(session, Review, Review.run_id == r.id),
                                "audit drawn": await _count(session, AuditItem, AuditItem.run_id == r.id)}})
    for j in jobs:
        if j.run_id is not None:
            edge(f"job:{j.id}", f"run:{j.run_id}")
    snaps = (await session.execute(select(TrainingSnapshot).order_by(TrainingSnapshot.id))).scalars().all()
    for s in snaps:
        nodes.append({"id": f"snapshot:{s.id}", "kind": "snapshot", "label": f"snapshot {s.id}", "status": "frozen",
                      "facts": {"cut day": s.cut_day, "rows": s.n_rows, "labels": ", ".join(f"{k} {v}" for k, v in (s.manifest or {}).get("label_counts", {}).items()) or "none",
                                "sha256": s.sha256[:12]}})
        for rid in (s.manifest or {}).get("runs", []):
            edge(f"run:{rid}", f"snapshot:{s.id}")
    tjobs = (await session.execute(select(TrainingJob).order_by(TrainingJob.id))).scalars().all()
    for t in tjobs:
        nodes.append({"id": f"train:{t.id}", "kind": "train", "label": f"training {t.id} ({t.target})", "status": t.status,
                      "facts": {"target": t.target, "notebook": t.slug or "-", "error": t.error or "-"}})
        edge(f"snapshot:{t.snapshot_id}", f"train:{t.id}")
    models = (await session.execute(select(ModelVersion).order_by(ModelVersion.id))).scalars().all()
    for m in models:
        gate = m.gate or {}
        nodes.append({"id": f"model:{m.id}", "kind": "model", "label": f"{m.name} {m.version}", "status": m.alias,
                      "facts": {"alias": m.alias, "gate": ("passed" if gate.get("passed") else "failed") if gate else "not run yet",
                                "metrics": "declared, not verified"},
                      "gate_checks": gate.get("checks", [])})
        trained_by = [t for t in tjobs if t.model_id == m.id]
        for t in trained_by:
            edge(f"train:{t.id}", f"model:{m.id}")
        if not trained_by and m.snapshot_id is not None:
            edge(f"snapshot:{m.snapshot_id}", f"model:{m.id}")           # a model trained elsewhere and registered by hand
    known = {n["id"] for n in nodes}
    edges = [e for e in edges if e["from"] in known and e["to"] in known]
    return {"columns": list(COLUMNS), "nodes": nodes, "edges": edges,
            "note": "Built from the stored jobs, runs, snapshots, training jobs and models. Row-level lineage (flag, evidence, raw hours, proposal, label) is in the run view."}
