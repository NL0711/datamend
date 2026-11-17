"""Gate 5: fusion, validation curves, calibration, and the logged choice of the two budgets."""

import shutil

import numpy as np
import pytest

from qc.baselines import run_untrained
from qc.config import load_config
from qc.evaluate import score_store
from qc.fusion import FusionFit, VARIANTS, apply_fusion, component_names, fit_fusion, fused_name, load_features
from qc.fusion_eval import (PROTOCOL, budgets_path, load_budgets, plot_curves, run_fusion_validation, scored_after_validation,
                            set_budgets, validation_curves)
from qc.prepare import load_prepared
from qc.runs import write_json
from qc.scoring import ScoreStore
from qc.splits import LeakageError
from qc.trained import run_component
from qc.tests.test_gate4 import TINY


@pytest.fixture(scope="module")
def gp(world, bench):
    cfg = load_config(world / "test.yaml", TINY + ["name=g5", "fusion.max_rows=200000", "fusion.boosted_iter=20"])
    p = load_prepared(cfg)
    run_untrained(p, ("val",))
    for comp in ("spatial", "temporal"):
        assert run_component(p, comp, 0, ("val",), max_years=2)["train"].status == "done"
    return p


@pytest.fixture(scope="module")
def fit(gp):
    f = fit_fusion(gp, 0)
    apply_fusion(gp, f, ("val",))
    return f


def test_fit_uses_only_the_fusion_fit_years(gp, fit):
    assert fit.fit_years == gp.split.years["fusion_fit"]
    assert not set(fit.fit_years) & set(gp.split.years["threshold"])
    assert fit.n_positive > 0 and fit.names == component_names(0)


def test_overlapping_fit_and_threshold_years_are_refused(world, gp):
    with pytest.raises(LeakageError, match="overlap"):
        load_prepared(load_config(world / "test.yaml", TINY + ["years.fusion_fit=[1997,1998]"]))


def test_logistic_score_matches_hand_computation():
    f = FusionFit(0, ["a", "b", "c", "d"], mu=np.zeros(4), sd=np.ones(4), fit_years=[1], n_rows=1, n_positive=1,
                  logistic={"coef": np.array([2.0, 0, 0, 0.5]), "intercept": -1.0}, boosted=None, per_client={},
                  tail_sorted=[np.arange(100, dtype=float)] * 4)
    feats = np.log1p(np.array([[[3.0, 9.0, 1.0, 7.0]]]))
    assert np.allclose(f.score("logistic", feats), 2.0 * np.log(4.0) + 0.5 * np.log(8.0) - 1.0)
    assert np.allclose(f.score("mean", feats), np.log1p([3, 9, 1, 7]).mean())
    top = np.log1p(np.array([[[1000.0, 0, 0, 0]]]))
    assert np.allclose(f.score("or", top), -np.log10(0.5 / 100))               # rarer than every clean score
    mid = np.log1p(np.array([[[49.5, 0, 0, 0]]]))
    assert np.isclose(f.score("or", mid)[0, 0], np.log10(2), atol=1e-4)           # half of the clean scores are at least this large
    nan = np.full((1, 1, 4), np.nan)
    assert np.isnan(f.score("logistic", nan)).all()                            # nothing scored: no fused score
    part = np.array([[[np.log1p(3.0), np.nan, np.nan, np.nan]]])
    assert np.isfinite(f.score("logistic", part)).all()


def test_all_variants_score_every_year(gp, fit):
    store = score_store(gp)
    for v in VARIANTS:
        for y in gp.split.years["val"]:
            s = store.load(fused_name(v, 0), "val", y)
            assert s.shape[1] == gp.grid.n_land and np.isfinite(s).any()
        for y in gp.split.years["threshold"]:
            assert store.has(fused_name(v, 0), "clean", y)
    held = gp.cell_role == 3
    feats = load_features(store, fit.names, "val", gp.split.years["val"][0])
    shared, per = fit.score("logistic", feats, gp.cell_client), fit.score("per_client", feats, gp.cell_client)
    assert np.allclose(shared[:, held], per[:, held], equal_nan=True)          # unseen client uses the shared fusion


def test_save_and_load_round_trip(tmp_path, gp, fit):
    fit.save(tmp_path)
    again = FusionFit.load(tmp_path, 0)
    feats = load_features(score_store(gp), fit.names, "val", gp.split.years["val"][1])
    for v in VARIANTS:
        assert np.allclose(fit.score(v, feats, gp.cell_client), again.score(v, feats, gp.cell_client), atol=1e-4, equal_nan=True)


def test_curves_calibration_and_comparison(tmp_path, gp, fit):
    res = run_fusion_validation(gp, fit, tmp_path)
    assert (tmp_path / "curves_s0.png").is_file() and (tmp_path / "comparison_s0.json").is_file()
    assert res["curves"]["years"] == gp.split.years["threshold"]
    for name, rows in res["curves"]["scores"].items():
        rec = [r["fault_recall"] for r in rows]
        assert all(0 <= r <= 1 for r in rec) and rec == sorted(rec), name         # flagging more never lowers recall
    assert {fused_name(v, 0) for v in VARIANTS} <= set(res["comparison"])
    for r in res["comparison"].values():
        assert r["years"] == [gp.split.years["threshold"][0], gp.split.years["threshold"][-1]]
    assert 0 <= res["calibration"]["expected_calibration_error"] <= 1
    # the logistic fusion should not be worse than the average of nothing: it beats the base rate on held-out faults
    assert res["comparison"][fused_name("logistic", 0)]["groups"]["seen"]["pr_auc"] > 0.02


# ---------------------------------------------------------------- fixing the budgets

@pytest.fixture
def budget_env(world, tmp_path):
    cfg = load_config(world / "test.yaml", TINY + [f"name=budget_{tmp_path.name[-8:]}"])
    p = load_prepared(cfg)
    proto = tmp_path / "protocol.md"
    shutil.copy(PROTOCOL, proto)
    curves = tmp_path / "curves.json"
    write_json(curves, {"scores": {}})
    return p, proto, curves, ScoreStore(tmp_path / "scores")


def test_budgets_must_be_ordered_and_curves_must_exist(budget_env):
    p, proto, curves, store = budget_env
    with pytest.raises(ValueError, match="smaller"):
        set_budgets(p, 5, 1, curves, proto, store)
    with pytest.raises(RuntimeError, match="curves"):
        set_budgets(p, 1, 5, curves.parent / "none.json", proto, store)
    assert not budgets_path(p).exists()
    with pytest.raises(RuntimeError, match="not fixed"):
        load_budgets(p)                                                        # test scoring cannot start without them


def test_budgets_refused_after_test_scoring(budget_env):
    p, proto, curves, store = budget_env
    store.save("rules", "test", 2000, np.zeros((3, 3)))
    assert scored_after_validation(p, store)
    with pytest.raises(RuntimeError, match="before any test"):
        set_budgets(p, 1, 5, curves, proto, store)
    assert not budgets_path(p).exists()


def test_budgets_are_logged_and_cannot_be_changed(budget_env):
    p, proto, curves, store = budget_env
    doc = set_budgets(p, 1, 5, curves, proto, store, today="2026-11-20")
    assert doc["final_per_1000"] == 1 and load_budgets(p)["review_per_1000"] == 5
    text = proto.read_text(encoding="utf-8")
    assert "| 2026-11-20 | 1 / 5 |" in text and "Status (2026-11-20): fixed" in text
    assert text.count("| 2026-11-20 |") == 1
    with pytest.raises(RuntimeError, match="already exists"):
        set_budgets(p, 2, 8, curves, proto, store)
    budgets_path(p).unlink()
