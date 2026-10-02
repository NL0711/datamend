"""
tests/test_noaa_benchmark.py
SkyGuard AI — Test Suite for NOAA ISD Benchmark Pipeline.
"""

from pathlib import Path
import pytest
import pandas as pd

from scripts.benchmark_noaa import run_noaa_benchmark
from scripts.import_noaa_data import generate_sample_noaa_dataset


def test_noaa_benchmark_execution(tmp_path: Path):
    """Verifies that the benchmark runs across a test dataset and generates valid reports."""
    # 1. Create small test dataset
    data_path = tmp_path / "test_data.csv"
    df = generate_sample_noaa_dataset(num_records=50)
    df.to_csv(data_path, index=False)

    reports_dir = tmp_path / "reports"
    report_data = run_noaa_benchmark(dataset_path=data_path, reports_dir=reports_dir)

    # 2. Check JSON output
    json_path = reports_dir / "noaa_benchmark.json"
    assert json_path.exists()
    assert report_data["dataset"]["total_observations"] == 50
    assert "anomaly_summary" in report_data
    assert "score_distribution" in report_data
    assert "classification_breakdown" in report_data

    # 3. Check Markdown output
    md_path = reports_dir / "noaa_benchmark.md"
    assert md_path.exists()
    md_content = md_path.read_text(encoding="utf-8")
    assert "SkyGuard AI — NOAA ISD Observational Benchmark Report" in md_content
    assert "Executive Summary" in md_content
