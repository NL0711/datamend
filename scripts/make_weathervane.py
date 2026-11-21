"""Builds Weathervane-1, DataMend's SYNTHETIC weather-fault benchmark, from the seeded simulator (nothing here is measured on real stations).

Six simulator stations, one reading a minute for two days (17,280 rows). The first six hours are clean; after that every station gets each of
the eight fault kinds once, in turn, spaced so events do not overlap. Each row carries the injected-fault label (ground truth, synthetic) and,
for comparison, what DataMend's own checks said about it (verdict, rule score, checks that fired). Same seed, same file.

    python scripts/make_weathervane.py            # writes data/samples/weathervane_1/weathervane_1.csv
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.stream.scoring import climate_sample, score_reading  # noqa: E402
from backend.app.stream.sim_physics import SIM_STATIONS  # noqa: E402
from backend.app.stream.simulator import SimulatorSource  # noqa: E402
from backend.app.validation.weather_checks import ClimateHistory  # noqa: E402

SEED = 7
T0 = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
TICKS, STEP_S, CLEAN_TICKS, SPACING = 2880, 60.0, 360, 160
# kind, parameter, magnitude (None = the injector's own fixed disturbance), duration in readings
PLAN = [("SPIKE", "temperature", 12.0, 2), ("DRIFT", "pressure", 8.0, 60), ("FROZEN", "humidity", None, 40), ("DROPOUT", "temperature", None, 5),
        ("NOISE_BURST", "pressure", 4.0, 10), ("MULTIVARIATE_INCONSISTENCY", "temperature", None, 5),
        ("METEOROLOGICAL_EXTREME", "pressure", -14.0, 5), ("DATA_CORRUPTION", "humidity", None, 3)]


def main() -> Path:
    out_dir = ROOT / "data" / "samples" / "weathervane_1"
    out_dir.mkdir(parents=True, exist_ok=True)
    sim = SimulatorSource(interval_seconds=STEP_S, seed=SEED)
    ids = [s.station_id for s in SIM_STATIONS]
    schedule = {}
    for si, sid in enumerate(ids):
        for k, (kind, param, mag, dur) in enumerate(PLAN):
            tick = CLEAN_TICKS + si * 25 + k * SPACING
            schedule.setdefault(tick, []).append((kind, sid, param, mag, dur))
    history = {}
    path = out_dir / "weathervane_1.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "station_id", "temperature_c", "pressure_hpa", "humidity_pct", "source", "injected_fault",
                    "datamend_verdict", "datamend_rule_score", "datamend_checks_fired"])
        for i in range(TICKS):
            for kind, sid, param, mag, dur in schedule.get(i, []):
                sim.inject(kind, sid, param, mag, dur)
            for r in sim.tick(T0 + timedelta(seconds=i * STEP_S)):
                h = history.setdefault(r.station_id, ClimateHistory())
                o = score_reading(r, (), h.recent(r.station_id))
                h.add(r.station_id, climate_sample(r))

                def f(v):
                    return "" if v is None else repr(round(float(v), 3))
                w.writerow([r.timestamp.isoformat(), r.station_id, f(r.temperature_c), f(r.pressure_hpa), f(r.humidity_pct), r.source, r.injected or "",
                            o.status, "" if o.rule_score is None else round(o.rule_score, 4), ";".join(dict.fromkeys(hh["check"] for hh in o.hits))])
    return path


if __name__ == "__main__":
    p = main()
    print(p, sum(1 for _ in p.open(encoding="utf-8")) - 1, "rows")
