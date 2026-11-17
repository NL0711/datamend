"""Command line for the QC system.

  python -m qc client-map --config qc/configs/base.yaml      # once: create qc/assets/client_map.json
  python -m qc prepare    --config qc/configs/base.yaml      # data contract, splits, training statistics
  python -m qc benchmark  --config qc/configs/base.yaml      # frozen validation, test and stress fault benchmark

Common options: ``--profile kaggle|single-gpu`` and ``--set key.sub=value`` (repeatable).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import numpy as np

from qc import paths
from qc.config import ConfigError, available_profiles, load_config
from qc.grid import ContractError
from qc.splits import LeakageError

log = logging.getLogger("qc")


def cmd_client_map(cfg, args) -> int:
    from qc.clients import build_client_map, map_hash, save_client_map
    from training.data import RainfallArchive

    if paths.CLIENT_MAP_ASSET.is_file() and not args.force:
        print(f"{paths.CLIENT_MAP_ASSET} already exists. It is the fixed client map; use --force only to replace it "
              "(that invalidates every split, benchmark and result made with the old one).")
        return 1
    arch = RainfallArchive(paths.rf25_dir(cfg))
    cm = build_client_map(arch.land_mask, arch.lat, arch.lon, cfg.clients.k, cfg.clients.seed)
    save_client_map(paths.CLIENT_MAP_ASSET, cm, cfg.clients.k, cfg.clients.seed)
    rows, cols = np.nonzero(cm)
    for c in range(1, cfg.clients.k + 1):
        sel = cm[rows, cols] == c
        print(f"client {c}: {int(sel.sum()):4d} cells, centre {arch.lat[rows[sel]].mean():5.1f}N {arch.lon[cols[sel]].mean():5.1f}E")
    print(f"wrote {paths.CLIENT_MAP_ASSET} (hash {map_hash(cm)})")
    return 0


def cmd_prepare(cfg, args) -> int:
    from qc.prepare import prepare

    p = prepare(cfg, check_data=not args.skip_contract)
    m = p.manifest
    print(json.dumps({k: m[k] for k in ("years", "train_clients", "heldout_clients", "buffer_cells", "cells_per_client",
                                        "client_scale", "client_map_hash", "hash") if k in m}, indent=1))
    if "data" in m:
        print("data:", json.dumps(m["data"]))
    return 0


def cmd_benchmark(cfg, args) -> int:
    from qc.benchmark import build_benchmark
    from qc.prepare import load_prepared

    m = build_benchmark(load_prepared(cfg), overwrite=args.overwrite)
    for split, s in m["summary"].items():
        print()
        print(f"== {split} {s['years'][0]}-{s['years'][1]}: {s['events']} faults, {s['cell_days']} fault cell-days "
              f"({100 * s['fault_share_of_cell_days']:.2f}% of cell-days), {s['events_unseen_setting']} with test-only settings")
        print(f"   protected extremes: {s['protected_events']} events, {s['protected_cell_days']} cell-days | "
              f"ambiguous: {s['ambiguous_cell_days']} cell-days | heavy groups of 2-3 cells: {s['small_heavy_groups']}")
        for group in ("by_kind", "by_radius", "by_strength"):
            print("   " + group + ": " + ", ".join(f"{k} {v['events']} ev / {v['cell_days']} cd" for k, v in s[group].items()))
    print()
    print(f"benchmark hash: {m['hash']}  (set benchmark.expected_hash to this value)")
    return 0


COMMANDS = {"client-map": cmd_client_map, "prepare": cmd_prepare, "benchmark": cmd_benchmark}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m qc", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in COMMANDS:
        s = sub.add_parser(name)
        s.add_argument("--config", default=str(paths.ASSETS.parent / "configs" / "base.yaml"))
        s.add_argument("--profile", choices=available_profiles(), default=None)
        s.add_argument("--set", action="append", metavar="KEY=VALUE", help="config override, e.g. clients.buffer_cells=6")
    sub.choices["client-map"].add_argument("--force", action="store_true")
    sub.choices["prepare"].add_argument("--skip-contract", action="store_true",
                                        help="skip the per-file data-contract check (use only for quick local tests)")
    sub.choices["benchmark"].add_argument("--overwrite", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        cfg = load_config(args.config, args.set, args.profile)
        return COMMANDS[args.cmd](cfg, args)
    except (ConfigError, ContractError, LeakageError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
