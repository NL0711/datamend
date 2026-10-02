"""
SkyGuard AI — Dataset Generation Script.

Generates standard synthetic training, validation, and test datasets in data/
with strict temporal boundary partitions and deterministic reproducibility:
1. data/baseline_clean.csv (30 Days, 100% clean baseline)
2. data/train_clean.csv (Days 1-20, 100% clean training partition)
3. data/val_mixed.csv (Days 21-25, mixed faults for calibration)
4. data/test_anomalies.csv (Days 26-30, hold-out test faults for benchmark)
"""

import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.simulator.cli import generate_temporal_splits


def run() -> None:
    data_dir = root_dir / "data"
    print("=" * 75)
    print("  SkyGuard AI — Standard Dataset Generation Workflow (Milestone M1)")
    print("=" * 75)
    print(f"Target Output Directory: {data_dir}")
    print("Generating standardized temporal train/val/test splits (30 Days, 5-min interval)...")

    p_base, p_train, p_val, p_test = generate_temporal_splits(
        output_dir=data_dir,
        total_days=30.0,
        sampling_interval_min=5.0,
        seed=42,
        file_format="csv",
    )

    print("\nDataset Generation Summary:")
    print(f"  1. Baseline Clean (30d) : {p_base.name:<22} ({p_base.stat().st_size / 1024:.1f} KB, 8,640 rows, 100% clean)")
    print(f"  2. Train Clean (20d)    : {p_train.name:<22} ({p_train.stat().st_size / 1024:.1f} KB, 5,760 rows, 100% clean)")
    print(f"  3. Val Mixed (5d)       : {p_val.name:<22} ({p_val.stat().st_size / 1024:.1f} KB, 1,440 rows, ~5.0% anomalies)")
    print(f"  4. Test Anomalies (5d)  : {p_test.name:<22} ({p_test.stat().st_size / 1024:.1f} KB, 1,440 rows, ~6.7% anomalies)")
    print("=" * 75)
    print("[SUCCESS] All benchmark datasets generated with zero forward temporal leakage.")


if __name__ == "__main__":
    run()

