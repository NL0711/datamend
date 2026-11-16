"""End-to-end: archive -> split -> fit transform+climatology (train only) -> train -> calibrate -> evaluate -> artifact."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional

import numpy as np

from training import artifact
from training.calibration import Calibration
from training.climatology import ClimatologyAccumulator
from training.data import RainfallArchive
from training.elevation import load_elevation
from training.evaluate import evaluate
from training.leakage import assert_no_leakage
from training.sampler import NullStationProvider
from training.partition import partition_cells
from training.sampler import WindowSampler, YearCube
from training.splits import YearSplit, split_years
from training.trainer import LocalTrainer, TrainConfig
from training.transform import RainfallTransform


@dataclass
class Prepared:
    """Everything derived from the data, reusable across many training runs (sweeps)."""
    archive: RainfallArchive
    split: YearSplit
    cubes: Dict[int, YearCube]
    transform: RainfallTransform
    clim: np.ndarray
    cells: np.ndarray
    coarse_blocks: tuple = ()
    elevation: Optional[np.ndarray] = None
    stat_baseline: Optional[object] = None
    provenance: dict = field(default_factory=dict)  # statistic -> years it was fit on (see training/leakage.py)


def prepare(
    data_dir: str | Path,
    val_years: int = 3,
    test_years: int = 4,
    max_train_years: Optional[int] = None,
    coarse_blocks=(),
    elevation_path: Optional[str] = None,
    build_stat: bool = False,
    log=print,
) -> Prepared:
    arch = RainfallArchive(data_dir)
    split = split_years(arch.years, val_years, test_years)
    if max_train_years:
        split = YearSplit(split.train[-max_train_years:], split.val, split.test)
    log(f"years={arch.years[0]}-{arch.years[-1]} missing={arch.missing_years} train={len(split.train)} "
        f"val={split.val} test={split.test} land_cells={int(arch.land_mask.sum())}")
    acc = ClimatologyAccumulator(arch.land_mask.shape)
    samples, cubes = [], {}
    for y in split.train + split.val + split.test:
        cube = arch.load(y)
        if y in split.train:  # transform and climatology never see val/test years
            samples.append(cube[::5].ravel())
            acc.add(cube)
        cubes[y] = YearCube.build(cube, coarse_blocks)
    transform = RainfallTransform.fit(np.concatenate(samples))
    log(f"transform scale={transform.scale:.3f}")
    stat = None
    if build_stat:
        from ensemble.statbaseline import StatBaseline
        stat = StatBaseline.fit([cubes[y] for y in split.train], split.train)
    prov = {"transform": list(split.train), "climatology": list(split.train),
            "stat_baseline": list(split.train) if build_stat else None}
    assert_no_leakage(prov, split)
    return Prepared(arch, split, cubes, transform, acc.result(), partition_cells(arch.land_mask, "all")[0],
                    tuple(coarse_blocks), load_elevation(elevation_path, arch.land_mask.shape) if elevation_path else None,
                    stat, prov)


def make_sampler(prep: Prepared, config: TrainConfig, years, seed: int, patch: Optional[int] = None) -> WindowSampler:
    """Sampler over ``years`` for ``config``. ``patch`` overrides the neighbourhood patch size (the
    ensemble runner uses one sampler for all members, so it must carry what the richest member needs)."""
    a = prep.archive
    lat = (a.lat - a.lat.min()) / max(float(np.ptp(a.lat)), 1e-6)
    lon = (a.lon - a.lon.min()) / max(float(np.ptp(a.lon)), 1e-6)
    if config.use_elevation and prep.elevation is None:
        logging.getLogger(__name__).warning("use_elevation is set but no elevation was loaded (pass --elevation): "
                                            "elevation is marked unavailable")
    patch = (config.patch if config.arch == "scalenet" else 0) if patch is None else patch
    return WindowSampler([prep.cubes[y] for y in years], a.land_mask, prep.cells, config.window, seed,
                         prep.clim, lat, lon, patch, prep.elevation if config.use_elevation else None,
                         NullStationProvider() if config.use_stations else None)


@dataclass
class Member:
    """A fitted model with its own calibration and the samplers it was trained with."""
    trainer: LocalTrainer
    cal: Calibration
    history: dict
    train_s: WindowSampler
    val_s: WindowSampler
    test_s: WindowSampler


def fit_member(prep: Prepared, config: TrainConfig, epochs: int, log=print) -> Member:
    if config.arch == "msnet" and tuple(config.coarse_blocks) != prep.coarse_blocks:
        raise ValueError(f"config.coarse_blocks={config.coarse_blocks} but data was prepared with {list(prep.coarse_blocks)}")
    train_s = make_sampler(prep, config, prep.split.train, config.seed)
    val_s = make_sampler(prep, config, prep.split.val, config.seed + 1)
    test_s = make_sampler(prep, config, prep.split.test, config.seed + 2)
    trainer = LocalTrainer(prep.transform, config)
    log(f"arch={config.arch} device={trainer.device} params="
        f"{sum(p.numel() for p in trainer.model.parameters()):,}")
    t0, hist = time.time(), {"train_loss": [], "val_loss": []}
    for e in range(epochs):
        hist["train_loss"] += trainer.fit(train_s, 1, total_epochs=epochs)["train_loss"]
        hist["val_loss"].append(trainer.validate(val_s))
        log(f"epoch {e + 1}/{epochs} train={hist['train_loss'][-1]:.4f} "
            f"val={hist['val_loss'][-1]:.4f} ({time.time() - t0:.0f}s)")
    return Member(trainer, Calibration.fit(trainer, val_s), hist, train_s, val_s, test_s)


def train_prepared(
    prep: Prepared,
    config: TrainConfig,
    epochs: int,
    out_dir: Optional[str | Path] = None,
    eval_windows: int = 4096,
    log=print,
) -> Dict:
    m = fit_member(prep, config, epochs, log)
    result = {
        "val": evaluate(m.trainer, m.val_s, m.cal, eval_windows, seed=11),
        "test": evaluate(m.trainer, m.test_s, m.cal, eval_windows, seed=0),
        "history": m.history,
        "config": config.to_dict(),
    }
    log(f"val  primary={result['val']['primary']}")
    log(f"test primary={result['test']['primary']}")
    log(f"test per-stream={result['test']['scores']}")
    log(f"test per-kind={result['test']['per_kind_roc_auc']}")
    if out_dir:
        artifact.save(artifact.Artifact(m.trainer, m.cal, {
            "train_years": prep.split.train, "val_years": prep.split.val, "test_years": prep.split.test,
            "missing_years": prep.archive.missing_years, "history": m.history,
            "sources": [asdict(sp) for sp in m.train_s.specs],
            "val_metrics": result["val"], "test_metrics": result["test"],
        }), out_dir)
    return result


def run(
    data_dir: str | Path,
    out_dir: str | Path,
    config: Optional[TrainConfig] = None,
    epochs: int = 10,
    max_train_years: Optional[int] = None,
    val_years: int = 3,
    test_years: int = 4,
    log=print,
) -> Dict:
    config = config or TrainConfig()
    prep = prepare(data_dir, val_years, test_years, max_train_years, config.coarse_blocks, log=log)
    return train_prepared(prep, config, epochs, out_dir, log=log)
