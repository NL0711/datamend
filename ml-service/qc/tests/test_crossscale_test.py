"""qc.crossscale_test on the generated QC world, in its own run folder (name xtest) so it cannot disturb the other tests' score stores."""

import numpy as np
import pytest

from qc import crossscale_run as CR
from qc import crossscale_test as CT
from qc.baselines import run_untrained
from qc.config import load_config
from qc.fusion_eval import budgets_path
from qc.period_benchmark import build_period_benchmark
from qc.prepare import prepare
from qc.runs import write_json
from qc.testscore import lock_path as daily_lock_path


@pytest.fixture(scope="module")
def px(world, bench):
    p = prepare(load_config(world / "test.yaml", ["name=xtest"]), check_data=False)
    run_untrained(p, ("val", "test"))
    build_period_benchmark(p, splits=("val", "test"), overwrite=True)
    return p


@pytest.fixture(autouse=True)
def clean_state(px):
    def reset():
        for f in (CT.lock_path(px), CT.choice_path(px), budgets_path(px), daily_lock_path(px)):
            if f.is_file():
                f.unlink()
    reset()
    yield
    reset()


@pytest.fixture(scope="module")
def validation(px):
    CR.compute_scale_scores(px, "monthly", "gamma_zero")
    return CR.compare_cross_scale(px, "rules", {"monthly": "gamma_zero"}, [1.0, 5.0], overwrite=True)


def _arm(p, validation, combination=True):
    write_json(daily_lock_path(p), {"status": "done", "finished": "test"})
    write_json(budgets_path(p), {"final_per_1000": 1.0, "review_per_1000": 5.0})
    comp = "xscale_max_daily+monthly"
    chosen = ({"scales": ["monthly"], "fusion": "fixed", "component": comp, "scorers": {"monthly": "gamma_zero"}} if combination
              else {"scales": [], "fusion": "daily", "component": "rules", "scorers": {}})
    write_json(CT.choice_path(p), {"chosen": chosen, "daily": "rules", "commit": "abc123", "rule": {"final_budget": 1.0, "min_recall_gain": 0.02},
                                   "fusion_info": validation["fusions"][comp] if combination else None})


def test_preflight_refuses_until_everything_is_in_place(px, validation):
    with pytest.raises(RuntimeError, match="daily test pass is not finished"):
        CT.preflight(px, ("test",))
    write_json(daily_lock_path(px), {"status": "done"})
    with pytest.raises(RuntimeError, match="architecture has not been chosen"):
        CT.preflight(px, ("test",))
    write_json(CT.choice_path(px), {"chosen": {"fusion": "daily", "component": "rules", "scales": [], "scorers": {}}, "daily": "rules"})
    with pytest.raises(RuntimeError, match="budgets are not fixed"):
        CT.preflight(px, ("test",))
    write_json(budgets_path(px), {"final_per_1000": 1.0, "review_per_1000": 5.0})
    assert CT.preflight(px, ("test",))["budgets"]["review_per_1000"] == 5.0


def test_a_combination_without_frozen_fusion_information_is_refused(px, validation):
    _arm(px, validation)
    doc = CT.choice_path(px)
    import json
    d = json.loads(doc.read_text())
    d["fusion_info"] = None
    write_json(doc, d)
    with pytest.raises(RuntimeError, match="no frozen fusion information"):
        CT.preflight(px, ("test",))


def test_full_pass_scores_the_chosen_architecture_once(px, validation):
    _arm(px, validation)
    report = CT.run_cross_scale_test(px, splits=("test",))
    assert report["label"] == "SYNTHETIC faults" and report["chosen"]["component"] == "xscale_max_daily+monthly"
    labels = {r["architecture"] for r in report["rows"]}
    assert {"chosen architecture", "daily only", "untrained: slow", "untrained: neighbour_baseline"} <= labels
    assert {r["group"] for r in report["rows"]} == {"seen", "unseen"} and {r["budget_per_1000"] for r in report["rows"]} == {1.0, 5.0}
    from qc.evaluate import score_store
    store = score_store(px)
    for y in px.split.years["test"]:
        assert store.has("xscale_max_daily+monthly", "test", y) and store.has("scale_monthly_gamma_zero", "test", y)
    md = (CT.report_dir(px) / "cross_scale_test_report.md").read_text(encoding="utf-8")
    assert "SYNTHETIC" in md and "abc123" in md and "single use" not in md
    from qc.runs import read_json
    assert read_json(CT.lock_path(px))["status"] == "done"
    with pytest.raises(RuntimeError, match="single use"):
        CT.run_cross_scale_test(px, splits=("test",))


def test_an_unfinished_pass_needs_resume(px, validation):
    _arm(px, validation, combination=False)
    write_json(CT.lock_path(px), {"status": "started"})
    with pytest.raises(RuntimeError, match="unfinished"):
        CT.run_cross_scale_test(px, splits=("test",))
    rep = CT.run_cross_scale_test(px, splits=("test",), resume=True)
    assert rep["chosen"]["fusion"] == "daily"


def test_daily_only_choice_scores_only_baselines(px, validation):
    _arm(px, validation, combination=False)
    rep = CT.run_cross_scale_test(px, splits=("test",))
    assert rep["components"]["chosen architecture"] == "rules" and "daily only" not in rep["components"]      # the same component is listed once
    assert {"untrained: slow", "untrained: neighbour_baseline"} <= set(rep["components"])


def test_budgets_record_the_fused_score_they_apply_to(px, tmp_path):
    from qc.fusion_eval import set_budgets
    from qc.scoring import ScoreStore

    curves = tmp_path / "curves.json"
    curves.write_text("{}", encoding="utf-8")
    proto = tmp_path / "protocol.md"
    proto.write_text("**Status (x): not yet fixed.** n\n\n| date | budgets chosen | commit | confirmed |\n|---|---|---|---|\n| | | | |\n", encoding="utf-8")
    doc = set_budgets(px, 1, 5, curves, proto, ScoreStore(tmp_path / "scores"), today="2026-11-20", component="xscale_max_daily+monthly")
    assert doc["applies_to"] == "xscale_max_daily+monthly"
    row = [ln for ln in proto.read_text(encoding="utf-8").splitlines() if ln.startswith("| 2026-11-20")][0]
    assert "applies to xscale_max_daily+monthly" in row and row.count("|") == 5            # still the four columns of the table


def test_names_to_score_lists_each_component_once():
    names = CT.names_to_score({"chosen": {"component": "xs"}, "daily": "fusion_logistic_s0"})
    assert list(names.values()) == ["xs", "fusion_logistic_s0", "rules", "slow", "neighbour_baseline"]
    same = CT.names_to_score({"chosen": {"component": "rules"}, "daily": "rules"})
    assert list(same.values()) == ["rules", "slow", "neighbour_baseline"]
