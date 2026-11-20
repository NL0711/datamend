"""Scoring a pipeline run with a registered model, and the shadow run of a challenger beside the champion.

Only a ``label_fusion`` model can score here: it needs just which checks fired on a row (the same inputs it was trained on), so there is
nothing to fake. An RF25 STNet model needs grid neighbours the server does not have; asking for it raises a plain error (NOT IMPLEMENTED).

A score is stored in ``pipeline_model_scores`` apart from the verdict and the rule score, which it never changes. The shadow run scores the
same run with the champion and the challenger and reports both on the rows a reviewer labelled; it is measured on those rows only, they are
one reviewer's judgements and not ground truth, and the report says so. It changes nothing by itself: the promotion gate may read it.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pipeline import registry
from backend.app.pipeline.models import ModelScore, ModelVersion, ShadowRun
from backend.app.validation.models import Review, ValidationCheckHit, ValidationResult, ValidationRun

LABEL_OF = {"confirmed_fault": "fault", "false_alarm": "clean", "genuine_extreme": "genuine_extreme"}   # needs_followup is not a label
NOTE = ("measured on the rows a reviewer labelled in this run: one person's judgements, not ground truth, and only rows the rule checks "
        "flagged (an unflagged row is not in it unless it was audited and labelled)")


class CannotScore(ValueError):
    pass


def artifact_of(model: ModelVersion) -> Dict[str, Any]:
    m = model.metrics or {}
    art = m.get("artifact") if isinstance(m, dict) else None
    if m.get("kind") != "label_fusion" or not isinstance(art, dict) or art.get("kind") != "label_fusion":
        raise CannotScore("only a label-fusion model can score on the server; the RF25 STNet needs grid neighbours the server does not have (NOT IMPLEMENTED)")
    for k in ("checks", "weights", "bias", "threshold"):
        if k not in art:
            raise CannotScore(f"the model artifact has no {k!r}")
    if len(art["checks"]) != len(art["weights"]):
        raise CannotScore("the model artifact is inconsistent (checks and weights differ in length)")
    return art


def score_checks(art: Dict[str, Any], fired: List[str]) -> Tuple[float, bool]:
    """The logistic score of a row from the checks that fired, and whether it reaches the threshold fixed at training time."""
    fired_set = set(fired)
    z = float(art["bias"]) + sum(float(w) for c, w in zip(art["checks"], art["weights"]) if c in fired_set)
    p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
    return p, p >= float(art["threshold"])


async def _rows_and_checks(session: AsyncSession, run_id: int) -> Tuple[List[ValidationResult], Dict[int, List[str]]]:
    rows = list((await session.execute(select(ValidationResult).where(ValidationResult.run_id == run_id).order_by(ValidationResult.position))).scalars())
    fired: Dict[int, List[str]] = defaultdict(list)
    for rid, name in (await session.execute(select(ValidationCheckHit.result_id, ValidationCheckHit.check).where(ValidationCheckHit.run_id == run_id))).all():
        fired[rid].append(name)
    return rows, fired


async def _pipeline_run(session: AsyncSession, run_id: int) -> ValidationRun:
    run = await session.get(ValidationRun, run_id)
    if run is None or run.source != "pipeline":
        raise CannotScore("scoring is done on pipeline runs only")
    return run


async def score_run(session: AsyncSession, run_id: int, model_id: int) -> Dict[str, Any]:
    """Score every row of a pipeline run with a model; any earlier scores of the same model on the run are replaced."""
    await _pipeline_run(session, run_id)
    model = await session.get(ModelVersion, model_id)
    if model is None:
        raise LookupError("no such model")
    art = artifact_of(model)
    rows, fired = await _rows_and_checks(session, run_id)
    await session.execute(delete(ModelScore).where(ModelScore.run_id == run_id, ModelScore.model_id == model_id))
    flagged = 0
    for r in rows:
        score, flag = score_checks(art, fired.get(r.id, []))
        flagged += flag
        session.add(ModelScore(run_id=run_id, model_id=model_id, row_ref=r.row_ref, score=score, flagged=flag))
    await session.commit()
    return {"run_id": run_id, "model_id": model_id, "rows": len(rows), "flagged": flagged, "threshold": art["threshold"],
            "note": "uncalibrated for this run: the threshold was fixed on the training snapshot's clean days; the verdicts and rule scores are unchanged"}


async def scores_for_run(session: AsyncSession, run_id: int, model_id: Optional[int] = None, flagged_only: bool = False, limit: int = 500) -> List[Dict[str, Any]]:
    q = select(ModelScore).where(ModelScore.run_id == run_id)
    if model_id is not None:
        q = q.where(ModelScore.model_id == model_id)
    if flagged_only:
        q = q.where(ModelScore.flagged.is_(True))
    q = q.order_by(ModelScore.score.desc(), ModelScore.id).limit(max(1, min(limit, 2000)))
    return [{"row_ref": s.row_ref, "model_id": s.model_id, "score": s.score, "flagged": s.flagged} for s in (await session.execute(q)).scalars()]


async def provider_block(session: AsyncSession, run_id: int, row_ref: str) -> Optional[Dict[str, Any]]:
    """The ``provider`` block of the evidence for a row: the champion's stored score if there is one, else the newest stored score; None when
    no model has scored the run (never invented). Matches the schema in docs/contracts/evidence-v1.schema.json."""
    scores = list((await session.execute(select(ModelScore).where(ModelScore.run_id == run_id, ModelScore.row_ref == row_ref)
                                         .order_by(ModelScore.id.desc()))).scalars())
    if not scores:
        return None
    models = {m.id: m for m in (await session.execute(select(ModelVersion).where(ModelVersion.id.in_({s.model_id for s in scores})))).scalars()}
    champ = next((s for s in scores if models.get(s.model_id) is not None and models[s.model_id].alias == "champion"), None)
    s = champ or scores[0]
    m = models.get(s.model_id)
    return {"model_id": f"{m.name}:{m.version}" if m else str(s.model_id), "model_kind": "label_fusion", "score": s.score, "flagged": s.flagged,
            "calibrated": False, "label_tier": "reviewer_labels"}


def _confusion(flags: Dict[str, bool], labels: Dict[str, str]) -> Dict[str, Any]:
    faults = [r for r, l in labels.items() if l == "fault"]
    clean = [r for r, l in labels.items() if l == "clean"]
    genuine = [r for r, l in labels.items() if l == "genuine_extreme"]
    return {"faults": len(faults), "faults_flagged": sum(flags.get(r, False) for r in faults),
            "recall_on_reviewed": (sum(flags.get(r, False) for r in faults) / len(faults)) if faults else None,
            "false_alarms_labelled": len(clean), "false_alarms_flagged": sum(flags.get(r, False) for r in clean),
            "genuine_extremes": len(genuine), "genuine_extremes_flagged": sum(flags.get(r, False) for r in genuine)}


async def shadow(session: AsyncSession, run_id: int, challenger_id: int) -> ShadowRun:
    """Score the run with the current champion (of the same model name) and the challenger and store the comparison."""
    await _pipeline_run(session, run_id)
    chal = await session.get(ModelVersion, challenger_id)
    if chal is None:
        raise LookupError("no such model")
    if chal.alias != "challenger":
        raise CannotScore(f"a shadow run is for a challenger (this model is {chal.alias})")
    champ = await registry.champion(session, chal.name)
    art_c = artifact_of(chal)
    art_h = artifact_of(champ) if champ is not None else None
    rows, fired = await _rows_and_checks(session, run_id)
    reviews: Dict[str, Review] = {}
    for rv in (await session.execute(select(Review).where(Review.run_id == run_id).order_by(Review.id))).scalars():
        reviews[rv.row_ref] = rv
    labels = {ref: LABEL_OF[rv.decision] for ref, rv in reviews.items() if rv.decision in LABEL_OF}
    flags_c: Dict[str, bool] = {}
    flags_h: Dict[str, bool] = {}
    for r in rows:
        flags_c[r.row_ref] = score_checks(art_c, fired.get(r.id, []))[1]
        if art_h is not None:
            flags_h[r.row_ref] = score_checks(art_h, fired.get(r.id, []))[1]
    only_c = sorted(ref for ref in flags_c if flags_c[ref] and not flags_h.get(ref, False)) if art_h is not None else []
    only_h = sorted(ref for ref in flags_h if flags_h[ref] and not flags_c.get(ref, False))
    report: Dict[str, Any] = {
        "rows": len(rows), "reviewed_rows_used": len(labels), "note": NOTE,
        "challenger": {"model_id": chal.id, "flagged": sum(flags_c.values()), **_confusion(flags_c, labels)},
        "champion": ({"model_id": champ.id, "flagged": sum(flags_h.values()), **_confusion(flags_h, labels)} if champ is not None else None),
        "only_challenger_flags": only_c[:20], "only_champion_flags": only_h[:20], "disagreements": len(only_c) + len(only_h),
        "no_champion": champ is None,
    }
    sr = ShadowRun(run_id=run_id, champion_id=champ.id if champ else None, challenger_id=chal.id, report=report)
    session.add(sr)
    await session.commit()
    return sr


def shadow_dict(s: ShadowRun) -> Dict[str, Any]:
    return {"id": s.id, "run_id": s.run_id, "champion_id": s.champion_id, "challenger_id": s.challenger_id, "report": s.report,
            "created_at": s.created_at.isoformat() if s.created_at else None}


async def latest_shadow(session: AsyncSession, challenger_id: int) -> Optional[ShadowRun]:
    return (await session.execute(select(ShadowRun).where(ShadowRun.challenger_id == challenger_id).order_by(ShadowRun.id.desc()))).scalars().first()


def evaluate_shadow(report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The gate rules a shadow report adds when the gate is asked to require one. A report with no reviewed fault or no champion cannot show the
    challenger is better, so it can only fail those rules (never pass them by default)."""
    checks: List[Dict[str, Any]] = []

    def add(rule: str, ok: bool, detail: str) -> None:
        checks.append({"rule": rule, "passed": bool(ok), "detail": detail})
    if not report:
        add("shadow_run_done", False, "no shadow run of this challenger exists; run one on a reviewed pipeline run first")
        return {"passed": False, "checks": checks}
    add("shadow_run_done", True, f"run {report.get('rows')} rows, {report.get('reviewed_rows_used')} reviewed rows used")
    c, h = report["challenger"], report.get("champion")
    if h is None:
        add("shadow_vs_champion", True, "there is no champion to compare with")
    else:
        ok_recall = c["recall_on_reviewed"] is not None and h["recall_on_reviewed"] is not None and c["recall_on_reviewed"] >= h["recall_on_reviewed"]
        add("shadow_recall_not_lower", ok_recall, f"challenger {c['recall_on_reviewed']} against champion {h['recall_on_reviewed']} on reviewed faults")
        add("shadow_false_alarms_not_higher", c["false_alarms_flagged"] <= h["false_alarms_flagged"],
            f"{c['false_alarms_flagged']} against {h['false_alarms_flagged']} reviewed false alarms flagged")
        add("shadow_extremes_not_higher", c["genuine_extremes_flagged"] <= h["genuine_extremes_flagged"],
            f"{c['genuine_extremes_flagged']} against {h['genuine_extremes_flagged']} genuine extremes flagged")
    return {"passed": all(x["passed"] for x in checks), "checks": checks}
