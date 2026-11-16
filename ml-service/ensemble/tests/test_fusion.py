import numpy as np
import pytest

from ensemble.branches import RuleBranch, StatBranch, daily_rule_severity
from ensemble.fusion import (RULES, LikelihoodNormalizer, RankNormalizer, calibrate_threshold, fuse, owa_weights)
from ensemble.pipeline import FusionConfig, FusionPipeline
from ensemble.statbaseline import StatBaseline
from training.sampler import Batch, YearCube


# ---------------------------------------------------------------- normalization -------------------------
def test_rank_normalizer_range_monotone_and_uniform_on_its_own_clean_data():
    rng = np.random.default_rng(0)
    clean = rng.gamma(2.0, 3.0, size=20000)
    n = RankNormalizer().fit(clean)
    r = n.transform(clean)
    assert r.min() > 0 and r.max() <= 1.0
    assert abs(np.mean(r < 0.5) - 0.5) < 0.02 and abs(np.mean(r < 0.99) - 0.99) < 0.01   # ~uniform on clean data
    xs = np.linspace(0, 40, 200)
    assert (np.diff(n.transform(xs)) >= 0).all()                       # monotone
    assert n.transform(np.array([1e9]))[0] == 1.0 and n.transform(np.array([-1e9]))[0] == 0.0


def test_rank_normalizer_puts_different_units_on_one_scale():
    rng = np.random.default_rng(1)
    a, b = rng.normal(0, 1, 5000), rng.normal(0, 1, 5000) * 1000 + 5e5   # wildly different units
    ra, rb = RankNormalizer().fit(a), RankNormalizer().fit(b)
    q = lambda f, x: np.quantile(f.transform(x), [0.25, 0.5, 0.75])
    np.testing.assert_allclose(q(ra, a), q(rb, b), atol=0.03)


def test_rank_normalizer_respects_valid_mask_and_subsamples(monkeypatch):
    s = np.array([1.0, 2.0, 3.0, 1e9])
    n = RankNormalizer().fit(s, valid=np.array([True, True, True, False]))
    assert n.ref.max() == 3.0                                          # masked value never enters the reference
    monkeypatch.setattr("ensemble.fusion._MAX_REF", 50)
    assert RankNormalizer().fit(np.arange(1000.0)).ref.size == 50


def test_likelihood_normalizer_probability_properties():
    rng = np.random.default_rng(2)
    nll = rng.gamma(2.0, 1.0, 10000) + 3.0
    n = LikelihoodNormalizer().fit(nll)
    p = n.transform(nll)
    assert ((p >= 0) & (p < 1)).all()
    assert n.transform(np.array([n.ref - 5]))[0] == 0.0                # below the clean median -> 0
    assert n.transform(np.array([n.ref + 1000 * n.temperature]))[0] > 0.999
    assert (np.diff(n.transform(np.linspace(0, 30, 100))) >= 0).all()


# ---------------------------------------------------------------- fusion rules --------------------------
def test_fusion_rules_on_known_values():
    ranks = {"a": np.array([0.2, 0.9]), "b": np.array([0.4, 0.1]), "c": np.array([0.6, 0.5])}
    np.testing.assert_allclose(fuse(ranks, rule="mean_rank"), [0.4, 0.5])
    np.testing.assert_allclose(fuse(ranks, rule="max"), [0.6, 0.9])
    np.testing.assert_allclose(fuse(ranks, rule="owa", owa_orness=0.5), [0.4, 0.5])      # orness 0.5 == mean
    assert (fuse(ranks, rule="owa", owa_orness=0.99) > fuse(ranks, rule="owa", owa_orness=0.5)).any()
    near_max = fuse(ranks, rule="owa", owa_orness=0.999)
    np.testing.assert_allclose(near_max, fuse(ranks, rule="max"), atol=0.01)
    near_min = fuse(ranks, rule="owa", owa_orness=0.001)
    np.testing.assert_allclose(near_min, [0.2, 0.1], atol=0.01)
    np.testing.assert_allclose(fuse(ranks, rule="owa", owa_w=[1, 0, 0]), [0.6, 0.9])     # explicit weights


def test_prob_avg_uses_branch_probabilities_where_available():
    ranks = {"a": np.array([0.5]), "b": np.array([0.5])}
    probs = {"a": np.array([0.9])}                                      # b has none -> falls back to its rank
    np.testing.assert_allclose(fuse(ranks, probs, "prob_avg"), [0.7])


def test_fusion_stays_in_unit_interval_and_validates_input():
    rng = np.random.default_rng(3)
    ranks = {k: rng.random((4, 7)) for k in "abc"}
    for rule in RULES:
        out = fuse(ranks, ranks, rule)
        assert out.shape == (4, 7) and (out >= 0).all() and (out <= 1).all()
    with pytest.raises(ValueError):
        fuse(ranks, rule="stacking")
    with pytest.raises(ValueError):
        fuse({}, rule="max")
    with pytest.raises(ValueError):
        fuse(ranks, rule="owa", owa_w=[0.5, 0.5])
    assert owa_weights(4, 0.7).sum() == pytest.approx(1.0) and (np.diff(owa_weights(4, 0.7)) < 0).all()


# ---------------------------------------------------------------- threshold calibration -----------------
def test_threshold_hits_target_fpr_on_clean_validation():
    rng = np.random.default_rng(4)
    clean = rng.random((400, 30))
    info = calibrate_threshold(clean, target_fpr=0.02)
    assert info["achieved_fpr"] == pytest.approx(0.02, abs=0.003)
    looser = calibrate_threshold(clean, target_fpr=0.1)["threshold"]
    assert looser < info["threshold"]


def test_threshold_ignores_invalid_points_and_supports_event_budget():
    rng = np.random.default_rng(5)
    clean = rng.random((300, 30))
    valid = np.ones_like(clean, bool)
    valid[:, :5] = False
    clean[:, :5] = 1e9                                                  # garbage under the mask
    info = calibrate_threshold(clean, valid, target_fpr=0.05)
    assert info["threshold"] < 1.0 and info["n_points"] == valid.sum()
    ev = calibrate_threshold(clean, valid, method="events", max_events_per_1000=10)
    assert ev["events_per_1000"] <= 10.0
    with pytest.raises(ValueError):
        calibrate_threshold(clean, method="percentile99")
    with pytest.raises(ValueError):
        calibrate_threshold(np.zeros((2, 2)), np.zeros((2, 2), bool))


# ---------------------------------------------------------------- branches & pipeline -------------------
def test_rule_severity_negative_extreme_and_stuck_runs():
    x = np.zeros((1, 20))
    x[0, 2] = -3.0
    x[0, 5] = 900.0
    x[0, 10:16] = 7.0                                                   # six identical non-zero days
    sev = daily_rule_severity(x)[0]
    assert sev[2] == 1.0 and 0.8 < sev[5] <= 1.0
    assert (sev[10:16] == 0.8).all() and sev[0] == 0 and sev[8] == 0


def _batch(n=40, w=20, seed=0, rate=0.0):
    from training.sampler import WindowSampler
    rng = np.random.default_rng(seed)
    cube = rng.gamma(0.3, 8.0, size=(60, 8, 9)).astype("float32")
    cube[:, :2] = np.nan
    yc = YearCube.build(cube)
    return WindowSampler([yc], ~np.isnan(cube).all(0), window=w, seed=seed).batch(n, rate), yc


def test_pipeline_fit_fuse_threshold_save_reload_roundtrip(tmp_path):
    b, yc = _batch(60, seed=1)
    stat = StatBaseline.fit([yc], [2000])
    pipe = FusionPipeline([RuleBranch(), StatBranch(stat)], FusionConfig(rule="owa", owa_orness=0.8))
    pipe.fit_normalizers([b])
    info = pipe.fit_threshold([_batch(60, seed=2)[0]])
    test_b, _ = _batch(30, seed=3, rate=0.5)
    fused = pipe.fuse(test_b)
    assert fused.shape == test_b.labels.shape and (fused >= 0).all() and (fused <= 1).all()
    pipe.save(tmp_path / "p")
    again = FusionPipeline.load(tmp_path / "p")
    np.testing.assert_allclose(again.fuse(test_b), fused)
    assert again.threshold_info["threshold"] == info["threshold"] and again.config.rule == "owa"
    np.testing.assert_array_equal(again.flags(test_b), pipe.flags(test_b))


def test_unavailable_branch_is_skipped_not_fatal(caplog):
    b, yc = _batch(30, seed=4)
    stat = StatBaseline.fit([yc], [2000])
    pipe = FusionPipeline([RuleBranch(), StatBranch(stat)])
    pipe.fit_normalizers([b])
    no_cell = Batch.from_windows(b.x_mm[..., 0])                        # no cell/doy-> stat branch cannot score
    with caplog.at_level("WARNING"):
        ranks, _ = pipe.normalized(no_cell)
    assert set(ranks) == {"rule"} and "stat" in caplog.text
    with pytest.raises(ValueError):
        FusionPipeline([RuleBranch(), RuleBranch()])


def test_no_supervised_stacking_in_default_pipeline():
    import ensemble.pipeline as mod
    src = open(mod.__file__, encoding="utf-8").read().lower()
    assert "logisticregression" not in src and "sklearn" not in src      # fusion is label-free by default
