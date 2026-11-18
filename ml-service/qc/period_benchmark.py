"""Frozen synthetic benchmark for the coarser time scales (monthly, seasonal, yearly).

STATUS: new, unit-tested on a generated world only; nothing has run on real RF25. SYNTHETIC faults, not real QC labels.

It is built on top of the frozen DAILY benchmark (``qc.benchmark``), so every scale is scored on the same faults:

1. take a benchmark year (clean daily values, the injected daily faults, protected and ambiguous extremes);
2. aggregate the clean and the corrupted days to periods (``qc.resolution.aggregate``);
3. a period is labelled faulty if an injected daily fault is in it and moved its total beyond the tolerance (``visible``);
4. add faults that exist only at period level (a whole period scaled or lost, ``corrupt_periods``), never on a period holding a
   protected extreme, and label them too.

``make_period_year`` is the pure step (arrays in, ``PeriodYear`` out). ``build_period_benchmark`` writes one file per
(scale, split, year) next to the daily benchmark with a manifest and a hash that includes the hash of the daily benchmark.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np

from qc.resolution import (PERIOD_KINDS, SEASON_MONTHS, Periods, aggregate, aggregate_labels, corrupt_periods, period_ids)

SCALES = ("monthly", "seasonal", "yearly")
SPLITS = ("val", "test", "stress")
SCHEMA = 1


@dataclass
class PeriodYear:
    year: int
    scale: str
    clean: Periods
    corrupted: Periods           # what a scorer is given
    fault: np.ndarray            # (P, n) bool: visible daily fault or period-level fault
    from_daily: np.ndarray       # (P, n) bool: the fault came from an injected daily fault
    period_kind: np.ndarray      # (P, n) int8: index into PERIOD_KINDS for period-level faults, -1 none
    protected: np.ndarray        # (P, n) bool: the period holds a protected genuine extreme day
    ambiguous: np.ndarray        # (P, n) bool: the period holds an ambiguous extreme day
    valid: np.ndarray            # (P, n) bool: clean and corrupted totals are both defined

    @property
    def clean_mask(self) -> np.ndarray:
        """Periods with no fault and no extreme: the ones false alarms are counted on."""
        return self.valid & ~self.fault & ~self.protected & ~self.ambiguous


def _any_over_periods(mask: np.ndarray, ids: np.ndarray, n_periods: int) -> np.ndarray:
    out = np.zeros((n_periods, mask.shape[1]), bool)
    for p in range(n_periods):
        sel = ids == p
        if sel.any():
            out[p] = mask[sel].any(axis=0)
    return out


def make_period_year(clean: np.ndarray, corrupted: np.ndarray, day_labels: np.ndarray, protected: np.ndarray,
                     ambiguous: np.ndarray, year: int, scale: str, rng: np.random.Generator, rate: float = 0.01,
                     kinds: Sequence[str] = PERIOD_KINDS, season: Sequence[int] = SEASON_MONTHS) -> PeriodYear:
    if scale not in SCALES:
        raise ValueError(f"scale must be one of {SCALES}, not {scale!r}")
    ids = period_ids(year, clean.shape[0], scale, season)
    P = 12 if scale == "monthly" else 1
    c = aggregate(clean, year, scale, season=season)
    k = aggregate(corrupted, year, scale, season=season)
    lab = aggregate_labels(clean, corrupted, day_labels, year, scale, season=season)
    prot = _any_over_periods(protected, ids, P)
    amb = _any_over_periods(ambiguous, ids, P)
    k2, pf = corrupt_periods(k, rng, rate, kinds, forbidden=prot)
    from_daily = lab.visible & c.valid & k.valid
    fault = from_daily | pf.labels
    return PeriodYear(int(year), scale, c, k2, fault, from_daily, pf.kind, prot, amb, c.valid & k2.valid)


# --------------------------------------------------------------------------------------------- files
def period_dir(daily_bench_dir: Path) -> Path:
    return Path(daily_bench_dir) / "period"


def _file(root: Path, scale: str, split: str, year: int) -> Path:
    return Path(root) / f"{scale}_{split}_{year}.npz"


def save_period_year(root: Path, split: str, py: PeriodYear) -> Path:
    path = _file(root, py.scale, split, py.year)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, clean_total=py.clean.total, corrupted_total=py.corrupted.total, clean_wet=py.clean.wet_days,
                        corrupted_wet=py.corrupted.wet_days, clean_max=py.clean.max_mm, corrupted_max=py.corrupted.max_mm,
                        n_days=py.clean.n_days, clean_valid=py.clean.valid, corrupted_valid=py.corrupted.valid,
                        fault=py.fault, from_daily=py.from_daily, period_kind=py.period_kind, protected=py.protected,
                        ambiguous=py.ambiguous, valid=py.valid, year=np.array(py.year), scale=np.array(py.scale))
    return path


def load_period_year(root: Path, scale: str, split: str, year: int) -> PeriodYear:
    z = np.load(_file(root, scale, split, year))
    mk = lambda pre: Periods(scale, year, z[f"{pre}_total"], z[f"{pre}_wet"], z[f"{pre}_max"], z["n_days"], z[f"{pre}_valid"])
    return PeriodYear(int(year), scale, mk("clean"), mk("corrupted"), z["fault"], z["from_daily"], z["period_kind"],
                      z["protected"], z["ambiguous"], z["valid"])


def _digest(h, *arrays) -> None:
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())


def build_period_benchmark(p, scales: Sequence[str] = SCALES, splits: Sequence[str] = SPLITS, rate: Optional[float] = None,
                           seed: Optional[int] = None, overwrite: bool = False) -> Dict:
    """Build the period benchmark from the frozen daily benchmark of ``p`` (a ``qc.prepare.Prepared``)."""
    from qc.benchmark import bench_dir, check_benchmark, load_bench_year

    daily = check_benchmark(p)
    root = period_dir(bench_dir(p.cfg))
    manifest_path = root / "manifest.json"
    if manifest_path.is_file() and not overwrite:
        raise FileExistsError(f"{manifest_path} exists; pass overwrite=True to rebuild it")
    cfg = p.cfg
    pb = cfg.get("period_benchmark")
    if rate is None:
        rate = float(pb.get("rate", 0.02)) if pb is not None else 0.02
    seed = int(p.cfg.seed) if seed is None else int(seed)
    h = hashlib.sha256()
    h.update(daily["hash"].encode())
    h.update(json.dumps({"rate": rate, "scales": list(scales), "schema": SCHEMA}, sort_keys=True).encode())
    summary: Dict = {}
    for split in splits:
        years = p.split.years["stress" if split == "stress" else split]
        for si, scale in enumerate(scales):
            n_fault = n_valid = 0
            for year in years:
                by = load_bench_year(p, split, year)
                rng = np.random.default_rng([seed, int(year), si])
                py = make_period_year(by.clean, by.corrupted, by.faults.labels(), by.extremes.protected, by.extremes.ambiguous,
                                      year, scale, rng, rate)
                save_period_year(root, split, py)
                _digest(h, py.fault, py.corrupted.total.astype(np.float32), py.period_kind)
                n_fault += int(py.fault.sum())
                n_valid += int(py.valid.sum())
            summary[f"{split}/{scale}"] = {"years": [int(min(years)), int(max(years))], "fault_periods": n_fault,
                                           "valid_periods": n_valid, "fault_share": n_fault / max(n_valid, 1)}
    manifest = {"schema": SCHEMA, "daily_benchmark_hash": daily["hash"], "rate": rate, "seed": seed, "scales": list(scales),
                "splits": list(splits), "hash": h.hexdigest()[:16], "summary": summary,
                "note": "SYNTHETIC faults: aggregated daily faults (visible) plus period-level scale and dropout faults"}
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def check_period_benchmark(p, expected_hash: Optional[str] = None) -> Dict:
    """Load the manifest; refuse if it was built on a different daily benchmark or is not the pinned one."""
    from qc.benchmark import bench_dir, check_benchmark
    from qc.grid import ContractError

    daily = check_benchmark(p)
    path = period_dir(bench_dir(p.cfg)) / "manifest.json"
    if not path.is_file():
        raise ContractError(f"no period benchmark at {path.parent}. Build it with: python -m qc period-benchmark")
    m = json.loads(path.read_text(encoding="utf-8"))
    if m["daily_benchmark_hash"] != daily["hash"]:
        raise ContractError("the period benchmark was built on a different daily benchmark; rebuild it with --overwrite")
    if expected_hash and m["hash"] != expected_hash:
        raise ContractError(f"period benchmark hash is {m['hash']} but {expected_hash} was expected; refusing to score")
    return m
