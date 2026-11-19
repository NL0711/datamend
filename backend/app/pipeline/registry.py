"""Model registry and the promotion gate.

A model is trained OFFLINE (Kaggle or a GPU machine) from a training snapshot and registered here with the metrics its training job
reports. The platform cannot check those metrics itself, so the gate records them as DECLARED. A candidate becomes champion only when
the gate passes against the current champion (docs/mlops-feedback-loop-spec.md section 6):

- recall at the fixed false-alarm budget is not lower than the champion's;
- false alarms per 1,000 clean items stay within the budget (the budget is fixed on validation data, never on the test years);
- protected (genuine) extremes flagged are not higher than the champion's;
- the training job declares that it used the frozen protocol and never touched the locked test years.

NOT IMPLEMENTED: scoring with a registered model on the server (a model needs RF25 grid neighbours), the shadow run, and training itself.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pipeline.models import ModelVersion

REQUIRED = ("recall_at_budget", "false_alarms_per_1000", "protected_extremes_flagged", "false_alarm_budget_per_1000",
            "frozen_protocol", "test_years_untouched")


def model_dict(m: ModelVersion) -> Dict[str, Any]:
    return {"id": m.id, "created_at": m.created_at.isoformat() if m.created_at else None, "name": m.name, "version": m.version,
            "artifact_sha256": m.artifact_sha256, "artifact_uri": m.artifact_uri, "snapshot_id": m.snapshot_id, "metrics": m.metrics,
            "gate": m.gate, "alias": m.alias, "notes": m.notes, "metrics_basis": "declared by the training job, not verified by the platform"}


def evaluate_gate(candidate: Dict[str, Any], champion: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Pure function: the gate result with one entry per rule. ``passed`` is True only when every rule holds."""
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"rule": name, "passed": bool(ok), "detail": detail})

    missing = [k for k in REQUIRED if k not in candidate]
    add("metrics_complete", not missing, "all required metrics present" if not missing else "missing: " + ", ".join(missing))
    if missing:
        return {"passed": False, "checks": checks, "champion_compared": champion is not None}
    budget = float(candidate["false_alarm_budget_per_1000"])
    add("false_alarms_within_budget", float(candidate["false_alarms_per_1000"]) <= budget,
        f"{candidate['false_alarms_per_1000']} per 1,000 against a budget of {budget:g}")
    add("frozen_protocol", candidate["frozen_protocol"] is True, "the training job declares it followed the frozen evaluation protocol")
    add("test_years_untouched", candidate["test_years_untouched"] is True, "the training job declares the locked test years were never used")
    if champion is not None:
        add("recall_not_lower", float(candidate["recall_at_budget"]) >= float(champion.get("recall_at_budget", 0.0)),
            f"{candidate['recall_at_budget']} against the champion's {champion.get('recall_at_budget')}")
        add("protected_extremes_not_higher", float(candidate["protected_extremes_flagged"]) <= float(champion.get("protected_extremes_flagged", float("inf"))),
            f"{candidate['protected_extremes_flagged']} against the champion's {champion.get('protected_extremes_flagged')}")
    else:
        add("no_champion_yet", True, "there is no champion to compare with; the first model is held to the budget and the declarations only")
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "champion_compared": champion is not None}


async def champion(session: AsyncSession, name: str) -> Optional[ModelVersion]:
    return (await session.execute(select(ModelVersion).where(ModelVersion.name == name, ModelVersion.alias == "champion"))).scalars().first()


async def register(session: AsyncSession, name: str, version: str, metrics: Dict[str, Any], snapshot_id: Optional[int] = None,
                   artifact_sha256: Optional[str] = None, artifact_uri: Optional[str] = None, notes: Optional[str] = None) -> ModelVersion:
    m = ModelVersion(name=name.strip()[:64], version=version.strip()[:32], metrics=metrics, snapshot_id=snapshot_id, artifact_sha256=artifact_sha256,
                     artifact_uri=artifact_uri, notes=notes, alias="challenger")
    session.add(m)
    await session.commit()
    return m


async def promote(session: AsyncSession, model_id: int) -> ModelVersion:
    """Run the gate on a challenger. Passed: it becomes champion and the old champion is archived. Failed: it is marked rejected with the gate result."""
    m = await session.get(ModelVersion, model_id)
    if m is None:
        raise LookupError("no such model")
    if m.alias != "challenger":
        raise ValueError(f"only a challenger can be promoted (this one is {m.alias})")
    cur = await champion(session, m.name)
    result = evaluate_gate(m.metrics, cur.metrics if cur else None)
    m.gate = result
    if result["passed"]:
        if cur is not None:
            cur.alias = "archived"
        m.alias = "champion"
    else:
        m.alias = "rejected"
    await session.commit()
    return m


async def rollback(session: AsyncSession, name: str) -> ModelVersion:
    """Put the most recent archived model back as champion; the current champion is archived. Recorded in the model's notes."""
    cur = await champion(session, name)
    prev = (await session.execute(select(ModelVersion).where(ModelVersion.name == name, ModelVersion.alias == "archived")
                                  .order_by(ModelVersion.id.desc()))).scalars().first()
    if prev is None:
        raise ValueError("no archived model to roll back to")
    if cur is not None:
        cur.alias = "archived"
        cur.notes = ((cur.notes or "") + " | rolled back").strip(" |")
    prev.alias = "champion"
    await session.commit()
    return prev
