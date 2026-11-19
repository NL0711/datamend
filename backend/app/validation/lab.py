"""Anomaly Lab: generate a SYNTHETIC rainfall upload with faults injected at known places, run it through the real pipeline, and report
whether each injected fault was flagged by the check it was built to trigger.

Everything here is synthetic and labelled so: invented stations about 1 km apart, invented rain, faults placed by a seeded generator (the
same seed gives the same file). It shows that each check fires on a clean, hand-made case. It is NOT an accuracy measurement: the faults are
easy, the generator is ours, and the platform's rules were written knowing what the faults look like.
"""
from __future__ import annotations

import csv
import io
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.validation.ingest import UploadOptions
from backend.app.validation.models import ValidationCheckHit, ValidationResult
from backend.app.validation import runs as runs_svc

FAULTS: Dict[str, Tuple[str, ...]] = {
    "reading": ("counter_jump", "frozen_intensity", "intensity_above_ceiling", "negative_value", "isolated_wet"),
    "daily": ("repeated_value", "impossible_value", "isolated_wet"),
}
EXPECTED_CHECK = {"counter_jump": "counter_jump", "frozen_intensity": "frozen_intensity", "intensity_above_ceiling": "intensity_above_ceiling",
                  "negative_value": "negative_value", "isolated_wet": "neighbour_isolated_wet", "repeated_value": "repeated_value",
                  "impossible_value": "impossible_value"}
STATIONS = (5, 10)
LENGTH = {"reading": (120, 288), "daily": (30, 120)}       # 15-minute readings (30 to 72 hours); days
SLOT = {"reading": 12, "daily": 6}


class LabError(ValueError):
    """The requested lab run is not possible (the API answers 422 with this message)."""


@dataclass
class LabFile:
    content: bytes
    options: Dict[str, Any]
    injected: List[Dict[str, Any]]
    n_rows: int
    filename: str


def _check_params(profile: str, n_stations: int, length: int, faults: Sequence[str]) -> List[str]:
    if profile not in FAULTS:
        raise LabError("profile must be 'reading' or 'daily'")
    if not (STATIONS[0] <= n_stations <= STATIONS[1]):
        raise LabError(f"stations must be between {STATIONS[0]} and {STATIONS[1]} (the neighbour check needs several gauges within 10 km)")
    lo, hi = LENGTH[profile]
    if not (lo <= length <= hi):
        raise LabError(f"length must be between {lo} and {hi} {'readings' if profile == 'reading' else 'days'}")
    chosen = list(dict.fromkeys(faults))
    if not chosen:
        raise LabError("choose at least one fault to inject")
    bad = [f for f in chosen if f not in FAULTS[profile]]
    if bad:
        raise LabError(f"unknown fault(s) for the {profile} profile: {', '.join(bad)}")
    if len(chosen) > n_stations:
        raise LabError("at most one fault per station: use more stations or fewer faults")
    return chosen


def _slots(profile: str, length: int) -> List[int]:
    """Start positions of fault slots, only in the dry parts of the series, so a fault never overlaps the shared shower."""
    w = SLOT[profile]
    if profile == "daily":
        return list(range(0, length - w + 1, w))
    z1_end, z2_start = int(0.4 * length) - 4, int(0.6 * length) + 4
    return [s for s in range(4, z1_end - w + 1, w)] + [s for s in range(z2_start, length - 2 - w + 1, w)]


def generate(profile: str, n_stations: int, length: int, faults: Sequence[str], seed: int) -> LabFile:
    chosen = _check_params(profile, n_stations, length, faults)
    rng = random.Random(seed)
    slots = _slots(profile, length)
    if len(slots) < len(chosen):
        raise LabError("the series is too short for that many faults; lengthen it")
    rng.shuffle(slots)
    st_order = rng.sample(range(n_stations), len(chosen))
    plan = {(st, kind): slots[i] for i, (st, kind) in enumerate(zip(st_order, chosen))}     # (station, fault) -> slot start
    ids = [f"LAB-{k + 1:02d}" for k in range(n_stations)]
    coords = [(19.0 + 0.004 * k, 72.8 + 0.003 * (k % 3)) for k in range(n_stations)]
    rows: List[Dict[str, Any]] = []
    injected: List[Dict[str, Any]] = []

    if profile == "reading":
        t0 = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
        shower = range(int(0.4 * length), int(0.6 * length))
        for k, sid in enumerate(ids):
            acc = 0.0
            faults_here = {kind: s for (st, kind), s in plan.items() if st == k}
            for i in range(length):
                inten = round(1.5 + 0.5 * ((i + k) % 4) + rng.random() * 0.3, 2) if i in shower else 0.0
                acc += inten * 0.25
                val = acc
                for kind, s in faults_here.items():
                    if kind == "counter_jump" and i == s + 2:
                        acc += 120.0; val = acc
                    elif kind == "frozen_intensity" and s + 1 <= i <= s + 6:
                        inten = 2.0
                    elif kind == "intensity_above_ceiling" and i == s + 3:
                        inten = 450.0
                    elif kind == "negative_value" and i == s + 3:
                        val = -2.5
                    elif kind == "isolated_wet" and i == s + 3:
                        inten = 6.0; acc += 3.0; val = acc
                rows.append({"timestamp": (t0 + timedelta(minutes=15 * i)).isoformat().replace("+00:00", "Z"), "station_id": sid,
                             "accumulation": round(val, 3), "intensity": round(inten, 3), "latitude": round(coords[k][0], 5), "longitude": round(coords[k][1], 5)})
                for kind, s in faults_here.items():
                    at = {"counter_jump": s + 2, "frozen_intensity": s + 6, "intensity_above_ceiling": s + 3, "negative_value": s + 3, "isolated_wet": s + 3}[kind]
                    if i == at:
                        injected.append({"fault": kind, "station_id": sid, "row_ref": str(len(rows)), "time": rows[-1]["timestamp"], "expected_check": EXPECTED_CHECK[kind]})
        options = {"profile": "reading", "accumulation_mode": "cumulative", "interval_minutes": 15.0}
    else:
        d0 = date(2026, 7, 1)
        for k, sid in enumerate(ids):
            faults_here = {kind: s for (st, kind), s in plan.items() if st == k}
            for i in range(length):
                mm = round(2.0 + rng.random() * 6.0, 1) if (i % 6) in (3, 4) else 0.0
                for kind, s in faults_here.items():
                    if kind == "repeated_value" and s <= i <= s + 2:
                        mm = 7.7
                    elif kind == "impossible_value" and i == s + 1:
                        mm = 1200.0
                    elif kind == "isolated_wet" and i == s + 1:
                        mm = 85.0
                rows.append({"day": (d0 + timedelta(days=i)).isoformat(), "station_id": sid, "mm": mm, "latitude": round(coords[k][0], 5), "longitude": round(coords[k][1], 5)})
                for kind, s in faults_here.items():
                    at = {"repeated_value": s + 2, "impossible_value": s + 1, "isolated_wet": s + 1}[kind]
                    if i == at:
                        injected.append({"fault": kind, "station_id": sid, "row_ref": str(len(rows)), "time": rows[-1]["day"], "expected_check": EXPECTED_CHECK[kind]})
        options = {"profile": "daily"}

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return LabFile(buf.getvalue().encode(), options, injected, len(rows), f"lab-{profile}-seed{seed}.csv")


async def run_lab(session: AsyncSession, profile: str, n_stations: int, length: int, faults: Sequence[str], seed: int) -> Dict[str, Any]:
    """Generate, validate through the real pipeline as a SYNTHETIC run, and compare what was flagged with what was injected."""
    lab = generate(profile, n_stations, length, faults, seed)
    run = await runs_svc.run_upload(session, lab.content, lab.filename, UploadOptions(fmt="csv", **lab.options), synthetic=True)
    hits: Dict[str, set] = defaultdict(set)
    for ref, check in (await session.execute(select(ValidationResult.row_ref, ValidationCheckHit.check)
                                             .join(ValidationCheckHit, ValidationCheckHit.result_id == ValidationResult.id)
                                             .where(ValidationResult.run_id == run.id))).all():
        hits[ref].add(check)
    flagged = {ref for (ref,) in (await session.execute(select(ValidationResult.row_ref).where(
        ValidationResult.run_id == run.id, ValidationResult.verdict.in_(("SUSPECT", "UNCERTAIN"))))).all()}
    injected = [{**inj, "caught": inj["expected_check"] in hits.get(inj["row_ref"], set())} for inj in lab.injected]
    refs = {inj["row_ref"] for inj in lab.injected}
    return {"run": runs_svc.run_dict(run, full=True), "seed": seed, "injected": injected,
            "summary": {"injected": len(injected), "caught": sum(1 for i in injected if i["caught"]),
                        "other_flagged_rows": len(flagged - refs), "rows": lab.n_rows, "label": "SYNTHETIC"},
            "note": "Synthetic faults made by this app and placed where the checks can see them. This shows each check fires on a clean case; "
                    "it is not an accuracy measurement. Other flagged rows are real consequences of the injected faults (for example a frozen "
                    "intensity also stops the counter) or of the generator, not necessarily false alarms."}
