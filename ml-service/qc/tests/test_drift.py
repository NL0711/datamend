"""qc.drift: the CUSUM drift score on generated rain (no real data), and the decision-rule verdict."""
import numpy as np
import pytest

from qc import drift as D
from qc.scoring import Block

PAD, T, N = 90, 220, 14


def _ring(n=N):
    return np.array([[j for j in range(n) if j != i] for i in range(n)], dtype=np.int64)


def _rain(seed=0, pad=PAD, t=T, n=N):
    """Shared weather (a wet-day pattern common to all cells) plus a little local noise, in mm."""
    rng = np.random.default_rng(seed)
    days = pad + t
    wet = rng.random(days) < 0.45
    base = rng.gamma(2.0, 4.0, size=days) * wet
    local = np.exp(rng.normal(0.0, 0.15, size=(days, n)))
    return (base[:, None] * local).astype(np.float32)


def _block(obs, pad=PAD):
    doy = (np.arange(obs.shape[0]) % 365).astype(np.int16)
    return Block(2014, "clean", obs, pad, doy, None)


def _drifted(factor=2.0, start=PAD + 60, dur=40, cell=0, additive=False):
    obs = _rain()
    ramp = np.linspace(0.0, 1.0, dur, dtype=np.float32)
    seg = slice(start, start + dur)
    if additive:
        wet = obs[seg, cell] > D.WET_MM
        obs[seg, cell] = np.where(wet, obs[seg, cell] + ramp * 6.0, obs[seg, cell])
    else:
        obs[seg, cell] = obs[seg, cell] * (1.0 + ramp * (factor - 1.0))
    return obs, seg


def test_a_multiplicative_ramp_scores_far_above_the_untouched_cells():
    obs, seg = _drifted(2.0)
    s = D.drift_score(_block(obs), _ring())
    window = slice(seg.start - PAD, seg.stop - PAD + 10)                    # score rows are offset by the history days
    assert s[window, 0].max() > 3.0 * s[window, 1:].max()
    assert s.shape == (T, N) and s.dtype == np.float32


def test_an_additive_ramp_on_wet_days_is_found_too():
    obs, seg = _drifted(additive=True)
    s = D.drift_score(_block(obs), _ring())
    window = slice(seg.start - PAD, seg.stop - PAD + 10)
    assert s[window, 0].max() > 2.0 * s[window, 1:].max()


def test_a_downward_ramp_is_found_by_the_other_side_of_the_cusum():
    obs, seg = _drifted(factor=0.4)
    s = D.drift_score(_block(obs), _ring())
    window = slice(seg.start - PAD, seg.stop - PAD + 10)
    assert s[window, 0].max() > 3.0 * s[window, 1:].max()


def test_one_huge_day_does_not_look_like_drift():
    obs = _rain()
    obs[PAD + 100, 0] = 500.0                                               # a spike, not a ramp
    s = D.drift_score(_block(obs), _ring())
    quiet = D.drift_score(_block(_rain()), _ring())
    assert s[:, 0].max() <= quiet[:, 1:].max() * 1.5 + D.CLIP                # one clipped day adds at most the clip


def test_the_score_is_causal_future_days_do_not_change_earlier_scores():
    obs, _ = _drifted(2.0)
    full = D.drift_score(_block(obs), _ring(), spread=0.5)
    cut = obs.copy()
    cut[PAD + 150:] = 0.0
    short = D.drift_score(_block(cut), _ring(), spread=0.5)
    assert np.allclose(full[:150], short[:150], equal_nan=True, atol=1e-5)


def test_missing_values_give_nan_scores_only_where_the_day_is_missing():
    obs, _ = _drifted(2.0)
    obs[PAD + 20, 3] = np.nan
    s = D.drift_score(_block(obs), _ring())
    assert np.isnan(s[20, 3]) and np.isfinite(s[21, 3]) and np.isfinite(s[20, 4])


def test_all_dry_data_scores_zero_and_does_not_crash():
    s = D.drift_score(_block(np.zeros((PAD + 30, N), np.float32)), _ring())
    assert np.nanmax(s) == 0.0


def test_a_cell_without_neighbours_has_no_evidence():
    ring = _ring()
    ring[0, :] = -1
    s = D.drift_score(_block(_rain()), ring)
    assert np.nanmax(s[:, 0]) == 0.0


def _row(a, b):
    return {"a": a, "b": b, "diff": None if a is None or b is None else b - a}


def test_the_rule_needs_all_four_conditions():
    ok = D.rule_verdict(_row(0.24, 0.55), _row(0.01, 0.20), false_per_1000=1.2, protected_share=0.003)
    assert ok["met"] and ok["verdict"].startswith("rule met")
    for kw in ({"false_per_1000": 2.5}, {"protected_share": 0.05}):
        args = {"false_per_1000": 1.2, "protected_share": 0.003, **kw}
        assert not D.rule_verdict(_row(0.24, 0.55), _row(0.01, 0.20), **args)["met"]
    assert not D.rule_verdict(_row(0.24, 0.30), _row(0.01, 0.20), 1.2, 0.003)["met"]          # recall below 0.40 and gain below 0.10
    assert not D.rule_verdict(_row(0.24, 0.55), _row(0.01, 0.04), 1.2, 0.003)["met"]          # PR-AUC gain below 0.05
    assert not D.rule_verdict(_row(0.24, None), _row(0.01, None), 1.2, 0.003)["met"]


def test_a_tiny_stored_run_goes_through_scoring_comparison_and_the_written_report(prepared, bench):
    import json as _json

    from qc import paths
    from qc import stnet as S
    p = prepared
    cfg = S.STConfig(width=8, c_feat=8, long_hidden=8, epochs=1, steps=2, batch=2, window=8, burn=2, crop=24, long_epochs=1, long_steps=2, long_cells=64, prefix="stp")
    S.run_stnet(p, 0, cfg, ("val",), max_years=2)
    doc = D.run_drift_check(p, 0, "stp", 1.0)
    assert doc["compare"]["years"] == list(p.split.years["val"])
    assert set(doc["verdict"]["checks"]) == {"event_recall_at_least_min", "event_recall_gain_over_stnet", "pr_auc_gain_over_stnet",
                                             "false_alerts_within_limit", "protected_extremes_within_limit"}
    out = paths.out_dir(p.cfg) / str(p.cfg.name) / "drift"
    assert "SYNTHETIC" in (out / "drift_check_s0.md").read_text(encoding="utf-8")
    assert _json.loads((out / "drift_check_s0.json").read_text(encoding="utf-8"))["params"]["k"] == D.REFERENCE_K


def test_the_command_is_registered_and_takes_the_documented_options():
    from qc.__main__ import COMMANDS
    assert "drift-check" in COMMANDS
