"""What the checks say about one stream reading.

Rainfall goes through the existing rainfall check catalogue (validation/checks.py, reading profile) together with the station's recent earlier
rain readings. Temperature, pressure and humidity go through the checks of validation/weather_checks.py (slice S4) together with the station's
recent earlier readings (a causal, bounded ``ClimateHistory`` kept by the caller). A reading with both is checked by both and gets one verdict.
A reading that nothing can be said about (no variable at all and no history) stays NO_CHECKS with no score. Nothing here invents a number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from backend.app.stream.types import StreamReading
from backend.app.validation import checks as catalogue
from backend.app.validation import weather_checks as weather
from backend.app.validation.records import Reading
from backend.app.validation.weather_checks import ClimateSample

NO_CHECKS = "NO_CHECKS"
FLAGGED = ("SUSPECT", "UNCERTAIN")
HISTORY_READINGS = 12        # earlier rain readings of the station given to the checks (frozen-value needs 6)
CLIMATE_VARIABLES = (("temperature", "temperature_c"), ("pressure", "pressure_hpa"), ("humidity", "humidity_pct"))


@dataclass
class CheckOutcome:
    """Verdict of the checks for one reading. ``ran`` is False when no check applied (status NO_CHECKS)."""
    status: str = NO_CHECKS
    rule_score: Optional[float] = None
    severity: Optional[str] = None
    hits: List[Dict[str, Any]] = field(default_factory=list)
    not_run: List[Dict[str, str]] = field(default_factory=list)

    @property
    def ran(self) -> bool:
        return self.status != NO_CHECKS

    @property
    def flagged(self) -> bool:
        return self.status in FLAGGED

    @property
    def reason(self) -> Optional[str]:
        return "; ".join(h["reason"] for h in self.hits) or None

    @property
    def classification(self) -> Optional[str]:
        return ", ".join(dict.fromkeys(h["check"] for h in self.hits)) or None

    @property
    def variable(self) -> Optional[str]:
        """The variable the hits are about: its name, 'multiple', or None when no hit names one."""
        names = list(dict.fromkeys(h["variable"] for h in self.hits if h.get("variable")))
        return names[0] if len(names) == 1 else ("multiple" if names else None)

    @property
    def genuine_extreme(self) -> bool:
        """A deviation that several variables made together with a steady dew point: reported as UNCERTAIN, never as a fault."""
        return any((h.get("evidence") or {}).get("corroboration", {}).get("coherent") for h in self.hits)


def as_record(reading: StreamReading, row_ref: Any) -> Reading:
    """The reading as the check catalogue's own record. Rain of a reading interval is a per-reading accumulation; its unit is assumed mm."""
    return Reading(source="stream", station_id=reading.station_id, timestamp=reading.timestamp, accumulation=reading.rain_mm, intensity=None,
                   time_basis="observed", accumulation_mode="per_reading", units_confirmed=False, row_ref=row_ref)


def climate_sample(reading: StreamReading) -> ClimateSample:
    return ClimateSample(reading.timestamp, reading.temperature_c, reading.pressure_hpa, reading.humidity_pct)


def has_climate(reading: StreamReading) -> bool:
    return any(getattr(reading, attr) is not None for _, attr in CLIMATE_VARIABLES)


def _hit_dict(h: catalogue.CheckHit, variable: Optional[str]) -> Dict[str, Any]:
    return {"check": h.check, "layer": h.layer, "kind": h.kind, "weight": h.weight, "reason": h.reason, "evidence": h.evidence,
            "variable": h.evidence.get("variable", variable)}


def score_reading(reading: StreamReading, history: Sequence[Reading] = (), climate_history: Sequence[ClimateSample] = ()) -> CheckOutcome:
    """Run the checks that exist for the variables of the reading. ``history`` (rain) and ``climate_history`` hold EARLIER readings of the station only."""
    do_climate = has_climate(reading) or (reading.rain_mm is None and len(climate_history) > 0)
    if reading.rain_mm is None and not do_climate:
        return CheckOutcome(not_run=[{"check": "all", "reason": "the reading has no value of any variable and the station has no earlier readings"}])
    hits: List[catalogue.CheckHit] = []
    not_run: List[Dict[str, str]] = []
    no_data = True
    rain_variable: Dict[int, str] = {}
    if reading.rain_mm is not None:
        current = as_record(reading, "current")
        series = [*history[-HISTORY_READINGS:], current]
        result = catalogue.run_reading_checks(series)
        row = result.results[-1]            # same order as the input: the reading just given is last
        no_data = row.verdict == "NO_DATA"
        for h in row.hits:
            rain_variable[id(h)] = "rain"
        hits.extend(row.hits)
        not_run.extend({k: v for k, v in n.items()} for n in result.not_run if n.get("station_id") in (None, reading.station_id))
    if do_climate:
        w = weather.run_weather_checks({"temperature": reading.temperature_c, "pressure": reading.pressure_hpa, "humidity": reading.humidity_pct},
                                       reading.timestamp, climate_history)
        hits.extend(w.hits)
        not_run.extend(w.not_run)
        no_data = no_data and not w.has_data
    score = catalogue.rule_score(hits)
    status = catalogue._verdict(hits, no_data)
    return CheckOutcome(status=status, rule_score=0.0 if no_data else score, severity=None if no_data else catalogue.severity(score),
                        hits=[_hit_dict(h, rain_variable.get(id(h))) for h in hits], not_run=not_run)
