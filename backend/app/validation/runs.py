"""Validation runs: execute the catalogue on an input, store the run, build the report, page and export (spec section 5).

The report headline is measured numbers only (completeness, shares by verdict, counts per check, the "not run" list). There is NO
composite quality grade in v1: without labels it would be arbitrary.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings as app_settings
from backend.app.places.grid import GridError
from backend.app.places.lookup import locate
from backend.app.validation import checks
from backend.app.validation.ingest import InputRejected, ParsedInput, UploadOptions, parse_upload
from backend.app.validation.models import Explanation, Review, ValidationCheckHit, ValidationResult, ValidationRun
from backend.app.validation.records import DailyTotal, Reading

RUN_CAP = 50
PAGE_SIZE = 50
# Said from the real DATABASE_URL, not hard-coded: a SQLite file is lost when a free Render service restarts; PostgreSQL (Supabase, or TimescaleDB on
# Tiger Cloud) keeps the runs.
STORAGE_LABEL = "SQLite file" if app_settings.DATABASE_URL.startswith("sqlite") else "PostgreSQL"


@lru_cache(maxsize=1)
def git_commit() -> str:
    """GIT_COMMIT from the environment (set at image build), else the working tree's HEAD, else "unknown". Never invented."""
    env = os.environ.get("GIT_COMMIT")
    if env:
        return env.strip()[:64]
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent, capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def check_settings(profile: str, opts: Optional[UploadOptions], interval_minutes: Optional[float]) -> Dict[str, Any]:
    """The thresholds and options a run used, recorded so the run can be reproduced."""
    return {
        "profile": profile, "accumulation_mode": getattr(opts, "accumulation_mode", None), "timezone": getattr(opts, "timezone", None),
        "interval_minutes": interval_minutes, "neighbour_radius_km": checks.NEIGHBOUR_RADIUS_KM, "min_neighbours": checks.MIN_NEIGHBOURS,
        "thresholds": {
            "intensity_ceiling_mm_h": checks.INTENSITY_CEILING, "counter_jump_mm": checks.JUMP_MM, "frozen_n": checks.FROZEN_N,
            "mismatch_n": checks.MISMATCH_N, "daily_max_mm": checks.DAILY_MAX_MM, "repeat_days": checks.REPEAT_DAYS,
            "climatology_min_wet_days": checks.CLIM_MIN_WET, "climatology_window_days": checks.CLIM_WINDOW_DAYS,
            "climatology_tail_p": checks.CLIM_TAIL_P, "neighbour_agree": checks.NEIGHBOUR_AGREE,
            "severity_high": checks.HIGH, "severity_medium": checks.MEDIUM,
        },
        "thresholds_basis": "design choices, uncalibrated",
    }


# ------------------------------------------------------------------------------------------------ report

def _completeness(profile: str, recs: Sequence[Union[Reading, DailyTotal]], interval_minutes: Optional[float]) -> Dict[str, Any]:
    if profile == "daily":
        days = sorted({r.day for r in recs if r.day is not None})
        if not days:
            return {"value": None, "reason": "no usable day"}
        expected = (days[-1] - days[0]).days + 1
        return {"value": round(len(days) / expected, 4), "n": len(days), "expected": expected, "basis": "derived"}
    if not interval_minutes:
        return {"value": None, "reason": "not computed: no interval_minutes declared"}
    stamps = sorted({r.timestamp for r in recs if r.timestamp is not None})
    if not stamps:
        return {"value": None, "reason": "no usable timestamp"}
    expected = int((stamps[-1] - stamps[0]).total_seconds() // (interval_minutes * 60)) + 1
    return {"value": round(min(1.0, len(stamps) / expected), 4), "n": len(stamps), "expected": expected, "basis": "derived"}


def _place(recs: Sequence[Union[Reading, DailyTotal]]) -> Optional[Dict[str, Any]]:
    """The station's RF25 cell and client region from its first coordinates (stateless lookup); None when it has no coordinates."""
    for r in recs:
        if r.latitude is not None and r.longitude is not None:
            try:
                return locate(r.latitude, r.longitude)
            except GridError as e:
                return {"latitude": r.latitude, "longitude": r.longitude, "cell": None, "reason": str(e)}
    return None


def build_report(profile: str, records: Sequence[Union[Reading, DailyTotal]], cat: checks.CatalogueResult,
                 interval_minutes: Optional[float]) -> Dict[str, Any]:
    n = len(records)
    verdicts = Counter(r.verdict for r in cat.results)
    per_check = Counter(h.check for r in cat.results for h in r.hits)
    by_station: Dict[str, List[Any]] = defaultdict(list)
    for rec, res in zip(records, cat.results):
        by_station[rec.station_id].append((rec, res))
    stations = {}
    for sid, pairs in by_station.items():
        v = Counter(res.verdict for _, res in pairs)
        stations[sid] = {"rows": len(pairs), "verdicts": dict(v),
                         "checks": dict(Counter(h.check for _, res in pairs for h in res.hits)),
                         "completeness": _completeness(profile, [rec for rec, _ in pairs], interval_minutes),
                         "place": _place([rec for rec, _ in pairs])}

    def share(k: str) -> Optional[float]:
        return round(verdicts.get(k, 0) / n, 4) if n else None

    return {
        "headline": {"rows": n, "stations": len(by_station), "completeness": _completeness(profile, records, interval_minutes),
                     "share_suspect": share("SUSPECT"), "share_uncertain": share("UNCERTAIN"), "share_no_data": share("NO_DATA"),
                     "checks_not_run": len(cat.not_run), "basis": "measured counts of this run; no composite grade"},
        "verdicts": dict(verdicts), "checks": dict(per_check), "stations": stations,
        "score_note": "rule score: fixed-weight ordering of suspicion, uncalibrated, not a probability",
        "method": cat.method,
    }


# ------------------------------------------------------------------------------------------------ storage

def _time_key(rec: Union[Reading, DailyTotal]) -> Optional[str]:
    if isinstance(rec, Reading):
        return rec.timestamp.isoformat() if rec.timestamp else None
    return rec.day.isoformat() if rec.day else None


def _result_row(run_id: int, pos: int, rec: Union[Reading, DailyTotal], res: checks.RowResult) -> ValidationResult:
    return ValidationResult(
        run_id=run_id, position=pos, row_ref=str(rec.row_ref), station_id=rec.station_id, time_key=_time_key(rec),
        intensity=getattr(rec, "intensity", None), accumulation=getattr(rec, "accumulation", None), mm=getattr(rec, "mm", None),
        verdict=res.verdict, rule_score=res.rule_score, severity=res.severity, original_row=_jsonable(rec.raw),
        issues=[{"code": i.code, "message": i.message} for i in rec.issues])


def _jsonable(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in d.items():
        out[str(k)] = v if isinstance(v, (str, int, float, bool, type(None), dict, list)) else str(v)
    return out


async def _store_rows(session: AsyncSession, run: ValidationRun, records: Sequence[Union[Reading, DailyTotal]], cat: checks.CatalogueResult) -> None:
    CHUNK = 2000
    for start in range(0, len(records), CHUNK):
        batch = [(i, rec, res) for i, (rec, res) in enumerate(zip(records[start:start + CHUNK], cat.results[start:start + CHUNK]), start=start)]
        rows = [_result_row(run.id, i, rec, res) for i, rec, res in batch]
        session.add_all(rows)
        await session.flush()
        hits = [ValidationCheckHit(run_id=run.id, result_id=row.id, check=h.check, layer=h.layer, kind=h.kind, weight=h.weight,
                                   reason=h.reason, evidence=_jsonable(h.evidence))
                for row, (_, _, res) in zip(rows, batch) for h in res.hits]
        session.add_all(hits)
        await session.flush()


async def prune_runs(session: AsyncSession, cap: int = RUN_CAP) -> int:
    """Keep at most `cap` runs, deleting the oldest. An open live run is never pruned. Returns the number deleted."""
    # pipeline runs hold reviewer labels that feed training, so they are never pruned and do not count against the cap
    total = (await session.execute(select(func.count()).select_from(ValidationRun).where(ValidationRun.source != "pipeline"))).scalar_one()
    excess = total - cap
    if excess <= 0:
        return 0
    # rejected uploads go first, so repeated bad files cannot evict completed runs (and their explanations); then the oldest
    ids = (await session.execute(select(ValidationRun.id).where(ValidationRun.status != "open", ValidationRun.source != "pipeline")
                                 .order_by((ValidationRun.status != "failed"), ValidationRun.id).limit(excess))).scalars().all()
    await _delete_runs(session, list(ids))
    return len(ids)


async def _delete_runs(session: AsyncSession, ids: List[int]) -> None:
    if not ids:
        return
    await session.execute(delete(Review).where(Review.run_id.in_(ids)))
    await session.execute(delete(Explanation).where(Explanation.run_id.in_(ids)))
    await session.execute(delete(ValidationCheckHit).where(ValidationCheckHit.run_id.in_(ids)))
    await session.execute(delete(ValidationResult).where(ValidationResult.run_id.in_(ids)))
    await session.execute(delete(ValidationRun).where(ValidationRun.id.in_(ids)))


class RunRejected(InputRejected):
    """The input was rejected as a whole. The rejection is stored as a failed run, whose id is ``run_id``."""

    def __init__(self, reason: str, run_id: int):
        super().__init__(reason)
        self.run_id = run_id


@dataclass
class RunSpec:
    """What an input source says about its input, before any record is read (the interface of the Run module, with ``execute_run``)."""
    profile: str                                   # "reading" or "daily"
    source: str                                    # "upload", "live"
    label: str
    settings: Dict[str, Any]                       # thresholds and options, recorded so the run can be reproduced
    interval_minutes: Optional[float] = None
    synthetic: bool = False
    input_sha256: Optional[str] = None             # known up front (upload) or supplied by the loader through ParsedInput
    replaces_rain_day: Optional[str] = None        # live: the one open run for this rain day is re-scored in place
    report_extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """What a finished run returns, so callers read it instead of querying the database again."""
    run: ValidationRun
    hits: Dict[str, Set[str]]                      # row_ref -> names of the checks that fired on it
    flagged: Set[str]                              # row_refs judged SUSPECT or UNCERTAIN


async def execute_run(session: AsyncSession, spec: RunSpec, load: Callable[[], ParsedInput]) -> RunResult:
    """The one pipeline every input source goes through: load, run the check catalogue, build the report, store the run, prune, commit.

    ``load`` returns the parsed records, or raises InputRejected for a file-level problem; that is stored as a failed run and re-raised
    as RunRejected (run id on ``exc.run_id``). A spec with ``replaces_rain_day`` is an open live run: older open live runs are closed
    and an existing run for the same rain day is re-scored in place."""
    t0 = time.perf_counter()
    live = spec.replaces_rain_day is not None
    base = dict(profile=spec.profile, source=spec.source, label=spec.label[:255], platform_version=app_settings.VERSION,
                git_commit=git_commit(), settings=spec.settings, synthetic=spec.synthetic, rain_day=spec.replaces_rain_day)
    try:
        parsed = load()
    except InputRejected as e:
        failed = ValidationRun(**base, input_sha256=spec.input_sha256, status="failed", error=str(e),
                               duration_ms=(time.perf_counter() - t0) * 1000)
        session.add(failed)
        await session.flush()
        await prune_runs(session)
        await session.commit()
        raise RunRejected(str(e), failed.id) from e

    cat = checks.run_checks(parsed.records, parsed.profile, spec.interval_minutes)
    report = build_report(parsed.profile, parsed.records, cat, spec.interval_minutes)
    report.update(spec.report_extra)
    existing: Optional[ValidationRun] = None
    if live:
        for old in (await session.execute(select(ValidationRun).where(ValidationRun.source == spec.source, ValidationRun.status == "open",
                                                                       ValidationRun.rain_day != spec.replaces_rain_day))).scalars():
            old.status = "completed"
        existing = (await session.execute(select(ValidationRun).where(ValidationRun.source == spec.source,
                                                                       ValidationRun.rain_day == spec.replaces_rain_day))).scalars().first()
    if existing is None:
        run = ValidationRun(**base)
        session.add(run)
    else:
        run = existing
        ids = [run.id]
        await session.execute(delete(ValidationCheckHit).where(ValidationCheckHit.run_id.in_(ids)))
        await session.execute(delete(ValidationResult).where(ValidationResult.run_id.in_(ids)))
        run.settings = spec.settings
    run.status = "open" if live else "completed"
    run.input_sha256 = parsed.input_sha256 or spec.input_sha256
    run.n_rows, run.n_stations = len(parsed.records), len({r.station_id for r in parsed.records})
    run.not_run, run.report = list(parsed.not_run) + list(cat.not_run), report
    run.renamed_headers, run.issue_counts = parsed.renamed, parsed.issue_counts
    await session.flush()
    await _store_rows(session, run, parsed.records, cat)
    run.duration_ms = (time.perf_counter() - t0) * 1000
    await prune_runs(session)
    await session.commit()
    hits = {str(rec.row_ref): {h.check for h in res.hits} for rec, res in zip(parsed.records, cat.results)}
    flagged = {str(rec.row_ref) for rec, res in zip(parsed.records, cat.results) if res.verdict in ("SUSPECT", "UNCERTAIN")}
    return RunResult(run, hits, flagged)


async def run_upload(session: AsyncSession, content: bytes, filename: str, opts: UploadOptions, synthetic: bool = False) -> RunResult:
    """The upload source: parse the bytes, then hand over to the Run module. A rejected file is stored as a failed run (RunRejected)."""
    spec = RunSpec(profile=opts.profile, source="upload", label=filename, settings=check_settings(opts.profile, opts, opts.interval_minutes),
                   interval_minutes=opts.interval_minutes, synthetic=synthetic, input_sha256=hashlib.sha256(content).hexdigest())
    return await execute_run(session, spec, lambda: parse_upload(content, opts))


async def refresh_live_run(session: AsyncSession, readings: Sequence[Reading], day: date, interval_minutes: Optional[float],
                           accumulation_mode: str, provider: str = "weather_union") -> ValidationRun:
    """One open live run per rain day: re-score the day's readings and replace the run's rows. Opening a new day closes older open runs.
    The run is labelled source 'live'; its settings say which provider fed it (Weather Union gauges: time basis 'received', units unconfirmed;
    Open-Meteo: hourly MODEL values, not a gauge)."""
    label = day.isoformat()
    st = check_settings("reading", None, interval_minutes)
    st["provider"] = provider
    st["accumulation_mode"] = accumulation_mode
    st["accumulation_mode_note"] = ("each hourly model value is the rain of that hour (Open-Meteo, mm, a model estimate not a gauge)" if provider == "open_meteo"
                                    else "configured, units and period UNCONFIRMED")
    spec = RunSpec(profile="reading", source="live", label=f"live rain day ending {label}", settings=st, interval_minutes=interval_minutes,
                   replaces_rain_day=label)
    records = list(readings)
    parsed = ParsedInput("reading", records, issue_counts=dict(Counter(i.code for r in records for i in r.issues)))
    return (await execute_run(session, spec, lambda: parsed)).run


# ------------------------------------------------------------------------------------------------ reading back

def run_dict(run: ValidationRun, full: bool = False) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": run.id, "created_at": run.created_at.isoformat() if run.created_at else None, "profile": run.profile, "source": run.source,
        "label": run.label, "status": run.status, "error": run.error, "n_rows": run.n_rows, "n_stations": run.n_stations,
        "duration_ms": run.duration_ms, "synthetic": run.synthetic, "rain_day": run.rain_day, "storage": STORAGE_LABEL,
        "headline": (run.report or {}).get("headline"),
    }
    if full:
        d.update({"input_sha256": run.input_sha256, "settings": run.settings, "platform_version": run.platform_version, "git_commit": run.git_commit,
                  "not_run": run.not_run, "renamed_headers": run.renamed_headers, "issue_counts": run.issue_counts, "report": run.report})
    return d


async def get_row(session: AsyncSession, run_id: int, result_id: int) -> Optional[ValidationResult]:
    row = await session.get(ValidationResult, result_id)
    return row if row is not None and row.run_id == run_id else None


async def list_runs(session: AsyncSession) -> List[ValidationRun]:
    return list((await session.execute(select(ValidationRun).order_by(ValidationRun.id.desc()))).scalars())


async def get_run(session: AsyncSession, run_id: int) -> Optional[ValidationRun]:
    return await session.get(ValidationRun, run_id)


async def rows_page(session: AsyncSession, run_id: int, page: int = 1, page_size: int = PAGE_SIZE, verdict: Optional[str] = None,
                    check: Optional[str] = None, station: Optional[str] = None, flagged_only: bool = True, sort: str = "score",
                    time_from: Optional[str] = None, time_to: Optional[str] = None) -> Dict[str, Any]:
    """Server-side page of rows, by default sorted by rule score (highest first) and limited to flagged rows (SUSPECT or UNCERTAIN)
    unless a verdict is named or flagged_only is False (the Data Explorer asks for every row, sorted by time). time_from and time_to are
    ISO date or timestamp prefixes compared as text. Evidence is NOT included; GET one row for it."""
    page_size = max(1, min(page_size, PAGE_SIZE))
    page = max(1, page)
    q = select(ValidationResult).where(ValidationResult.run_id == run_id)
    if verdict:
        q = q.where(ValidationResult.verdict == verdict)
    elif flagged_only:
        q = q.where(ValidationResult.verdict.in_(("SUSPECT", "UNCERTAIN")))
    if station:
        q = q.where(ValidationResult.station_id == station)
    if time_from:
        q = q.where(ValidationResult.time_key >= time_from)
    if time_to:
        q = q.where(ValidationResult.time_key <= time_to + "￿")      # a date prefix includes the whole day
    if check:
        q = q.where(ValidationResult.id.in_(select(ValidationCheckHit.result_id).where(ValidationCheckHit.run_id == run_id, ValidationCheckHit.check == check)))
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    order = (ValidationResult.station_id, ValidationResult.time_key, ValidationResult.position) if sort == "time" \
        else (ValidationResult.rule_score.desc(), ValidationResult.position)
    rows = (await session.execute(q.order_by(*order).limit(page_size).offset((page - 1) * page_size))).scalars().all()
    names: Dict[int, List[str]] = defaultdict(list)
    if rows:
        for rid, name in (await session.execute(select(ValidationCheckHit.result_id, ValidationCheckHit.check).where(
                ValidationCheckHit.result_id.in_([r.id for r in rows])))).all():
            names[rid].append(name)
    return {"page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size,
            "rows": [{"id": r.id, "row_ref": r.row_ref, "station_id": r.station_id, "time": r.time_key, "verdict": r.verdict,
                      "rule_score": r.rule_score, "severity": r.severity, "checks": names.get(r.id, []),
                      "intensity": r.intensity, "accumulation": r.accumulation, "mm": r.mm} for r in rows]}


async def row_context(session: AsyncSession, run_id: int, row: ValidationResult, before: int = 6, after: int = 6) -> Dict[str, Any]:
    """The rows of the same station just before and after one row, in time order (event forensics): the original values, the verdict
    and the checks that fired, so a flag can be read against what the gauge did around it."""
    before, after = max(0, min(before, 24)), max(0, min(after, 24))
    base = select(ValidationResult).where(ValidationResult.run_id == run_id, ValidationResult.station_id == row.station_id,
                                          ValidationResult.time_key.is_not(None))
    prev = (await session.execute(base.where(ValidationResult.time_key < row.time_key).order_by(ValidationResult.time_key.desc()).limit(before))).scalars().all() \
        if row.time_key and before else []
    nxt = (await session.execute(base.where(ValidationResult.time_key > row.time_key).order_by(ValidationResult.time_key).limit(after))).scalars().all() \
        if row.time_key and after else []
    seq = list(reversed(prev)) + [row] + list(nxt)
    names: Dict[int, List[str]] = defaultdict(list)
    for rid, name in (await session.execute(select(ValidationCheckHit.result_id, ValidationCheckHit.check).where(
            ValidationCheckHit.result_id.in_([r.id for r in seq])))).all():
        names[rid].append(name)
    return {"station_id": row.station_id, "selected_id": row.id,
            "rows": [{"id": r.id, "row_ref": r.row_ref, "time": r.time_key, "intensity": r.intensity, "accumulation": r.accumulation, "mm": r.mm,
                      "verdict": r.verdict, "rule_score": r.rule_score, "checks": names.get(r.id, [])} for r in seq]}


async def row_evidence(session: AsyncSession, run_id: int, result_id: int) -> Optional[Dict[str, Any]]:
    r = await session.get(ValidationResult, result_id)
    if r is None or r.run_id != run_id:
        return None
    hits = (await session.execute(select(ValidationCheckHit).where(ValidationCheckHit.result_id == r.id).order_by(ValidationCheckHit.weight.desc()))).scalars().all()
    return {"id": r.id, "run_id": run_id, "row_ref": r.row_ref, "station_id": r.station_id, "time": r.time_key, "verdict": r.verdict,
            "rule_score": r.rule_score, "severity": r.severity, "score_kind": "rule score (uncalibrated)",
            "original_row": r.original_row, "input_issues": r.issues,
            "hits": [{"check": h.check, "layer": h.layer, "kind": h.kind, "weight": h.weight, "reason": h.reason, "evidence": h.evidence} for h in hits]}


async def series(session: AsyncSession, run_id: int, station: str, max_points: int = 1500) -> Dict[str, Any]:
    """One station's series for the chart, downsampled on the server: every flagged row is kept as a marker (up to 2,000, highest score
    first) and the line is reduced to at most max_points by keeping the largest value in each time bucket."""
    max_points = max(50, min(max_points, 5000))
    q = select(ValidationResult.id, ValidationResult.time_key, ValidationResult.intensity, ValidationResult.accumulation, ValidationResult.mm,
               ValidationResult.verdict, ValidationResult.rule_score).where(
        ValidationResult.run_id == run_id, ValidationResult.station_id == station, ValidationResult.time_key.is_not(None)).order_by(ValidationResult.time_key)
    rows = (await session.execute(q)).all()

    def pt(r) -> Dict[str, Any]:
        return {"id": r.id, "time": r.time_key, "intensity": r.intensity, "accumulation": r.accumulation, "mm": r.mm,
                "verdict": r.verdict, "rule_score": r.rule_score}

    n = len(rows)
    if n <= max_points:
        points = [pt(r) for r in rows]
    else:
        size = n / max_points
        points = []
        for b in range(max_points):
            chunk = rows[int(b * size): int((b + 1) * size)]
            if chunk:
                points.append(pt(max(chunk, key=lambda r: max(r.intensity or 0.0, r.mm or 0.0, r.accumulation or 0.0))))
    flagged = sorted((r for r in rows if r.verdict in ("SUSPECT", "UNCERTAIN")), key=lambda r: -r.rule_score)[:2000]
    checks_of: Dict[int, List[str]] = defaultdict(list)
    if flagged:
        for rid, name in (await session.execute(select(ValidationCheckHit.result_id, ValidationCheckHit.check).where(
                ValidationCheckHit.run_id == run_id, ValidationCheckHit.result_id.in_([r.id for r in flagged])))).all():
            checks_of[rid].append(name)
    return {"station_id": station, "n_total": n, "downsampled": n > max_points, "max_points": max_points, "points": points,
            "flagged": [{**pt(r), "checks": checks_of.get(r.id, [])} for r in sorted(flagged, key=lambda r: r.time_key)]}


# ------------------------------------------------------------------------------------------------ exports

async def _latest_reviews(session: AsyncSession, run_id: int) -> Dict[str, Review]:
    out: Dict[str, Review] = {}
    for r in (await session.execute(select(Review).where(Review.run_id == run_id).order_by(Review.id))).scalars():
        out[r.row_ref] = r                                              # ascending id: the newest wins
    return out


async def _pipeline_extras(session: AsyncSession, run: ValidationRun) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Per row_ref of a pipeline run: stored model scores, proposals (rule or AI, always generated) and accepted corrections. Empty for other
    runs. Each piece is stored apart from the data; the export only lays them beside it, labelled."""
    out: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: {"model_scores": [], "proposals": [], "corrections": []})
    if run.source != "pipeline":
        return out
    from backend.app.pipeline.models import Correction, ModelScore, Proposal         # imported here: the pipeline package imports this one
    for s in (await session.execute(select(ModelScore).where(ModelScore.run_id == run.id).order_by(ModelScore.id))).scalars():
        out[s.row_ref]["model_scores"].append({"model_id": s.model_id, "score": s.score, "flagged": s.flagged})
    for p in (await session.execute(select(Proposal).where(Proposal.run_id == run.id).order_by(Proposal.id))).scalars():
        out[p.row_ref]["proposals"].append({"kind": p.kind, "generator": p.generator, "generated": True, "status": p.status, "text": p.text,
                                            "decided_by": p.decided_by})
    for c in (await session.execute(select(Correction).where(Correction.run_id == run.id).order_by(Correction.id))).scalars():
        out[c.row_ref]["corrections"].append({"original_mm": c.original_mm, "corrected_mm": c.corrected_mm, "reviewer": c.reviewer, "note": c.note})
    return out


async def export_json(session: AsyncSession, run: ValidationRun) -> Dict[str, Any]:
    rows = (await session.execute(select(ValidationResult).where(ValidationResult.run_id == run.id).order_by(ValidationResult.position))).scalars().all()
    hits: Dict[int, List[ValidationCheckHit]] = defaultdict(list)
    for h in (await session.execute(select(ValidationCheckHit).where(ValidationCheckHit.run_id == run.id))).scalars():
        hits[h.result_id].append(h)
    reviews = await _latest_reviews(session, run.id)
    extras = await _pipeline_extras(session, run)
    note = ("model_scores are a registered model's own numbers, proposals are generated text (rule-based or AI) and never decisions, corrections are "
            "reviewer-accepted values kept beside the original; none of them changes a verdict, rule score or the original row" if run.source == "pipeline" else None)
    return {"run": run_dict(run, full=True), "export_note": "full run record; the durable copy (server storage resets on restart)",
            "review_note": "reviewer decisions are one person's judgement on the rows they reviewed; not ground truth",
            **({"pipeline_note": note} if note else {}),
            "rows": [{"row_ref": r.row_ref, "station_id": r.station_id, "time": r.time_key, "original_row": r.original_row,
                      "input_issues": r.issues, "verdict": r.verdict, "rule_score": r.rule_score, "severity": r.severity,
                      **(extras[r.row_ref] if run.source == "pipeline" else {}),
                      "review": ({"decision": reviews[r.row_ref].decision, "note": reviews[r.row_ref].note, "reviewer": reviews[r.row_ref].reviewer,
                                  "at": reviews[r.row_ref].created_at.isoformat() if reviews[r.row_ref].created_at else None}
                                 if r.row_ref in reviews else None),
                      "hits": [{"check": h.check, "layer": h.layer, "kind": h.kind, "weight": h.weight, "reason": h.reason, "evidence": h.evidence}
                               for h in hits.get(r.id, [])]} for r in rows]}


def _csv_cell(v: Any) -> Any:
    """An uploaded cell as written back to CSV. Numbers and plain text are untouched; a TEXT cell that starts with = + - @ (a spreadsheet
    formula when opened in Excel or Sheets) gets a leading apostrophe; a JSON object or list is written as JSON, not a Python repr."""
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        try:
            float(v)
            return v                                    # a number such as -3.0 stays as it was
        except ValueError:
            return "'" + v
    return v


async def export_csv(session: AsyncSession, run: ValidationRun) -> str:
    """One row per input row: the original columns untouched, then verdict, rule_score, severity, fired_checks, input_issues."""
    rows = (await session.execute(select(ValidationResult).where(ValidationResult.run_id == run.id).order_by(ValidationResult.position))).scalars().all()
    names: Dict[int, List[str]] = defaultdict(list)
    for rid, name in (await session.execute(select(ValidationCheckHit.result_id, ValidationCheckHit.check).where(ValidationCheckHit.run_id == run.id))).all():
        names[rid].append(name)
    cols: List[str] = []
    for r in rows:
        for k in r.original_row:
            if k not in cols:
                cols.append(k)
    extra = ["verdict", "rule_score", "severity", "fired_checks", "input_issues", "review_decision"]
    extras = await _pipeline_extras(session, run)
    with_scores = any(v["model_scores"] for v in extras.values())          # the model columns exist only when a model scored this run
    with_ai = any(p["generator"] not in ("baseline-rules",) for v in extras.values() for p in v["proposals"])
    if with_scores:
        extra += ["model_score", "model_flagged"]
    if with_ai:
        extra += ["ai_proposal"]
    extra = [e if e not in cols else f"validation_{e}" for e in extra]
    reviews = await _latest_reviews(session, run.id)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols + extra)
    for r in rows:
        line = [_csv_cell(r.original_row.get(c, "")) for c in cols] + [r.verdict, r.rule_score, r.severity or "", ";".join(names.get(r.id, [])),
                                                                       ";".join(i["code"] for i in r.issues),
                                                                       reviews[r.row_ref].decision if r.row_ref in reviews else ""]
        if with_scores:
            ms = extras[r.row_ref]["model_scores"] if r.row_ref in extras else []
            line += [ms[-1]["score"], ms[-1]["flagged"]] if ms else ["", ""]               # the newest scoring of the row
        if with_ai:
            ai = [p for p in (extras[r.row_ref]["proposals"] if r.row_ref in extras else []) if p["generator"] != "baseline-rules"]
            line += [_csv_cell(f"[AI-generated, {ai[-1]['status']}] {ai[-1]['kind']}: {ai[-1]['text']}") if ai else ""]
        w.writerow(line)
    return buf.getvalue()
