"""Gate 7: the single test-scoring pass. Guards, one-time lock, unseen and stress evaluation, alerts, report."""

import shutil

import numpy as np
import pandas as pd
import pytest

from qc.baselines import run_untrained
from qc.benchmark import build_benchmark
from qc.config import load_config
from qc.evaluate import score_store
from qc.federated import run_federated
from qc.fusion import VARIANTS, apply_fusion, fit_fusion, fit_fusion_federated
from qc.fusion_eval import PROTOCOL, budgets_path, run_fusion_validation, set_budgets
from qc.prepare import load_prepared
from qc.runs import read_json, write_json
from qc.testscore import (aggregate_seeds, base_name, final_checkpoint, format_report, lock_path, preflight, run_root,
                          run_test_scoring)
from qc.trained import run_component
from qc.tests.test_gate4 import TINY

BASE = TINY + ["name=g7", "benchmark.name=g7bench", "fusion.max_rows=100000", "fusion.boosted_iter=10", "federated.finetune_steps=2"]


@pytest.fixture(scope="module")
def p7(world, prepared, tmp_path_factory):
    cfg = load_config(world / "test.yaml", BASE)
    p = load_prepared(cfg)
    build_benchmark(p, splits=("val", "test", "stress"), overwrite=True)
    return p


@pytest.fixture(scope="module")
def ready(p7, tmp_path_factory):
    """Validation work of gates 3-6 done on the small world, budgets not yet fixed."""
    p = p7
    run_untrained(p, ("val",))
    for c in ("spatial", "temporal", "plain_gru"):
        assert run_component(p, c, 0, ("val",), max_years=2)["train"].status == "done"
    assert run_federated(p, "temporal", "fedavg", 0, ("val",), max_years=2)["train"].status == "done"
    fit = fit_fusion(p, 0)
    fit_fusion_federated(p, fit, rounds=5)
    fit.save(run_root(p) / "fusion" / "models")
    apply_fusion(p, fit, ("val",), VARIANTS + ("logistic_fed",))
    run_fusion_validation(p, fit, run_root(p) / "fusion" / "validation")
    return p


def test_nothing_is_scored_before_the_budgets_are_fixed(ready):
    with pytest.raises(RuntimeError, match="not fixed"):
        preflight(ready, [0], ("test",))
    assert not lock_path(ready).exists()
    assert not list(score_store(ready).root.glob("*/test_*.npy"))


@pytest.fixture(scope="module")
def fixed(ready, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("proto")
    proto = tmp / "protocol.md"
    shutil.copy(PROTOCOL, proto)
    set_budgets(ready, 1, 5, run_root(ready) / "fusion" / "validation" / "curves_s0.json", proto, today="2026-11-21")
    return ready


def test_missing_models_are_reported_before_scoring(fixed):
    ck = final_checkpoint(fixed, "plain_gru", 0)
    hidden = ck.with_suffix(".hidden")
    ck.rename(hidden)
    try:
        with pytest.raises(RuntimeError, match="missing"):
            preflight(fixed, [0], ("test",))
        with pytest.raises(RuntimeError, match="missing"):
            preflight(fixed, [0, 1], ("test",))                 # seed 1 was never trained
    finally:
        hidden.rename(ck)
    assert not lock_path(fixed).exists()


def test_budgets_from_another_benchmark_are_refused(fixed):
    doc = read_json(budgets_path(fixed))
    write_json(budgets_path(fixed), {**doc, "benchmark_hash": "feedfeedfeedfeed"})
    try:
        with pytest.raises(RuntimeError, match="different benchmark"):
            preflight(fixed, [0], ("test",))
    finally:
        write_json(budgets_path(fixed), doc)


def test_test_scoring_runs_once_and_reports_everything(fixed):
    p = fixed
    report = run_test_scoring(p, [0], ("test", "stress"))
    root = run_root(p) / "test"
    lock = read_json(lock_path(p))
    assert lock["status"] == "done" and lock["benchmark_hash"] and lock["budgets"]["final_per_1000"] == 1

    # headline numbers, both client groups, at both budgets, for the main fusion and every component
    fam = report["splits"]["test"]["by_model_family"]
    assert {"rules", "slow", "neighbour_baseline", "spatial", "temporal", "plain_gru", "fusion_logistic",
            "fusion_logistic_fed", "fedavg_temporal"} <= set(fam)
    for name, groups in fam.items():
        assert set(groups) == {"seen", "unseen"}, name
    row = fam["fusion_logistic"]["seen"]["1.0"]
    assert 0 <= row["recall"]["mean"] <= 1 and row["false_per_1000"]["n_seeds"] == 1
    cal = report["splits"]["test"]["calibration_main_fusion"]["0"]
    assert set(cal) == {"seen", "unseen"} and 0 <= cal["seen"]["expected_calibration_error"] <= 1
    assert "stress" in report["splits"] and report["splits"]["stress"]["calibration_main_fusion"] is None

    # intervals are in the per-model metrics files
    m = read_json(root / "metrics_test.json")["fusion_logistic_s0"]
    assert "recall_ci" in m["groups"]["seen"]["by_budget"]["1.0"]["faults"]
    assert m["label_tier"] == "synthetic faults"

    # what was not run is listed, not hidden
    text = (root / "test_report.md").read_text(encoding="utf-8")
    assert "offline comparison" in text and "no artifact configured" in text and "fedpers_spatial_s0" in text
    assert "fusion fitted on fedpers components" in text and "NOT IMPLEMENTED" not in text
    assert "Labels: synthetic faults" in text

    # per-alert records: the four component scores, the fused score and the flag
    alerts = pd.read_parquet(root / "alerts" / "alerts_test_s0.parquet")
    assert {"fused_score", "flag", "score_rules", "score_slow", "score_spatial_s0", "score_temporal_s0", "synthetic_fault"} <= set(alerts)
    assert set(alerts["flag"]) <= {"final", "review"} and (alerts["year"].between(2000, 2001)).all()
    assert len(alerts) > 0

    # only test years were scored with the test lock; the test set cannot be scored again
    with pytest.raises(RuntimeError, match="single use"):
        run_test_scoring(p, [0], ("test",))
    with pytest.raises(RuntimeError, match="single use"):
        run_test_scoring(p, [0], ("test",), resume=True)
    run_test_scoring(p, [0], ("stress",))                        # stress has no lock and is evaluation only


def test_an_unfinished_pass_can_only_be_resumed(ready, world):
    cfg = load_config(world / "test.yaml", BASE + ["name=g7_resume"])
    # reuse the finished validation work by pointing a fresh run at the same scores is not needed: only the lock logic is tested
    p = load_prepared(cfg)
    run_root(p).mkdir(parents=True, exist_ok=True)
    write_json(run_root(p) / "fusion_budgets.json",
               {"final_per_1000": 1, "review_per_1000": 5, "benchmark_hash": None, "split_manifest_hash": p.manifest["hash"]})
    write_json(lock_path(p), {"status": "started"})
    for c in ("spatial", "temporal", "plain_gru"):
        ck = final_checkpoint(p, c, 0)
        ck.parent.mkdir(parents=True, exist_ok=True)
        ck.write_bytes(b"x")
    (run_root(p) / "fusion" / "models").mkdir(parents=True, exist_ok=True)
    (run_root(p) / "fusion" / "models" / "logistic_s0.json").write_text("{}")
    with pytest.raises(RuntimeError, match="--resume"):
        preflight(p, [0], ("test",))
    assert preflight(p, [0], ("test",), resume=True)["final_per_1000"] == 1


# ---------------------------------------------------------------- aggregation

def test_aggregation_over_seeds_gives_mean_and_range():
    def res(recall):
        return {"component": "x", "groups": {"seen": {"pr_auc": recall, "by_budget": {"1.0": {
            "faults": {"recall": recall, "event_recall": recall}, "false_alerts": {"per_1000_clean": 1.0},
            "protected_extremes": {"flagged_share_of_cell_days": 0.1}}}}}}

    agg = aggregate_seeds({"spatial_s0": res(0.2), "spatial_s1": res(0.4), "spatial_s2": res(0.6), "rules": res(0.5)}, [1.0])
    r = agg["spatial"]["seen"]["1.0"]["recall"]
    assert np.isclose(r["mean"], 0.4) and r["min"] == 0.2 and r["max"] == 0.6 and r["n_seeds"] == 3
    assert agg["rules"]["seen"]["1.0"]["recall"]["n_seeds"] == 1
    assert base_name("fedpers_prox_spatial_s2") == "fedpers_prox_spatial" and base_name("rules") == "rules"
