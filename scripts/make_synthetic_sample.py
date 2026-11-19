"""Write small SYNTHETIC sample uploads with injected faults, so the platform can be tried without real data.

    python scripts/make_synthetic_sample.py            # writes data/samples/synthetic_*.csv

Everything produced here is synthetic: invented stations near one point, invented rain, hand-placed faults. It demonstrates that each
check fires; it says nothing about accuracy on real data. Deterministic (no randomness), so the files are reproducible.
Upload the reading file with profile "reading", accumulation mode "cumulative", interval 15 and "this data is synthetic" ticked; the daily
file with profile "daily".
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "samples"
STATIONS = [("SYN-A", 19.0000, 72.8000), ("SYN-B", 19.0030, 72.8010), ("SYN-C", 19.0010, 72.8040), ("SYN-D", 19.0050, 72.8030), ("SYN-E", 19.0040, 72.8060)]


def readings() -> list[dict]:
    t0 = datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc)
    rows = []
    for sid, lat, lon in STATIONS:
        acc = 0.0
        for i in range(48):                                    # 12 hours of 15-minute readings
            raining = 16 <= i < 28                            # a shared shower, 4 hours
            intensity = 3.0 + (i % 4) * 0.5 if raining else 0.0
            acc += intensity * 0.25 if raining else 0.0
            val = acc
            if sid == "SYN-A" and i == 36:
                acc += 120.0; val = acc                         # counter_jump
            if sid == "SYN-B" and 8 <= i < 14:
                intensity = 2.0                                 # frozen_intensity; it also trips the counter mismatch and the isolated-wet check (checked)
            if sid == "SYN-C" and i == 40:
                intensity = 450.0                               # intensity_above_ceiling
            if sid == "SYN-D" and i == 4:
                intensity = 6.0; val = acc + 3.0; acc = val     # isolated wet reading while the neighbours are dry
            if sid == "SYN-E" and i == 44:
                val = -2.5                                      # negative_value
            rows.append({"timestamp": (t0 + timedelta(minutes=15 * i)).isoformat().replace("+00:00", "Z"), "station_id": sid,
                         "accumulation": round(val, 3), "intensity": round(intensity, 3), "latitude": lat, "longitude": lon})
    return rows


def daily() -> list[dict]:
    d0 = date(2026, 7, 1)
    rows = []
    for sid, lat, lon in STATIONS:
        for i in range(30):
            mm = 0.0 if i % 7 in (0, 1, 2) else round(2.0 + (i % 5) * 1.3, 1)
            if sid == "SYN-A" and 10 <= i < 13:
                mm = 7.7                                        # repeated_value (the same positive value three days running)
            if sid == "SYN-B" and i == 20:
                mm = 1200.0                                     # impossible_value
            if sid == "SYN-C" and i == 22:
                mm = 85.0 if mm == 0.0 else mm + 80.0           # an isolated wet day against dry neighbours is only UNCERTAIN
            rows.append({"day": (d0 + timedelta(days=i)).isoformat(), "station_id": sid, "mm": mm, "latitude": lat, "longitude": lon})
    # make the neighbours of SYN-C dry on its isolated day
    for r in rows:
        if r["station_id"] != "SYN-C" and r["day"] == (d0 + timedelta(days=22)).isoformat():
            r["mm"] = 0.0
    return rows


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows, SYNTHETIC)")


if __name__ == "__main__":
    write(OUT / "synthetic_readings_with_faults.csv", readings())
    write(OUT / "synthetic_daily_with_faults.csv", daily())
