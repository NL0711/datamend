"""SYNTHETIC evaluation of the temperature, pressure and humidity checks against the seeded simulator (not collected by pytest).

Everything here is synthetic: the background is the simulator's diurnal physics, the faults are the simulator's own injector. No real labelled
fault exists, so the numbers say how the checks behave on this simulator, not how accurate they are on real stations.

Per fault kind: event-level recall (an injection counts as detected when at least one reading it disturbed is flagged SUSPECT or UNCERTAIN),
detection delay in readings (0 = flagged on the first disturbed reading), and how often the verdict was SUSPECT (a fault call). False alarms:
flagged readings per 1,000 clean readings of fault-free runs. Latency: wall time of ``score_reading`` per reading.
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from backend.app.stream.scoring import FLAGGED, climate_sample, score_reading
from backend.app.stream.simulator import SimulatorSource
from backend.app.stream.sim_physics import SIM_STATIONS
from backend.app.validation.weather_checks import ClimateHistory

T0 = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
WARMUP = 120
STATION_IDS = [s.station_id for s in SIM_STATIONS]

# (kind, parameter, magnitude, duration in readings); magnitude None = the injector's own fixed disturbance
CONFIGS: List[Tuple[str, str, Optional[float], int]] = (
    [("SPIKE", "temperature", m, 2) for m in (4.0, 8.0, 15.0, 25.0)] + [("SPIKE", "pressure", m, 2) for m in (-3.0, -6.0, -12.0, -20.0)]
    + [("SPIKE", "humidity", m, 2) for m in (-15.0, -25.0, -40.0)]
    + [("DRIFT", "temperature", m, 60) for m in (3.0, 5.0, 8.0)] + [("DRIFT", "pressure", m, 60) for m in (4.0, 8.0, 12.0)]
    + [("DRIFT", "humidity", m, 60) for m in (10.0, 15.0, 25.0)]
    + [("FROZEN", p, None, 40) for p in ("temperature", "pressure", "humidity")]
    + [("DROPOUT", p, None, 5) for p in ("temperature", "pressure", "humidity")]
    + [("NOISE_BURST", p, m, 10) for p in ("temperature", "pressure", "humidity") for m in (2.0, 4.0, 8.0)]
    + [("MULTIVARIATE_INCONSISTENCY", "temperature", None, 5)]
    + [("METEOROLOGICAL_EXTREME", "pressure", m, 5) for m in (-8.0, -14.0, -20.0)]
    + [("DATA_CORRUPTION", p, None, 3) for p in ("temperature", "pressure", "humidity")]
)


def _run(sim: SimulatorSource, ticks: int, step_s: float, history: Dict[str, ClimateHistory], latencies: Optional[List[float]] = None,
         start_tick: int = 0):
    """Tick the simulator, score every reading causally; yield (tick index, reading, outcome)."""
    out = []
    for i in range(start_tick, start_tick + ticks):
        for r in sim.tick(T0 + timedelta(seconds=i * step_s)):
            h = history.setdefault(r.station_id, ClimateHistory())
            prior = h.recent(r.station_id)
            t = time.perf_counter()
            o = score_reading(r, (), prior)
            if latencies is not None:
                latencies.append(time.perf_counter() - t)
            h.add(r.station_id, climate_sample(r))
            out.append((i, r, o))
    return out


def false_alarms(seeds=range(100, 104), ticks: int = 1440, step_s: float = 60.0, latencies: Optional[List[float]] = None) -> Dict[str, Any]:
    n = flagged = suspect = 0
    by_check: Dict[str, int] = defaultdict(int)
    for seed in seeds:
        sim = SimulatorSource(seed=seed)
        for _, r, o in _run(sim, ticks, step_s, {}, latencies):
            n += 1
            if o.flagged:
                flagged += 1
                suspect += o.status == "SUSPECT"
                for h in o.hits:
                    by_check[h["check"]] += 1
    return {"clean_readings": n, "flagged": flagged, "suspect": suspect, "per_1000_flagged": 1000.0 * flagged / max(1, n),
            "per_1000_suspect": 1000.0 * suspect / max(1, n), "by_check": dict(by_check)}


def trial(kind: str, parameter: str, magnitude: Optional[float], duration: int, seed: int, station: str, step_s: float) -> Dict[str, Any]:
    sim = SimulatorSource(seed=seed)
    sim.configure(station_ids=[station])
    history: Dict[str, ClimateHistory] = {}
    _run(sim, WARMUP, step_s, history)
    sim.inject(kind, station, parameter, magnitude, duration)
    rows = _run(sim, duration + 15, step_s, history, start_tick=WARMUP)
    labelled = [(k, o) for k, (_, r, o) in enumerate(rows) if r.injected == kind]
    first = labelled[0][0]
    hit = next((k for k, o in labelled if o.flagged), None)
    return {"detected": hit is not None, "delay": None if hit is None else hit - first, "suspect": any(o.status == "SUSPECT" for _, o in labelled),
            "labelled": len(labelled)}


def evaluate(seeds=range(1, 13), step_s: float = 60.0) -> Dict[str, Any]:
    per_kind: Dict[str, Dict[str, Any]] = {}
    per_config: Dict[str, Dict[str, Any]] = {}
    for kind, parameter, magnitude, duration in CONFIGS:
        res = [trial(kind, parameter, magnitude, duration, s, STATION_IDS[s % len(STATION_IDS)], step_s) for s in seeds]
        per_config[f"{kind}/{parameter}/{magnitude}"] = {"trials": len(res), "recall": sum(r["detected"] for r in res) / len(res),
                                                         "suspect_rate": sum(r["suspect"] for r in res) / len(res)}
        agg = per_kind.setdefault(kind, {"trials": 0, "detected": 0, "suspect": 0, "delays": []})
        agg["trials"] += len(res)
        agg["detected"] += sum(r["detected"] for r in res)
        agg["suspect"] += sum(r["suspect"] for r in res)
        agg["delays"] += [r["delay"] for r in res if r["delay"] is not None]
    summary = {k: {"trials": v["trials"], "recall": v["detected"] / v["trials"], "suspect_rate": v["suspect"] / v["trials"],
                   "median_delay": float(np.median(v["delays"])) if v["delays"] else None, "max_delay": max(v["delays"]) if v["delays"] else None}
               for k, v in per_kind.items()}
    return {"per_kind": summary, "per_config": per_config}


def latency_summary(latencies: List[float]) -> Dict[str, float]:
    a = np.asarray(latencies) * 1e6
    return {"readings": len(a), "mean_us": float(a.mean()), "p99_us": float(np.percentile(a, 99))}


if __name__ == "__main__":
    import json
    import sys
    step = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    lat: List[float] = []
    print(json.dumps({"step_s": step, "false_alarms": false_alarms(step_s=step, ticks=int(86400 / step) if step >= 60 else 5000, latencies=lat),
                      "latency": latency_summary(lat), "evaluation": evaluate(step_s=step)}, indent=1))
