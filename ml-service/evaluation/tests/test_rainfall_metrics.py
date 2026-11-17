"""Metric functions on toy arrays only: checks they compute and satisfy their defining properties."""

import numpy as np
import pytest

from evaluation.rainfall_metrics import (ablation_variants, affiliation, breakdown, concat_windows, event_metrics,
                                         fpr_on_clean, pointwise, random_baseline, region_labels, run_seeds,
                                         season_labels, threshold_metrics, to_events, window_metrics)


def _y():
    y = np.zeros(100, bool)
    y[10:15] = True
    y[60:62] = True
    return y


def test_to_events():
    assert to_events(_y()) == [(10, 14), (60, 61)]
    assert to_events(np.zeros(5, bool)) == []


def test_pointwise_and_random_baseline():
    y = _y()
    assert pointwise(y, y.astype(float))["pr_auc"] == pytest.approx(1.0)
    rb = random_baseline(y, seed=0)["pr_auc"]
    assert abs(rb - y.mean()) < 0.15                                 # random scoring hovers near prevalence
    assert np.isnan(pointwise(np.zeros(5, bool), np.arange(5.0))["pr_auc"])


def test_threshold_metrics_and_fpr():
    y, pred = _y(), _y().copy()
    pred[0] = True                                                   # one false alarm
    m = threshold_metrics(y, pred)
    assert m["recall"] == 1.0 and m["precision"] == pytest.approx(7 / 8)
    assert m["fpr"] == pytest.approx(1 / 93) and fpr_on_clean(pred, y) == m["fpr"]
    assert fpr_on_clean(np.zeros(100, bool), y) == 0.0


def test_event_metrics_no_point_adjustment():
    y = _y()
    pred = np.zeros(100, bool)
    pred[12] = True                                                  # a single point inside the first event
    pred[90] = True                                                  # a false alarm
    m = event_metrics(y, pred, tol=0)
    assert m["event_recall"] == 0.5 and m["event_precision"] == 0.5
    assert m["false_alarm_events"] == 1.0 and m["mean_delay"] == 2.0
    assert threshold_metrics(y, pred)["recall"] == pytest.approx(1 / 7)   # point recall is NOT inflated to 5/7
    assert event_metrics(y, y)["event_f1"] == 1.0
    assert event_metrics(y, pred, tol=3)["event_recall"] == 0.5


def test_affiliation_defining_properties():
    y = _y()
    perfect = affiliation(y, y)
    assert perfect["aff_precision"] == pytest.approx(1.0) and perfect["aff_recall"] == pytest.approx(1.0)
    assert perfect["aff_f1"] == pytest.approx(1.0)
    none = affiliation(y, np.zeros(100, bool))
    assert none["aff_recall"] == 0.0 and none["aff_f1"] == 0.0 and np.isnan(none["aff_precision"])
    assert np.isnan(affiliation(np.zeros(10, bool), np.ones(10, bool))["aff_f1"])    # no events -> undefined
    near, far = np.zeros(100, bool), np.zeros(100, bool)
    near[16:18] = True
    near[63:65] = True
    far[40:42] = True
    far[85:87] = True
    assert affiliation(y, near)["aff_f1"] > affiliation(y, far)["aff_f1"]            # closer alarms score higher
    for k in ("aff_precision", "aff_recall", "aff_f1"):
        assert 0.0 <= affiliation(y, near)[k] <= 1.0


def test_affiliation_random_alarms_are_not_rewarded_like_perfect_ones():
    rng = np.random.default_rng(0)
    y = _y()
    scores = [affiliation(y, rng.random(100) < 0.1)["aff_f1"] for _ in range(30)]
    assert np.nanmean(scores) < 0.9


def test_window_metrics_on_toy_windows():
    rng = np.random.default_rng(1)
    y = np.zeros((40, 20), bool)
    y[::2, 5:8] = True
    s = y * 1.0 + rng.random(y.shape) * 0.1
    m = window_metrics(y, s, s > 0.5, seed=0)
    assert m["pr_auc"] == pytest.approx(1.0) and m["event_f1"] == 1.0 and m["fpr_clean"] == 0.0
    assert m["random_pr_auc"] < 0.5 and m["aff_f1"] > 0.9
    assert concat_windows(y, 20).shape == (40 * 40,)                 # a gap separates windows so events never join


def test_breakdowns_by_kind_season_region_with_toy_data():
    rng = np.random.default_rng(2)
    y = np.zeros((60, 20), bool)
    y[:30, 4:6] = True
    s = y * 1.0 + rng.random(y.shape) * 0.2
    pred = s > 0.5
    kinds = np.array(["clean"] * 30 + ["spike"] * 15 + ["stuck"] * 15, dtype=object)
    bk = breakdown(y, s, pred, np.where(np.arange(60) < 30, "spike", "clean"))
    assert set(bk) == {"spike", "clean"} and bk["clean"]["fpr"] == 0.0 and bk["spike"]["recall"] == 1.0
    doy = np.tile(np.arange(20) * 18, (60, 1))                       # covers every season
    labels = season_labels(doy)
    assert {"winter", "monsoon_onset", "monsoon"} <= set(np.unique(labels))
    seasons = breakdown(y, s, pred, labels)
    assert all("pr_auc" in v and "fpr" in v for v in seasons.values())
    regions = breakdown(y, s, pred, region_labels(np.linspace(0, 1, 60)))
    assert set(regions) == {"south", "central", "north"}
    assert kinds.shape == (60,)


def test_run_seeds_reports_every_run_and_rejects_bad_lists():
    out = run_seeds(lambda sd: {"pr_auc": 0.1 * sd, "f1": 0.5}, [0, 1, 2])
    assert out["seeds"] == [0, 1, 2] and len(out["runs"]) == 3
    assert out["mean"]["pr_auc"] == pytest.approx(0.1) and out["std"]["f1"] == 0.0
    assert [r["pr_auc"] for r in out["runs"]] == pytest.approx([0.0, 0.1, 0.2])   # nothing dropped, no "best"
    assert "best" not in out
    with pytest.raises(ValueError):
        run_seeds(lambda sd: {}, [])
    with pytest.raises(ValueError):
        run_seeds(lambda sd: {}, [1, 1])


def test_ablation_grid_covers_rules_branches_and_scale_modes():
    v = ablation_variants(["rule", "stat", "rainnet"], ["mean_rank", "max"])
    assert {(x["scale_mode"], x["rule"], x["drop_branch"]) for x in v} >= {
        ("multi_scale", "mean_rank", None), ("single_scale", "max", None), ("multi_scale", "max", "stat")}
    assert len(v) == 2 * 2 + 2 * 3
