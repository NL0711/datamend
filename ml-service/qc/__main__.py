"""Command line for the QC system.

  python -m qc client-map --config qc/configs/base.yaml      # once: create qc/assets/client_map.json
  python -m qc prepare    --config qc/configs/base.yaml      # data contract, splits, training statistics
  python -m qc benchmark  --config qc/configs/base.yaml      # frozen validation, test and stress fault benchmark
  python -m qc untrained  --config qc/configs/base.yaml      # rules, slow component, neighbour baseline: scores and metrics
  python -m qc federated  --variants fedpers fedavg fedft local   # gate 6: federated simulation, seeds from train.seeds
  python -m qc uk-grid / uk-labels --config qc/configs/uk.yaml   # UK MIDAS real-label study (see that file for the run order)
  python -m qc test-score --config qc/configs/base.yaml      # gate 7: the single test-year pass (needs fixed budgets), stress, report
  python -m qc fusion     --config qc/configs/base.yaml      # gate 5: fit the fusion, validation curves, comparison
  python -m qc set-budgets --final 1 --review 5              # gate 5: fix the two budgets (once, before test scoring)
  python -m qc paper      --config qc/configs/base.yaml      # gate 9: tables, figures, claim check from the saved test outputs
  python -m qc train      --config qc/configs/base.yaml --components spatial temporal plain_gru   # gate 4, seeds from train.seeds

Common options: ``--profile kaggle|single-gpu`` and ``--set key.sub=value`` (repeatable).
"""

from __future__ import annotations

import argparse
from pathlib import Path
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

    target = Path(cfg.clients.map) if cfg.clients.get("map") else paths.CLIENT_MAP_ASSET
    if target.is_file() and not args.force:
        print(f"{target} already exists. It is the fixed client map; use --force only to replace it "
              "(that invalidates every split, benchmark and result made with the old one).")
        return 1
    arch = RainfallArchive(paths.rf25_dir(cfg))
    cm = build_client_map(arch.land_mask, arch.lat, arch.lon, cfg.clients.k, cfg.clients.seed)
    save_client_map(target, cm, cfg.clients.k, cfg.clients.seed)
    rows, cols = np.nonzero(cm)
    for c in range(1, cfg.clients.k + 1):
        sel = cm[rows, cols] == c
        print(f"client {c}: {int(sel.sum()):4d} cells, centre {arch.lat[rows[sel]].mean():5.1f}N {arch.lon[cols[sel]].mean():5.1f}E")
    print(f"wrote {target} (hash {map_hash(cm)})")
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


def print_table(results, budget: float, group: str = "seen") -> None:
    from qc.evaluate import summary_row

    fmt = lambda v, pct=False: "   -  " if v is None else (f"{100 * v:5.1f}%" if pct else f"{v:6.3f}")
    tier = next((r.get("label_tier") for r in results if r.get("label_tier")), "synthetic faults")
    print(f"group: {group} | budget: {budget} false alerts per 1,000 clean cell-days | labels: {tier}")
    print(f"{'component':28s} {'PR-AUC':>7s} {'recall':>7s} {'ev.rec':>7s} {'FA/1000':>8s} {'prot.flag':>9s} {'IoU':>6s}")
    for res in results:
        if group not in res["groups"]:
            continue
        r = summary_row(res, group, budget)
        print(f"{r['component']:28s} {fmt(r['pr_auc']):>7s} {fmt(r['recall'], True):>7s} {fmt(r['event_recall'], True):>7s} "
              f"{fmt(r['false_per_1000']):>8s} {fmt(r['protected_flagged'], True):>9s} {fmt(r['iou']):>6s}")
    for c in sorted({c for res in results for c in res.get("caveats", [])}):
        print("CAVEAT:", c)


def cmd_untrained(cfg, args) -> int:
    from qc.baselines import run_untrained
    from qc.prepare import load_prepared

    results = run_untrained(load_prepared(cfg), tuple(args.splits), args.overwrite)
    for split in args.splits:
        print()
        print(f"== {split}")
        for b in args.show_budgets:
            print_table([r for (n, s), r in results.items() if s == split], b)
    return 0


def cmd_train(cfg, args) -> int:
    from qc.prepare import load_prepared
    from qc.trained import run_component

    p = load_prepared(cfg)
    seeds = args.seeds if args.seeds is not None else [int(s) for s in cfg.train.seeds]
    results = []
    for comp in args.components:
        for seed in seeds:
            out = run_component(p, comp, seed, tuple(args.splits), args.max_train_years, args.time_cap_hours, args.overwrite)
            tr = out["train"]
            print(f"{tr.name}: {tr.status}, {tr.years_done}/{tr.years_total} year-steps, last loss {tr.last_loss}, {tr.seconds:.0f} s")
            if tr.status != "done":
                print("  stopped at the time cap; run the same command again to resume")
                return 3
            results.extend(out["metrics"].values())
    for split in args.splits:
        print()
        print(f"== {split}")
        for b in args.show_budgets:
            print_table([r for r in results if r["split"] == split], b)
    return 0


def cmd_fusion(cfg, args) -> int:
    from qc.evaluate import score_store
    from qc.fusion import VARIANTS, apply_fusion, component_names, fit_fusion, fit_fusion_federated
    from qc.fusion_eval import holdout_years, run_fusion_validation
    from qc.prepare import load_prepared
    from qc.runs import RunDir

    p = load_prepared(cfg)
    store = score_store(p)
    seeds = args.seeds if args.seeds is not None else [int(s) for s in cfg.train.seeds]
    out = RunDir(paths.out_dir(cfg) / str(cfg.name), "fusion")
    out.start(cfg, int(cfg.seed), {"split_manifest_hash": p.manifest["hash"], "seeds": seeds})
    for seed in seeds:
        missing = [n for n in component_names(seed) for tag, y in [("val", p.split.years["fusion_fit"][0])] if not store.has(n, tag, y)]
        if missing:
            print(f"error: seed {seed}: missing validation scores for {missing}. Run `python -m qc untrained` and "
                  "`python -m qc train` first.", file=sys.stderr)
            return 2
        fit = fit_fusion(p, seed, store)
        fit_fusion_federated(p, fit, store)              # the shared logistic fusion again, by federated averaging
        fit.save(out.path / "models")
        apply_fusion(p, fit, ("val",), VARIANTS + ("logistic_fed",), store, args.overwrite)
        res = run_fusion_validation(p, fit, out.path / "validation", store)
        print(f"== seed {seed}: fit on {fit.fit_years[0]}-{fit.fit_years[-1]} ({fit.n_positive} fault rows of {fit.n_rows}); "
              f"evaluated on {holdout_years(p)[0]}-{holdout_years(p)[-1]}; ECE {res['calibration']['expected_calibration_error']:.4f}")
        for b in args.show_budgets:
            print_table(list(res["comparison"].values()), b)
        print(f"curves: {out.path / 'validation' / f'curves_s{seed}.png'}")
    out.mark_done("fusion")
    return 0


def cmd_federated(cfg, args) -> int:
    from qc.federated import run_federated
    from qc.prepare import load_prepared

    p = load_prepared(cfg)
    seeds = args.seeds if args.seeds is not None else [int(s) for s in cfg.train.seeds]
    results = []
    for variant in args.variants:
        for comp in args.components:
            for seed in seeds:
                out = run_federated(p, comp, variant, seed, ("val",), args.max_train_years, args.time_cap_hours, args.overwrite)
                tr = out["train"]
                print(f"{tr.name}: {tr.status}, round {tr.rounds_done}/{tr.rounds_total}, {tr.gradient_steps} gradient steps "
                      f"(centralized {tr.centralized_steps}), {tr.seconds:.0f} s")
                if tr.status != "done":
                    print("  stopped at the time cap; run the same command again to resume")
                    return 3
                results.extend(out["metrics"].values())
    print()
    for b in args.show_budgets:
        print_table(results, b)
    return 0


def cmd_test_score(cfg, args) -> int:
    from qc.prepare import load_prepared
    from qc.testscore import run_root, run_test_scoring

    p = load_prepared(cfg)
    report = run_test_scoring(p, args.seeds, tuple(args.splits), args.resume)
    print(f"wrote {run_root(p) / 'test'}/test_report.md (and metrics, alerts)")
    print("not run:")
    for k, v in report["not_run"].items():
        print(f"  - {k}: {v}")
    return 0


def cmd_uk_grid(cfg, args) -> int:
    from qc.uk.build import build_grid

    s = build_grid(cfg)
    print(json.dumps(s, indent=1))
    print("SUBSET:", s["subset_note"])
    return 0


def cmd_uk_labels(cfg, args) -> int:
    from qc.prepare import load_prepared
    from qc.uk.build import build_uk_benchmark

    m = build_uk_benchmark(load_prepared(cfg), args.overwrite)
    print(json.dumps(m["summary"], indent=1))
    for c in m["caveats"]:
        print("CAVEAT:", c)
    print(f"benchmark hash: {m['hash']}  (set benchmark.expected_hash to this value, then benchmark.allow_unpinned=false)")
    return 0


def cmd_set_budgets(cfg, args) -> int:
    from qc.fusion_eval import set_budgets
    from qc.prepare import load_prepared

    p = load_prepared(cfg)
    curves = paths.out_dir(cfg) / str(cfg.name) / "fusion" / "validation" / f"curves_s{args.seed}.json"
    doc = set_budgets(p, args.final, args.review, curves)
    print(json.dumps(doc, indent=1))
    print("logged in docs/qc-evaluation-protocol.md: commit that file now, before any test-year scoring.")
    return 0


def cmd_paper(cfg, args) -> int:
    from qc import paper
    from qc.prepare import load_prepared
    from qc.testscore import run_root

    p = load_prepared(cfg)
    root = run_root(p)
    run = paper.load_run(root / "test")
    uk = None
    if "uk" in cfg.to_dict():
        from qc.uk.build import CAVEATS
        uk = CAVEATS
    out = Path(args.out) if args.out else root / "paper"
    manifest = paper.build_all(p, out, run, root / "fusion" / "validation" / f"curves_s{args.seed}.json", uk, args.seed)
    print(json.dumps(manifest, indent=1))
    print(f"wrote {out}")
    return 0


COMMANDS = {"uk-grid": cmd_uk_grid, "uk-labels": cmd_uk_labels, "test-score": cmd_test_score, "federated": cmd_federated, "fusion": cmd_fusion, "set-budgets": cmd_set_budgets, "client-map": cmd_client_map, "prepare": cmd_prepare, "benchmark": cmd_benchmark, "untrained": cmd_untrained,
            "train": cmd_train, "paper": cmd_paper}


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
    u = sub.choices["untrained"]
    u.add_argument("--splits", nargs="+", default=["val"], choices=["val", "test", "stress"])
    u.add_argument("--overwrite", action="store_true")
    u.add_argument("--show-budgets", nargs="+", type=float, default=[1.0])
    t = sub.choices["train"]
    t.add_argument("--components", nargs="+", default=["spatial", "temporal", "plain_gru"], choices=["spatial", "temporal", "plain_gru"])
    t.add_argument("--seeds", nargs="+", type=int, default=None, help="default: train.seeds from the config")
    t.add_argument("--splits", nargs="+", default=["val"], choices=["val"],
                   help="validation only: test years are scored once, at gate 7")
    t.add_argument("--max-train-years", type=int, default=None, help="train on the earliest N training years (smoke runs)")
    t.add_argument("--time-cap-hours", type=float, default=None)
    t.add_argument("--overwrite", action="store_true", help="recompute saved scores")
    t.add_argument("--show-budgets", nargs="+", type=float, default=[1.0])
    sub.choices["uk-labels"].add_argument("--overwrite", action="store_true")
    ts = sub.choices["test-score"]
    ts.add_argument("--seeds", nargs="+", type=int, default=None, help="default: train.seeds from the config")
    ts.add_argument("--splits", nargs="+", default=["test", "stress"], choices=["test", "stress"])
    ts.add_argument("--resume", action="store_true", help="continue an unfinished test pass; a finished one cannot be repeated")
    pp = sub.choices["paper"]
    pp.add_argument("--out", default=None, help="default: <run folder>/paper")
    pp.add_argument("--seed", type=int, default=0, help="seed whose alerts and validation curves are drawn")
    g = sub.choices["federated"]
    g.add_argument("--variants", nargs="+", default=["fedpers"], choices=["fedpers", "fedavg", "fedft", "local"],
                   help="priority order: fedpers (main) first, then fedavg, fedft, local; FedProx via --set federated.prox_mu=0.01")
    g.add_argument("--components", nargs="+", default=["spatial", "temporal"], choices=["spatial", "temporal"])
    g.add_argument("--seeds", nargs="+", type=int, default=None, help="default: train.seeds from the config")
    g.add_argument("--max-train-years", type=int, default=None)
    g.add_argument("--time-cap-hours", type=float, default=None)
    g.add_argument("--overwrite", action="store_true")
    g.add_argument("--show-budgets", nargs="+", type=float, default=[1.0])
    f = sub.choices["fusion"]
    f.add_argument("--seeds", nargs="+", type=int, default=None, help="default: train.seeds from the config")
    f.add_argument("--overwrite", action="store_true")
    f.add_argument("--show-budgets", nargs="+", type=float, default=[1.0])
    b = sub.choices["set-budgets"]
    b.add_argument("--final", type=float, required=True, help="false alerts per 1,000 clean cell-days for the final flag")
    b.add_argument("--review", type=float, required=True, help="the same for the review flag (larger)")
    b.add_argument("--seed", type=int, default=0, help="whose validation curves the choice was made from")
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
