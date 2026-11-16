"""Leakage guard: which years each fitted statistic was computed from, and a check against the split.

Rules (see README): climatology, normalization scale, the statistical-baseline bound, station affine
parameters and the rank-normalization reference are fit on **training years only**; the operating
threshold is calibrated on **clean validation years**; test years are never used to fit anything.
"""

from __future__ import annotations

from typing import Dict, Iterable

ALLOWED_SPLIT = {
    "transform": "train",
    "climatology": "train",
    "stat_baseline": "train",
    "station_affine": "train",
    "rank_reference": "train",
    "threshold": "val",
}


class LeakageError(AssertionError):
    pass


def assert_no_leakage(provenance: Dict[str, Iterable[int]], split) -> None:
    """Raise ``LeakageError`` if any recorded statistic used years outside its allowed split.

    ``provenance`` maps a statistic name to the years it was computed from (None / empty = not built).
    Unknown statistic names are an error too, so a new statistic cannot silently skip the check.
    """
    for stat, years in provenance.items():
        if stat not in ALLOWED_SPLIT:
            raise LeakageError(f"statistic {stat!r} has no declared allowed split; add it to ALLOWED_SPLIT")
        used = set(years or [])
        allowed = set(getattr(split, ALLOWED_SPLIT[stat]))
        bad = used - allowed
        if bad:
            raise LeakageError(f"{stat} used years {sorted(bad)} outside its allowed {ALLOWED_SPLIT[stat]} years")
        if used & set(split.test):
            raise LeakageError(f"{stat} used test years {sorted(used & set(split.test))}")
