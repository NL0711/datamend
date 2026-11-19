"""One-station rainfall quality scorer for live gauge readings.

METHOD: fixed rules plus a neighbour (buddy) check. It is NOT a trained model: the grid-trained components of ml-service/qc need
a field of neighbouring cells, which a single gauge does not have. Every result says so in ``method``.

Each triggered check adds a reason with a fixed weight; the score is 1 - prod(1 - weight), so independent evidence combines and the
score stays in [0, 1]. The weights are design choices, not fitted values, and there are no labels to calibrate them against; the
score is therefore an ordering of suspicion, not a probability.

Assessment:
  NO_DATA   - the station returned no rain fields (offline or all null).
  SUSPECT   - at least one rule found an internal inconsistency or an impossible value.
  UNCERTAIN - only the neighbour check disagrees. Convective rain can be genuinely local, so this is NOT called a fault.
  OK        - nothing triggered.

Intensity units are unconfirmed (see weather_union.py); the ceiling below assumes mm per hour and is generous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from backend.app.rainfall.weather_union import RainObservation

METHOD = "rules + neighbour check (not a trained model); weights are design choices, not calibrated"

# weights of each check
WEIGHTS = {
    "NEGATIVE_VALUE": 0.95,
    "INTENSITY_IMPLAUSIBLE": 0.9,
    "ACCUMULATION_JUMP": 0.7,
    "FROZEN_INTENSITY": 0.6,
    "INTENSITY_ACCUMULATION_MISMATCH": 0.5,
    "ISOLATED_WET": 0.3,
    "ISOLATED_DRY": 0.3,
    "COUNTER_RESET": 0.1,
}
INTENSITY_CEILING = 300.0       # assumed mm/h; the highest 1-minute-rate records are of this order
JUMP_MM = 50.0                  # increase in one reading interval, cumulative mode
FROZEN_N = 6                    # identical non-zero intensities in a row
MISMATCH_N = 3                  # readings with intensity > 0 but a flat counter
MIN_BUDDIES = 3
BUDDY_AGREE = 0.75


@dataclass
class ScoreResult:
    station_id: str
    assessment: str
    score: float
    reasons: List[Dict[str, object]] = field(default_factory=list)
    n_neighbours_used: int = 0
    method: str = METHOD


def _wet(o: RainObservation, prev: Optional[RainObservation]) -> bool:
    if o.rain_intensity is not None and o.rain_intensity > 0:
        return True
    return bool(prev and prev.rain_accumulation is not None and o.rain_accumulation is not None and o.rain_accumulation > prev.rain_accumulation)


def _combine(reasons: Sequence[Dict[str, object]]) -> float:
    p = 1.0
    for r in reasons:
        p *= 1.0 - float(r["weight"])  # type: ignore[arg-type]
    return round(1.0 - p, 3)


def score_reading(history: Sequence[RainObservation], neighbours: Optional[Dict[str, Sequence[RainObservation]]] = None,
                  mode: str = "cumulative") -> ScoreResult:
    """Score the LAST observation in ``history`` (chronological, same station). ``neighbours`` maps a station id to that
    station's own recent observations (chronological); only neighbours with rain fields count."""
    if not history:
        raise ValueError("history is empty")
    cur = history[-1]
    if cur.status != "OK" or not cur.has_rain_fields:
        return ScoreResult(cur.station_id, "NO_DATA", 0.0, [{"check": "NO_RAIN_FIELDS", "weight": 0.0, "detail": f"status {cur.status}"}])

    reasons: List[Dict[str, object]] = []

    def hit(check: str, detail: str) -> None:
        reasons.append({"check": check, "weight": WEIGHTS[check], "detail": detail})

    prev = next((o for o in reversed(history[:-1]) if o.status == "OK" and o.rain_accumulation is not None), None)
    if (cur.rain_intensity is not None and cur.rain_intensity < 0) or (cur.rain_accumulation is not None and cur.rain_accumulation < 0):
        hit("NEGATIVE_VALUE", f"intensity={cur.rain_intensity}, accumulation={cur.rain_accumulation}")
    if cur.rain_intensity is not None and cur.rain_intensity > INTENSITY_CEILING:
        hit("INTENSITY_IMPLAUSIBLE", f"{cur.rain_intensity} > {INTENSITY_CEILING} (assumed mm/h)")

    if mode == "cumulative" and prev is not None and cur.rain_accumulation is not None and prev.rain_accumulation is not None:
        step = cur.rain_accumulation - prev.rain_accumulation
        if step > JUMP_MM:
            hit("ACCUMULATION_JUMP", f"+{step:.1f} between consecutive readings (limit {JUMP_MM})")
        elif step < 0:
            hit("COUNTER_RESET", f"counter fell {prev.rain_accumulation} -> {cur.rain_accumulation}")

    recent = [o for o in history[-FROZEN_N:] if o.status == "OK" and o.rain_intensity is not None]
    if len(recent) == FROZEN_N and recent[-1].rain_intensity > 0 and len({o.rain_intensity for o in recent}) == 1:
        hit("FROZEN_INTENSITY", f"intensity {recent[-1].rain_intensity} unchanged for {FROZEN_N} readings")

    if mode == "cumulative":
        tail = [o for o in history[-(MISMATCH_N + 1):] if o.status == "OK" and o.rain_accumulation is not None and o.rain_intensity is not None]
        if len(tail) == MISMATCH_N + 1 and all(o.rain_intensity > 0 for o in tail[1:]) and len({o.rain_accumulation for o in tail}) == 1:
            hit("INTENSITY_ACCUMULATION_MISMATCH", f"intensity > 0 for {MISMATCH_N} readings but the counter did not move")

    used = 0
    if neighbours:
        votes_wet = votes_dry = 0
        for hist in neighbours.values():
            ok = [o for o in hist if o.status == "OK" and o.has_rain_fields]
            if not ok:
                continue
            used += 1
            if _wet(ok[-1], ok[-2] if len(ok) > 1 else None):
                votes_wet += 1
            else:
                votes_dry += 1
        cur_wet = _wet(cur, prev)
        if used >= MIN_BUDDIES:
            if cur_wet and votes_dry / used >= BUDDY_AGREE:
                hit("ISOLATED_WET", f"wet here, {votes_dry} of {used} neighbours dry")
            elif not cur_wet and votes_wet / used >= BUDDY_AGREE:
                hit("ISOLATED_DRY", f"dry here, {votes_wet} of {used} neighbours wet")

    rule_hits = [r for r in reasons if r["check"] not in ("ISOLATED_WET", "ISOLATED_DRY", "COUNTER_RESET")]
    if rule_hits:
        assessment = "SUSPECT"
    elif any(r["check"] in ("ISOLATED_WET", "ISOLATED_DRY") for r in reasons):
        assessment = "UNCERTAIN"
    else:
        assessment = "OK"
    return ScoreResult(cur.station_id, assessment, _combine(reasons), reasons, used)
