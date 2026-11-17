"""CLI.

  python -m training train --preset base --out artifacts/run1 --epochs 10
  python -m training train --preset scalenet --scales 1 5 30 --out artifacts/scalenet
  python -m training train --preset large --set device=cuda --holdout zeroed,repeat
  python -m training sweep --preset base --grid '{"hidden":[128,256],"lr":[1e-3,2e-3]}' --out artifacts/sweep1
  python -m training ensemble --preset ensemble --fusion owa --scales 1 5 30 --seeds 0 1 2 --out artifacts/ens
"""

import argparse
import json
import logging

from training.injection import KINDS
from training.presets import ENSEMBLE_PRESETS, PRESETS, make_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _overrides(a):
    o = {}
    for p in a.set or []:
        k, v = p.split("=", 1)
        try:
            o[k] = json.loads(v)
        except json.JSONDecodeError:
            o[k] = v
    if a.holdout:
        gone = set(a.holdout.split(","))
        o["train_kinds"] = [k for k in KINDS if k not in gone]
    if getattr(a, "scales", None):
        o["scales"] = a.scales
    if getattr(a, "single_scale", False):
        o["single_scale"] = True
    if getattr(a, "elevation", None):
        o["use_elevation"] = True
    if getattr(a, "use_stations", False):
        o["use_stations"] = True
    return o


p = argparse.ArgumentParser(description="RF25 rainfall anomaly model training")
sub = p.add_subparsers(dest="cmd", required=True)
for name in ("train", "sweep", "ensemble"):
    s = sub.add_parser(name)
    s.add_argument("--data-dir", default=None, help="RF25 .nc directory (auto-detected: $DATAMEND_DATA_DIR, ../data, /kaggle/input)")
    s.add_argument("--epochs", type=int, default={"train": 10, "sweep": 5, "ensemble": 10}[name])
    s.add_argument("--max-train-years", type=int, default=None)
    s.add_argument("--holdout", help="comma-separated anomaly kinds excluded from training")
    s.add_argument("--scales", type=int, nargs="+", help="scalenet aggregation scales in days, e.g. 1 5 30")
    s.add_argument("--single-scale", action="store_true", help="scalenet ablation: daily branch only")
    s.add_argument("--elevation", help=".npy elevation array on the rainfall grid (optional)")
    s.add_argument("--use-stations", action="store_true", help="enable the station branch (stub without station data)")
    s.add_argument("--out", default="artifacts/run")
    if name != "ensemble":
        s.add_argument("--preset", choices=sorted(PRESETS), default="base")
        s.add_argument("--set", action="append", help="config override key=value (JSON value)")
sub.choices["sweep"].add_argument("--grid", required=True, help="JSON {field: [values]}")
sub.choices["sweep"].add_argument("--trials", type=int, default=None)
e = sub.choices["ensemble"]
e.add_argument("--preset", choices=sorted(ENSEMBLE_PRESETS), default="ensemble")
e.add_argument("--fusion", choices=["mean_rank", "max", "prob_avg", "owa"], default="mean_rank",
               help="label-free fusion rule")
e.add_argument("--owa-orness", type=float, default=0.7)
e.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2], help="fixed seed list; every run is reported")
e.add_argument("--threshold-method", choices=["fpr", "events"], default="fpr")
e.add_argument("--target-fpr", type=float, default=0.01)
a = p.parse_args()

from training.paths import resolve_data_dir, resolve_out_dir

a.data_dir = str(resolve_data_dir(a.data_dir))
a.out = resolve_out_dir(a.out)
logging.getLogger("training").info("data_dir=%s out=%s", a.data_dir, a.out)

if a.cmd == "ensemble":
    from training.ensemble_run import run_ensemble
    run_ensemble(a.data_dir, a.out, a.preset, a.fusion, a.scales, a.single_scale, a.seeds, a.epochs,
                 a.max_train_years, a.elevation, a.use_stations, a.threshold_method, a.target_fpr, a.owa_orness,
                 a.holdout.split(",") if a.holdout else None)
elif a.cmd == "train":
    from training.pipeline import run
    cfg = make_config(a.preset, **_overrides(a))
    if a.elevation:
        from training.pipeline import prepare, train_prepared
        prep = prepare(a.data_dir, max_train_years=a.max_train_years, coarse_blocks=cfg.coarse_blocks,
                       elevation_path=a.elevation)
        train_prepared(prep, cfg, a.epochs, a.out)
    else:
        run(a.data_dir, a.out, cfg, a.epochs, a.max_train_years)
else:
    from training.experiments import sweep
    sweep(a.data_dir, a.out, json.loads(a.grid), a.preset, a.epochs, a.trials, 0, a.max_train_years)
