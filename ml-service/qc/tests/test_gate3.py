"""Gate 3: untrained scores and the metric definitions (checked against hand-computed values)."""

import numpy as np
import pytest
from sklearn.metrics import average_precision_score

from qc.baselines import UNTRAINED, run_untrained, score_functions
from qc.benchmark import BenchYear
from qc.extremes import Extremes
from qc.faults import FaultSet
from qc.grid import Grid
from qc.metrics import YearScores, budget_thresholds, calibration, evaluate, pr_auc
from qc.neighbours import gather, ring_index
from qc.scoring import make_block
from qc.splits import LeakageError
from qc.untrained import trailing_total


# ---------------------------------------------------------------- metric definitions on a hand-made case

def _toy():
    """4 x 4 land grid, 10 days. Returns (grid, YearScores, cells, client ids)."""
    grid = Grid.from_land(np.arange(4), np.arange(4), np.ones((4, 4), bool))
    T, n = 10, 16
    # fault 0: stuck, single cell 5, days 2-4.  fault 1: spike with a footprint, cells 10 and 11, day 6.
    events = [{"kind": "stuck", "bases": ["stuck"], "strength": 0.5, "radius": 0.0, "centre": 5, "start": 2, "duration": 3, "n_changed": 3},
              {"kind": "spike", "bases": ["spike"], "strength": 0.5, "radius": 1.5, "centre": 10, "start": 6, "duration": 1, "n_changed": 2}]
    fs = FaultSet((T, n), np.array([2, 3, 4, 6, 6]), np.array([5, 5, 5, 10, 11]), np.ones(5, np.float32),
                  np.ones(5, np.float32), np.array([0, 0, 0, 1, 1]), events)
    protected = np.zeros((T, n), bool)
    protected[9, 0:4] = True                       # one protected event of 4 cells
    ambiguous = np.zeros((T, n), bool)
    ambiguous[1, 12] = True
    group = np.zeros((T, n), np.int32)
    group[9, 0:4] = 1
    group[1, 12] = 2
    bench = BenchYear(2000, "val", np.zeros((T, n), np.float32), fs, Extremes(protected, ambiguous, group, 1, 0), np.array([False, True]))
    score = np.zeros((T, n), np.float32)
    for t, c in [(3, 5), (4, 5), (6, 10),          # fault cell-days that get flagged
                 (0, 0), (8, 15),                  # two false alerts on clean cell-days
                 (9, 1),                           # one protected cell-day flagged
                 (1, 12)]:                         # the ambiguous cell-day flagged
        score[t, c] = 1.0
    return grid, YearScores(bench, score), np.ones(n, bool), np.ones(n, np.int8)


def test_metrics_match_hand_computation():
    grid, ys, cells, client = _toy()
    r = evaluate([ys], cells, 0.5, grid, client, bootstrap=0)
    assert r["faults"]["cell_days"] == 5 and r["faults"]["recall"] == pytest.approx(3 / 5)
    assert r["faults"]["event_recall"] == 1.0
    assert r["by_kind"]["stuck"]["recall"] == pytest.approx(2 / 3)
    assert r["by_kind"]["spike"]["recall"] == pytest.approx(1 / 2)
    assert r["by_radius"]["single cell"]["events"] == 1 and r["by_radius"]["radius 1.5-4"]["events"] == 1
    assert r["by_setting"]["test-only settings"]["events"] == 1
    # clean = 160 cell-days - 5 fault - 4 protected - 1 ambiguous
    assert r["false_alerts"]["clean_cell_days"] == 150 and r["false_alerts"]["false_alerts"] == 2
    assert r["false_alerts"]["per_1000_clean"] == pytest.approx(2000 / 150)
    assert r["false_alerts"]["per_daily_field"] == pytest.approx(2 / 150 * 16)
    # footprint overlap: fault 0 -> days (0/1, 1/1, 1/1); fault 1 -> 1/2
    assert r["by_kind"]["stuck"]["footprint_iou"] == pytest.approx(2 / 3)
    assert r["by_kind"]["spike"]["footprint_iou"] == pytest.approx(1 / 2)
    assert r["by_kind"]["stuck"]["delay_days_median"] == 1.0 and r["by_kind"]["stuck"]["never_detected"] == 0
    pe = r["protected_extremes"]
    assert pe["cell_days"] == 4 and pe["flagged_share_of_cell_days"] == 0.25 and pe["events_with_any_flag_share"] == 1.0
    assert pe["cell_days_flagged_by"]["size"]["4-9 cells"]["cell_days"] == 4
    assert pe["cell_days_flagged_by"]["season"]["rest of year"]["flagged_share"] == 0.25
    assert r["ambiguous_extremes"] == {"cell_days": 1, "flagged_share": 1.0}


def test_undetected_and_out_of_group_faults():
    grid, ys, cells, client = _toy()
    r = evaluate([ys], cells, 2.0, grid, client, bootstrap=0)            # nothing is flagged
    assert r["faults"]["recall"] == 0 and r["faults"]["event_recall"] == 0
    assert "footprint_iou" not in r["faults"] and r["by_kind"]["stuck"]["never_detected"] == 1
    cells[5] = False                                                     # fault 0 now lies outside the group
    r = evaluate([ys], cells, 0.5, grid, client, bootstrap=0)
    assert r["faults"]["events"] == 1 and r["faults"]["cell_days"] == 2


def test_pr_auc_excludes_ambiguous_and_keeps_protected_as_negatives():
    grid, ys, cells, _ = _toy()
    keep = ~ys.bench.extremes.ambiguous
    want = average_precision_score(ys.bench.faults.labels()[keep], ys.score[keep])
    assert pr_auc([ys], cells) == pytest.approx(want)


def test_budget_thresholds_never_exceed_the_budget():
    scores = np.arange(1000, dtype=np.float32)
    thr = budget_thresholds(scores, [10, 1])
    assert (scores > thr[10.0]).sum() == 10 and (scores > thr[1.0]).sum() == 1
    ties = np.zeros(1000, np.float32)
    ties[:3] = 1.0
    assert (ties > budget_thresholds(ties, [10])[10.0]).sum() <= 10


def test_calibration_of_a_perfectly_calibrated_score():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 200_000)
    c = calibration(p, rng.uniform(0, 1, p.size) < p)
    assert c["expected_calibration_error"] < 0.01 and len(c["bins"]) == 10
    assert calibration(np.clip(p * 3, 0, 1), rng.uniform(0, 1, p.size) < p)["expected_calibration_error"] > 0.2


# ---------------------------------------------------------------- neighbours

def test_ring_never_includes_the_hidden_disc(prepared):
    g = prepared.grid
    ring = ring_index(g, 2, 3)
    for i in (0, g.n_land // 2, g.n_land - 1):
        nb = ring[i][ring[i] >= 0]
        d = np.hypot(g.rows[nb] - g.rows[i], g.cols[nb] - g.cols[i])
        assert (d > 2).all() and (d <= 3).all() and i not in nb
    own = ring_index(g, 2, 3, allowed=prepared.split.input_mask(1))       # one client's view
    seen = own[own >= 0]
    assert (prepared.cell_client[seen] == 1).all()
    x = np.arange(g.n_land, dtype=np.float32)[None, :]
    assert np.isnan(gather(x, ring)[0][ring < 0]).all()


def test_trailing_total():
    x = np.arange(1, 7, dtype=np.float32)[:, None]
    assert np.allclose(trailing_total(x, 3)[2:, 0], [6, 9, 12, 15]) and np.isnan(trailing_total(x, 3)[:2]).all()


# ---------------------------------------------------------------- untrained components on the test world

@pytest.fixture(scope="module")
def fns(prepared):
    return score_functions(prepared)


@pytest.fixture(scope="module")
def block(prepared):
    return make_block(prepared, prepared.split.years["val"][1], None, pad=prepared.cfg.components.history_days)


def _with(block, t, cell, value):
    b = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    b.obs[b.pad + t, cell] = value
    return b


def test_each_component_reacts_to_what_it_is_for(prepared, fns, block):
    cell = int(np.argmax((prepared.grid.rows == 12) & (prepared.grid.cols == 8)))
    t = 20                                                    # dry season: neighbours are mostly dry
    spike = _with(block, t, cell, 2000.0)
    for name in ("rules", "neighbour_baseline"):
        base, hit = fns[name](block), fns[name](spike)
        assert hit[t, cell] > base[t, cell] and hit[t, cell] >= np.nanpercentile(hit, 99.9)
    stuck = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    stuck.obs[stuck.pad + 100:stuck.pad + 110, cell] = 7.5
    assert fns["rules"](stuck)[105:110, cell].min() >= 0.8
    drift = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    drift.obs[drift.pad + 150:drift.pad + 240, cell] *= 6.0
    s0, s1 = fns["slow"](block), fns["slow"](drift)
    assert s1[239, cell] > s0[239, cell] + 2 and s1[239, cell] >= np.nanpercentile(s1[239], 99)


def test_untrained_components_are_causal(prepared, fns, block):
    t = 180
    future = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    future.obs[future.pad + t + 1:] = 500.0
    for name in UNTRAINED:
        assert np.allclose(fns[name](block)[:t + 1], fns[name](future)[:t + 1], equal_nan=True), name


def test_neighbour_views_do_not_read_the_hidden_disc(prepared, fns, block):
    """Changing a cell inside the target's hidden disc must not change the target's neighbour-based scores."""
    g = prepared.grid
    target = int(np.argmax((g.rows == 12) & (g.cols == 8)))
    inside = int(np.argmax((g.rows == 13) & (g.cols == 9)))               # distance 1.41 < hidden radius 2
    outside = int(np.argmax((g.rows == 12) & (g.cols == 11)))             # distance 3
    t = 200
    assert fns["neighbour_baseline"](_with(block, t, inside, 900.0))[t, target] == fns["neighbour_baseline"](block)[t, target]
    assert fns["neighbour_baseline"](_with(block, t, outside, 900.0))[t, target] != fns["neighbour_baseline"](block)[t, target]


def test_reach_beyond_the_buffer_is_refused(world, prepared):
    from qc.config import load_config
    from qc.prepare import load_prepared
    wide = load_prepared(load_config(world / "test.yaml", ["components.neighbour_baseline.radius=5"]))
    with pytest.raises(LeakageError, match="reach"):
        score_functions(wide)


def test_untrained_run_end_to_end(prepared, bench):
    results = run_untrained(prepared, ("val", "test"))
    assert set(n for n, _ in results) == set(UNTRAINED)
    for (name, split), res in results.items():
        assert res["label_tier"] == "synthetic faults" and res["benchmark_hash"] == bench["hash"]
        assert set(res["groups"]) == ({"seen"} if split == "val" else {"seen", "unseen"})
        for g in res["groups"].values():
            for b, r in g["by_budget"].items():
                assert 0 <= r["faults"]["recall"] <= 1
                assert r["false_alerts"]["per_1000_clean"] <= 50          # budget is set on clean data; faults nearby add some
    # The test world's rain is independent between cells, so only the rules can beat the 1% base rate here;
    # the neighbour-based scores are checked for correctness above and measured on real data.
    assert results[("rules", "val")]["groups"]["seen"]["pr_auc"] > 0.02
