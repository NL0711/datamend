"""Versioned decision evidence built from scorer inputs, never from a narrator."""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .geo import haversine_distance_km
from .scorer import (BUDDY_AGREE, FROZEN_N, INTENSITY_CEILING, JUMP_MM,
                     MIN_BUDDIES, MISMATCH_N, ScoreResult, _wet)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)


class Quantity(Contract):
    value: float | None
    unit: str
    basis: Literal["measured", "assumed", "derived"]


def quantity(value, unit="", basis="derived") -> Quantity:
    return Quantity(value=value, unit=unit, basis=basis)


class WindowRow(Contract):
    row_ref: str
    received_at: str
    intensity: Quantity
    accumulation: Quantity


class Neighbour(Contract):
    station_id: str
    distance: Quantity
    wet: bool
    reading: WindowRow
    previous_reading: WindowRow | None = None


class Threshold(Contract):
    description: str
    why: str = "Design choice, uncalibrated; not a learned probability."
    parameters: dict[str, Quantity]


class Evidence(Contract):
    schema_version: Literal["evidence-v1"] = "evidence-v1"
    run_id: str
    row_ref: str
    station_id: str
    verdict: Literal["OK", "SUSPECT", "UNCERTAIN", "NO_DATA"]
    rule_score: float = Field(ge=0, le=1)
    rule_score_basis: Literal["derived"] = "derived"
    severity: Literal["low", "medium", "high"]
    check: str
    layer: Literal["input", "rule", "neighbour"]
    profile: Literal["reading"] = "reading"
    observed: Quantity
    threshold: Threshold
    weight: Quantity
    window: list[WindowRow]
    neighbours: list[Neighbour]
    time_basis: Literal["received"] = "received"
    accumulation_mode: str
    units_confirmed: Literal[False] = False
    reason: str


class DecisionEvidence(Contract):
    schema_version: Literal["evidence-v1"] = "evidence-v1"
    run_id: str
    row_ref: str
    station_id: str
    verdict: Literal["OK", "SUSPECT", "UNCERTAIN", "NO_DATA"]
    rule_score: float = Field(ge=0, le=1)
    rule_score_basis: Literal["derived"] = "derived"
    severity: Literal["low", "medium", "high"]
    checks: list[Evidence]
    checks_run: list[str]
    not_run: list[str]
    limitations: list[str]

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True, allow_nan=False).encode()).hexdigest()


def window_row(obs) -> WindowRow:
    return WindowRow(row_ref=f"{obs.station_id}:{obs.observed_at.isoformat()}",
                     received_at=obs.observed_at.isoformat(),
                     intensity=quantity(obs.rain_intensity, "mm/h", "assumed"),
                     accumulation=quantity(obs.rain_accumulation, "mm", "assumed"))


def build_evidence(station, history, neighbours, stations, score: ScoreResult, mode: str,
                   radius_km: float = 10) -> DecisionEvidence:
    cur = history[-1]
    row = window_row(cur)
    # IMD labels the rain day by its ending date, regardless of legacy total labels.
    day = (cur.observed_at - timedelta(hours=3)).date() + timedelta(days=1)
    severity = "high" if score.score >= .7 else "medium" if score.score >= .3 else "low"
    common = dict(run_id=f"live:{day}", row_ref=row.row_ref, station_id=station.locality_id,
                  verdict=score.assessment, rule_score=score.score, severity=severity)
    usable = {sid: [o for o in hist if o.status == "OK" and o.has_rain_fields]
              for sid, hist in neighbours.items()}
    buddies = [Neighbour(station_id=sid,
                         distance=quantity(haversine_distance_km(station.latitude, station.longitude,
                                                                stations[sid].latitude, stations[sid].longitude), "km"),
                         wet=_wet(hist[-1], hist[-2] if len(hist) > 1 else None), reading=window_row(hist[-1]),
                         previous_reading=window_row(hist[-2]) if len(hist) > 1 else None)
               for sid, hist in usable.items() if hist]
    prev = next((o for o in reversed(history[:-1]) if o.status == "OK" and o.rain_accumulation is not None), None)
    step = None if prev is None or cur.rain_accumulation is None else cur.rain_accumulation - prev.rain_accumulation
    thresholds = {
        "NEGATIVE_VALUE": ("Rainfall cannot be negative.", {"minimum": quantity(0, "mm", "assumed")}),
        "INTENSITY_IMPLAUSIBLE": ("Intensity exceeds the configured ceiling.", {"ceiling": quantity(INTENSITY_CEILING, "mm/h", "assumed")}),
        "ACCUMULATION_JUMP": ("Counter increase exceeds the per-reading limit.", {"jump_limit": quantity(JUMP_MM, "mm", "assumed")}),
        "COUNTER_RESET": ("A falling counter is informational, not proof of a fault.", {"step_below": quantity(0, "mm", "assumed")}),
        "FROZEN_INTENSITY": ("Identical positive intensity across the configured window.", {"readings": quantity(FROZEN_N, "readings", "assumed")}),
        "INTENSITY_ACCUMULATION_MISMATCH": ("Positive intensity while the counter stays unchanged.", {"readings": quantity(MISMATCH_N, "readings", "assumed")}),
        "NO_RAIN_FIELDS": ("No usable rainfall fields in this response.", {}),
    }
    checks = []
    for hit in score.reasons:
        check = hit["check"]
        neighbour = check in ("ISOLATED_WET", "ISOLATED_DRY")
        if neighbour:
            description = "Disagreement with nearby gauges alone gives UNCERTAIN, not a diagnosed fault."
            parameters = {"minimum_neighbours": quantity(MIN_BUDDIES, "stations", "assumed"),
                          "agreement": quantity(BUDDY_AGREE, "fraction", "assumed"),
                          "radius": quantity(radius_km, "km", "assumed")}
            observed = quantity(sum(b.wet == (check == "ISOLATED_DRY") for b in buddies) / len(buddies), "fraction")
        else:
            description, parameters = thresholds[check]
            if check in ("ACCUMULATION_JUMP", "COUNTER_RESET"):
                observed = quantity(step, "mm", "derived")
            elif check == "NEGATIVE_VALUE":
                observed = row.intensity if cur.rain_intensity is not None and cur.rain_intensity < 0 else row.accumulation
                parameters = {"minimum": quantity(0, observed.unit, "assumed")}
            else:
                observed = row.intensity
        win = [cur]
        if check in ("ACCUMULATION_JUMP", "COUNTER_RESET", "ISOLATED_WET", "ISOLATED_DRY") and prev is not None:
            win = [prev, cur]
        elif check == "FROZEN_INTENSITY":
            win = history[-FROZEN_N:]
        elif check == "INTENSITY_ACCUMULATION_MISMATCH":
            win = history[-(MISMATCH_N + 1):]
        checks.append(Evidence(**common, check=check, layer="neighbour" if neighbour else "input" if check == "NO_RAIN_FIELDS" else "rule",
                               observed=observed, threshold=Threshold(description=description, parameters=parameters),
                               weight=quantity(hit["weight"], "score weight", "assumed"),
                               window=[window_row(o) for o in win], neighbours=buddies if neighbour else [],
                               accumulation_mode=mode, reason=hit["detail"]))
    valid = cur.status == "OK" and cur.has_rain_fields
    recent = [o for o in history[-FROZEN_N:] if o.status == "OK" and o.rain_intensity is not None]
    mismatch = [o for o in history[-(MISMATCH_N + 1):] if o.status == "OK" and o.rain_accumulation is not None and o.rain_intensity is not None]
    availability = {
        "NO_RAIN_FIELDS": (True, ""),
        "NEGATIVE_VALUE": (valid, "No usable rainfall fields."),
        "INTENSITY_IMPLAUSIBLE": (valid and cur.rain_intensity is not None, "No usable intensity."),
        "ACCUMULATION_JUMP": (valid and mode == "cumulative" and step is not None, "Needs cumulative mode and two usable counter readings."),
        "COUNTER_RESET": (valid and mode == "cumulative" and step is not None, "Needs cumulative mode and two usable counter readings."),
        "FROZEN_INTENSITY": (valid and len(recent) == FROZEN_N, "Needs six recent usable intensity readings."),
        "INTENSITY_ACCUMULATION_MISMATCH": (valid and mode == "cumulative" and len(mismatch) == MISMATCH_N + 1, "Needs cumulative mode and four usable paired readings."),
        "NEIGHBOUR_CHECK": (valid and len(buddies) >= MIN_BUDDIES, "Needs a usable reading and three usable nearby gauges."),
    }
    not_run = [f"{name}: {why}" for name, (ran, why) in availability.items() if not ran]
    not_run.extend(["Trained grid models: no score provider connected.", "Input-integrity catalogue: not implemented for live readings yet."])
    return DecisionEvidence(**common, checks=checks, checks_run=[name for name, (ran, _) in availability.items() if ran], not_run=not_run,
                            limitations=["Rainfall units and accumulation period are unconfirmed.",
                                         "Times are received times, not observation times.",
                                         "The rule score is uncalibrated and is not a probability.",
                                         "No real Indian fault labels support an accuracy claim."])
