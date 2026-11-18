"""qc.crossscale_run on the generated QC world: scale scores into the store, fusion, and the comparison table."""

import numpy as np
import pytest

from qc import crossscale_run as CR
from qc.baselines import run_untrained
from qc.evaluate import score_store
from qc.period_benchmark import build_period_benchmark


@pytest.fixture(scope="module")
def ready(prepared, bench):
    run_untrained(prepared, ("val",))
    build_period_benchmark(prepared, splits=("val", "test"), overwrite=True)
    return prepared


def test_scale_scores_are_stored_day_aligned_for_val_and_clean_years(ready):
    p = ready
    store = score_store(p)
    name = CR.compute_scale_scores(p, "monthly", "gamma_zero")
    assert name == "scale_monthly_gamma_zero"
    daily = store.load("rules", "val", p.split.years["val"][0])
    for y in p.split.years["val"]:
        a = store.load(name, "val", y)
        assert a.shape[1] == daily.shape[1] and a.shape[0] == (366 if y % 4 == 0 else 365)
    for y in p.split.years["threshold"]:
        assert store.has(name, "clean", y)
    again = CR.compute_scale_scores(p, "monthly", "gamma_zero")                 # already stored: nothing is recomputed
    assert again == name
    with pytest.raises(ValueError, match="scale must be"):
        CR.compute_scale_scores(p, "daily", "gamma_zero")


def test_fusion_is_the_max_of_the_standardised_parts_and_discounts_protected_cells(ready):
    p = ready
    store = score_store(p)
    CR.compute_scale_scores(p, "monthly", "gamma_zero")
    info = CR.fuse_cross_scale(p, "rules", {"monthly": "gamma_zero"}, "max", 0.5, overwrite=True)
    assert info["name"] == "xscale_max_daily+monthly" and set(info["references"]) == {"daily", "monthly"}
    assert abs(sum(v for v in info["driver_share"].values() if v is not None) - 1.0) < 1e-6
    from qc.benchmark import load_bench_year
    # The generated world has no protected extreme in any year, so the discount itself is covered by the unit test of fuse_scales
    # (test_crossscale_regions_bridge.py); here the stored arrays must equal the fixed rule applied to the stored parts.
    for y in p.split.years["val"]:
        d, m = store.load("rules", "val", y), store.load("scale_monthly_gamma_zero", "val", y)
        f = store.load(info["name"], "val", y)
        prot = load_bench_year(p, "val", y).extremes.protected
        expect = np.fmax(d / info["references"]["daily"], m / info["references"]["monthly"])
        expect = np.where(prot, expect * 0.5, expect)
        ok = np.isfinite(expect)
        assert np.allclose(f[ok], expect[ok], rtol=1e-4)
        assert np.isnan(f[~ok]).all()


def test_a_logit_scale_daily_score_is_fused_through_softplus(ready):
    """A fused logistic score is a log-odds value: negative for clean days (the real run's clean 99.9th percentile was -1.5).
    It must not stop the fusion; it is mapped to log(1 + exp(z)), positive and equal to z in the tail, in every place it is read."""
    p = ready
    store = score_store(p)
    CR.compute_scale_scores(p, "monthly", "gamma_zero")
    for tag, years in (("val", p.split.years["val"]), ("clean", p.split.years["threshold"])):
        for y in years:
            r = store.load("rules", tag, y)
            store.save("fusion_logistic_s7", tag, y, (r * 4.0 - 6.0).astype(np.float32))      # mostly negative, as in the real run
    info = CR.fuse_cross_scale(p, "fusion_logistic_s7", {"monthly": "gamma_zero"}, "max", 1.0, overwrite=True)
    assert info["references"]["daily"] > 0
    y = p.split.years["val"][0]
    z, m = store.load("fusion_logistic_s7", "val", y), store.load("scale_monthly_gamma_zero", "val", y)
    f = store.load(info["name"], "val", y)
    expect = np.fmax(np.logaddexp(0.0, z) / info["references"]["daily"], m / info["references"]["monthly"])
    ok = np.isfinite(expect)
    assert np.allclose(f[ok], expect[ok], rtol=1e-4)
    # a frozen fusion applied to the same split reads the parts the same way
    CR.fuse_frozen(p, info, "val", overwrite=True)
    assert np.allclose(store.load(info["name"], "val", y)[ok], expect[ok], rtol=1e-4)


def test_noisy_or_adds_the_ratios(ready):
    p = ready
    store = score_store(p)
    CR.compute_scale_scores(p, "monthly", "gamma_zero")
    info = CR.fuse_cross_scale(p, "rules", {"monthly": "gamma_zero"}, "noisy_or", 1.0, overwrite=True)
    y = p.split.years["val"][0]
    d, m = store.load("rules", "val", y), store.load("scale_monthly_gamma_zero", "val", y)
    f = store.load(info["name"], "val", y)
    ok = np.isfinite(d) & np.isfinite(m)
    assert np.allclose(f[ok], d[ok] / info["references"]["daily"] + m[ok] / info["references"]["monthly"], rtol=1e-4)


def _row(comb, scales, fusion, recall, false=0.5, prot=0.1, budget=1.0, comp=None):
    return {"combination": comb, "scales": scales, "fusion": fusion, "component": comp or comb, "budget_per_1000": budget, "recall": recall,
            "false_per_1000_clean": false, "protected_flagged": prot, "event_recall": None, "pr_auc": None}


def _table(extra):
    rows = [_row("daily only", [], "daily", 0.60, comp="daily")] + extra
    return {"rows": rows, "scorers": {"monthly": "loo_median", "yearly": "gamma_zero"}}


def test_decision_rule_keeps_daily_only_unless_a_combination_clears_the_bar():
    t = _table([_row("daily + monthly", ["monthly"], "fixed", 0.61)])
    assert CR.decide_architecture(t)["chosen"]["fusion"] == "daily"                      # +0.01 is below the 0.02 bar
    t = _table([_row("daily + monthly", ["monthly"], "fixed", 0.63, comp="xs_m")])
    c = CR.decide_architecture(t)["chosen"]
    assert c["scales"] == ["monthly"] and c["component"] == "xs_m" and c["scorers"] == {"monthly": "loo_median"}


def test_decision_rule_guards_false_alarms_and_protected_extremes():
    too_many_false = _table([_row("daily + monthly", ["monthly"], "fixed", 0.80, false=1.5)])
    assert CR.decide_architecture(too_many_false)["chosen"]["fusion"] == "daily"
    flags_more_extremes = _table([_row("daily + monthly", ["monthly"], "fixed", 0.80, prot=0.5)])
    assert CR.decide_architecture(flags_more_extremes)["chosen"]["fusion"] == "daily"


def test_decision_rule_prefers_the_simplest_and_makes_learned_beat_its_fixed_twin():
    t = _table([_row("daily + monthly", ["monthly"], "fixed", 0.65, comp="m"),
                _row("daily + monthly + yearly", ["monthly", "yearly"], "fixed", 0.70, comp="my")])
    assert CR.decide_architecture(t)["chosen"]["component"] == "m"                       # fewer scales wins over higher recall
    t = _table([_row("daily + monthly", ["monthly"], "fixed", 0.65, comp="m"),
                _row("daily + monthly (learned)", ["monthly"], "learned", 0.66, comp="ml")])
    out = CR.decide_architecture(t)
    assert out["chosen"]["component"] == "m" and out["notes"]                            # learned is only +0.01 over its fixed twin
    t = _table([_row("daily + monthly", ["monthly"], "fixed", 0.65, comp="m"),
                _row("daily + monthly (learned)", ["monthly"], "learned", 0.70, comp="ml")])
    assert CR.decide_architecture(t)["chosen"]["component"] == "m"                       # both qualify; fixed is simpler, so it still wins
    t = _table([_row("daily + monthly (learned)", ["monthly"], "learned", 0.70, comp="ml")])
    assert CR.decide_architecture(t)["chosen"]["fusion"] == "daily"                      # no fixed twin to beat: not eligible
    with pytest.raises(ValueError, match="no rows at the final budget"):
        CR.decide_architecture(t, final_budget=9.0)


def test_comparison_table_has_daily_alone_and_the_combination(ready, tmp_path):
    p = ready
    res = CR.compare_cross_scale(p, "rules", {"monthly": "gamma_zero"}, (1.0, 5.0), overwrite=True)
    combos = {r["combination"] for r in res["rows"]}
    assert combos == {"daily only", "daily + monthly", "daily + monthly (learned)"} and len(res["rows"]) == 6
    assert {r["fusion"] for r in res["rows"]} == {"daily", "fixed", "learned"} and res["scorers"] == {"monthly": "gamma_zero"}
    learned = res["fusions"]["xscale_learned_daily+monthly"]["learned"]
    assert min(learned["weights"]) >= 0 and learned["positive_rows"] > 0 and learned["fit_years"] == [1996, 1997]
    assert "SYNTHETIC" in res["label"] and res["evaluation_years"] == list(p.split.years["threshold"])
    assert any("no confidence interval" in c for c in res["caveats"])
    r = res["rows"][0]
    assert {"recall", "event_recall", "false_per_1000_clean", "protected_flagged", "pr_auc"} <= set(r)
    md = CR.write_comparison(tmp_path, res)
    text = md.read_text(encoding="utf-8")
    assert "daily only" in text and "daily + monthly" in text and (tmp_path / "cross_scale_validation.json").is_file()
