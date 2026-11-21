"""Per-station view of the check -> flag -> audit cycle, read from the stored runs and reviews. Measured counts only.

  check  : rows of the station that went through the check catalogue (all stored runs that did not fail)
  flag   : of those, rows judged SUSPECT or UNCERTAIN (NO_DATA is counted apart)
  audit  : flagged rows with a reviewer decision (the admin review loop). A decision is one person's judgement, not ground truth,
           and it never changes a verdict, score or evidence.

A station's position comes from the Weather Union catalogue when its id matches, otherwise from latitude and longitude columns of an
uploaded file; with neither it has no position and is listed but not drawn. Nothing here invents a coordinate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.validation.models import Review, ValidationCheckHit, ValidationResult, ValidationRun
from backend.app.validation.review import DECISIONS, SUMMARY_CAP
from backend.app.validation.runs import STORAGE_LABEL

FLAGGED = ("SUSPECT", "UNCERTAIN")
LAT_KEYS = ("latitude", "lat")
LON_KEYS = ("longitude", "lon", "lng", "long")
UPLOAD_POSITION_LOOKUPS = 2000         # at most this many stations unknown to the catalogue get a position from their file
STATION_CAP = 2000                     # the response holds at most this many stations (those awaiting audit first)


def _num(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def position_from_row(row: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Latitude and longitude from an uploaded row, if it has both columns and they are valid coordinates."""
    low = {str(k).strip().lower(): v for k, v in (row or {}).items()}
    lat = next((_num(low[k]) for k in LAT_KEYS if k in low and _num(low[k]) is not None), None)
    lon = next((_num(low[k]) for k in LON_KEYS if k in low and _num(low[k]) is not None), None)
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return lat, lon


async def station_cycle(session: AsyncSession) -> Dict[str, Any]:
    from backend.app.rainfall.catalog import load_catalog
    catalogue = load_catalog()

    live = ValidationRun.status != "failed"
    rows = (await session.execute(
        select(ValidationResult.station_id, func.count(ValidationResult.id),
               func.sum(case((ValidationResult.verdict == "SUSPECT", 1), else_=0)),
               func.sum(case((ValidationResult.verdict == "UNCERTAIN", 1), else_=0)),
               func.sum(case((ValidationResult.verdict == "NO_DATA", 1), else_=0)),
               func.sum(case((ValidationRun.synthetic.is_(True), 1), else_=0)),
               func.count(func.distinct(ValidationResult.run_id)), func.max(ValidationRun.created_at), func.max(ValidationResult.run_id))
        .join(ValidationRun, ValidationRun.id == ValidationResult.run_id).where(live).group_by(ValidationResult.station_id))).all()

    checks: Dict[str, Counter] = defaultdict(Counter)
    for sid, check, n in (await session.execute(
            select(ValidationResult.station_id, ValidationCheckHit.check, func.count(ValidationCheckHit.id))
            .join(ValidationResult, ValidationResult.id == ValidationCheckHit.result_id)
            .join(ValidationRun, ValidationRun.id == ValidationResult.run_id).where(live)
            .group_by(ValidationResult.station_id, ValidationCheckHit.check))).all():
        checks[sid][check] = n

    revs = list((await session.execute(select(Review).order_by(Review.id.desc()).limit(SUMMARY_CAP))).scalars())
    latest: Dict[Tuple[int, str], Review] = {}
    for r in revs:                                                        # newest first: keep the first seen per row
        latest.setdefault((r.run_id, r.row_ref), r)
    # An audit counts only while its row is still flagged: a live run re-scores its rows, and reviews survive that (they are keyed by
    # run and row_ref), so a review of a row that is now OK must not hide a different flagged row that nobody audited.
    flagged_keys: set = set()
    if latest:
        for run_id, row_ref in (await session.execute(
                select(ValidationResult.run_id, ValidationResult.row_ref)
                .where(ValidationResult.run_id.in_({k[0] for k in latest}), ValidationResult.verdict.in_(FLAGGED)))).all():
            if (run_id, row_ref) in latest:
                flagged_keys.add((run_id, row_ref))
    audited: Dict[str, Counter] = defaultdict(Counter)
    for key, r in latest.items():
        if key in flagged_keys:
            audited[r.station_id][r.decision] += 1

    # Positions of stations the catalogue does not know, from latitude and longitude columns of the upload: the first row of each station,
    # fetched in batches (not one query per station). More than UPLOAD_POSITION_LOOKUPS such stations are reported as truncated.
    unknown_all = [sid for sid, *_ in rows if sid not in catalogue]
    positions_truncated = len(unknown_all) > UPLOAD_POSITION_LOOKUPS
    unknown = unknown_all[:UPLOAD_POSITION_LOOKUPS]
    upload_pos: Dict[str, Tuple[float, float]] = {}
    for i in range(0, len(unknown), 400):
        batch = unknown[i:i + 400]
        first_ids = select(func.min(ValidationResult.id)).where(ValidationResult.station_id.in_(batch)).group_by(ValidationResult.station_id)
        for sid, first in (await session.execute(
                select(ValidationResult.station_id, ValidationResult.original_row).where(ValidationResult.id.in_(first_ids)))).all():
            pos = position_from_row(first or {})
            if pos:
                upload_pos[sid] = pos

    out: List[Dict[str, Any]] = []
    for sid, n, sus, unc, nod, syn, n_runs, last, latest_run in rows:
        sus, unc, nod, syn = int(sus or 0), int(unc or 0), int(nod or 0), int(syn or 0)
        cat = catalogue.get(sid)
        if cat:
            lat, lon, source, place, city = cat.latitude, cat.longitude, "catalogue", cat.place, cat.city
        elif sid in upload_pos:
            (lat, lon), source, place, city = upload_pos[sid], "upload", None, None
        else:
            lat = lon = place = city = None
            source = None
        flagged = sus + unc
        dec = audited.get(sid, Counter())
        n_audited = sum(dec.values())
        out.append({
            "station_id": sid, "place": place, "city": city, "latitude": lat, "longitude": lon, "position_source": source,
            "checked": int(n), "runs": int(n_runs), "synthetic_rows": syn, "last_run_at": last.isoformat() if last else None,
            "latest_run_id": int(latest_run) if latest_run is not None else None,
            "flagged": flagged, "suspect": sus, "uncertain": unc, "no_data": nod,
            "audited": n_audited, "unaudited": max(0, flagged - n_audited), "decisions": {d: dec.get(d, 0) for d in DECISIONS},
            "top_checks": dict(checks.get(sid, Counter()).most_common(6)),
        })
    out.sort(key=lambda s: (-s["unaudited"], -s["flagged"], s["station_id"]))
    total, positioned = len(out), sum(1 for s in out if s["latitude"] is not None)
    out = out[:STATION_CAP]
    return {"storage": STORAGE_LABEL, "count": total, "shown": len(out), "truncated": total > len(out), "positioned": positioned,
            "positions_truncated": positions_truncated, "truncated_reviews": len(revs) >= SUMMARY_CAP, "stations": out,
            "note": "counts of stored rows; synthetic rows are counted apart; an audit is one reviewer's judgement, not ground truth"}
