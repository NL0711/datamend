"""
scripts/generate_replay_dataset.py
DataMend — Multi-Station 30-Day Historical Benchmark Generator.

Generates physically realistic AWS time series (diurnal temperature curves, barometric tides,
psychrometric relative humidity inverse correlation) across multiple stations (AWS-001, AWS-002, AWS-003, AWS-004),
injecting labeled meteorological faults:
- Sudden thermal and pressure spikes
- Stuck / frozen sensor values
- Progressive sensor calibration drift (+0.2°C/day)
- Communication dropouts (NaN gaps)
- Correlated regional heatwave (genuine meteorological front across multiple stations)
"""

import copy
import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd

STATION_METADATA = {
    "AWS-001": {"name": "Central Meteorological Observatory (New Delhi)", "lat": 28.6139, "lon": 77.2090, "alt_m": 216.0},
    "AWS-002": {"name": "Coastal Marine Weather Tower (Mumbai)", "lat": 18.9220, "lon": 72.8347, "alt_m": 14.0},
    "AWS-003": {"name": "Plateau Highland Station (Dharamshala)", "lat": 32.2190, "lon": 76.3234, "alt_m": 1457.0},
    "AWS-004": {"name": "Arid Subtropical Outpost (Jaisalmer)", "lat": 26.9124, "lon": 70.9022, "alt_m": 225.0},
}


def generate_base_weather(num_days: int = 30, interval_mins: int = 15, start_date_str: str = "2026-08-01T00:00:00Z") -> pd.DataFrame:
    """Generates base synoptic weather patterns."""
    start_date = datetime.strptime(start_date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    total_steps = int(num_days * 24 * 60 / interval_mins)

    timestamps = [start_date + timedelta(minutes=i * interval_mins) for i in range(total_steps)]
    df = pd.DataFrame(index=timestamps)
    df.index.name = "timestamp"

    t = np.arange(total_steps) * (interval_mins / 60.0)

    # Diurnal temperature cycle: peak at 14:00, trough at 05:00
    temp_base = 28.0 + 6.0 * np.cos(2 * np.pi * (t - 14) / 24.0)
    temp_trend = 1.5 * np.sin(2 * np.pi * t / (24.0 * 30))
    df["temp_base"] = temp_base + temp_trend

    # Humidity: Inversely correlated with temperature
    humidity_base = 65.0 - 20.0 * np.cos(2 * np.pi * (t - 14) / 24.0)
    df["humidity_base"] = np.clip(humidity_base - 1.5 * temp_trend, 10.0, 95.0)

    # Pressure: Semi-diurnal atmospheric tides (peaks at 10:00 and 22:00)
    df["pressure_base"] = 1008.0 + 1.2 * np.cos(4 * np.pi * (t - 10) / 24.0)

    return df


def get_altitude_pressure_factor(alt_m: float) -> float:
    """Standard barometric hypsometric scale factor."""
    return (1.0 - 0.0065 * alt_m / 288.15) ** 5.255


def generate_clean_data(num_days: int = 30) -> Dict[str, List[Dict[str, Any]]]:
    """Generates clean tri-variate observations for all stations."""
    base_df = generate_base_weather(num_days=num_days)
    station_data = {}

    offsets = {
        "AWS-001": {"t_off": 0.0, "p_off": 0.0, "h_off": 0.0, "noise_sd": 0.3},
        "AWS-002": {"t_off": 1.2, "p_off": 2.5, "h_off": 8.0, "noise_sd": 0.4},
        "AWS-003": {"t_off": -6.5, "p_off": -12.0, "h_off": -5.0, "noise_sd": 0.5},
        "AWS-004": {"t_off": 4.0, "p_off": -3.0, "h_off": -18.0, "noise_sd": 0.4},
    }

    for sid, meta in STATION_METADATA.items():
        cfg = offsets[sid]
        scale = get_altitude_pressure_factor(meta["alt_m"])
        np.random.seed(hash(sid) % 2**31)

        readings = []
        for ts, row in base_df.iterrows():
            noise_t = np.random.normal(0, cfg["noise_sd"])
            noise_p = np.random.normal(0, cfg["noise_sd"] * 0.4)
            noise_h = np.random.normal(0, cfg["noise_sd"] * 1.5)

            t_val = round(float(row["temp_base"] + cfg["t_off"] + noise_t), 2)
            p_val = round(float(row["pressure_base"] * scale + cfg["p_off"] + noise_p), 2)
            h_val = round(float(np.clip(row["humidity_base"] + cfg["h_off"] + noise_h, 5.0, 99.0)), 2)

            readings.append({
                "station_id": sid,
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "temperature": t_val,
                "pressure": p_val,
                "humidity": h_val,
                "latitude": meta["lat"],
                "longitude": meta["lon"],
                "elevation": meta["alt_m"],
                "is_anomaly": False,
                "fault_type": "NORMAL",
            })
        station_data[sid] = readings

    return station_data


def inject_faults(station_data: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Injects controlled ground-truth faults across stations."""
    data = copy.deepcopy(station_data)

    # 1. Genuine Regional Event (Correlated Heatwave across AWS-001 and AWS-002 on Day 15)
    # Between step 1440 and 1536 (24 hours)
    for sid in ["AWS-001", "AWS-002"]:
        readings = data[sid]
        for idx in range(1440, min(1536, len(readings))):
            r = readings[idx]
            r["temperature"] = round(r["temperature"] + 8.5, 2)
            r["pressure"] = round(r["pressure"] - 5.0, 2)
            r["humidity"] = round(max(10.0, r["humidity"] - 20.0), 2)
            # Ground truth: Validated regional event, NOT a hardware sensor fault
            r["is_anomaly"] = False
            r["fault_type"] = "GENUINE_WEATHER_EVENT"

    # 2. AWS-001 Sudden Spike (Day 5, step 480)
    r_spike = data["AWS-001"][480]
    r_spike["temperature"] = round(r_spike["temperature"] + 14.5, 2)
    r_spike["is_anomaly"] = True
    r_spike["fault_type"] = "SPIKE"

    # 3. AWS-002 Frozen Sensor (Day 8, step 768 to 800)
    frozen_val = data["AWS-002"][768]["temperature"]
    for idx in range(768, 800):
        r_f = data["AWS-002"][idx]
        r_f["temperature"] = frozen_val
        r_f["is_anomaly"] = True
        r_f["fault_type"] = "FROZEN_SENSOR"

    # 4. AWS-003 Calibration Drift (Day 20 to 25, +0.25°C per day)
    start_step = 1920
    drift = 0.0
    for idx in range(start_step, min(2400, len(data["AWS-003"]))):
        drift += 0.005  # Accumulates across 15-min intervals
        r_d = data["AWS-003"][idx]
        r_d["temperature"] = round(r_d["temperature"] + drift, 2)
        if drift > 1.5:  # Noticeable drift threshold
            r_d["is_anomaly"] = True
            r_d["fault_type"] = "CALIBRATION_DRIFT"

    # 5. AWS-004 Communication Dropout / Null gap (Day 10, step 960 to 975)
    for idx in range(960, 975):
        r_drop = data["AWS-004"][idx]
        r_drop["temperature"] = None
        r_drop["pressure"] = None
        r_drop["humidity"] = None
        r_drop["is_anomaly"] = True
        r_drop["fault_type"] = "COMMUNICATION_DROPOUT"

    # Flatten and sort strictly by timestamp ASC, station_id ASC
    all_readings = []
    for sid, readings in data.items():
        all_readings.extend(readings)

    all_readings.sort(key=lambda x: (x["timestamp"], x["station_id"]))
    return all_readings


def main():
    output_dir = Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "historical_benchmark_30d.csv"

    print("Generating 30-day multi-station clean baseline...")
    clean = generate_clean_data(num_days=30)

    print("Injecting labeled meteorological faults and regional events...")
    dataset = inject_faults(clean)

    fieldnames = [
        "station_id",
        "timestamp",
        "temperature",
        "pressure",
        "humidity",
        "latitude",
        "longitude",
        "elevation",
        "is_anomaly",
        "fault_type",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dataset)

    print(f"Generated {len(dataset)} chronological records written to {output_file}.")


if __name__ == "__main__":
    main()
