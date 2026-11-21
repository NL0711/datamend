"""Chronological split by whole years (no random splitting -> no temporal leakage)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


@dataclass(frozen=True)
class YearSplit:
    train: List[int]
    val: List[int]
    test: List[int]


def split_years(years: Sequence[int], val_years: int = 3, test_years: int = 4) -> YearSplit:
    """Latest ``test_years`` -> test, the ``val_years`` before them -> val, rest -> train.

    Operates on the years that actually exist, so a gap such as 1992 simply
    never appears in any split.
    """
    ys = sorted(set(years))
    if len(ys) <= val_years + test_years:
        raise ValueError(f"Need more than {val_years + test_years} years, got {len(ys)}")
    return YearSplit(
        train=ys[: -(val_years + test_years)],
        val=ys[-(val_years + test_years) : -test_years],
        test=ys[-test_years:],
    )
