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

from backend.app.pipeline import fusion
from backend.app.pipeline.models import ModelVersion

REQUIRED = ("recall_at_budget", "false_alarms_per_1000", "protected_extremes_flagged", "false_alarm_budget_per_1000",
            "frozen_protocol", "test_years_untouched")


def model_dict(m: ModelVersion) -> Dict[str, Any]:
    return {"id": m.id, "created_at": m.created_at.isoformat() if m.created_at else None, "name": m.name, "version": m.version,
            "artifact_sha256": m.artifact_sha256, "artifact_uri": m.artifact_uri, "snapshot_id": m.snapshot_id, "metrics": m.metrics,
            "gate": m.gate, "alias": m.alias, "notes": m.notes, "metrics_basis": "declared by the training job, not verified by the platform"}


def evaluate_gate(candidate: Dict[str, Any], champion: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Pure function: the gate result with one entry per rule. ``passed`` is True only when every rule holds. Metrics that are not numbers
    (hand-registered or Kaggle results) make the gate FAIL with a reason; they never raise."""
    try:
        return _evaluate_gate(candidate, champion)
    except (TypeError, ValueError, AttributeError, KeyError, OverflowError) as e:
        return {"passed": False, "champion_compared": False,
                "checks": [{"rule": "metrics_valid", "passed": False, "detail": f"a metric is missing its expected type or is not a number ({type(e).__name__})"}]}


def _evaluate_gate(candidate: Dict[str, Any], champion: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(candidate, dict):
        raise TypeError("metrics must be an object")
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"rule": name, "passed": bool(ok), "detail": detail})

    if candidate.get("kind") == "label_fusion":
        return _evaluate_label_model(candidate, champion)
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


LABEL_REQUIRED = ("recall_at_budget", "false_alarms_per_1000", "protected_extremes_flagged", "false_alarm_budget_per_1000", "baseline", "validation", "train")


def _evaluate_label_model(c: Dict[str, Any], champion: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Gate for a model trained from reviewer labels (kind label_fusion). It is judged on the later part of its own snapshot against the
    fixed-weight rule score on the SAME days; it is never compared with a champion trained on a different snapshot (not comparable). The frozen
    RF25 protocol does not apply to it, and the result says so."""
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"rule": name, "passed": bool(ok), "detail": detail})

    missing = [k for k in LABEL_REQUIRED if k not in c]
    add("metrics_complete", not missing, "all required metrics present" if not missing else "missing: " + ", ".join(missing))
    if missing:
        return {"passed": False, "checks": checks, "champion_compared": False, "profile": "label_fusion"}
    base, val, tr = c["baseline"], c["validation"], c["train"]
    add("temporal_split", c.get("temporal_split") is True, "earlier days train, later days validate")
    add("enough_labels", tr.get("n_fault", 0) >= fusion.MIN_FAULT and tr.get("n_clean", 0) >= fusion.MIN_CLEAN
        and val.get("n_fault", 0) >= fusion.MIN_VAL_FAULT and val.get("n_clean", 0) >= fusion.MIN_VAL_CLEAN,
        f"train {tr.get('n_fault')} faults and {tr.get('n_clean')} clean, validation {val.get('n_fault')} faults and {val.get('n_clean')} clean "
        f"(needs {fusion.MIN_FAULT} and {fusion.MIN_CLEAN} to train, {fusion.MIN_VAL_FAULT} and {fusion.MIN_VAL_CLEAN} to judge)")
    add("false_alarms_within_budget", c["false_alarms_per_1000"] is not None and float(c["false_alarms_per_1000"]) <= float(c["false_alarm_budget_per_1000"]),
        f"{c['false_alarms_per_1000']} per 1,000 against a budget of {c['false_alarm_budget_per_1000']}")
    add("recall_not_below_rules", c["recall_at_budget"] is not None and base.get("recall_at_budget") is not None and float(c["recall_at_budget"]) >= float(base["recall_at_budget"]),
        f"{c['recall_at_budget']} against the fixed rule weights' {base.get('recall_at_budget')} on the same validation days")
    add("protected_extremes_not_higher", int(c["protected_extremes_flagged"]) <= int(base.get("protected_extremes_flagged", 0)),
        f"{c['protected_extremes_flagged']} genuine extremes flagged against the rules' {base.get('protected_extremes_flagged')}")
    same = champion is not None and c.get("snapshot_sha256") is not None and champion.get("snapshot_sha256") == c.get("snapshot_sha256")   # None == None is not "same"
    if champion is not None and not same:
        add("champion_not_comparable", True, "the champion was trained and judged on a different snapshot, so the two are not compared; this model is judged against the rules only")
    elif champion is not None:
        add("recall_not_lower_than_champion", float(c["recall_at_budget"] or 0) >= float(champion.get("recall_at_budget") or 0),
            f"{c['recall_at_budget']} against the champion's {champion.get('recall_at_budget')} on the same snapshot")
    return {"passed": all(x["passed"] for x in checks), "checks": checks, "champion_compared": bool(same), "profile": "label_fusion"}


async def _champions(session: AsyncSession, name: str) -> List[ModelVersion]:
    """All champions of a name, newest first (there should be one; defensive against two)."""
    return list((await session.execute(select(ModelVersion).where(ModelVersion.name == name, ModelVersion.alias == "champion")
                                       .order_by(ModelVersion.id.desc()))).scalars())


async def champion(session: AsyncSession, name: str) -> Optional[ModelVersion]:
    found = await _champions(session, name)
    return found[0] if found else None


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
    champs = await _champions(session, m.name)
    cur = champs[0] if champs else None
    result = evaluate_gate(m.metrics, cur.metrics if cur else None)
    if result["passed"]:
        for old in champs:                                   # demote ALL existing champions of this name
            old.alias = "archived"
        # the history for rollback: which model was champion immediately before this one (gate JSON, no new column)
        m.gate = {**result, "replaces": cur.id if cur is not None else None}
        m.alias = "champion"
    else:
        m.gate = result
        m.alias = "rejected"
    await session.commit()
    return m


async def rollback(session: AsyncSession, name: str) -> ModelVersion:
    """Put the model that was champion immediately before the current one back as champion; the current champion is archived. Repeating it
    walks back along the history to the oldest model, then refuses. The order is the ``replaces`` link recorded when each model was promoted
    (for older rows without the link: the nearest earlier archived model by id)."""
    cur = await champion(session, name)
    if cur is None:
        raise ValueError("there is no champion to roll back from")
    prev_id = (cur.gate or {}).get("replaces") if isinstance(cur.gate, dict) else None
    prev: Optional[ModelVersion] = await session.get(ModelVersion, prev_id) if prev_id is not None else None
    if prev is None and (not isinstance(cur.gate, dict) or "replaces" not in cur.gate):
        prev = (await session.execute(select(ModelVersion).where(ModelVersion.name == name, ModelVersion.alias == "archived", ModelVersion.id < cur.id)
                                      .order_by(ModelVersion.id.desc()))).scalars().first()
    if prev is None or prev.name != name or prev.alias != "archived":
        raise ValueError("this is the oldest model; there is nothing earlier to roll back to")
    cur.alias = "archived"
    cur.notes = ((cur.notes or "") + " | rolled back").strip(" |")
    for extra in (await _champions(session, name)):
        extra.alias = "archived"
    prev.alias = "champion"
    await session.commit()
    return prev
