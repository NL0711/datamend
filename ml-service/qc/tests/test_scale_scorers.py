"""qc.scale_scorers on a small generated spatial world (no RF25 needed)."""

import numpy as np
import pytest

from qc import resolution as R
from qc import scale_scorers as S
from qc.grid import Grid
from qc.splits import Split

H, W = 14, 16
YEARS = list(range(1980, 2000))
TRAIN = YEARS[:14]
VAL = YEARS[14:]


@pytest.fixture(scope="module")
def world():
    lat = np.linspace(8, 30, H)
    lon = np.linspace(70, 90, W)
    land = np.ones((H, W), bool)
    land[:, :2] = False
    grid = Grid.from_land(lat, lon, land)
    n = grid.n_land
    rng = np.random.default_rng(0)
    base = 80 + 40 * np.sin(grid.rows / 3.0) + 30 * np.cos(grid.cols / 4.0)      # smooth spatial pattern, mm per month
    periods = {}
    for y in YEARS:
        yr = rng.normal(0, 0.25)                                                # a wet or dry year shared by all cells
        field = np.exp(yr + 0.1 * rng.normal(size=n))
        tot = np.zeros((12, n), np.float32)
        for m in range(12):
            season = 0.3 + 1.4 * np.exp(-((m - 6.5) / 1.8) ** 2)
            tot[m] = rng.gamma(8.0, base * season * field / 8.0)
        periods[y] = R.Periods("monthly", y, tot, (tot > 1).astype(np.float32) * 10, tot / 8, np.full(12, 30, np.int32), np.ones((12, n), bool))
    client = np.where(grid.cols < 8, 1, 2)
    split = Split(np.zeros((H, W), np.int8), np.zeros((H, W), np.int8), [], 0,
                  {"train": TRAIN, "val": VAL, "test": [], "fusion_fit": VAL, "threshold": VAL, "stress": []})
    stats = R.fit_scale_stats({y: periods[y] for y in TRAIN}, TRAIN, split, client, "monthly")
    ctx = S.make_context(grid, client, stats, hidden_radius=2.0, near=4.0, far=7.0)
    return grid, periods, ctx, stats


def _train(periods):
    return {y: periods[y] for y in TRAIN}


def test_context_never_lists_cells_inside_the_hidden_disc(world):
    grid, _, ctx, _ = world
    d_near = np.hypot(grid.rows[ctx.near_idx] - grid.rows[:, None], grid.cols[ctx.near_idx] - grid.cols[:, None])
    ok = ctx.near_idx >= 0
    assert ok.any() and (d_near[ok] > 2.0).all() and (d_near[ok] <= 4.0).all()
    assert (ctx.near_w[~ok] == 0).all()
    with pytest.raises(ValueError):
        S.make_context(grid, ctx.cell_client, ctx.stats, hidden_radius=4.0, near=3.0, far=7.0)


def test_target_value_is_not_an_input(world):
    grid, periods, ctx, _ = world
    base = periods[VAL[0]]
    X0, _, _ = S.neighbour_features(ctx, base, None)
    mod = base.copy()
    cell, month = 40, 7
    mod.total[month, cell] *= 50.0                                  # change the target's own value in ONE period
    X1, _, _ = S.neighbour_features(ctx, mod, None)
    assert np.allclose(X0[month, cell], X1[month, cell], equal_nan=True)     # that period's own features did not move
    assert not np.allclose(X0[month + 1, cell], X1[month + 1, cell], equal_nan=True)   # the next period may read it (own earlier period)
    far = np.hypot(grid.rows - grid.rows[cell], grid.cols - grid.cols[cell]) > 7.5
    assert np.allclose(X0[:, far], X1[:, far], equal_nan=True)               # cells beyond its reach are untouched
    within_hidden = (np.hypot(grid.rows - grid.rows[cell], grid.cols - grid.cols[cell]) <= 2.0)
    within_hidden[cell] = False
    assert np.allclose(X0[month, within_hidden][:, :2], X1[month, within_hidden][:, :2], equal_nan=True)   # nor the cells inside its hidden disc


def test_read_ok_hides_cells_while_fitting(world):
    _, periods, ctx, _ = world
    hide = np.zeros(ctx.near_idx.shape[0], bool)
    hide[:30] = True
    X, _, n_near = S.neighbour_features(ctx, periods[VAL[0]], None, read_ok=~hide)
    Xa, _, n_all = S.neighbour_features(ctx, periods[VAL[0]], None)
    assert (n_near <= n_all).all() and (n_near < n_all).any()


def test_lagged_totals(world):
    _, periods, _, _ = world
    p, prev = periods[VAL[0]], periods[TRAIN[-1]]
    lag = S.lagged_totals(p, prev)
    assert np.array_equal(lag[1:], p.total[:-1]) and np.array_equal(lag[0], prev.total[-1])
    assert np.isnan(S.lagged_totals(p, None)[0]).all()


def _inject(p, cell, factor, month=7):
    q = p.copy()
    q.total[month, cell] = p.total[month, cell] * factor
    return q


@pytest.mark.parametrize("name", ["gamma_zero", "loo_median"])
def test_baselines_flag_a_scaled_period(world, name):
    grid, periods, ctx, _ = world
    sc = S.make_scorer(name).fit(_train(periods), ctx, seed=0)
    clean = periods[VAL[0]]
    s_clean = sc.score(clean, periods[TRAIN[-1]], ctx)
    assert s_clean.shape == clean.total.shape and np.isfinite(s_clean).mean() > 0.9
    cell = 60
    bad = sc.score(_inject(clean, cell, 6.0), periods[TRAIN[-1]], ctx)
    assert bad[7, cell] > np.nanpercentile(s_clean, 99)
    others = np.delete(bad[7], cell)
    assert np.nanmedian(others) < bad[7, cell]


def test_gamma_zero_sees_a_dropout(world):
    _, periods, ctx, _ = world
    sc = S.GammaZeroScorer().fit(_train(periods), ctx)
    clean = periods[VAL[0]]
    drop = clean.copy()
    drop.total[7, 50] = 0.0
    assert sc.score(drop, None, ctx)[7, 50] > np.nanpercentile(sc.score(clean, None, ctx), 99)


def test_loo_residual_does_not_smear_far_into_neighbours(world):
    grid, periods, ctx, _ = world
    sc = S.LooResidualScorer().fit(_train(periods), ctx)
    clean = periods[VAL[0]]
    cell = 90
    s0 = sc.score(clean, None, ctx)
    s1 = sc.score(_inject(clean, cell, 8.0), None, ctx)
    near_d = np.hypot(grid.rows - grid.rows[cell], grid.cols - grid.cols[cell])
    nbrs = (near_d > 2) & (near_d <= 4)
    rise_cell = s1[7, cell] - s0[7, cell]
    rise_nbr = np.nanmax(np.abs(s1[7, nbrs] - s0[7, nbrs]))          # change in a neighbour's score caused by the bad cell
    assert rise_cell > 2.0 and rise_nbr < 0.3 * rise_cell


@pytest.mark.parametrize("name", ["gbm_neighbour", "mlp_neighbour"])
def test_regression_candidates_fit_score_and_flag(world, name):
    _, periods, ctx, _ = world
    sc = S.make_scorer(name).fit(_train(periods), ctx, seed=1)
    clean = periods[VAL[0]]
    s_clean = sc.score(clean, periods[TRAIN[-1]], ctx)
    assert s_clean.shape == clean.total.shape and np.isfinite(s_clean).any()
    bad = sc.score(_inject(clean, 70, 8.0), periods[TRAIN[-1]], ctx)
    assert bad[7, 70] > np.nanmedian(s_clean) * 3
    again = S.make_scorer(name).fit(_train(periods), ctx, seed=1).score(clean, periods[TRAIN[-1]], ctx)
    assert np.allclose(s_clean, again, equal_nan=True)              # deterministic for a fixed seed


def test_regression_candidate_refuses_too_little_data(world):
    grid, periods, ctx, _ = world
    tiny = S.make_context(grid, ctx.cell_client, ctx.stats, target_ok=np.arange(grid.n_land) < 3)
    with pytest.raises(ValueError, match="usable training rows"):
        S.GbmNeighbourScorer().fit({TRAIN[0]: periods[TRAIN[0]]}, tiny)


def test_invalid_periods_score_nan(world):
    _, periods, ctx, _ = world
    p = periods[VAL[0]].copy()
    p.valid[3, :10] = False
    p.total[3, :10] = np.nan
    for name in S.CANDIDATES:
        sc = S.make_scorer(name).fit(_train(periods), ctx)
        assert np.isnan(sc.score(p, None, ctx)[3, :10]).all()


def test_unknown_scorer_name():
    with pytest.raises(KeyError):
        S.make_scorer("nope")
    assert sorted(S.CANDIDATES) == ["gamma_zero", "gbm_neighbour", "loo_median", "mlp_neighbour"]
    assert [S.CANDIDATES[k].complexity for k in ("gamma_zero", "loo_median", "gbm_neighbour", "mlp_neighbour")] == [0, 1, 2, 3]
