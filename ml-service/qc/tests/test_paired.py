"""qc.paired: the paired whole-year comparison, on hand-made year tables (no model) and on a tiny stored run."""
import json

import numpy as np
import pytest

from qc import paired as P


def _table(event_recall, ap, years=(2013, 2014, 2015, 2016, 2017), false_rate=1.0, events=40):
    """One fault kind ('drift') with the given yearly event recall and yearly PR-AUC; clean cell-days chosen so false alerts per 1,000 = false_rate."""
    n = len(years)
    ev = np.full(n, float(events))
    hit = np.round(np.asarray(event_recall, float) * ev)
    cd = np.full(n, 400.0)
    fl = np.round(np.asarray(event_recall, float) * cd)
    counts = {"all": np.stack([ev, hit, cd, fl], axis=1), "drift": np.stack([ev, hit, cd, fl], axis=1)}
    clean_cd = np.full(n, 100_000.0)
    return {"component": "x", "budget": 1.0, "threshold": 0.5, "years": list(years), "counts": counts,
            "ap": {"all": np.asarray(ap, float), "drift": np.asarray(ap, float)},
            "clean": np.stack([clean_cd, np.round(false_rate / 1000.0 * clean_cd)], axis=1)}


def test_a_gain_in_every_year_has_an_interval_above_zero_and_every_resample_is_enumerated():
    a = _table([0.20, 0.25, 0.30, 0.20, 0.25], [0.10, 0.12, 0.11, 0.09, 0.10])
    b = _table([0.40, 0.45, 0.50, 0.40, 0.45], [0.30, 0.32, 0.31, 0.29, 0.30])
    r = P.compare(a, b)
    d = r["kinds"]["drift"]
    assert "5^5 = 3,125" in r["interval"] and "undercovers" in r["interval"]
    assert d["event_recall"]["diff"] == pytest.approx(0.2, abs=0.02)
    assert d["event_recall"]["diff_ci"][0] > 0 and d["pr_auc_mean_over_years"]["diff_ci"][0] > 0
    assert d["event_recall"]["years_b_better"] == 5 and d["event_recall"]["years_compared"] == 5
    assert P.compare(a, b) == r                                                   # nothing random with 5 years


def test_no_difference_gives_an_interval_around_zero_and_a_failed_rule():
    a = _table([0.2, 0.3, 0.2, 0.3, 0.2], [0.1, 0.2, 0.1, 0.2, 0.1])
    r = P.compare(a, _table([0.2, 0.3, 0.2, 0.3, 0.2], [0.1, 0.2, 0.1, 0.2, 0.1]))
    ci = r["kinds"]["drift"]["event_recall"]["diff_ci"]
    assert ci == [0.0, 0.0] and r["kinds"]["drift"]["event_recall"]["years_b_better"] == 0
    rule = P.drift_rule(r)
    assert rule["rule_met_on_point_estimates"] is False and "NOT met" in rule["verdict"] and "not that long memory is useless" in rule["verdict"]


def test_the_rule_needs_both_gains_and_no_worse_false_alerts_and_flags_moved_controls():
    a = _table([0.2] * 5, [0.1] * 5, false_rate=1.0)
    good = P.compare(a, _table([0.4] * 5, [0.3] * 5, false_rate=1.0))
    assert P.drift_rule(good)["rule_met_on_point_estimates"] is True
    worse = P.compare(a, _table([0.4] * 5, [0.3] * 5, false_rate=3.0))                  # same recall but three times the false alerts
    assert P.drift_rule(worse)["false_alerts_no_worse"] is False and P.drift_rule(worse)["rule_met_on_point_estimates"] is False
    only_recall = P.compare(a, _table([0.4] * 5, [0.1] * 5))
    assert P.drift_rule(only_recall)["rule_met_on_point_estimates"] is False            # PR-AUC did not move
    moved = P.drift_rule(good, controls=("drift",))                                      # a control that did move is named
    assert moved["controls_that_moved"] == ["drift"] and "CONTROLS MOVED" in moved["verdict"]


def test_fewer_than_five_years_gives_no_interval_and_different_years_are_refused():
    y3 = (2013, 2014, 2015)
    r = P.compare(_table([0.2] * 3, [0.1] * 3, years=y3), _table([0.4] * 3, [0.3] * 3, years=y3))
    assert r["kinds"]["drift"]["event_recall"]["diff_ci"] is None and "no interval" in r["interval"]
    assert r["kinds"]["drift"]["event_recall"]["diff"] == pytest.approx(0.2, abs=0.02)      # the per-year numbers are still there
    with pytest.raises(ValueError, match="same years"):
        P.compare(_table([0.2] * 3, [0.1] * 3, years=y3), _table([0.2] * 3, [0.1] * 3, years=(2013, 2014, 2016)))


def test_more_than_six_years_uses_a_fixed_number_of_random_resamples():
    yrs = tuple(range(2010, 2018))
    r = P.compare(_table([0.2] * 8, [0.1] * 8, years=yrs), _table([0.4] * 8, [0.3] * 8, years=yrs), seed=1)
    assert "2,000 random resamples" in r["interval"]
    assert r["kinds"]["drift"]["event_recall"]["diff_ci"][0] > 0


def test_a_stored_run_compared_with_itself_has_no_difference(prepared, bench):
    from qc import paths
    from qc import stnet as S
    p = prepared
    cfg = S.STConfig(width=8, c_feat=8, long_hidden=8, epochs=1, steps=2, batch=2, window=8, burn=2, crop=24, long_epochs=1, long_steps=2, long_cells=64, prefix="stp")
    S.run_stnet(p, 0, cfg, ("val",), max_years=2)
    res = P.run_paired(p, "stp", ["stp"], 0)["stp"]
    assert res["years"] == list(p.split.years["val"]) and "all" in res["kinds"]
    for row in res["kinds"].values():
        for m in ("event_recall", "recall"):
            assert row[m]["diff"] in (0.0, None)
    assert res["false_alerts_per_1000_clean"]["diff"] == 0.0
    out = paths.out_dir(p.cfg) / str(p.cfg.name) / "paired" / "paired_stp_vs_stp_s0"
    assert json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))["rule"]["hypothesis"] == "drift"
    assert "SYNTHETIC" in out.with_suffix(".md").read_text(encoding="utf-8")
