"""Feedback ingestion and dataset assembly (Phase 5, Task 5.1).

Joins raw telemetry, residual features, and operator labels into versioned
training partitions, validates data integrity, and flags systematic
operator disagreement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

EXPECTED_CHANNELS: tuple[str, ...] = ("temperature", "pressure", "humidity")

EXPECTED_RESIDUAL_COLUMNS: tuple[str, ...] = ("T_resid", "P_resid", "RH_resid")

ALLOWED_LABELS: frozenset[str] = frozenset(
    {
        "SPIKE",
        "FROZEN_SENSOR",
        "COMMUNICATION_DROPOUT",
        "CALIBRATION_DRIFT",
        "POWER_FLUCTUATION",
        "DATA_CORRUPTION",
        "GENUINE_WEATHER_EVENT",
        "NORMAL",
    }
)


@dataclass
class TrainingPartition:
    """One station/window join of telemetry + residuals + labels."""

    station: str
    version: str
    frame: pd.DataFrame
    n_telemetry: int
    n_residual: int
    n_label: int
    n_joined: int


@dataclass
class MissingWindow:
    """A station window excluded from training with the cause recorded."""

    station: str
    missing_input: str  # telemetry | residuals | labels | timestamps
    detail: str = ""


@dataclass
class PartitionValidation:
    """Integrity verdict for one partition."""

    station: str
    is_valid: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class DisagreementFlag:
    """A slice whose label contradiction rate exceeds the threshold."""

    slice_key: str
    contradiction_rate: float
    n_samples: int


def build_partitions(
    telemetry: dict[str, pd.DataFrame],
    residuals: dict[str, pd.DataFrame],
    labels: dict[str, pd.DataFrame],
    version: str,
) -> tuple[list[TrainingPartition], list[MissingWindow]]:
    """Join the three inputs per station on timestamp index.

    Stations missing from any input are excluded with the missing input
    recorded. Stations whose inputs share no overlapping timestamps are
    excluded with ``missing_input="timestamps"``.
    """
    partitions: list[TrainingPartition] = []
    missing: list[MissingWindow] = []
    for station in sorted(set(telemetry) | set(residuals) | set(labels)):
        for name, source in (
            ("telemetry", telemetry),
            ("residuals", residuals),
            ("labels", labels),
        ):
            if station not in source:
                missing.append(
                    MissingWindow(
                        station=station,
                        missing_input=name,
                        detail=f"station {station!r} absent from {name}",
                    )
                )
                break
        else:
            joined, n_t, n_r, n_l = _inner_join(
                telemetry[station], residuals[station], labels[station]
            )
            if joined is None:
                missing.append(
                    MissingWindow(
                        station=station,
                        missing_input="timestamps",
                        detail="no overlapping timestamps across inputs",
                    )
                )
                continue
            partitions.append(
                TrainingPartition(
                    station=station,
                    version=version,
                    frame=joined,
                    n_telemetry=n_t,
                    n_residual=n_r,
                    n_label=n_l,
                    n_joined=len(joined),
                )
            )
    return partitions, missing


def _inner_join(
    telemetry: pd.DataFrame, residuals: pd.DataFrame, labels: pd.DataFrame
) -> tuple[pd.DataFrame | None, int, int, int]:
    n_t, n_r, n_l = len(telemetry), len(residuals), len(labels)
    common = (
        telemetry.index.intersection(residuals.index).intersection(labels.index)
    )
    if len(common) == 0:
        return None, n_t, n_r, n_l
    tel = telemetry.loc[common]
    # Guard against column-name collisions across the three inputs.
    clashes = set(tel.columns) & (
        set(residuals.columns) | set(labels.columns)
    )
    if clashes:
        tel = tel.rename(columns={c: f"{c}__tel" for c in clashes})
    joined = pd.concat(
        [tel, residuals.loc[common], labels.loc[common]], axis=1
    )
    return joined.sort_index(), n_t, n_r, n_l


def validate_partition(
    partition: TrainingPartition,
    expected_channels: tuple[str, ...] = EXPECTED_CHANNELS,
    allowed_labels: frozenset[str] = ALLOWED_LABELS,
) -> PartitionValidation:
    """Check timestamp alignment, channel completeness, and label schema."""
    reasons: list[str] = []
    frame = partition.frame

    dropped = (
        (partition.n_telemetry - partition.n_joined)
        + (partition.n_residual - partition.n_joined)
        + (partition.n_label - partition.n_joined)
    )
    if dropped > 0:
        reasons.append(
            "timestamp misalignment: "
            f"{partition.n_telemetry}/{partition.n_residual}/{partition.n_label} "
            f"rows collapsed to {partition.n_joined} joined rows"
        )
    if not frame.index.is_unique:
        reasons.append("timestamp misalignment: duplicate timestamps in join")
    try:
        if not frame.index.is_monotonic_increasing:
            reasons.append("timestamp misalignment: index not monotonic")
    except TypeError:
        reasons.append("timestamp misalignment: unsortable index")

    for channel in expected_channels:
        if channel not in frame.columns:
            reasons.append(f"missing channel: {channel}")
    for column in EXPECTED_RESIDUAL_COLUMNS:
        if column not in frame.columns:
            reasons.append(f"missing residual column: {column}")

    if "label" not in frame.columns:
        reasons.append("malformed labels: missing 'label' column")
    else:
        raw = frame["label"]
        if raw.isna().any():
            reasons.append("malformed labels: null label values")
        unknown = set(raw.dropna().unique()) - set(allowed_labels)
        if unknown:
            reasons.append(
                "malformed labels: unknown classes "
                + ", ".join(sorted(str(v) for v in unknown))
            )
    if "operator" not in frame.columns:
        reasons.append("malformed labels: missing 'operator' column")

    return PartitionValidation(
        station=partition.station, is_valid=not reasons, reasons=reasons
    )


def flag_operator_disagreement(
    labels: pd.DataFrame,
    *,
    group_by: tuple[str, ...] = ("station",),
    threshold: float = 0.2,
) -> list[DisagreementFlag]:
    """Flag slices whose label contradiction rate exceeds ``threshold``.

    Contradiction rate for a slice is ``1 - max_class_share``: 0 when every
    label in the slice agrees, approaching 1 when labels are evenly split.
    """
    if "label" not in labels.columns:
        raise ValueError("labels frame must contain a 'label' column")
    missing_groups = [c for c in group_by if c not in labels.columns]
    if missing_groups:
        raise ValueError(f"missing group columns: {missing_groups}")
    flags: list[DisagreementFlag] = []
    for key, group in labels.groupby(list(group_by), sort=True):
        counts = group["label"].value_counts()
        total = int(counts.sum())
        if total == 0:
            continue
        rate = 1.0 - float(counts.iloc[0]) / total
        if rate > threshold:
            label = (
                "|".join(str(p) for p in key)
                if isinstance(key, tuple)
                else str(key)
            )
            flags.append(
                DisagreementFlag(
                    slice_key=label, contradiction_rate=rate, n_samples=total
                )
            )
    return flags
