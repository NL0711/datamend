"""SYNTHETIC fault injection for the simulator source: the original injector's fault kinds, applied to a live stream step by step.

Each injection lasts ``duration`` simulator ticks (one tick produces one reading per station, so a duration is the same for every station it
targets). A reading disturbed by an injection carries the fault kind as its ground-truth label; METEOROLOGICAL_EXTREME is a genuine
(physically consistent) event, not a sensor fault, and is labelled as such by its kind. Nothing here touches any real source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

FAULT_KINDS = ("SPIKE", "DRIFT", "FROZEN", "DROPOUT", "NOISE_BURST", "MULTIVARIATE_INCONSISTENCY", "METEOROLOGICAL_EXTREME", "DATA_CORRUPTION")
PARAMETERS = ("temperature", "pressure", "humidity")
CORRUPT_VALUE = 9999.9              # a non-physical number, as the original injector wrote
Values = Dict[str, Optional[float]]


def default_magnitude(kind: str, parameter: str) -> float:
    """The original injector's defaults: a spike is 25 C, -20 hPa or -40 %; a drift reaches 5 units; a noise burst has a standard deviation of 8."""
    if kind == "SPIKE":
        return {"temperature": 25.0, "pressure": -20.0}.get(parameter, -40.0)
    if kind == "DRIFT":
        return {"temperature": 5.0, "pressure": 8.0}.get(parameter, 15.0)
    if kind == "NOISE_BURST":
        return 8.0
    return 0.0


def _clamp_humidity(parameter: str, value: float) -> float:
    return max(0.0, min(100.0, value)) if parameter == "humidity" else value


@dataclass
class Injection:
    injection_id: str
    kind: str
    station_id: Optional[str]           # None or "ALL": every station of the simulator
    parameter: str
    magnitude: float
    duration: int
    decay: bool = False
    step: int = 0                       # ticks applied so far
    frozen: Dict[str, float] = field(default_factory=dict)      # "station:parameter" -> the stuck value

    def targets(self, station_id: str) -> bool:
        return self.station_id in (None, "", "ALL") or self.station_id == station_id

    @property
    def finished(self) -> bool:
        return self.step >= self.duration

    def apply(self, station_id: str, values: Values, rng: np.random.Generator) -> bool:
        """Disturb ``values`` of one station for the current tick. Returns True: the reading belongs to the injection and takes its label, even on a
        step where the value happens not to move (the first step of a frozen sensor)."""
        p, k = self.parameter, self.kind
        if k == "SPIKE" and values.get(p) is not None:
            factor = 0.5 ** self.step if self.decay else 1.0
            values[p] = round(_clamp_humidity(p, values[p] + self.magnitude * factor), 2)
        elif k == "DRIFT" and values.get(p) is not None:
            values[p] = round(_clamp_humidity(p, values[p] + self.magnitude * (self.step + 1) / max(1, self.duration)), 2)   # linear ramp to `magnitude`
        elif k == "FROZEN" and values.get(p) is not None:
            key = f"{station_id}:{p}"
            self.frozen.setdefault(key, values[p])
            values[p] = self.frozen[key]
        elif k == "DROPOUT":
            values[p] = None
        elif k == "NOISE_BURST" and values.get(p) is not None:
            values[p] = round(_clamp_humidity(p, values[p] + float(rng.normal(0.0, self.magnitude))), 2)
        elif k == "MULTIVARIATE_INCONSISTENCY":                  # warmer and much more humid at once: not physically consistent
            if values.get("temperature") is not None:
                values["temperature"] = round(values["temperature"] + 12.0, 2)
            if values.get("humidity") is not None:
                values["humidity"] = round(min(100.0, values["humidity"] + 35.0), 2)
        elif k == "METEOROLOGICAL_EXTREME":                      # a squall front: temperature and pressure fall, humidity rises, consistently
            if values.get("temperature") is not None:
                values["temperature"] = round(values["temperature"] - 8.0, 2)
            if values.get("pressure") is not None:
                drop = self.magnitude if (p == "pressure" and self.magnitude) else -14.0
                values["pressure"] = round(values["pressure"] + drop, 2)
            if values.get("humidity") is not None:
                values["humidity"] = round(min(100.0, values["humidity"] + 25.0), 2)
        elif k == "DATA_CORRUPTION":
            values[p] = CORRUPT_VALUE
        return True
