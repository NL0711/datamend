"""Gate 6: federated training of the spatial and temporal components, simulated sequentially on one machine.

This is a simulation of the training procedure. It makes NO privacy claim: all data sits on one machine.

Clients are the training clients of the split (six of eight). In a client's local training every other client's
cells are NaN in every input (``Split.input_mask(client)``) and its targets are its own cells of role ``train``.
Held-out clients take no part in training. Normalization is per client (``stats.scale``), fitted on that client's
training years only, so it is local in every variant.

Variants
  fedpers  main: the *body* of the network is averaged across clients every round; each client keeps its own
           *head* (the final linear layer, ``head.*``). Unseen clients get the body and the weighted mean of the
           clients' heads.
  fedavg   every parameter is averaged every round; one global model for everyone, unseen clients included.
  fedft    fedavg, then each training client fine-tunes the global model on its own cells for
           ``federated.finetune_steps`` steps. Unseen clients use the global model.
  local    no communication: each client trains alone. Unseen clients have no model (NOT AVAILABLE: their cells
           are left unscored rather than given another client's model).
Any variant with ``federated.prox_mu > 0`` adds the FedProx term to every local loss (switch, off by default).

Schedule. One round = every training client, in a seeded order, does one local epoch (``steps_per_year`` gradient
steps on one training year drawn at random), then the server aggregates. Rounds are set so the total number of
gradient steps equals the centralized run: ``epochs * years`` year-steps spread over the clients.
Everything is seeded from ``(seed, round, client)``; a checkpoint is written after every round.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np
import torch

from qc import paths
from qc.benchmark import check_benchmark
from qc.evaluate import compute_scores, evaluate_component, score_store
from qc.faults import FaultGenerator
from qc.prepare import Prepared
from qc.runs import RunDir, write_json
from qc.scoring import Block
from qc.splits import audit_split
from qc.trained import build_model, reach_cells, resolve_device, score_function, year_steps

log = logging.getLogger(__name__)
VARIANTS = ("fedpers", "fedavg", "fedft", "local")
COMPONENTS = ("spatial", "temporal")


def is_head(name: str) -> bool:
    return name.startswith("head.")


def label(variant: str, prox_mu: float) -> str:
    return variant + ("_prox" if prox_mu > 0 else "")


def run_label(variant: str, component: str, seed: int, prox_mu: float = 0.0) -> str:
    return f"{label(variant, prox_mu)}_{component}_s{seed}"


def average_states(states: Sequence[Dict[str, torch.Tensor]], weights: Sequence[float],
                   keys: Optional[Callable[[str], bool]] = None) -> Dict[str, torch.Tensor]:
    """Weighted mean of state dicts (weights are normalized). ``keys`` selects which entries are averaged."""
    w = np.asarray(weights, np.float64)
    w = w / w.sum()
    out = {}
    for k in states[0]:
        if keys is not None and not keys(k):
            continue
        out[k] = sum(float(wi) * s[k].detach().float() for wi, s in zip(w, states)).to(states[0][k].dtype)
    return out


def round_count(p: Prepared, max_years: Optional[int] = None) -> int:
    cfg = p.cfg
    if cfg.federated.rounds:
        return int(cfg.federated.rounds)
    n_years = len(p.split.years["train"][:max_years] if max_years else p.split.years["train"])
    return max(1, int(round(int(cfg.train.epochs) * n_years / len(p.split.train_clients))))


@dataclass
class ClientModels:
    """What scoring needs: one model per training client, and the model unseen clients use (None = unavailable)."""
    by_client: Dict[int, torch.nn.Module]
    default: Optional[torch.nn.Module]


@dataclass
class FedResult:
    name: str
    status: str                    # done | stopped
    rounds_done: int
    rounds_total: int
    gradient_steps: int
    centralized_steps: int
    seconds: float
    checkpoint: Path
    last_loss: Optional[float] = None


def _client_targets(p: Prepared, client: int) -> np.ndarray:
    return np.nonzero(p.grid.to_series(p.split.target_mask(client)))[0]


def _train_local(p, component, state, client, year, rng, steps, device, gen, prox_mu, lr_scale=1.0):
    """Train a copy of ``state`` on one client's cells for ``steps`` steps; returns (state, mean loss)."""
    cfg, tr = p.cfg, p.cfg.train
    model = build_model(cfg, component).to(device)
    model.load_state_dict(state)
    model.train()
    ref = {n: q.detach().clone() for n, q in model.named_parameters()} if prox_mu > 0 else None
    opt = torch.optim.AdamW(model.parameters(), lr=float(tr.lr) * lr_scale, weight_decay=float(tr.weight_decay))
    amp = bool(cfg.compute.amp) and device.type == "cuda"
    bs = int(tr.batch_size or cfg.compute.batch_size)
    losses = year_steps(p, component, model, opt, torch.amp.GradScaler(enabled=amp), amp, device, year, rng, steps, bs,
                        p.split.input_mask(client), _client_targets(p, client), gen, int(cfg.components.history_days),
                        ref, prox_mu)
    return {k: v.detach().clone() for k, v in model.state_dict().items()}, (float(np.mean(losses)) if losses else None)


def train_federated(p: Prepared, component: str, variant: str, seed: int, run: RunDir, max_years: Optional[int] = None,
                    time_cap_hours: Optional[float] = None) -> FedResult:
    cfg, tr, fc = p.cfg, p.cfg.train, p.cfg.federated
    if component not in COMPONENTS:
        raise ValueError(f"federated training covers {COMPONENTS}, not {component!r}")
    if variant not in VARIANTS:
        raise ValueError(f"unknown federated variant {variant!r}; choose from {VARIANTS}")
    audit_split(p.split, reach_cells=reach_cells(cfg, component))
    prox = float(fc.prox_mu)
    name = run_label(variant, component, seed, prox)
    ck_last, ck_final = run.path / "checkpoints" / f"{name}_last.pt", run.path / "checkpoints" / f"{name}_final.pt"
    device = resolve_device(cfg)
    clients = list(p.split.train_clients)
    for c in clients:
        if _client_targets(p, c).size == 0:
            raise RuntimeError(f"client {c} has no training target cells")
    years = list(p.split.years["train"])
    if max_years:
        years = years[:int(max_years)]
    steps = int(tr.steps_per_year)
    rounds = round_count(p, max_years)
    central = int(tr.epochs) * len(years) * steps
    if ck_final.is_file():
        ck = torch.load(ck_final, map_location="cpu", weights_only=False)
        return FedResult(name, "done", rounds, rounds, ck["gradient_steps"], central, 0.0, ck_final)

    torch.manual_seed(seed)
    init = {k: v.clone() for k, v in build_model(cfg, component).state_dict().items()}
    weights = {c: float(_client_targets(p, c).size) for c in clients}
    state = {"round": 0, "global": init, "clients": {c: {k: v.clone() for k, v in init.items()} for c in clients},
             "log": [], "steps": 0}
    if ck_last.is_file():
        ck = torch.load(ck_last, map_location="cpu", weights_only=False)
        if ck["config_digest"] != cfg.digest() or ck["seed"] != seed or ck["rounds"] != rounds:
            raise RuntimeError(f"{ck_last} was made under a different config, seed or run length; use a new run name or delete it")
        state = ck["state"]
        log.info("%s: resuming at round %d of %d", name, state["round"], rounds)

    gen = FaultGenerator(p.grid)
    start = time.time()
    cap = time_cap_hours if time_cap_hours is not None else cfg.compute.max_hours_per_run
    last = None
    while state["round"] < rounds:
        r = state["round"]
        order = [clients[i] for i in np.random.default_rng([seed, r]).permutation(len(clients))]
        trained: Dict[int, Dict[str, torch.Tensor]] = {}
        losses = []
        for c in order:
            rng = np.random.default_rng([seed, r, c])
            year = years[int(rng.integers(len(years)))]
            if variant == "fedpers":
                start_state = {**state["global"], **{k: v for k, v in state["clients"][c].items() if is_head(k)}}
            elif variant == "local":
                start_state = state["clients"][c]
            else:
                start_state = state["global"]
            trained[c], loss = _train_local(p, component, start_state, c, year, rng, steps, device, gen, prox)
            state["steps"] += steps
            if loss is not None:
                losses.append(loss)
        w = [weights[c] for c in clients]
        if variant == "fedpers":
            state["global"] = {**state["global"], **average_states([trained[c] for c in clients], w, lambda k: not is_head(k))}
            for c in clients:
                state["clients"][c] = trained[c]
        elif variant == "local":
            for c in clients:
                state["clients"][c] = trained[c]
        else:
            state["global"] = average_states([trained[c] for c in clients], w)
        state["round"] = r + 1
        last = float(np.mean(losses)) if losses else None
        state["log"].append({"round": r, "loss": last, "order": order})
        log.info("%s: round %d/%d loss %s", name, r + 1, rounds, "n/a" if last is None else f"{last:.4f}")
        torch.save({"state": state, "config_digest": cfg.digest(), "seed": seed, "rounds": rounds}, ck_last.with_suffix(".tmp"))
        ck_last.with_suffix(".tmp").replace(ck_last)
        if cap and (time.time() - start) / 3600.0 >= float(cap) and state["round"] < rounds:
            log.warning("%s: stopped at the time cap; run again to resume", name)
            return FedResult(name, "stopped", state["round"], rounds, state["steps"], central, time.time() - start, ck_last, last)

    # ---- final per-client models and the model unseen clients use
    ft_steps = int(fc.finetune_steps)
    final: Dict = {"clients": {}, "default": None}
    if variant == "fedpers":
        head_mean = average_states([state["clients"][c] for c in clients], [weights[c] for c in clients], is_head)
        for c in clients:
            final["clients"][c] = {**state["global"], **{k: v for k, v in state["clients"][c].items() if is_head(k)}}
        final["default"] = {**state["global"], **head_mean}
    elif variant == "fedavg":
        final["clients"] = {c: state["global"] for c in clients}
        final["default"] = state["global"]
    elif variant == "fedft":
        for c in clients:
            rng = np.random.default_rng([seed, rounds, c])
            final["clients"][c], _ = _train_local(p, component, state["global"], c, years[int(rng.integers(len(years)))], rng,
                                                  ft_steps, device, gen, 0.0)
            state["steps"] += ft_steps
        final["default"] = state["global"]
    else:
        final["clients"] = {c: state["clients"][c] for c in clients}
    torch.save({"final": final, "component": component, "variant": variant, "seed": seed, "config_digest": cfg.digest(),
                "gradient_steps": state["steps"], "rounds": rounds, "prox_mu": prox, "train_years": years},
               ck_final)
    write_json(run.file(f"train_log_{name}.json"), state["log"])
    return FedResult(name, "done", rounds, rounds, state["steps"], central, time.time() - start, ck_final, last)


def load_client_models(p: Prepared, component: str, path: Path, device: torch.device) -> ClientModels:
    ck = torch.load(path, map_location=device, weights_only=False)
    if ck["config_digest"] != p.cfg.digest():
        raise RuntimeError(f"{path} was trained under a different config")

    def make(state):
        m = build_model(p.cfg, component).to(device)
        m.load_state_dict(state)
        return m.eval()

    cache: Dict[int, torch.nn.Module] = {}

    def shared(state):                                     # one module per distinct state object
        if id(state) not in cache:
            cache[id(state)] = make(state)
        return cache[id(state)]

    return ClientModels({int(c): shared(s) for c, s in ck["final"]["clients"].items()},
                        None if ck["final"]["default"] is None else shared(ck["final"]["default"]))


def federated_score_function(p: Prepared, component: str, cm: ClientModels, device: torch.device) -> Callable[[Block], np.ndarray]:
    """Every cell is scored by the model of its own client; cells of unseen clients by ``cm.default``."""
    jobs: List = []
    for c in range(1, int(p.split.client_map.max()) + 1):
        model = cm.by_client.get(c, cm.default) if c not in p.split.heldout else cm.default
        cells = np.nonzero(p.cell_client == c)[0]
        if model is not None and cells.size:
            jobs.append((score_function(p, component, model, device, cells=cells), cells))

    def fn(block: Block) -> np.ndarray:
        out = np.full((block.days, p.grid.n_land), np.nan, np.float32)
        for f, cells in jobs:
            out[:, cells] = f(block)[:, cells]
        return out

    return fn


def run_federated(p: Prepared, component: str, variant: str, seed: int, splits: Sequence[str] = ("val",),
                  max_years: Optional[int] = None, time_cap_hours: Optional[float] = None, overwrite_scores: bool = False,
                  pinned: bool = True) -> Dict:
    """Train (or resume), score the benchmark and the clean threshold years, evaluate. The benchmark is checked
    first, so a run on a different benchmark stops before any training."""
    cfg = p.cfg
    bench = check_benchmark(p, require_pinned=pinned)
    prox = float(cfg.federated.prox_mu)
    name = run_label(variant, component, seed, prox)
    run = RunDir(paths.out_dir(cfg) / str(cfg.name), name)
    run.start(cfg, seed, {"split_manifest_hash": p.manifest["hash"], "benchmark_hash": bench["hash"], "component": component,
                          "variant": variant, "prox_mu": prox})
    res = train_federated(p, component, variant, seed, run, max_years, time_cap_hours)
    out = {"train": res, "metrics": {}}
    if res.status != "done":
        return out
    device = resolve_device(cfg)
    fn = federated_score_function(p, component, load_client_models(p, component, res.checkpoint, device), device)
    store = score_store(p)
    compute_scores(p, name, fn, splits, store, overwrite_scores)
    for split in splits:
        groups = ("seen",) if split == "val" else ("seen", "unseen")
        m = evaluate_component(p, name, split, cfg.evaluation.budgets, groups, store, pinned)
        m.update({"seed": seed, "component_kind": component, "variant": label(variant, prox),
                  "gradient_steps": res.gradient_steps, "centralized_gradient_steps": res.centralized_steps,
                  "unseen_clients": "not available" if variant == "local" else "scored"})
        write_json(run.file("metrics", f"{name}_{split}.json"), m)
        out["metrics"][split] = m
    return out
