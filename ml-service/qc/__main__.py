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
    from qc.clients import build_client_map, load_client_map, map_hash, save_client_map

    target = Path(cfg.clients.map) if cfg.clients.get("map") else paths.CLIENT_MAP_ASSET
    if target.is_file() and not args.force:
        print(f"{target} already exists. It is the fixed client map; use --force only to replace it "
              "(that invalidates every split, benchmark and result made with the old one).")
        return 1
    if args.nest_imd:
        return _nest_client_map(cfg, args, target)
    from training.data import RainfallArchive
    arch = RainfallArchive(paths.rf25_dir(cfg))
    cm = build_client_map(arch.land_mask, arch.lat, arch.lon, cfg.clients.k, cfg.clients.seed)
    save_client_map(target, cm, cfg.clients.k, cfg.clients.seed)
    rows, cols = np.nonzero(cm)
    for c in range(1, cfg.clients.k + 1):
        sel = cm[rows, cols] == c
        print(f"client {c}: {int(sel.sum()):4d} cells, centre {arch.lat[rows[sel]].mean():5.1f}N {arch.lon[cols[sel]].mean():5.1f}E")
    print(f"wrote {target} (hash {map_hash(cm)})")
    return 0


def _nest_client_map(cfg, args, target: Path) -> int:
    """Rebuild the client map so that every client is a union of whole IMD sub-divisions (starting from the current map)."""
    import hashlib
    from qc.clients import load_client_map, map_hash, save_client_map
    from qc.grid import Grid
    from qc.imd_regions import DEFAULT_ANCHORS, nested_client_map

    old = load_client_map(target)
    g = cfg.grid
    grid = Grid.from_land(float(g.lat0) + float(g.step) * np.arange(int(g.n_lat)), float(g.lon0) + float(g.step) * np.arange(int(g.n_lon)), old > 0)
    path = Path(args.nest_imd)
    new, rep = nested_client_map(old, grid, path, int(cfg.clients.k), DEFAULT_ANCHORS)
    held = sorted(set(rep["anchors"].values()))
    if held != sorted(int(c) for c in cfg.clients.heldout):
        print(f"WARNING: the anchor clients are {held} but clients.heldout is {list(cfg.clients.heldout)}; update the config before preparing")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    save_client_map(target, new, int(cfg.clients.k), int(cfg.clients.seed),
                    {"derivation": "k-means blobs (seed 0) re-cut so that every client is a union of whole IMD sub-divisions "
                                   "(qc.clients.nest_in_subdivisions); land cells in no polygon take the sub-division of the nearest cell",
                     "imd_boundary_sha256": sha, "anchors": rep["anchors"]})
    sub_file = target.with_name("client_subdivisions.json")
    sub_file.write_text(json.dumps({"map_hash": map_hash(new), "imd_boundary_url": "https://mausam.imd.gov.in/imd_latest/contents/district_shapefiles/sd_boundary_rainfall.json",
                                    "imd_boundary_sha256": sha, "licence": "not stated by IMD; no polygons are stored here, only which sub-divisions form each client",
                                    "cells_per_client": rep["cells_per_client"], "anchors": rep["anchors"],
                                    "cells_assigned_to_nearest_sub_division": rep["cells_assigned_to_nearest_sub_division"],
                                    "clients": rep["clients"]}, indent=1), encoding="utf-8")
    for c, n in rep["cells_per_client"].items():
        print(f"client {c}: {n:4d} cells: {', '.join(rep['clients'][c])}")
    print(f"anchors (held-out candidates): {rep['anchors']}; wrote {target} (hash {map_hash(new)}) and {sub_file}")
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
    print(f"benchmark hash: {m['hash']}  (recorded in the manifest; pinning is optional: set benchmark.expected_hash to enforce it)")
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


def shard_units(units, spec):
    """The units of work this process takes. ``spec`` is "I/N": unit k goes to shard k % N, so N processes (for example one
    per GPU) split the work with no overlap. None = everything."""
    units = list(units)
    if not spec:
        return units
    try:
        i, n = (int(x) for x in str(spec).split("/"))
    except ValueError:
        raise ConfigError(f"--shard must look like 0/2, not {spec!r}") from None
    if n < 1 or not 0 <= i < n:
        raise ConfigError(f"--shard {spec}: need 0 <= I < N")
    return [u for k, u in enumerate(units) if k % n == i]


def cmd_train(cfg, args) -> int:
    from qc.prepare import load_prepared
    from qc.trained import run_component

    p = load_prepared(cfg)
    seeds = args.seeds if args.seeds is not None else [int(s) for s in cfg.train.seeds]
    results = []
    for comp, seed in shard_units([(c, s) for c in args.components for s in seeds], args.shard):
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
        src = args.on
        missing = [n for n in component_names(seed, source=src, prox_mu=float(cfg.federated.prox_mu))
                   for tag, y in [("val", p.split.years["fusion_fit"][0])] if not store.has(n, tag, y)]
        if missing:
            print(f"error: seed {seed}: missing validation scores for {missing}. Run `python -m qc untrained` and "
                  "`python -m qc train` (or `python -m qc federated` for --on a federated variant) first.", file=sys.stderr)
            return 2
        fit = fit_fusion(p, seed, store, source=src)
        fit_fusion_federated(p, fit, store)              # the shared logistic fusion again, by federated averaging
        fit.save(out.path / "models")
        apply_fusion(p, fit, ("val",), VARIANTS + ("logistic_fed",), store, args.overwrite)
        res = run_fusion_validation(p, fit, out.path / "validation", store)
        print(f"== seed {seed}: fit on {fit.fit_years[0]}-{fit.fit_years[-1]} ({fit.n_positive} fault rows of {fit.n_rows}); "
              f"evaluated on {holdout_years(p)[0]}-{holdout_years(p)[-1]}; ECE {res['calibration']['expected_calibration_error']:.4f}")
        for b in args.show_budgets:
            print_table(list(res["comparison"].values()), b)
        print(f"curves: {out.path / 'validation' / f'curves{fit.tag}_s{seed}.png'}")
    out.mark_done("fusion")
    return 0


def cmd_ablate(cfg, args) -> int:
    from qc.ablate import format_rows, run_ablation
    from qc.prepare import load_prepared
    from qc.runs import RunDir, write_json

    p = load_prepared(cfg)
    rows = run_ablation(p, args.seed, args.budget)
    print(f"Fusion ablation, seed {args.seed}, validation years (held out from the fusion fit), budget {args.budget} false alerts per 1,000 "
          "clean cell-days, synthetic faults:")
    print(format_rows(rows))
    out = RunDir(paths.out_dir(cfg) / str(cfg.name), "ablation")
    out.start(cfg, int(cfg.seed), {"split_manifest_hash": p.manifest["hash"], "seed": args.seed})
    write_json(out.file("ablation_s%d.json" % args.seed), {"budget": args.budget, "seed": args.seed, "rows": rows})
    out.mark_done("ablation")
    return 0


def cmd_calibrate(cfg, args) -> int:
    from qc.calibration import check_budget, format_rows
    from qc.prepare import load_prepared
    from qc.runs import RunDir, write_json

    p = load_prepared(cfg)
    names = args.components or [f"fusion_boosted_s{args.seed}", f"fusion_logistic_s{args.seed}"]
    out = RunDir(paths.out_dir(cfg) / str(cfg.name), "calibration")
    out.start(cfg, int(cfg.seed), {"split_manifest_hash": p.manifest["hash"], "components": names})
    for n in names:
        rows = check_budget(p, n, args.budget)
        print(f"\n{n}: realised false alerts per 1,000 clean cell-days at budget {args.budget}, thresholds set on one threshold year and "
              "checked on the other (validation data only; no formal guarantee, cell-days are dependent):")
        print(format_rows(rows))
        write_json(out.file(f"budget_check_{n}.json"), rows)
    out.mark_done("calibration")
    return 0


def cmd_federated(cfg, args) -> int:
    from qc.federated import run_federated
    from qc.prepare import load_prepared

    p = load_prepared(cfg)
    seeds = args.seeds if args.seeds is not None else [int(s) for s in cfg.train.seeds]
    results = []
    units = [(v, c, s) for v in args.variants for c in args.components for s in seeds]
    for variant, comp, seed in shard_units(units, args.shard):
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
    print(f"benchmark hash: {m['hash']}  (recorded in the manifest; pinning is optional: set benchmark.expected_hash, then benchmark.allow_unpinned=false, to enforce it)")
    return 0


def cmd_set_budgets(cfg, args) -> int:
    from qc.fusion_eval import set_budgets
    from qc.prepare import load_prepared

    p = load_prepared(cfg)
    curves = paths.out_dir(cfg) / str(cfg.name) / "fusion" / "validation" / f"curves_s{args.seed}.json"
    choice_file = paths.out_dir(cfg) / str(cfg.name) / "scales" / "architecture_choice.json"
    component = None
    if choice_file.is_file():
        component = json.loads(choice_file.read_text(encoding="utf-8"))["chosen"]["component"]
        print(f"the budgets apply to the chosen architecture's fused score: {component}")
    else:
        print("WARNING: no architecture_choice.json: the budgets are logged for the daily fused score only. Run `qc cross-scale` and "
              "`qc choose-architecture` first if a cross-scale fusion may be used.")
    doc = set_budgets(p, args.final, args.review, curves, component=component)
    print(json.dumps(doc, indent=1))
    print("logged in docs/qc-evaluation-protocol.md: commit that file now, before any test-year scoring.")
    return 0


def cmd_period_benchmark(cfg, args) -> int:
    from qc.benchmark import bench_dir
    from qc.period_benchmark import build_period_benchmark, period_dir
    from qc.prepare import load_prepared

    splits = list(args.splits)
    mf = period_dir(bench_dir(cfg)) / "manifest.json"
    if mf.is_file() and not args.overwrite:                       # splits already built are kept, so a resumed run does not fail
        have = json.loads(mf.read_text(encoding="utf-8")).get("split_hashes", {})
        kept = [s for s in splits if s in have]
        splits = [s for s in splits if s not in have]
        if kept:
            print(f"period benchmark already built for {kept}: kept as it is (use --overwrite to rebuild everything)")
        if not splits:
            print(f"period benchmark hash: {json.loads(mf.read_text(encoding='utf-8'))['hash']}")
            return 0
    m = build_period_benchmark(load_prepared(cfg), scales=args.scales, splits=splits, overwrite=args.overwrite)
    for k, v in m["summary"].items():
        print(f"{k}: years {v['years'][0]}-{v['years'][1]}, {v['fault_periods']} faulty of {v['valid_periods']} periods ({100 * v['fault_share']:.2f}%)")
    print(f"period benchmark hash: {m['hash']} (daily benchmark {m['daily_benchmark_hash']}); SYNTHETIC faults")
    return 0


def cmd_scale_select(cfg, args) -> int:
    from qc import paths
    from qc.prepare import load_prepared
    from qc.scale_select import run_for_prepared, selection_markdown

    p = load_prepared(cfg)
    out = paths.out_dir(cfg) / str(cfg.name) / "scales"
    for scale in args.scales:
        res = run_for_prepared(p, scale, args.candidates, out, seeds=args.seeds)
        print(selection_markdown(res))
    print(f"wrote {out}. Paste the tables into docs/qc-evaluation-protocol.md and commit them before any test year is scored.")
    return 0


def cmd_cross_scale(cfg, args) -> int:
    from qc import paths
    from qc.crossscale_run import compare_cross_scale, compute_scale_scores, comparison_markdown, write_comparison
    from qc.fusion import fused_name
    from qc.prepare import load_prepared

    p = load_prepared(cfg)
    out = paths.out_dir(cfg) / str(cfg.name) / "scales"
    scales = {}
    for scale in args.scales:
        chosen = None
        sel = out / f"selection_{scale}.json"
        if sel.is_file():
            chosen = json.loads(sel.read_text(encoding="utf-8")).get("selection", {}).get("chosen")
        scorer = getattr(args, scale, None) or chosen or "loo_median"
        print(f"{scale}: scorer {scorer} ({'given' if getattr(args, scale, None) else 'from the selection step' if chosen else 'DEFAULT: no selection result found, run scale-select first for an evidence-based choice'})")
        compute_scale_scores(p, scale, scorer, seed=args.seed, overwrite=args.overwrite)
        scales[scale] = scorer
    daily = args.daily or fused_name("logistic", args.seed)
    res = compare_cross_scale(p, daily, scales, [float(b) for b in cfg.evaluation.budgets], args.mode, args.factor, overwrite=args.overwrite)
    md = write_comparison(out, res)
    print(comparison_markdown(res))
    print(f"wrote {md}. Paste the table into docs/qc-evaluation-protocol.md before any test year is scored. SYNTHETIC faults, held-out threshold years only.")
    return 0


def cmd_regions_report(cfg, args) -> int:
    """Regional output by IMD sub-division and homogeneous region, from stored scores only (nothing is scored here)."""
    from qc import paths
    from qc.fusion import fused_name
    from qc.fusion_eval import budgets_path, load_budgets
    from qc.imd_regions import build_imd_maps
    from qc.prepare import load_prepared
    from qc.regions import region_map_from_clients
    from qc.regions_report import build_regional_output

    p = load_prepared(cfg)
    root = paths.out_dir(cfg) / str(cfg.name)
    choice_file = root / "scales" / "architecture_choice.json"
    choice = json.loads(choice_file.read_text(encoding="utf-8")) if choice_file.is_file() else None
    component = args.component or (choice["chosen"]["component"] if choice else fused_name("logistic", args.seed))
    if budgets_path(p).is_file():
        budgets = load_budgets(p)
    elif args.final is not None and args.review is not None:
        budgets = {"final_per_1000": args.final, "review_per_1000": args.review}
        print("the budgets are not fixed yet: --final and --review are used for this DEVELOPMENT report only")
    else:
        print("the budgets are not fixed: pass --final and --review for a development report, or run `set-budgets`")
        return 1
    if args.client_regions:
        from qc.regions import region_map_from_clients as _clients
        maps, prov = {"client region (stand-in, not IMD)": _clients(p.cell_client)}, None
    else:
        imd = Path(args.imd_file) if args.imd_file else paths.work_dir(cfg) / "regions" / "sd_boundary_rainfall.json"
        if not imd.is_file():
            print(f"IMD boundary file not found at {imd}: run `python scripts/fetch_imd_regions.py` (or pass --imd-file, or --client-regions for the stand-in)")
            return 1
        sub, reg = build_imd_maps(p.grid, imd)
        maps = {"IMD sub-division": sub, "IMD homogeneous region": reg}
        pf = imd.with_name("sd_boundary_rainfall.provenance.json")
        prov = json.loads(pf.read_text(encoding="utf-8")) if pf.is_file() else {"file": str(imd)}
    for split in args.splits:
        out = build_regional_output(p, component, split, maps, root / "regions", budgets, choice=choice, map_provenance=prov)
        print(f"{split}: wrote {out['json']} and {out['csv']} (component {component}; SYNTHETIC benchmark, not real data quality)")
    return 0


def cmd_cross_scale_test(cfg, args) -> int:
    """The cross-scale test pass: single use, after the daily test pass, with the architecture chosen on validation."""
    from qc.crossscale_test import report_dir, run_cross_scale_test
    from qc.prepare import load_prepared

    p = load_prepared(cfg)
    report = run_cross_scale_test(p, tuple(args.splits), resume=args.resume, seed=args.seed)
    ch = report["chosen"]
    print(f"cross-scale test pass done: chosen architecture daily + {', '.join(ch['scales']) or 'nothing'} ({ch['fusion']}), component {ch['component']}")
    print(f"wrote {report_dir(p) / 'cross_scale_test_report.md'}. SYNTHETIC faults. The test years cannot be scored again.")
    return 0


def cmd_choose_architecture(cfg, args) -> int:
    """Apply the frozen architecture rule (config `architecture:`, protocol log) to the cross-scale validation table. Written once."""
    import datetime
    from qc import paths
    from qc.crossscale_run import decide_architecture
    from qc.runs import git_commit, write_json

    out = paths.out_dir(cfg) / str(cfg.name) / "scales"
    src, dst = out / "cross_scale_validation.json", out / "architecture_choice.json"
    if dst.is_file():
        print(f"{dst} already exists: the architecture is chosen once and frozen before any test year is scored. "
              "Delete it only if you are starting the whole evaluation over, and say so in the protocol.")
        return 1
    if not src.is_file():
        print(f"no validation table at {src}; run `python -m qc cross-scale` first")
        return 1
    result = json.loads(src.read_text(encoding="utf-8"))
    rule = cfg.architecture
    choice = decide_architecture(result, float(rule.final_budget), float(rule.min_recall_gain))
    chosen_info = result.get("fusions", {}).get(choice["chosen"]["component"])          # references and weights, frozen with the choice
    doc = {**choice, "daily": result.get("daily"), "fusion_info": chosen_info,
           "label": "SYNTHETIC faults, held-out threshold years only", "commit": git_commit(),
           "chosen_on": datetime.date.today().isoformat(), "source": str(src),
           "scored_on_test": ["the chosen architecture", "daily only", "the untrained baselines (rules, slow, neighbour_baseline)"]}
    write_json(dst, doc)
    print(json.dumps(doc, indent=1))
    print(f"wrote {dst}. Log it in docs/qc-evaluation-protocol.md and commit BEFORE any test year is scored.")
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


COMMANDS = {"uk-grid": cmd_uk_grid, "uk-labels": cmd_uk_labels, "test-score": cmd_test_score, "federated": cmd_federated, "fusion": cmd_fusion, "ablate": cmd_ablate, "calibrate": cmd_calibrate, "set-budgets": cmd_set_budgets, "client-map": cmd_client_map, "prepare": cmd_prepare, "benchmark": cmd_benchmark, "untrained": cmd_untrained,
            "train": cmd_train, "paper": cmd_paper,
            "period-benchmark": cmd_period_benchmark, "scale-select": cmd_scale_select, "cross-scale": cmd_cross_scale, "choose-architecture": cmd_choose_architecture,
            "cross-scale-test": cmd_cross_scale_test, "regions-report": cmd_regions_report}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m qc", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in COMMANDS:
        s = sub.add_parser(name)
        s.add_argument("--config", default=str(paths.ASSETS.parent / "configs" / "base.yaml"))
        s.add_argument("--profile", choices=available_profiles(), default=None)
        s.add_argument("--set", action="append", metavar="KEY=VALUE", help="config override, e.g. clients.buffer_cells=6")
    sub.choices["client-map"].add_argument("--force", action="store_true")
    sub.choices["client-map"].add_argument("--nest-imd", default=None, metavar="FILE", help="re-cut the existing map so each client is a union of whole IMD sub-divisions (needs the file from scripts/fetch_imd_regions.py)")
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
    t.add_argument("--shard", default=None, metavar="I/N", help="take every Nth (component, seed) unit starting at I, so N processes "
                   "(one per GPU, each with --set compute.devices=[cuda:I]) split the work: 0/2 and 1/2")
    t.add_argument("--overwrite", action="store_true", help="recompute saved scores")
    t.add_argument("--show-budgets", nargs="+", type=float, default=[1.0])
    sub.choices["uk-labels"].add_argument("--overwrite", action="store_true")
    ts = sub.choices["test-score"]
    ts.add_argument("--seeds", nargs="+", type=int, default=None, help="default: train.seeds from the config")
    ts.add_argument("--splits", nargs="+", default=["test", "stress"], choices=["test", "stress"])
    ts.add_argument("--resume", action="store_true", help="continue an unfinished test pass; a finished one cannot be repeated")
    pb = sub.choices["period-benchmark"]
    pb.add_argument("--scales", nargs="+", default=["monthly", "seasonal", "yearly"], choices=["monthly", "seasonal", "yearly"])
    pb.add_argument("--splits", nargs="+", default=["val", "test", "stress"], choices=["val", "test", "stress"])
    pb.add_argument("--overwrite", action="store_true")
    ss = sub.choices["scale-select"]
    ss.add_argument("--scales", nargs="+", default=["monthly", "yearly"], choices=["monthly", "seasonal", "yearly"])
    ss.add_argument("--candidates", nargs="+", default=["gamma_zero", "loo_median", "loo_kriging", "gbm_neighbour", "mlp_neighbour"],
                    choices=["gamma_zero", "loo_median", "loo_kriging", "gbm_neighbour", "mlp_neighbour"])
    ss.add_argument("--seeds", nargs="+", type=int, default=None, help="default: train.seeds from the config")
    cs = sub.choices["cross-scale"]
    cs.add_argument("--scales", nargs="+", default=["monthly", "yearly"], choices=["monthly", "seasonal", "yearly"])
    cs.add_argument("--monthly", default=None, help="scorer for the monthly scale (default: the selection result, else loo_median)")
    cs.add_argument("--seasonal", default=None)
    cs.add_argument("--yearly", default=None)
    cs.add_argument("--daily", default=None, help="stored daily component to fuse with (default: fusion_logistic_s<seed>)")
    cs.add_argument("--mode", default="max", choices=["max", "noisy_or"])
    cs.add_argument("--factor", type=float, default=0.5, help="coherent-extreme discount on protected cells (1 = none)")
    cs.add_argument("--seed", type=int, default=0)
    cs.add_argument("--overwrite", action="store_true")
    rr = sub.choices["regions-report"]
    rr.add_argument("--splits", nargs="+", default=["val"], choices=["val", "test", "stress"],
                    help="test and stress years are written only after the daily test pass is finished")
    rr.add_argument("--component", default=None, help="stored fused score (default: the chosen architecture, else fusion_logistic_s<seed>)")
    rr.add_argument("--seed", type=int, default=0)
    rr.add_argument("--final", type=float, default=None, help="development report before the budgets are fixed: final-flag budget")
    rr.add_argument("--review", type=float, default=None, help="development report before the budgets are fixed: review-flag budget")
    rr.add_argument("--imd-file", default=None, help="IMD boundary file (default: <data dir>/regions/sd_boundary_rainfall.json)")
    rr.add_argument("--client-regions", action="store_true", help="use the 8 client regions (a stand-in, not IMD units)")
    ct = sub.choices["cross-scale-test"]
    ct.add_argument("--splits", nargs="+", default=["test", "stress"], choices=["test", "stress"])
    ct.add_argument("--resume", action="store_true", help="continue an unfinished pass; a finished one cannot be repeated")
    ct.add_argument("--seed", type=int, default=0, help="seed of the monthly/yearly scorers; use the one given to `cross-scale`")
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
    g.add_argument("--shard", default=None, metavar="I/N", help="as for train: every Nth (variant, component, seed) unit starting at I")
    g.add_argument("--overwrite", action="store_true")
    g.add_argument("--show-budgets", nargs="+", type=float, default=[1.0])
    f = sub.choices["fusion"]
    f.add_argument("--seeds", nargs="+", type=int, default=None, help="default: train.seeds from the config")
    f.add_argument("--on", default="central", choices=["central", "fedpers", "fedavg", "fedft"],
                   help="fit on the centralized spatial and temporal scores (default, the main fusion) or on a federated variant's")
    f.add_argument("--overwrite", action="store_true")
    f.add_argument("--show-budgets", nargs="+", type=float, default=[1.0])
    ab = sub.choices["ablate"]
    ab.add_argument("--seed", type=int, default=0)
    ab.add_argument("--budget", type=float, default=1.0, help="false alerts per 1,000 clean cell-days the components are compared at")
    cb = sub.choices["calibrate"]
    cb.add_argument("--seed", type=int, default=0)
    cb.add_argument("--budget", type=float, default=1.0)
    cb.add_argument("--components", nargs="+", default=None, help="score names (default: the seed's boosted and logistic fusion)")
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
