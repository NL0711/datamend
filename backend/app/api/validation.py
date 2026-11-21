"""REST endpoints of the rainfall validation platform (backend/app/validation). Routes only parse and delegate to services.

Read-only except creating a run (POST /runs). Evidence is loaded one row at a time; rows come in server-side pages of at most 50.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.settings import require_admin
from backend.app.db.database import get_db
from backend.app.validation import insights as insights_svc, intake, lab, narrate, overview as overview_svc, review as review_svc, stations as stations_svc
from backend.app.validation import runs as svc
from backend.app.validation.explain import NarratorRateLimited, NarratorUnavailable
from backend.app.validation.ingest import MAX_BYTES, InputRejected

router = APIRouter(prefix="/api/validation", tags=["validation"])
_TIME = r"^\d{4}-\d{2}-\d{2}([T ][0-9:.+Z-]*)?$"          # an ISO date or timestamp (compared as text)


def _narrator_http(e: NarratorUnavailable) -> HTTPException:
    """The one place a narrator problem becomes an HTTP answer. NarratorRateLimited is a kind of NarratorUnavailable."""
    if isinstance(e, NarratorRateLimited):
        return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(e))
    if isinstance(e, narrate.NarratorNotConnected):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    if isinstance(e, narrate.NothingToExplain):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


async def _run_or_404(session: AsyncSession, run_id: int):
    run = await svc.get_run(session, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"run {run_id} not found")
    return run


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    file: UploadFile = File(...),
    profile: str = Form(...),
    accumulation_mode: Optional[str] = Form(None),
    timezone: Optional[str] = Form(None),
    interval_minutes: Optional[float] = Form(None),
    synthetic: bool = Form(False),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    content = await file.read(MAX_BYTES + 1)
    return await _validate_file(session, content, file.filename or "upload", profile, accumulation_mode, timezone, interval_minutes, synthetic)


async def _validate_file(session: AsyncSession, content: bytes, name: str, profile: str, accumulation_mode: Optional[str],
                         timezone: Optional[str], interval_minutes: Optional[float], synthetic: bool) -> Dict[str, Any]:
    try:
        run = await intake.run_file(session, content, name, profile, accumulation_mode, timezone, interval_minutes, synthetic)
    except intake.UnsupportedFile as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    except InputRejected as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"rejected": True, "reason": str(e), "run_id": getattr(e, "run_id", None)})
    return svc.run_dict(run, full=True)


class KaggleRunRequest(BaseModel):
    url: str = Field(min_length=3, max_length=300)
    token: Optional[str] = Field(None, max_length=200, repr=False)       # only for a private dataset; used for this call, never stored
    file: Optional[str] = Field(None, max_length=300)
    profile: Literal["reading", "daily"] = "reading"
    accumulation_mode: Optional[str] = None
    timezone: Optional[str] = None
    interval_minutes: Optional[float] = None
    synthetic: bool = False


@router.post("/runs/kaggle", status_code=status.HTTP_201_CREATED)
async def create_run_from_kaggle(body: KaggleRunRequest, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Import one CSV or JSON file from a Kaggle dataset link. Public datasets need no token; a private one answers 401 with needs_token."""
    try:
        name, content = await intake.fetch_link(body.url, body.token, body.file)
    except intake.LinkNeedsToken as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, {"needs_token": True, "reason": str(e)})
    except intake.LinkRejected as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    except intake.LinkUnreachable as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return await _validate_file(session, content, name, body.profile, body.accumulation_mode, body.timezone, body.interval_minutes, body.synthetic)


@router.get("/insights")
async def insights(run_id: Optional[int] = Query(None, ge=1), include_synthetic: bool = False,
                   station: Optional[List[str]] = Query(None, max_length=200), start: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                   end: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), granularity: Literal["month", "year"] = "month",
                   session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Five aggregate views of the stored rain days (anomaly, station similarity, climate bands, verdict mix, heavy rain against the verdict)."""
    if run_id is not None:
        await _run_or_404(session, run_id)
    return await insights_svc.build(session, run_id, include_synthetic, station, start, end, granularity)


@router.get("/runs")
async def list_runs(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return {"storage": svc.STORAGE_LABEL, "cap": svc.RUN_CAP, "runs": [svc.run_dict(r) for r in await svc.list_runs(session)]}


@router.get("/runs/{run_id}")
async def get_run(run_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return svc.run_dict(await _run_or_404(session, run_id), full=True)


@router.get("/runs/{run_id}/rows")
async def get_rows(run_id: int, page: int = Query(1, ge=1), page_size: int = Query(svc.PAGE_SIZE, ge=1, le=svc.PAGE_SIZE),
                   verdict: Optional[str] = Query(None, pattern="^(OK|SUSPECT|UNCERTAIN|NO_DATA)$"), check: Optional[str] = Query(None, max_length=48),
                   station: Optional[str] = Query(None, max_length=64), scope: Literal["flagged", "all"] = "flagged",
                   sort: Literal["score", "time"] = "score", time_from: Optional[str] = Query(None, pattern=_TIME, max_length=40),
                   time_to: Optional[str] = Query(None, pattern=_TIME, max_length=40), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Pages of rows. Default: flagged rows by rule score. scope=all and sort=time give the Data Explorer every row in time order."""
    await _run_or_404(session, run_id)
    return await svc.rows_page(session, run_id, page, page_size, verdict, check, station, flagged_only=(scope == "flagged"), sort=sort,
                               time_from=time_from, time_to=time_to)


@router.get("/runs/{run_id}/rows/{result_id}/context")
async def get_context(run_id: int, result_id: int, before: int = Query(6, ge=0, le=24), after: int = Query(6, ge=0, le=24),
                      session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Event forensics: the same station's rows just before and after this one."""
    await _run_or_404(session, run_id)
    row = await _row_or_404(session, run_id, result_id)
    return await svc.row_context(session, run_id, row, before, after)


@router.get("/runs/{run_id}/rows/{result_id}")
async def get_row_evidence(run_id: int, result_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    await _run_or_404(session, run_id)
    ev = await svc.row_evidence(session, run_id, result_id)
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"row {result_id} not in run {run_id}")
    return ev


async def _row_or_404(session: AsyncSession, run_id: int, result_id: int):
    row = await svc.get_row(session, run_id, result_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"row {result_id} not in run {run_id}")
    return row


@router.get("/overview")
async def get_overview(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await overview_svc.overview(session)


@router.get("/stations")
async def get_station_cycle(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Per station: rows checked, rows flagged and rows audited by a reviewer (the check, flag and audit cycle). Read-only."""
    return await stations_svc.station_cycle(session)


# ---------------------------------------------------------------- the admin review loop
class ReviewRequest(BaseModel):
    decision: Literal["confirmed_fault", "false_alarm", "genuine_extreme", "needs_followup"]
    note: Optional[str] = Field(None, max_length=1000)
    reviewer: Optional[str] = Field(None, max_length=60)


@router.get("/review/queue")
async def review_queue(page: int = Query(1, ge=1), page_size: int = Query(review_svc.PAGE, ge=1, le=review_svc.PAGE),
                       status_: Literal["unreviewed", "reviewed", "all"] = Query("unreviewed", alias="status"),
                       verdict: Optional[Literal["SUSPECT", "UNCERTAIN"]] = None, check: Optional[str] = Query(None, max_length=48),
                       run_id: Optional[int] = None, synthetic: Optional[bool] = None, station: Optional[str] = Query(None, max_length=64),
                       session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Flagged rows across every run with their review state, highest rule score first. ``station`` limits it to one station."""
    return await review_svc.queue(session, page, page_size, status_, verdict, check, run_id, synthetic, station)


@router.get("/review/summary")
async def review_summary(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await review_svc.summary(session)


@router.get("/runs/{run_id}/rows/{result_id}/reviews")
async def get_reviews(run_id: int, result_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    await _run_or_404(session, run_id)
    row = await _row_or_404(session, run_id, result_id)
    return {"reviews": [review_svc.review_dict(r) for r in await review_svc.reviews_for_row(session, run_id, row.row_ref)], "decisions": list(review_svc.DECISIONS)}


@router.post("/runs/{run_id}/rows/{result_id}/review", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def post_review(run_id: int, result_id: int, body: ReviewRequest, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Record a reviewer's decision on a flagged row (admin token required). It never changes the verdict, score or evidence."""
    await _run_or_404(session, run_id)
    row = await _row_or_404(session, run_id, result_id)
    try:
        rev = await review_svc.add_review(session, row, body.decision, body.note, body.reviewer)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    return review_svc.review_dict(rev)


# ---------------------------------------------------------------- Anomaly Lab (synthetic)
class LabRequest(BaseModel):
    profile: Literal["reading", "daily"] = "reading"
    n_stations: int = Field(6, ge=lab.STATIONS[0], le=lab.STATIONS[1])
    length: int = Field(144, ge=30, le=288)
    faults: List[str] = Field(default_factory=list, max_length=8)
    seed: int = Field(1, ge=0, le=2 ** 31 - 1)


@router.get("/lab/options")
async def lab_options() -> Dict[str, Any]:
    return {"label": "SYNTHETIC", "faults": {p: list(f) for p, f in lab.FAULTS.items()}, "expected_check": lab.EXPECTED_CHECK,
            "stations": list(lab.STATIONS), "length": {p: list(v) for p, v in lab.LENGTH.items()}}


@router.post("/lab/generate", status_code=status.HTTP_201_CREATED)
async def lab_generate(body: LabRequest, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Generate a synthetic upload with injected faults, validate it through the real pipeline as a SYNTHETIC run, and say what was caught."""
    try:
        return await lab.run_lab(session, body.profile, body.n_stations, body.length, body.faults, body.seed)
    except lab.LabError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/narrator")
async def narrator_status(narrator=Depends(narrate.get_narrator)) -> Dict[str, Any]:
    """Whether an AI narrator is configured. The URL is set in the environment only; this never reveals the token."""
    return narrate.narrator_status(narrator)


@router.get("/runs/{run_id}/rows/{result_id}/evidence")
async def get_evidence_v1(run_id: int, result_id: int, check: Optional[str] = None, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """GET-only evidence-v1 payloads (docs/contracts/evidence-v1.schema.json), one per fired check, each at most 64 KB."""
    run = await _run_or_404(session, run_id)
    row = await _row_or_404(session, run_id, result_id)
    evs = await narrate.evidence_for_row(session, run, row, check)
    # evidence_hash: send it back with the explain request and the server refuses an explanation of evidence that has changed since (409)
    return {"schema": "evidence-v1", "evidence": evs, "evidence_hash": narrate.evidence_digest(evs)}


@router.get("/runs/{run_id}/rows/{result_id}/explanations")
async def get_explanations(run_id: int, result_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    await _run_or_404(session, run_id)
    row = await _row_or_404(session, run_id, result_id)
    items = await narrate.list_explanations(session, run_id, row.row_ref, kind="explain")
    return {"explanations": [narrate.explanation_dict(e) for e in items]}


class ExplainRequest(BaseModel):
    generator: Literal["baseline", "narrator"] = "baseline"
    check: Optional[str] = Field(None, max_length=48)
    evidence_hash: Optional[str] = Field(None, pattern=r"^[a-f0-9]{64}$")      # from GET .../evidence; a changed row is refused with 409


@router.post("/runs/{run_id}/rows/{result_id}/explain", status_code=status.HTTP_201_CREATED)
async def explain(run_id: int, result_id: int, body: ExplainRequest, session: AsyncSession = Depends(get_db),
                  narrator=Depends(narrate.get_narrator)) -> Dict[str, Any]:
    """Explain the fired check(s) of a row and store the reply (the only write besides creating a run). The baseline always works;
    the narrator answers 503 'AI narrator not connected' when none is configured."""
    run = await _run_or_404(session, run_id)
    row = await _row_or_404(session, run_id, result_id)
    try:
        made = await narrate.explain_row(session, run, row, narrate.pick_explainer(body.generator, narrator), body.check, body.evidence_hash)
    except narrate.StaleEvidence as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except NarratorUnavailable as e:
        raise _narrator_http(e)
    return {"explanations": [narrate.explanation_dict(e) for e in made]}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=narrate.MAX_QUESTION_CHARS)
    row_id: Optional[int] = None

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("the question is empty")
        return v


@router.get("/runs/{run_id}/chat")
async def get_chat(run_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    await _run_or_404(session, run_id)
    return {"messages": [narrate.explanation_dict(e) for e in await narrate.list_explanations(session, run_id, kind="chat")]}


@router.post("/runs/{run_id}/chat", status_code=status.HTTP_201_CREATED)
async def chat(run_id: int, body: ChatRequest, session: AsyncSession = Depends(get_db), narrator=Depends(narrate.get_narrator)) -> Dict[str, Any]:
    """Ask the AI narrator a question about the run or a selected row. With no narrator configured this answers 503 and nothing is
    invented; the narrator's reply is stored as generated text and cannot change any verdict, score or evidence."""
    run = await _run_or_404(session, run_id)
    row = await _row_or_404(session, run_id, body.row_id) if body.row_id is not None else None
    try:
        saved = await narrate.chat_turn(session, run, body.message, narrator, row)
    except NarratorUnavailable as e:
        raise _narrator_http(e)
    return narrate.explanation_dict(saved)


@router.get("/runs/{run_id}/series")
async def get_series(run_id: int, station: str, max_points: int = Query(1500, ge=50, le=5000), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    await _run_or_404(session, run_id)
    return await svc.series(session, run_id, station, max_points)


@router.get("/runs/{run_id}/export.json")
async def export_json(run_id: int, session: AsyncSession = Depends(get_db)) -> Response:
    run = await _run_or_404(session, run_id)
    body = json.dumps(await svc.export_json(session, run), default=str)
    return Response(body, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="validation-run-{run_id}.json"'})


@router.get("/runs/{run_id}/export.csv")
async def export_csv(run_id: int, session: AsyncSession = Depends(get_db)) -> Response:
    run = await _run_or_404(session, run_id)
    return Response(await svc.export_csv(session, run), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="validation-run-{run_id}.csv"'})
