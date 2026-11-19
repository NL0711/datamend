"""Weather anomaly: is a day's value unusual for this cell and day of the year?

Temperature, humidity and pressure: z = (daily mean - normal mean) / normal sd, class by |z| (2 = unusual, 3 = extreme).
Rainfall is zero-inflated and skewed, so it is classed by the cell's wet-day percentiles instead of a z-score.
This says "unusual weather", NOT "wrong data"; see qc.py for that.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, Optional

from backend.app.locations.normals import VARIABLES, WET_MM, normal_for

UNUSUAL_Z = 2.0
EXTREME_Z = 3.0


def level_of(z: float) -> str:
    a = abs(z)
    return "extreme" if a >= EXTREME_Z else "unusual" if a >= UNUSUAL_Z else "normal"


def weather_anomaly(daily: Dict[str, float], normals: Dict[str, Any], d: date) -> Dict[str, Any]:
    """``daily``: {"temperature": mean, "humidity": mean, "pressure": mean, "precipitation": sum} for the date ``d``."""
    out: Dict[str, Any] = {}
    for v in VARIABLES:
        x = daily.get(v)
        if x is None or not math.isfinite(x):
            out[v] = {"value": None, "level": "unavailable"}
            continue
        n = normal_for(normals, v, d)
        z = (x - n["mean"]) / n["sd"]
        out[v] = {"value": round(x, 2), "normal": round(n["mean"], 2), "sd": round(n["sd"], 2), "z": round(z, 2),
                  "level": level_of(z), "direction": "above" if z > 0 else "below"}
    out["precipitation"] = rain_anomaly(daily.get("precipitation"), normals, d)
    return out


def rain_anomaly(mm: Optional[float], normals: Dict[str, Any], d: date) -> Dict[str, Any]:
    if mm is None or not math.isfinite(mm):
        return {"value": None, "level": "unavailable"}
    rain = normals["rain"]
    p95, p99 = rain.get("wet_p95"), rain.get("wet_p99")
    i = min(d.timetuple().tm_yday - 1, 365)
    res: Dict[str, Any] = {"value": round(mm, 2), "wet_probability_for_this_time_of_year": rain["wet_fraction"][i], "wet_p95": p95, "wet_p99": p99}
    if mm <= WET_MM:
        res["level"] = "dry"
    elif p95 is None:
        res["level"] = "unavailable"
    elif mm >= p99:
        res["level"] = "very_heavy"
    elif mm >= p95:
        res["level"] = "heavy"
    else:
        res["level"] = "normal"
    return res


def anomaly_strength(a: Dict[str, Any]) -> int:
    """0 none, 1 unusual, 2 extreme: the largest across the variables of one cell."""
    s = 0
    for v in VARIABLES:
        lv = a.get(v, {}).get("level")
        s = max(s, 2 if lv == "extreme" else 1 if lv == "unusual" else 0)
    rl = a.get("precipitation", {}).get("level")
    return max(s, 2 if rl == "very_heavy" else 1 if rl == "heavy" else 0)
