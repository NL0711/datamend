"""Gate 1: check the data contract, load the client map, build and audit the split, fit training statistics.

Writes ``<work>/splits/split_manifest.json`` and ``<work>/splits/train_stats.npz``. Later stages load both
through ``load_prepared`` and refuse to run if the manifest does not match the current config.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import numpy as np

from qc import paths
from qc.clients import load_client_map, map_hash
from qc.config import Config, year_range
from qc.grid import ContractError, Grid, SeriesStore, check_contract
from qc.runs import read_json, write_json
from qc.splits import Split, make_split
from qc.stats import TrainStats, fit_train_stats

log = logging.getLogger(__name__)


@dataclass
class Prepared:
    cfg: Config
    store: SeriesStore
    grid: Grid
    split: Split
    stats: TrainStats
    manifest: Dict
    cell_client: np.ndarray      # (n_land,) client id of each land cell
    cell_role: np.ndarray        # (n_land,) role of each land cell (qc.splits constants)

    def series(self, years):
        return self.store.years(list(years))


def all_years(cfg: Config):
    ys = set()
    for k in ("train", "val", "test", "stress"):
        ys |= set(year_range(cfg.years[k]))
    return sorted(ys)


def _client_map(cfg: Config, grid: Grid) -> np.ndarray:
    path = Path(cfg.clients.get("map") or paths.CLIENT_MAP_ASSET)
    if not path.is_file():
        raise ContractError(f"client map {path} not found. Create it once with: python -m qc client-map --config <config>")
    cm = load_client_map(path)
    if cm.shape != grid.shape or not np.array_equal(cm > 0, grid.land):
        raise ContractError(
            f"client map {path} does not match the data's land mask ({int((cm > 0).sum())} mapped cells, "
            f"{grid.n_land} land cells). It was built for a different grid."
        )
    if int(cm.max()) != int(cfg.clients.k):
        raise ContractError(f"client map has {int(cm.max())} clients, config says {cfg.clients.k}")
    return cm


def _open(cfg: Config):
    store = SeriesStore(paths.rf25_dir(cfg), paths.work_dir(cfg) / "cache")
    cm = _client_map(cfg, store.grid)
    split = make_split(cfg, cm)
    return store, cm, split


def prepare(cfg: Config, check_data: bool = True) -> Prepared:
    data_dir = paths.rf25_dir(cfg)
    years = all_years(cfg)
    report = None
    if check_data:
        log.info("checking the data contract for %d years in %s", len(years), data_dir)
        report = check_contract(data_dir, years, cfg.grid)
    store, cm, split = _open(cfg)
    if report is not None and not np.array_equal(report["land"], store.grid.land):
        raise ContractError("land mask from the contract check differs from the archive's land mask")
    cell_client = store.grid.to_series(cm).astype(np.int8)
    train = split.years["train"]
    log.info("fitting training statistics on %d-%d", train[0], train[-1])
    by_year = {y: store.year(y) for y in train}
    stats = fit_train_stats(by_year, train, split, cell_client, cfg.normalization.wet_mm,
                            cfg.normalization.wet_quantile, cfg.extremes.quantile)
    manifest = split.manifest()
    manifest["config_digest"] = cfg.digest()
    manifest["land_hash"] = store.grid.land_hash()
    manifest["client_scale"] = {str(k): v for k, v in stats.client_scale.items()}
    if report is not None:
        manifest["data"] = {"years": report["years"], "land_cells": report["land_cells"],
                            "missing_on_land_total": int(sum(report["missing_on_land"].values())),
                            "days_total": int(sum(report["days"].values()))}
    out = paths.work_dir(cfg) / "splits"
    stats.save(out / "train_stats.npz")
    write_json(out / "split_manifest.json", manifest)
    log.info("wrote %s", out)
    return Prepared(cfg, store, store.grid, split, stats, manifest, cell_client, store.grid.to_series(split.roles))


def load_prepared(cfg: Config) -> Prepared:
    """Load the saved split and statistics; fail if they were made under a different config, map or land mask."""
    out = paths.work_dir(cfg) / "splits"
    if not (out / "split_manifest.json").is_file():
        raise ContractError(f"{out} has no split manifest. Run first: python -m qc prepare --config <config>")
    saved = read_json(out / "split_manifest.json")
    store, cm, split = _open(cfg)
    now = split.manifest()
    for key, cur in (("hash", now["hash"]), ("client_map_hash", map_hash(cm)), ("land_hash", store.grid.land_hash())):
        if saved.get(key) != cur:
            raise ContractError(
                f"saved split manifest does not match the current config ({key}: saved {saved.get(key)}, now {cur}). "
                "Run `python -m qc prepare` again; frozen benchmarks made under the old split are then invalid."
            )
    stats = TrainStats.load(out / "train_stats.npz")
    if stats.years != split.years["train"]:
        raise ContractError("saved training statistics were fitted on different years than the config's training years")
    return Prepared(cfg, store, store.grid, split, stats, saved, store.grid.to_series(cm).astype(np.int8),
                    store.grid.to_series(split.roles))
