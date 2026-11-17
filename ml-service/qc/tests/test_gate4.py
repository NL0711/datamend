"""Gate 4: spatial and temporal components and the plain GRU baseline.

Exit checks: the target cell and its hidden disc cannot reach the spatial prediction; the temporal
component sees no same-day or future value. Plus: training runs, resumes identically, never reads a cell
the training run may not read, and the zero-inflated Gamma code matches a reference implementation.
"""

import numpy as np
import pytest
import torch
from scipy import stats as sps

from qc.batches import View, mask_unreadable
from qc.config import load_config
from qc.models import SpatialNet, TemporalGRU, PlainGRU, nll, surprise, zig_params
from qc.prepare import load_prepared
from qc.runs import RunDir
from qc.scoring import make_block
from qc.splits import HELDOUT, LeakageError, TRAIN, BUFFER
from qc.trained import (COMPONENTS, build_model, get_batch, make_view, run_component, score_function, train_block,
                        train_component, load_model, resolve_device)

TINY = ["components.spatial.radius=3", "components.spatial.width=8", "components.spatial.dense=16",
        "components.temporal.hidden=8", "components.temporal.dense=8", "components.plain_gru.hidden=8",
        "train.epochs=1", "train.steps_per_year=3", "train.batch_size=64", "train.infer_batch_size=4096",
        "compute.devices=[cpu]"]


@pytest.fixture(scope="module")
def tcfg(world):
    return load_config(world / "test.yaml", TINY)


@pytest.fixture(scope="module")
def tp(tcfg, prepared):
    return load_prepared(tcfg)


@pytest.fixture(scope="module")
def block(tp):
    return make_block(tp, tp.split.years["val"][1], None, pad=tp.cfg.components.history_days)


def _randomise(model):
    g = torch.Generator().manual_seed(0)
    for prm in model.parameters():
        prm.data = torch.randn(prm.shape, generator=g) * 0.3
    return model.eval()


# ---------------------------------------------------------------- the zero-inflated Gamma

def test_nll_matches_reference_gamma():
    raw = torch.tensor([[0.3, 0.5, -0.2], [-1.0, 1.0, 0.4]])
    mm = torch.tensor([12.0, 0.0])
    unit = torch.tensor([20.0, 20.0])
    logit, k, theta = zig_params(raw)
    p = torch.sigmoid(logit)
    ref_wet = -(np.log(p[0].item()) + sps.gamma.logpdf(12.0 / 20.0, k[0].item(), scale=theta[0].item()))
    ref_dry = -np.log(1 - p[1].item())
    got = nll(raw, mm, unit)
    assert np.allclose(got.numpy(), [ref_wet, ref_dry], atol=1e-4)


def test_surprise_orders_values_sensibly():
    raw = torch.tensor([[0.0, 0.0, 0.0]] * 3)                      # p_wet 0.5, one fixed Gamma
    unit = torch.full((3,), 10.0)
    s = surprise(raw, torch.tensor([0.0, 7.0, 400.0]), unit)
    assert s[2] > s[1] and s[2] > 5                                 # an enormous value is very surprising
    assert torch.isfinite(s).all() and (s >= 0).all()
    confident_dry = surprise(torch.tensor([[-8.0, 0.0, 0.0]]), torch.tensor([30.0]), torch.tensor([10.0]))
    assert confident_dry[0] > 5                                     # rain where none was expected


# ---------------------------------------------------------------- hidden disc

def test_spatial_net_ignores_target_and_hidden_disc():
    net = _randomise(SpatialNet(radius=6, hidden_radius=2.0, width=8, dense=16))
    g = torch.Generator().manual_seed(1)
    patch, valid, static = torch.rand(5, 13, 13, generator=g), torch.ones(5, 13, 13), torch.rand(5, 4, generator=g)
    base = net(patch, valid, static)
    keep = net.keep[0, 0].bool()
    p2, v2 = patch.clone(), valid.clone()
    p2[:, ~keep] = torch.rand(5, int((~keep).sum()), generator=g) * 9      # target and every cell inside radius 2
    v2[:, ~keep] = 0.0
    assert torch.equal(net(p2, v2, static), base)
    p3 = patch.clone()
    p3[:, 0, 0] += 5.0                                                     # a corner cell, far outside the disc
    assert not torch.equal(net(p3, valid, static), base)
    p4 = patch.clone()
    p4[:, 6, 8] += 5.0                                                     # distance 2: still hidden (<= radius)
    assert torch.equal(net(p4, valid, static), base)
    p5 = patch.clone()
    p5[:, 6, 9] += 5.0                                                     # distance 3: visible
    assert not torch.equal(net(p5, valid, static), base)


def test_spatial_prediction_does_not_depend_on_the_target_value(tp, block):
    """End to end through the view: changing the target cell-day or a cell in its disc leaves the output unchanged."""
    g = tp.grid
    target = int(np.argmax((g.rows == 12) & (g.cols == 12)))
    inside = int(np.argmax((g.rows == 13) & (g.cols == 13)))
    outside = int(np.argmax((g.rows == 12) & (g.cols == 15)))              # distance 3 (radius is 3 in the test world)
    net = _randomise(build_model(tp.cfg, "spatial"))
    t = np.array([150])
    cell = np.array([target])

    def out(modified=None, value=800.0):
        obs = block.obs.copy()
        if modified is not None:
            obs[block.pad + 150, modified] = value
        view = make_view(tp, "spatial", obs, block.doy, block.pad)
        b = get_batch(view, "spatial", tp.cfg, t, cell)
        return net(torch.from_numpy(b["patch"]), torch.from_numpy(b["valid"]), torch.from_numpy(b["static"]))

    base = out()
    assert torch.equal(out(target), base) and torch.equal(out(inside), base)
    assert not torch.equal(out(outside), base)


def test_spatial_reach_beyond_the_buffer_is_refused(world, prepared):
    cfg = load_config(world / "test.yaml", TINY + ["components.spatial.radius=4"])      # buffer is 3 cells
    p = load_prepared(cfg)
    with pytest.raises(LeakageError, match="reach"):
        train_component(p, "spatial", 0, RunDir(p.cfg.paths.out, "x"))


# ---------------------------------------------------------------- causality

@pytest.mark.parametrize("component", ["temporal", "plain_gru"])
def test_temporal_inputs_exclude_the_scored_day_and_the_future(tp, block, component):
    cell, t = np.array([100, 100]), np.array([60, 61])
    net = _randomise(build_model(tp.cfg, component))

    def out(obs):
        view = make_view(tp, component, obs, block.doy, block.pad)
        b = get_batch(view, component, tp.cfg, t, cell)
        return net(torch.from_numpy(b["hist"]), torch.from_numpy(b["valid"]), torch.from_numpy(b["static"])).detach()

    base = out(block.obs)
    future = block.obs.copy()
    future[block.pad + 60:, 100] = 999.0                    # the scored day (60) and everything after it
    assert torch.equal(out(future)[0], base[0])             # day 60 sees none of it
    assert not torch.equal(out(future)[1], base[1])         # day 61 does see day 60
    past = block.obs.copy()
    past[block.pad + 59, 100] += 50.0
    assert not torch.equal(out(past)[0], base[0])


@pytest.mark.parametrize("component", COMPONENTS)
def test_scores_are_causal(tp, block, component):
    model = _randomise(build_model(tp.cfg, component))
    fn = score_function(tp, component, model, torch.device("cpu"), batch_size=20000)
    t = 90
    future = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    future.obs[future.pad + t + 1:] = 500.0
    a, b = fn(block), fn(future)
    assert np.allclose(a[:t + 1], b[:t + 1], equal_nan=True)


def test_spatial_scores_use_only_the_same_day(tp, block):
    model = _randomise(build_model(tp.cfg, "spatial"))
    fn = score_function(tp, "spatial", model, torch.device("cpu"), batch_size=20000)
    other = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    other.obs[other.pad:other.pad + 100] = 123.0                            # change days 0-99 only
    assert np.allclose(fn(block)[100:], fn(other)[100:], equal_nan=True)


# ---------------------------------------------------------------- what training may read

def test_training_inputs_never_contain_unreadable_cells(tp):
    obs, doy = train_block(tp, tp.split.years["train"][1], int(tp.cfg.components.history_days))
    masked = mask_unreadable(obs, tp.split.input_mask(), tp.grid)
    held = tp.cell_role == HELDOUT
    assert held.any() and np.isnan(masked[:, held]).all()
    assert np.isfinite(masked[:, tp.cell_role == TRAIN]).any()
    targets = np.nonzero(tp.grid.to_series(tp.split.target_mask()))[0]
    assert set(tp.cell_role[targets]) == {TRAIN}                            # no buffer or held-out target


def test_first_training_year_gets_no_history_from_the_stress_years(tp):
    first = tp.split.years["train"][0]
    obs, _ = train_block(tp, first, int(tp.cfg.components.history_days))
    assert np.isnan(obs[:int(tp.cfg.components.history_days)]).all()


# ---------------------------------------------------------------- training, resume, scoring

@pytest.mark.parametrize("component", COMPONENTS)
def test_tiny_run_trains_saves_and_scores(world, bench, component):
    cfg = load_config(world / "test.yaml", TINY + ["name=tiny_" + component])
    p = load_prepared(cfg)
    out = run_component(p, component, 0, ("val",), max_years=2)
    assert out["train"].status == "done" and out["train"].checkpoint.is_file()
    m = out["metrics"]["val"]
    assert m["component"] == f"{component}_s0" and m["label_tier"] == "synthetic faults"
    from qc.evaluate import score_store
    sc = score_store(p).load(f"{component}_s0", "val", p.split.years["val"][0])
    assert sc.shape[1] == p.grid.n_land and np.isfinite(sc).any() and np.nanmin(sc) >= 0
    for r in m["groups"]["seen"]["by_budget"].values():
        assert 0 <= r["faults"]["recall"] <= 1


def test_resume_gives_the_same_weights_as_an_uninterrupted_run(world):
    def run(name, cap):
        cfg = load_config(world / "test.yaml", TINY + ["name=" + name, "train.epochs=2"])
        p = load_prepared(cfg)
        r = RunDir(__import__("qc.paths", fromlist=["x"]).out_dir(cfg) / name, "temporal_s0")
        r.start(cfg, 0, {})
        return p, r, train_component(p, "temporal", 0, r, max_years=2, time_cap_hours=cap)

    _, _, straight = run("resume_a", None)
    p, r, first = run("resume_b", 1e-9)                    # stops after the first year-step
    assert first.status == "stopped" and first.years_done == 1
    second = train_component(p, "temporal", 0, r, max_years=2)
    assert second.status == "done"
    a = torch.load(straight.checkpoint, weights_only=False)["model"]
    b = torch.load(second.checkpoint, weights_only=False)["model"]
    assert all(torch.equal(a[k], b[k]) for k in a)


def test_training_is_seeded(world):
    def final(name, seed):
        cfg = load_config(world / "test.yaml", TINY + ["name=" + name])
        p = load_prepared(cfg)
        r = RunDir(__import__("qc.paths", fromlist=["x"]).out_dir(cfg) / name, f"plain_gru_s{seed}")
        r.start(cfg, seed, {})
        return torch.load(train_component(p, "plain_gru", seed, r, max_years=1).checkpoint, weights_only=False)["model"]

    a, b, c = final("seed_a", 0), final("seed_b", 0), final("seed_c", 1)
    assert all(torch.equal(a[k], b[k]) for k in a)
    assert not all(torch.equal(a[k], c[k]) for k in a)
