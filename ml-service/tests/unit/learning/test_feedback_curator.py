"""Unit tests for Phase 5 feedback curation (Tasks 1.2-1.4)."""

import pandas as pd
import pytest

from src.learning.feedback_curator import (
    build_partitions,
    flag_operator_disagreement,
    validate_partition,
)


def _frame(index, data):
    return pd.DataFrame(data, index=pd.DatetimeIndex(index))


@pytest.fixture()
def three_station_inputs():
    """Aligned telemetry + residuals + labels for stations s1..s3."""
    index = pd.date_range("2026-01-01", periods=24, freq="h")
    telemetry, residuals, labels = {}, {}, {}
    for station in ("s1", "s2", "s3"):
        telemetry[station] = _frame(
            index,
            {
                "temperature": range(24),
                "pressure": range(24),
                "humidity": range(24),
            },
        )
        residuals[station] = _frame(
            index,
            {"T_resid": 0.1, "P_resid": 0.0, "RH_resid": -0.1},
        )
        labels[station] = _frame(
            index, {"label": "NORMAL", "operator": "op-1"}
        )
    return telemetry, residuals, labels


def test_join_three_stations_timestamp_aligned_with_versions(
    three_station_inputs,
):
    telemetry, residuals, labels = three_station_inputs
    partitions, missing = build_partitions(
        telemetry, residuals, labels, version="v3"
    )
    assert [p.station for p in partitions] == ["s1", "s2", "s3"]
    assert missing == []
    for partition in partitions:
        assert partition.version == "v3"
        assert partition.n_joined == 24
        assert validate_partition(partition).is_valid
        for column in (
            "temperature",
            "pressure",
            "humidity",
            "T_resid",
            "P_resid",
            "RH_resid",
            "label",
            "operator",
        ):
            assert column in partition.frame.columns


def test_missing_input_window_excluded_with_record(
    three_station_inputs,
):
    telemetry, residuals, labels = three_station_inputs
    del residuals["s2"]  # station s2 has no residual features
    partitions, missing = build_partitions(
        telemetry, residuals, labels, version="v3"
    )
    assert [p.station for p in partitions] == ["s1", "s3"]
    assert len(missing) == 1
    assert missing[0].station == "s2"
    assert missing[0].missing_input == "residuals"


def test_misaligned_timestamps_rejected_with_reason(
    three_station_inputs,
):
    telemetry, residuals, labels = three_station_inputs
    # Drop the last 4 residual rows for s1 -> join collapses 24 to 20.
    residuals["s1"] = residuals["s1"].iloc[:20]
    partitions, _ = build_partitions(
        telemetry, residuals, labels, version="v3"
    )
    verdict = validate_partition(partitions[0])
    assert not verdict.is_valid
    assert any(
        "timestamp misalignment" in reason for reason in verdict.reasons
    )


def test_malformed_labels_rejected_and_valid_accepted(
    three_station_inputs,
):
    telemetry, residuals, labels = three_station_inputs
    bad = labels["s1"].copy()
    bad.loc[bad.index[:2], "label"] = "BOGUS_CLASS"
    labels["s1"] = bad
    partitions, _ = build_partitions(
        telemetry, residuals, labels, version="v3"
    )
    by_station = {p.station: p for p in partitions}
    bad_verdict = validate_partition(by_station["s1"])
    assert not bad_verdict.is_valid
    assert any("BOGUS_CLASS" in reason for reason in bad_verdict.reasons)
    good_verdict = validate_partition(by_station["s2"])
    assert good_verdict.is_valid
    assert good_verdict.reasons == []


def test_systematic_disagreement_flagged_with_rate_and_n():
    index = pd.date_range("2026-01-01", periods=10, freq="h")
    labels = _frame(
        index,
        {
            "station": ["A"] * 10,
            "operator": ["op-1"] * 10,
            # 7 NORMAL vs 3 SPIKE -> contradiction rate 0.3.
            "label": ["NORMAL"] * 7 + ["SPIKE"] * 3,
        },
    )
    flags = flag_operator_disagreement(
        labels, group_by=("station",), threshold=0.2
    )
    assert len(flags) == 1
    assert flags[0].slice_key == "A"
    assert flags[0].contradiction_rate == pytest.approx(0.3)
    assert flags[0].n_samples == 10


def test_random_disagreement_below_threshold_not_flagged():
    index = pd.date_range("2026-01-01", periods=20, freq="h")
    labels = _frame(
        index,
        {
            "station": ["A"] * 10 + ["B"] * 10,
            "operator": ["op-1"] * 20,
            # 9 NORMAL vs 1 SPIKE -> rate 0.1, below threshold.
            "label": ["NORMAL"] * 9 + ["SPIKE"] + ["NORMAL"] * 10,
        },
    )
    flags = flag_operator_disagreement(
        labels, group_by=("station",), threshold=0.2
    )
    assert flags == []
