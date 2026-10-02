"""
SkyGuard AI — Command Line Interface for Dataset Generation and Benchmarking.

Exports labeled, temporally partitioned CSV, JSON, or Parquet datasets into data/
with strict temporal boundary enforcement (baseline_clean, train_clean, val_mixed, test_anomalies).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from backend.simulator.scenarios import (
    CleanBaselineScenario,
    MultiFaultStressScenario,
    ScenarioRegistry,
)


def export_dataframe(df: pd.DataFrame, output_path: Path, file_format: str = "csv") -> None:
    """Exports DataFrame to disk creating parent directories if needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if file_format == "csv":
        df.to_csv(output_path, index=False)
    elif file_format == "json":
        df.to_json(output_path, orient="records", date_format="iso", indent=2)
    elif file_format == "parquet":
        df.to_parquet(output_path, index=False)
    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def generate_temporal_splits(
    output_dir: Path,
    total_days: float = 30.0,
    sampling_interval_min: float = 5.0,
    seed: int = 42,
    file_format: str = "csv",
) -> Tuple[Path, Path, Path, Path]:
    """
    Generates standardized temporal train/val/test splits with zero forward leakage:
    1. data/baseline_clean.csv (Days 1-30, 100% clean baseline)
    2. data/train_clean.csv (Days 1-20, 100% clean training partition)
    3. data/val_mixed.csv (Days 21-25, mixed faults for calibration)
    4. data/test_anomalies.csv (Days 26-30, hold-out test faults for F1 benchmark)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate Full Clean Baseline
    clean_scenario = CleanBaselineScenario(duration_days=total_days, sampling_interval_min=sampling_interval_min)
    baseline_clean_df = clean_scenario.generate(seed=seed)
    baseline_path = output_dir / f"baseline_clean.{file_format}"
    export_dataframe(baseline_clean_df, baseline_path, file_format)

    # 2. Partition Train Set (Days 1-20, exactly 5,760 rows at 5-min intervals for 30d total)
    train_ratio = 20.0 / total_days if total_days >= 20.0 else 0.60
    train_rows = int(round(len(baseline_clean_df) * train_ratio))
    train_df = baseline_clean_df.iloc[:train_rows].copy().reset_index(drop=True)
    train_path = output_dir / f"train_clean.{file_format}"
    export_dataframe(train_df, train_path, file_format)

    # 3. Generate Multi-Fault Dataset for Val and Test partitions
    stress_scenario = MultiFaultStressScenario(duration_days=total_days, sampling_interval_min=sampling_interval_min)
    stress_df = stress_scenario.generate(seed=seed)

    # 4. Partition Validation Set (Days 21-25, rows 5760 to 7199 for 30d total)
    val_ratio = 25.0 / total_days if total_days >= 25.0 else 0.80
    val_start_row = train_rows
    val_end_row = int(round(len(stress_df) * val_ratio))
    val_df = stress_df.iloc[val_start_row:val_end_row].copy().reset_index(drop=True)
    val_path = output_dir / f"val_mixed.{file_format}"
    export_dataframe(val_df, val_path, file_format)

    # 5. Partition Test Set (Days 26-30, rows 7200 to 8639 for 30d total)
    test_start_row = val_end_row
    test_df = stress_df.iloc[test_start_row:].copy().reset_index(drop=True)
    test_path = output_dir / f"test_anomalies.{file_format}"
    export_dataframe(test_df, test_path, file_format)

    return baseline_path, train_path, val_path, test_path


def main(args: Optional[list] = None) -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="skyguard-sim",
        description="SkyGuard AI — Weather Telemetry & Anomaly Benchmark Dataset Generator",
    )
    parser.add_argument(
        "--scenario", "-s",
        type=str,
        default=None,
        help="Name of benchmark scenario to run (e.g. clean_baseline, multi_fault_stress, weather_front).",
    )
    parser.add_argument(
        "--splits",
        action="store_true",
        help="Generate standard train/val/test temporal dataset splits into data/.",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="data",
        help="Directory to save generated datasets (default: 'data').",
    )
    parser.add_argument(
        "--output-file", "-f",
        type=str,
        default=None,
        help="Specific target output file (overrides --output-dir).",
    )
    parser.add_argument(
        "--days", "-d",
        type=float,
        default=30.0,
        help="Total duration in days (default: 30.0).",
    )
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=5.0,
        help="Sampling interval in minutes (default: 5.0).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic random seed (default: 42).",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["csv", "json", "parquet"],
        default="csv",
        help="Output serialization format (default: csv).",
    )
    parser.add_argument(
        "--list-scenarios", "-l",
        action="store_true",
        help="List all registered benchmark scenarios and exit.",
    )

    parsed_args = parser.parse_args(args)

    if parsed_args.list_scenarios:
        scenarios = ScenarioRegistry.list_scenarios()
        print("\n=== SkyGuard AI Registered Benchmark Scenarios ===")
        print(f"{'Scenario Name':<28} | {'Days':<6} | {'Interval':<8} | {'Anomalies':<9} | {'Description'}")
        print("-" * 90)
        for meta in scenarios:
            print(f"{meta.name:<28} | {meta.duration_days:<6.1f} | {meta.sampling_interval_min:<8.1f} | {meta.expected_anomaly_count:<9} | {meta.description}")
        return 0

    out_dir = Path(parsed_args.output_dir)

    if parsed_args.splits:
        print(f"[SkyGuard Sim] Generating standardized temporal dataset splits (Seed={parsed_args.seed})...")
        p_base, p_train, p_val, p_test = generate_temporal_splits(
            output_dir=out_dir,
            total_days=parsed_args.days,
            sampling_interval_min=parsed_args.interval,
            seed=parsed_args.seed,
            file_format=parsed_args.format,
        )
        print(f"  [+] Baseline Clean : {p_base} ({p_base.stat().st_size / 1024:.1f} KB)")
        print(f"  [+] Train Clean    : {p_train} ({p_train.stat().st_size / 1024:.1f} KB)")
        print(f"  [+] Val Mixed      : {p_val} ({p_val.stat().st_size / 1024:.1f} KB)")
        print(f"  [+] Test Anomalies : {p_test} ({p_test.stat().st_size / 1024:.1f} KB)")
        print("[SkyGuard Sim] Temporal split generation complete with zero data leakage.")
        return 0

    if parsed_args.scenario:
        print(f"[SkyGuard Sim] Running benchmark scenario '{parsed_args.scenario}'...")
        scenario = ScenarioRegistry.get(parsed_args.scenario)
        df = scenario.generate(seed=parsed_args.seed)

        target_file = Path(parsed_args.output_file) if parsed_args.output_file else out_dir / f"{parsed_args.scenario}.{parsed_args.format}"
        export_dataframe(df, target_file, parsed_args.format)
        print(f"[SkyGuard Sim] Successfully exported {len(df)} rows to {target_file}")
        return 0

    # Default fallback: generate clean baseline
    print("[SkyGuard Sim] No scenario specified. Generating default clean baseline...")
    df = CleanBaselineScenario(duration_days=parsed_args.days, sampling_interval_min=parsed_args.interval).generate(seed=parsed_args.seed)
    target_file = Path(parsed_args.output_file) if parsed_args.output_file else out_dir / f"baseline_clean.{parsed_args.format}"
    export_dataframe(df, target_file, parsed_args.format)
    print(f"[SkyGuard Sim] Successfully exported {len(df)} rows to {target_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

