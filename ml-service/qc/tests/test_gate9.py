"""Gate 9: paper tables, figures and the claim check, on the outputs of a tiny real run (small synthetic world)
and on hand-written metric files for the verdict logic."""

import copy
import shutil

import numpy as np
import pytest

from training import artifact
from training.calibration import Calibration
from training.presets import make_config
from training.sampler import Batch
from training.trainer import LocalTrainer
from training.transform import RainfallTransform

from qc.baselines import run_untrained
from qc.benchmark import build_benchmark
from qc.config import load_config
from qc.federated import run_federated
from qc.fusion import VARIANTS, apply_fusion, fit_fusion, fit_fusion_federated
from qc.fusion_eval import PROTOCOL, run_fusion_validation, set_budgets
from qc.paper import (BARS, Run, build_all, build_tables, check_claims, claims_markdown, federated, fig_kerala, load_run,
                      main_results, protected_extremes, ablation)
from qc.prepare import load_prepared
from qc.testscore import run_root, run_test_scoring
from qc.trained import run_component
from qc.tests.test_gate4 import TINY

BASE = TINY + ["name=g9", "benchmark.name=g9bench", "fusion.max_rows=100000", "fusion.boosted_iter=10", "federated.finetune_steps=2"]


def _old_model(folder, arch, train_years):
    """A tiny old-format artifact (random weights: this tests the adapter, not the model)."""
    t = LocalTrainer(RainfallTransform(3.0), make_config("smoke", arch=arch, device="cpu"))
    w = t.config.window
    b = Batch.from_windows(np.random.default_rng(0).gamma(0.5, 5.0, (16, w)).astype(np.float32))
    st = t.score(b)
    cal = Calibration({k: (float(np.median(v)), max(float(np.std(v)), 1e-3)) for k, v in st.items()}, 1.0)
    artifact.save(artifact.Artifact(t, cal, {"train_years": train_years, "val_years": [train_years[-1] + 1]}), folder)
    return str(folder)


@pytest.fixture(scope="module")
def p9(world, prepared, tmp_path_factory):
    old = tmp_path_factory.mktemp("old_models")
    over = [f"offline.artifacts.rainnet={_old_model(old / 'rainnet', 'rainnet', [1900, 1901])}",
            f"offline.artifacts.lstm_ae={_old_model(old / 'lstm', 'lstm_ae', [1999, 2000])}"]      # 2000 is a test year here
    cfg = load_config(world / "test.yaml", BASE + over)
    p = load_prepared(cfg)
    build_benchmark(p, splits=("val", "test", "stress"), overwrite=True)
    run_untrained(p, ("val",))
    for c in ("spatial", "temporal", "plain_gru"):
        assert run_component(p, c, 0, ("val",), max_years=2)["train"].status == "done"
    for v in ("fedpers", "fedavg"):
        assert run_federated(p, "temporal", v, 0, ("val",), max_years=2)["train"].status == "done"
    assert run_federated(p, "spatial", "fedavg", 0, ("val",), max_years=2)["train"].status == "done"
    fit = fit_fusion(p, 0)
    fit_fusion_federated(p, fit, rounds=5)
    fit.save(run_root(p) / "fusion" / "models")
    apply_fusion(p, fit, ("val",), VARIANTS + ("logistic_fed",))
    run_fusion_validation(p, fit, run_root(p) / "fusion" / "validation")
    ffit = fit_fusion(p, 0, source="fedavg")                    # fusion fitted on the federated components
    ffit.save(run_root(p) / "fusion" / "models")
    apply_fusion(p, ffit, ("val",), VARIANTS)
    run_fusion_validation(p, ffit, run_root(p) / "fusion" / "validation")
    proto = run_root(p).parent / "protocol_copy.md"
    shutil.copy(PROTOCOL, proto)
    set_budgets(p, 1, 5, run_root(p) / "fusion" / "validation" / "curves_s0.json", proto, today="2026-11-21")
    run_test_scoring(p, [0], ("test", "stress"))
    return p


@pytest.fixture(scope="module")
def run9(p9):
    return load_run(run_root(p9) / "test")


# ---------------------------------------------------------------------------------------------- from the tiny run

def test_tables_match_the_test_report(p9, run9):
    tables = {t.key: t for t in build_tables(run9)}
    assert {"main_results", "ablation", "federated", "protected_extremes", "protected_extremes_breakdown"} <= set(tables)
    assert not any(t.columns == ["status"] for t in tables.values())
    # a cell in the ablation table is the report's number, formatted: no recomputation, no invention
    report = run9.report["splits"]["test"]["by_model_family"]["fusion_logistic"]["seen"][run9.final]
    row = next(r for r in tables["ablation"].rows if r[0] == "fusion_logistic")
    assert row[2] == f"{100 * report['recall']['mean']:.1f}%"
    assert row[4] == f"{report['false_per_1000']['mean']:.3f}"
    # main results: every fault kind present in the metrics has a row, 'all faults' first
    kinds = {k for g in run9.metrics["test"]["fusion_logistic_s0"]["groups"].values()
             for k in g["by_budget"][run9.final].get("by_kind", {})}
    assert tables["main_results"].rows[0][0] == "all faults"
    assert kinds <= {r[0] for r in tables["main_results"].rows}
    # federated: central and the two trained variants appear; ones that were not run are named as such
    labels = [r[0] for r in tables["federated"].rows]
    assert {"central temporal", "fedpers temporal", "fedavg temporal"} <= set(labels)
    assert any("NOT RUN" in n and "fedft" in n for n in tables["federated"].notes)
    assert any("privacy" in n for n in tables["federated"].notes)
    assert any("UNVERIFIED" in n for n in tables["protected_extremes"].notes)


def test_claims_cite_numbers_and_say_what_they_cannot_check(run9):
    claims = {c.key: c for c in check_claims(run9)}
    assert set(claims) == {"combined", "protected", "federated"}
    assert all(c.status.split(" (")[0] in {"SUPPORTED", "MIXED", "NOT SUPPORTED", "CANNOT CHECK"} for c in claims.values())
    assert claims["combined"].status != "CANNOT CHECK" and any("recall" in e for e in claims["combined"].evidence)
    assert claims["federated"].status != "CANNOT CHECK"
    md = claims_markdown(list(claims.values()))
    assert "protected_flagged_max" in md and "synthetic" in md


def test_build_all_writes_tables_figures_claims_and_a_manifest(p9, run9, tmp_path):
    curves = run_root(p9) / "fusion" / "validation" / "curves_s0.json"
    man = build_all(p9, tmp_path, run9, curves)
    for f in ("tables/all_tables.md", "tables/ablation.csv", "claims.md", "paper_manifest.json",
              "figures/fig_client_map.png", "figures/fig_example_faults.png", "figures/fig_recall_budget.png",
              "figures/fig_reliability.png"):
        assert (tmp_path / f).is_file() and (tmp_path / f).stat().st_size > 0, f
    assert man["claims"].keys() == {"combined", "protected", "federated"}
    # 2018 is not a test year in this world: the case study says so instead of drawing something
    assert man["figures"]["kerala_case"].startswith("NOT RUN")
    assert not (tmp_path / "figures" / "fig_kerala_case.png").exists()


def test_case_study_figure_draws_from_alerts_and_rainfall_only(p9, run9, tmp_path):
    path, why = fig_kerala(p9, run9, tmp_path, year=2001, month=8, bbox=(0, 90, 0, 180))
    assert why is None and path.is_file() and path.stat().st_size > 0
    path, why = fig_kerala(p9, run9, tmp_path, year=2001, month=8, bbox=(40, 41, 0, 1))
    assert path is None and "no grid cell" in why


def test_without_a_test_pass_everything_is_not_run(p9, tmp_path):
    assert load_run(tmp_path) is None
    assert all(t.columns == ["status"] and "NOT RUN" in t.rows[0][0] for t in build_tables(None))
    assert all(c.status == "CANNOT CHECK" for c in check_claims(None))


# ---------------------------------------------------------------------------------------------- verdict logic

def _model(recall, pr=0.5, false=1.0, protected=0.0, unseen_recall=None, kinds=None, local_unseen=True):
    def grp(r):
        b = {"faults": {"events": 10, "recall": r, "event_recall": r, "footprint_iou": 0.5},
             "false_alerts": {"per_1000_clean": false},
             "protected_extremes": {"flagged_share_of_cell_days": protected, "cell_days_flagged_by": {}},
             "ambiguous_extremes": {"flagged_share": 0.0},
             "by_kind": {k: {"events": 3, "recall": v, "event_recall": v} for k, v in (kinds or {}).items()}}
        return {"pr_auc": pr, "by_budget": {"1.0": b, "5.0": b}}
    groups = {"seen": grp(recall)}
    if local_unseen:
        groups["unseen"] = grp(recall if unseen_recall is None else unseen_recall)
    return {"groups": groups}


def _run(models):
    metrics = {}
    for fam, specs in models.items():
        for seed, spec in enumerate(specs if isinstance(specs, list) else [specs]):
            metrics.setdefault("test", {})[f"{fam}_s{seed}"] = spec
    report = {"label_tier": "synthetic faults", "budgets": {"final_per_1000": 1, "review_per_1000": 5}, "splits": {"test": {}}}
    return Run(report, metrics, None)


def _all_single(recall=0.4, pr=0.3):
    return {f: _model(recall, pr) for f in ("rules", "slow", "neighbour_baseline", "spatial", "temporal", "plain_gru")}


def test_combined_claim_verdicts():
    better = _run({**_all_single(), "fusion_logistic": _model(0.7, 0.6)})
    assert check_claims(better)[0].status.startswith("SUPPORTED")
    worse = _run({**_all_single(), "fusion_logistic": _model(0.2, 0.1)})
    assert check_claims(worse)[0].status == "NOT SUPPORTED"
    mixed = _run({**_all_single(), "fusion_logistic": _model(0.7, 0.1)})
    assert check_claims(mixed)[0].status == "MIXED"
    # with several seeds, overlapping ranges are not enough
    seeds = _run({**{k: [v, _model(0.7, 0.55)] for k, v in _all_single().items()}, "fusion_logistic": [_model(0.7, 0.6), _model(0.45, 0.6)]})
    assert check_claims(seeds)[0].status == "MIXED"
    missing = _run({"fusion_logistic": _model(0.7)})
    assert check_claims(missing)[0].status == "CANNOT CHECK"


def test_protected_claim_uses_the_stated_bar_and_the_worst_seed():
    bar = BARS["protected_flagged_max"]
    ok = _run({"fusion_logistic": _model(0.5, protected=bar / 2)})
    assert check_claims(ok)[1].status == "SUPPORTED"
    bad = _run({"fusion_logistic": _model(0.5, protected=bar * 2)})
    assert check_claims(bad)[1].status == "NOT SUPPORTED"
    one_bad_seed = _run({"fusion_logistic": [_model(0.5, protected=0.0), _model(0.5, protected=bar * 3)]})
    assert check_claims(one_bad_seed)[1].status == "NOT SUPPORTED"      # mean is under the bar, the worst seed is not
    assert check_claims(_run({}))[1].status == "CANNOT CHECK"


def test_federated_claim_and_unavailable_local():
    gap = BARS["federated_recall_gap"]
    good = _run({"temporal": _model(0.6), "fedpers_temporal": _model(0.6 - gap / 2),
                 "spatial": _model(0.6), "fedpers_spatial": _model(0.6)})
    assert check_claims(good)[2].status == "SUPPORTED"
    unseen_bad = _run({"temporal": _model(0.6), "fedpers_temporal": _model(0.6, unseen_recall=0.1)})
    unseen_bad.metrics["test"]["temporal_s0"]["groups"]["unseen"] = _model(0.6)["groups"]["unseen"]
    assert check_claims(unseen_bad)[2].status == "MIXED"
    assert check_claims(_run({"temporal": _model(0.6)}))[2].status == "CANNOT CHECK"
    # local-only has no model for unseen clients: the table says NOT AVAILABLE, never a number
    r = _run({"temporal": _model(0.6), "local_temporal": _model(0.5, local_unseen=False)})
    row = next(x for x in federated(r).rows if x[0].startswith("local"))
    assert row[4:7] == ["NOT AVAILABLE"] * 3


def test_per_kind_rows_and_missing_models_are_named():
    r = _run({"fusion_logistic": _model(0.5, kinds={"spike": 0.9, "drift": 0.1}), "rules": _model(0.3)})
    t = main_results(r)
    assert [x[0] for x in t.rows[:3]] == ["all faults", "drift", "spike"]
    assert t.rows[2][2] == "90.0%"
    ab = ablation(r)
    assert any("Not in this table" in n and "spatial" in n for n in ab.notes)
    assert protected_extremes(_run({}))[0].rows[0][0].startswith("NOT RUN")


# ---------------------------------------------------------------------------------------------- the two formerly missing pieces

def test_fusion_on_federated_components_is_fitted_stored_and_scored(p9, run9):
    root = run_root(p9)
    # it has its own files and score names: the main fusion is untouched
    assert (root / "fusion" / "models" / "logistic_fedavg_s0.json").is_file() and (root / "fusion" / "models" / "logistic_s0.json").is_file()
    assert (root / "fusion" / "validation" / "curves_fedavg_s0.json").is_file()
    from qc.fusion import FusionFit
    f = FusionFit.load(root / "fusion" / "models", 0, "fedavg")
    assert f.source == "fedavg" and f.names == ["rules", "slow", "fedavg_spatial_s0", "fedavg_temporal_s0"]
    assert FusionFit.load(root / "fusion" / "models", 0).names == ["rules", "slow", "spatial_s0", "temporal_s0"]
    # scored on the test years in the single pass, with metrics for both client groups
    fam = run9.report["splits"]["test"]["by_model_family"]
    assert {"fusion_logistic@fedavg", "fusion_mean@fedavg"} <= set(fam) and set(fam["fusion_logistic@fedavg"]) == {"seen", "unseen"}
    assert 0 <= fam["fusion_logistic@fedavg"]["seen"][run9.final]["recall"]["mean"] <= 1
    # variants that were not fitted are listed, not hidden
    nr = run9.report["not_run"]
    assert any("fedpers components" in k and "NOT RUN" in v for k, v in nr.items())
    assert not any("fedavg components" in k for k in nr)
    # the paper table shows it, and says what was not run
    t = federated(run9)
    assert any(r[0] == "fusion fitted on fedavg components" for r in t.rows)
    assert any("fusion fitted on fedpers components" in n for n in t.notes)


def test_fusion_source_must_score_every_cell():
    from qc.fusion import component_names
    assert component_names(1, source="fedpers") == ["rules", "slow", "fedpers_spatial_s1", "fedpers_temporal_s1"]
    with pytest.raises(ValueError, match="unseen cells unscored"):
        component_names(0, source="local")


def test_offline_models_are_scored_labelled_non_causal_and_leak_checked(p9, run9):
    fam = run9.report["splits"]["test"]["by_model_family"]
    assert "offline_rainnet" in fam
    # held-out clients were seen in the old model's training: not scored
    assert fam["offline_rainnet"]["unseen"][run9.final]["recall"] is None
    assert fam["offline_rainnet"]["seen"][run9.final]["recall"] is not None
    nr = run9.report["not_run"]
    # the model trained on a test year is refused with the year named; unconfigured models say so
    key = next(k for k in nr if "lstm_ae" in k)
    assert "NOT RUN" in nr[key] and "2000" in nr[key] and "leak" in nr[key]
    assert any("msnet" in k and "no artifact configured" in v for k, v in nr.items())
    assert "offline_lstm_ae" not in fam
    assert not any("NOT IMPLEMENTED" in v for v in nr.values())
    row = next(r for r in ablation(run9).rows if r[0].startswith("offline_rainnet"))
    assert "non-causal" in row[0]
    assert any("NON-CAUSAL" in n for n in ablation(run9).notes)


def test_offline_scores_use_the_same_budget_thresholds_and_skip_unseen_cells(p9):
    from qc.evaluate import score_store
    s = score_store(p9).load("offline_rainnet", "test", p9.split.years["test"][0])
    assert s.shape[1] == p9.grid.n_land
    assert np.isnan(s[:, p9.cell_role == 3]).all() and np.isfinite(s[:, p9.cell_role == 1]).any()
