"""What the checks say about one stream reading.

Only rainfall has checks. A reading with ``rain_mm`` goes through the existing rainfall check catalogue (validation/checks.py, reading profile)
together with the station's recent earlier rain readings. Temperature, pressure and humidity have NO checks yet (slice S4): such a reading is
stored and shown with status NO_CHECKS and no score, no verdict and no evidence. Nothing here invents a number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from backend.app.stream.types import StreamReading
from backend.app.validation import checks as catalogue
from backend.app.validation.records import Reading

NO_CHECKS = "NO_CHECKS"
FLAGGED = ("SUSPECT", "UNCERTAIN")
HISTORY_READINGS = 12        # earlier rain readings of the station given to the checks (frozen-value needs 6)
CLIMATE_VARIABLES = (("temperature", "temperature_c"), ("pressure", "pressure_hpa"), ("humidity", "humidity_pct"))
NO_CHECKS_REASON = "no checks exist yet for temperature, pressure and humidity (planned in slice S4)"


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
        return ", ".join(h["check"] for h in self.hits) or None


def _not_run_for_climate(reading: StreamReading) -> List[Dict[str, str]]:
    return [{"check": name, "reason": NO_CHECKS_REASON} for name, attr in CLIMATE_VARIABLES if getattr(reading, attr) is not None]


def as_record(reading: StreamReading, row_ref: Any) -> Reading:
    """The reading as the check catalogue's own record. Rain of a reading interval is a per-reading accumulation; its unit is assumed mm."""
    return Reading(source="stream", station_id=reading.station_id, timestamp=reading.timestamp, accumulation=reading.rain_mm, intensity=None,
                   time_basis="observed", accumulation_mode="per_reading", units_confirmed=False, row_ref=row_ref)


def score_reading(reading: StreamReading, history: Sequence[Reading] = ()) -> CheckOutcome:
    """Run the rainfall checks on the reading when it has rain; otherwise report that no check applies."""
    not_run = _not_run_for_climate(reading)
    if reading.rain_mm is None:
        return CheckOutcome(not_run=not_run or [{"check": "all", "reason": "the reading has no rainfall value, and rainfall is the only variable with checks"}])
    current = as_record(reading, "current")
    series = [*history[-HISTORY_READINGS:], current]
    result = catalogue.run_reading_checks(series)
    row = result.results[-1]            # same order as the input: the reading just given is last
    not_run = [*not_run, *({k: v for k, v in n.items()} for n in result.not_run if n.get("station_id") in (None, reading.station_id))]
    hits = [{"check": h.check, "layer": h.layer, "kind": h.kind, "weight": h.weight, "reason": h.reason, "evidence": h.evidence} for h in row.hits]
    return CheckOutcome(status=row.verdict, rule_score=row.rule_score, severity=row.severity, hits=hits, not_run=not_run)
