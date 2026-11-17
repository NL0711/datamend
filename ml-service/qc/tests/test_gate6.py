"""Gate 6: federated variants. Masking, aggregation, matched gradient steps, resume, one benchmark hash for every run."""

import numpy as np
import pytest
import torch

import qc.federated as fed
from qc.config import load_config
from qc.faults import FaultGenerator
from qc.federated import (ClientModels, average_states, federated_score_function, is_head, load_client_models, round_count,
                          run_federated, train_federated, _train_local)
from qc.fusion import FusionFit, _logit_fit, fit_fusion_federated
from qc.grid import ContractError
from qc.prepare import load_prepared
from qc.runs import RunDir
from qc.scoring import make_block
from qc.splits import HELDOUT, TRAIN
from qc.tests.test_gate4 import TINY
from qc.trained import resolve_device

FED = TINY + ["train.epochs=2", "federated.finetune_steps=3"]


def fcfg(world, name, extra=()):
    return load_config(world / "test.yaml", FED + [f"name={name}", *extra])


def new_run(p, name, comp, variant, seed=0):
    return RunDir(fed.paths.out_dir(p.cfg) / name, fed.run_label(variant, comp, seed, float(p.cfg.federated.prox_mu)))


# ---------------------------------------------------------------- aggregation

def test_average_states_is_a_weighted_mean():
    a = {"w": torch.tensor([0.0, 10.0]), "head.b": torch.tensor([1.0])}
    b = {"w": torch.tensor([4.0, 2.0]), "head.b": torch.tensor([3.0])}
    out = average_states([a, b], [1, 3])
    assert torch.allclose(out["w"], torch.tensor([3.0, 4.0])) and torch.allclose(out["head.b"], torch.tensor([2.5]))
    only_head = average_states([a, b], [1, 1], is_head)
    assert set(only_head) == {"head.b"} and torch.allclose(only_head["head.b"], torch.tensor([2.0]))


def test_heads_are_the_final_layer_of_both_networks(prepared):
    from qc.trained import build_model
    for comp in ("spatial", "temporal"):
        m = build_model(prepared.cfg, comp)
        heads = [n for n, _ in m.named_parameters() if is_head(n)]
        assert heads == ["head.weight", "head.bias"]


def test_round_count_matches_centralized_steps(world, prepared):
    p = load_prepared(fcfg(world, "rc"))
    n_clients = len(p.split.train_clients)
    rounds = round_count(p, max_years=3)
    assert rounds == round(2 * 3 / n_clients)
    assert rounds * n_clients == 2 * 3                            # one local epoch per client per round: same year-steps


# ---------------------------------------------------------------- masking

def test_clients_train_only_on_their_own_cells(world, prepared, bench, monkeypatch):
    p = load_prepared(fcfg(world, "mask"))
    seen = []
    real = fed.year_steps

    def spy(p_, comp, model, opt, scaler, amp, device, year, rng, steps, bs, readable, targets, gen, pad, *a):
        seen.append((readable.copy(), targets.copy()))
        return real(p_, comp, model, opt, scaler, amp, device, year, rng, steps, bs, readable, targets, gen, pad, *a)

    monkeypatch.setattr(fed, "year_steps", spy)
    train_federated(p, "temporal", "fedpers", 0, new_run(p, "mask", "temporal", "fedpers"), max_years=3)
    assert len(seen) == round_count(p, 3) * len(p.split.train_clients)
    for readable, targets in seen:
        cells = np.unique(p.split.client_map[readable])
        assert len(cells) == 1                                      # exactly one client is readable
        c = int(cells[0])
        assert c in p.split.train_clients and not (readable & (p.split.roles == HELDOUT)).any()
        assert set(p.cell_client[targets]) == {c} and set(p.cell_role[targets]) == {TRAIN}


def test_other_clients_cells_are_nan_in_a_clients_inputs(world, prepared):
    from qc.batches import mask_unreadable
    from qc.trained import train_block
    p = load_prepared(fcfg(world, "mask2"))
    obs, _ = train_block(p, p.split.years["train"][1], int(p.cfg.components.history_days))
    c = p.split.train_clients[0]
    m = mask_unreadable(obs, p.split.input_mask(c), p.grid)
    assert np.isnan(m[:, p.cell_client != c]).all() and np.isfinite(m[:, p.cell_client == c]).any()


# ---------------------------------------------------------------- variants

def final_states(p, comp, variant, name, **kw):
    r = train_federated(p, comp, variant, 0, new_run(p, name, comp, variant), max_years=3, **kw)
    assert r.status == "done"
    return r, torch.load(r.checkpoint, weights_only=False)["final"]


def same(a, b):
    return all(torch.equal(a[k], b[k]) for k in a)


def test_fedpers_shares_the_body_and_keeps_heads_local(world, bench):
    p = load_prepared(fcfg(world, "v_pers"))
    r, final = final_states(p, "temporal", "fedpers", "v_pers")
    c1, c2 = p.split.train_clients
    body = lambda s: {k: v for k, v in s.items() if not is_head(k)}
    head = lambda s: {k: v for k, v in s.items() if is_head(k)}
    assert same(body(final["clients"][c1]), body(final["clients"][c2]))
    assert not same(head(final["clients"][c1]), head(final["clients"][c2]))
    w = [float(fed._client_targets(p, c).size) for c in (c1, c2)]
    mean_head = average_states([head(final["clients"][c1]), head(final["clients"][c2])], w)
    assert same(head(final["default"]), mean_head) and same(body(final["default"]), body(final["clients"][c1]))
    assert r.gradient_steps == r.centralized_steps              # matched total gradient steps


def test_fedavg_gives_everyone_one_model_and_fedft_personalizes(world, bench):
    p = load_prepared(fcfg(world, "v_avg"))
    _, avg = final_states(p, "temporal", "fedavg", "v_avg")
    c1, c2 = p.split.train_clients
    assert same(avg["clients"][c1], avg["clients"][c2]) and same(avg["default"], avg["clients"][c1])
    r, ft = final_states(p, "temporal", "fedft", "v_ft")
    assert not same(ft["clients"][c1], ft["clients"][c2])
    assert same(ft["default"], avg["default"])                  # unseen clients use the un-tuned global model
    assert r.gradient_steps == r.centralized_steps + 3 * len(p.split.train_clients)


def test_local_only_never_aggregates_and_has_no_unseen_model(world, bench):
    p = load_prepared(fcfg(world, "v_loc"))
    _, loc = final_states(p, "temporal", "local", "v_loc")
    c1, c2 = p.split.train_clients
    assert loc["default"] is None
    assert not same(loc["clients"][c1], loc["clients"][c2])
    # the same client trained alone is independent of what the other client holds: its result equals a rerun
    p2 = load_prepared(fcfg(world, "v_loc2"))
    _, again = final_states(p2, "temporal", "local", "v_loc2")
    assert same(loc["clients"][c1], again["clients"][c1])


def test_fedprox_keeps_local_models_closer_to_the_global_one(world, bench):
    p = load_prepared(fcfg(world, "prox"))
    from qc.trained import build_model
    torch.manual_seed(0)
    start = {k: v.clone() for k, v in build_model(p.cfg, "temporal").state_dict().items()}
    gen, dev = FaultGenerator(p.grid), resolve_device(p.cfg)
    c = p.split.train_clients[0]
    year = p.split.years["train"][1]

    def drift(mu):
        end, _ = _train_local(p, "temporal", start, c, year, np.random.default_rng(1), 6, dev, gen, mu)
        return float(sum(((end[k] - start[k]) ** 2).sum() for k in start if start[k].dtype.is_floating_point))

    assert drift(50.0) < drift(0.0)


def test_unseen_clients_get_scores_except_in_local_only(world, bench):
    p = load_prepared(fcfg(world, "unseen"))
    held = p.cell_role == HELDOUT
    blk = make_block(p, p.split.years["val"][0], None, pad=p.cfg.components.history_days)
    dev = resolve_device(p.cfg)
    for variant, expect in (("fedpers", True), ("fedavg", True), ("local", False)):
        r = train_federated(p, "temporal", variant, 0, new_run(p, "unseen", "temporal", variant), max_years=2)
        fn = federated_score_function(p, "temporal", load_client_models(p, "temporal", r.checkpoint, dev), dev)
        s = fn(blk)
        assert np.isfinite(s[:, ~held]).any()
        assert bool(np.isfinite(s[:, held]).any()) is expect, variant


# ---------------------------------------------------------------- resume, benchmark hash, end to end

def test_resume_gives_the_same_models(world, bench):
    def run(name, cap):
        p = load_prepared(fcfg(world, name))
        return p, new_run(p, name, "temporal", "fedpers"), cap

    p, r1, _ = run("res_a", None)
    r1.start(p.cfg, 0, {})
    full = train_federated(p, "temporal", "fedpers", 0, r1, max_years=4)
    p2, r2, _ = run("res_b", 1e-9)
    r2.start(p2.cfg, 0, {})
    first = train_federated(p2, "temporal", "fedpers", 0, r2, max_years=4, time_cap_hours=1e-9)
    assert first.status == "stopped" and first.rounds_done == 1
    second = train_federated(p2, "temporal", "fedpers", 0, r2, max_years=4)
    a, b = torch.load(full.checkpoint, weights_only=False)["final"], torch.load(second.checkpoint, weights_only=False)["final"]
    assert all(same(a["clients"][c], b["clients"][c]) for c in a["clients"])


def test_every_variant_scores_the_same_benchmark(world, bench):
    hashes = set()
    for variant in fed.VARIANTS:
        p = load_prepared(fcfg(world, "e2e"))
        out = run_federated(p, "spatial" if variant == "fedpers" else "temporal", variant, 0, ("val",), max_years=2)
        m = out["metrics"]["val"]
        hashes.add(m["benchmark_hash"])
        assert m["label_tier"] == "synthetic faults" and m["variant"] == variant
        assert m["unseen_clients"] == ("not available" if variant == "local" else "scored")
        assert m["gradient_steps"] >= m["centralized_gradient_steps"] - 1
        for r in m["groups"]["seen"]["by_budget"].values():
            assert 0 <= r["faults"]["recall"] <= 1
    assert hashes == {bench["hash"]}


def test_a_different_benchmark_hash_stops_before_training(world, bench):
    p = load_prepared(fcfg(world, "wrong", ["benchmark.expected_hash=deadbeefdeadbeef"]))
    with pytest.raises(ContractError, match="refusing"):
        run_federated(p, "temporal", "fedavg", 0, ("val",), max_years=2)
    run_dir = fed.paths.out_dir(p.cfg) / "wrong"
    assert not list(run_dir.glob("**/*.pt"))


# ---------------------------------------------------------------- federated fusion

def test_federated_logistic_matches_the_pooled_fit(world, prepared, monkeypatch):
    p = load_prepared(fcfg(world, "fusion_fed"))
    rng = np.random.default_rng(0)
    n = 6000
    x = rng.normal(0.5, 1.0, (n, 4)).astype(np.float32)
    logit = -3.0 + 1.5 * x[:, 0] + 0.8 * x[:, 3]
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(np.int8)
    client = rng.choice(p.split.train_clients, n)
    w = np.ones(n, np.float32)
    monkeypatch.setattr("qc.fusion.fusion_rows", lambda *a, **k: (x, y, w, client))
    fit = FusionFit(0, list("abcd"), np.zeros(4), np.ones(4), [1], n, int(y.sum()), {}, None, {}, [])
    got = fit_fusion_federated(p, fit, store=object(), rounds=30)
    mu, sd = x.mean(0), x.std(0) + 1e-6
    ref = _logit_fit((x - mu) / sd, y, w, float(p.cfg.fusion.C))
    assert np.allclose(got["mu"], mu, atol=1e-5) and np.allclose(got["sd"], sd, atol=1e-5)    # sums aggregate to the pooled statistics
    assert np.allclose(got["coef"], ref["coef"], atol=0.05) and abs(got["intercept"] - ref["intercept"]) < 0.05
