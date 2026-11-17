"""Gate 4: train the centralized components (spatial, temporal, plain GRU) and score with them.

Training data. Each epoch visits the training years in a seeded order. For a year, the block of that year
plus 90 days of history is corrupted on the fly with the *seen* fault settings (``qc.faults``; never
touching protected extremes), after cells the training run may not read have been set to NaN. The
network inputs come from the corrupted block; the rainfall it is asked to predict is the clean value of
the same cell-day. So a network learns what a cell-day looks like given a possibly faulty context, and is
never taught that a faulty value is normal. Targets are cells of role ``train`` only.

Reads. History from before the first training year is NaN (never read from the evaluation-only years).
Reach is checked against the buffer around held-out clients (``qc.splits.audit_split``).

Randomness. Everything is seeded from ``(seed, epoch, year)``, so a run that stops and resumes draws
the same batches as one that never stopped. A checkpoint is written after every year.
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
from qc.batches import View, mask_unreadable, to_torch
from qc.evaluate import compute_scores, evaluate_component, score_store
from qc.extremes import find_extremes
from qc.faults import FaultGenerator, settings_from_config
from qc.models import PlainGRU, SpatialNet, TemporalGRU, nll, surprise
from qc.prepare import Prepared
from qc.runs import RunDir, read_json, write_json
from qc.scoring import Block
from qc.splits import audit_split

log = logging.getLogger(__name__)
COMPONENTS = ("spatial", "temporal", "plain_gru")


def resolve_device(cfg) -> torch.device:
    name = str(cfg.compute.devices[0])
    if name == "auto":
        name = "cuda:0" if torch.cuda.is_available() else "cpu"
    return torch.device(name)


def history_length(cfg, component: str) -> int:
    return int(cfg.components.temporal.history if component == "temporal" else cfg.components.plain_gru.history)


def build_model(cfg, component: str) -> torch.nn.Module:
    c = cfg.components
    if component == "spatial":
        return SpatialNet(int(c.spatial.radius), float(c.hidden_radius), int(c.spatial.width), int(c.spatial.dense))
    if component == "temporal":
        return TemporalGRU(int(c.temporal.hidden), int(c.temporal.dense))
    if component == "plain_gru":
        return PlainGRU(int(c.plain_gru.hidden))
    raise ValueError(f"unknown component {component!r}; choose from {COMPONENTS}")


def reach_cells(cfg, component: str) -> int:
    return int(cfg.components.spatial.radius) if component == "spatial" else 0


def run_name(component: str, seed: int) -> str:
    return f"{component}_s{seed}"


# ---------------------------------------------------------------------------------------------- the model's forward pass

def forward(model: torch.nn.Module, component: str, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
    if component == "spatial":
        return model(batch["patch"], batch["valid"], batch["static"])
    return model(batch["hist"], batch["valid"], batch["static"])


def make_view(p: Prepared, component: str, obs: np.ndarray, doy: np.ndarray, pad: int) -> View:
    radius = int(p.cfg.components.spatial.radius) if component == "spatial" else 0
    return View.build(p.grid, p.stats, obs, doy, pad, radius)


def get_batch(view: View, component: str, cfg, t: np.ndarray, cell: np.ndarray) -> Dict[str, np.ndarray]:
    return view.spatial(t, cell) if component == "spatial" else view.history(t, cell, history_length(cfg, component))


# ---------------------------------------------------------------------------------------------- training data

def train_block(p: Prepared, year: int, pad: int):
    """Clean (pad + T, n_land) block for a training year. History comes from the previous year only if that
    year is itself a training year; otherwise it is NaN."""
    cur = p.store.year(year)
    prev = year - 1
    if prev in set(p.split.years["train"]):
        old = p.store.year(prev)
        hist, hdoy = old[old.shape[0] - pad:], np.arange(old.shape[0] - pad, old.shape[0])
    else:
        hist, hdoy = np.full((pad, cur.shape[1]), np.nan, np.float32), np.arange(365 - pad, 365)
    obs = np.concatenate([hist, cur], axis=0).astype(np.float32)
    doy = np.concatenate([hdoy, np.arange(cur.shape[0])]).astype(np.int16)
    return obs, doy


def corrupt(p: Prepared, gen: FaultGenerator, obs: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    st = settings_from_config(p.cfg, "seen")
    ex = find_extremes(obs, p.stats.heavy_mm, p.grid, int(p.cfg.extremes.min_cells))
    return gen.generate(obs, st, rng, forbidden=ex.protected).apply(obs)


# ---------------------------------------------------------------------------------------------- loop

@dataclass
class TrainResult:
    name: str
    status: str                 # done | stopped (time cap)
    years_done: int
    years_total: int
    last_loss: Optional[float]
    seconds: float
    checkpoint: Path


def _loss(component: str, model, batch, mm, unit, scale, wet_mm) -> torch.Tensor:
    out = forward(model, component, batch)
    if component == "plain_gru":
        target = torch.log1p(mm.clamp_min(0)) / scale
        return torch.mean((out.float() - target) ** 2)
    return nll(out, mm, unit, wet_mm).mean()


def year_steps(p: Prepared, component: str, model: torch.nn.Module, opt, scaler, amp: bool, device: torch.device, year: int,
               rng: np.random.Generator, steps: int, bs: int, readable: np.ndarray, targets: np.ndarray, gen: FaultGenerator,
               pad: int, prox_ref: Optional[Dict[str, torch.Tensor]] = None, prox_mu: float = 0.0) -> List[float]:
    """``steps`` gradient steps on one training year. Cells outside ``readable`` (a (H, W) mask) are NaN in every
    input, so a client trains on its own cells only; targets are drawn from ``targets`` (land-cell indices).
    ``prox_ref``/``prox_mu`` add the FedProx term ``mu/2 * ||w - w_ref||^2`` (off when ``prox_mu`` is 0)."""
    cfg, tr = p.cfg, p.cfg.train
    clean, doy = train_block(p, year, pad)
    clean = mask_unreadable(clean, readable, p.grid)
    seen = corrupt(p, gen, clean, rng) if tr.corruption else clean
    view = make_view(p, component, seen, doy, pad)
    T = clean.shape[0] - pad
    wet = float(cfg.normalization.wet_mm)
    losses = []
    for _ in range(steps):
        t = rng.integers(0, T, bs)
        cell = targets[rng.integers(0, targets.size, bs)]
        mm = clean[pad + t, cell]
        ok = np.isfinite(mm)
        if not ok.any():
            continue
        t, cell, mm = t[ok], cell[ok], mm[ok]
        batch = to_torch(get_batch(view, component, cfg, t, cell), device)
        mm_t = torch.from_numpy(mm).to(device)
        unit = torch.from_numpy(view.unit(cell)).to(device)
        scale = torch.from_numpy(p.stats.scale[cell]).to(device)
        with torch.autocast(device.type, enabled=amp):
            loss = _loss(component, model, batch, mm_t, unit, scale, wet)
        if prox_mu > 0 and prox_ref is not None:
            loss = loss + 0.5 * prox_mu * sum(((q - prox_ref[n]) ** 2).sum() for n, q in model.named_parameters())
        opt.zero_grad(set_to_none=True)
        scaler.scale(loss).backward()
        scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(model.parameters(), float(tr.grad_clip))
        scaler.step(opt)
        scaler.update()
        losses.append(float(loss.detach()))
    return losses


def train_component(p: Prepared, component: str, seed: int, run: RunDir, max_years: Optional[int] = None,
                    time_cap_hours: Optional[float] = None) -> TrainResult:
    cfg, tr = p.cfg, p.cfg.train
    audit_split(p.split, reach_cells=reach_cells(cfg, component))
    name = run_name(component, seed)
    ck_last, ck_final = run.path / "checkpoints" / f"{name}_last.pt", run.path / "checkpoints" / f"{name}_final.pt"
    device = resolve_device(cfg)
    torch.manual_seed(seed)
    model = build_model(cfg, component).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=float(tr.lr), weight_decay=float(tr.weight_decay))
    amp = bool(cfg.compute.amp) and device.type == "cuda"
    scaler = torch.amp.GradScaler(enabled=amp)

    years = list(p.split.years["train"])
    if max_years:
        years = years[:int(max_years)]            # the earliest years: never reaches into the future
    epochs, steps, bs = int(tr.epochs), int(tr.steps_per_year), int(tr.batch_size or cfg.compute.batch_size)
    total = epochs * len(years)
    done, log_rows, last_loss = 0, [], None
    if ck_final.is_file():
        return TrainResult(name, "done", total, total, None, 0.0, ck_final)
    if ck_last.is_file():
        ck = torch.load(ck_last, map_location=device, weights_only=False)
        if ck["config_digest"] != cfg.digest() or ck["seed"] != seed or ck["total"] != total:
            raise RuntimeError(f"{ck_last} was made under a different config, seed or run length; use a new run name or delete it")
        model.load_state_dict(ck["model"]); opt.load_state_dict(ck["opt"]); done, log_rows = ck["done"], ck["log"]
        log.info("%s: resuming at year-step %d of %d", name, done, total)

    gen = FaultGenerator(p.grid)
    pad = int(cfg.components.history_days)
    readable = p.split.input_mask()
    targets = np.nonzero(p.grid.to_series(p.split.target_mask()))[0]
    start, cap = time.time(), (time_cap_hours if time_cap_hours is not None else cfg.compute.max_hours_per_run)
    wet = float(cfg.normalization.wet_mm)
    model.train()
    while done < total:
        epoch, i = divmod(done, len(years))
        order = np.random.default_rng([seed, epoch]).permutation(len(years))
        year = years[int(order[i])]
        rng = np.random.default_rng([seed, epoch, year])
        losses = year_steps(p, component, model, opt, scaler, amp, device, year, rng, steps, bs, readable, targets, gen, pad)
        done += 1
        last_loss = float(np.mean(losses)) if losses else None
        log_rows.append({"epoch": epoch, "year": year, "loss": last_loss})
        log.info("%s: epoch %d year %d loss %s (%d/%d)", name, epoch, year, "n/a" if last_loss is None else f"{last_loss:.4f}", done, total)
        torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "done": done, "total": total, "log": log_rows,
                    "seed": seed, "config_digest": cfg.digest()}, ck_last.with_suffix(".tmp"))
        ck_last.with_suffix(".tmp").replace(ck_last)
        if cap and (time.time() - start) / 3600.0 >= float(cap) and done < total:
            log.warning("%s: stopped at the time cap (%.2f h); run again to resume", name, cap)
            return TrainResult(name, "stopped", done, total, last_loss, time.time() - start, ck_last)
    torch.save({"model": model.state_dict(), "component": component, "seed": seed, "config_digest": cfg.digest(),
                "train_years": years, "epochs": epochs, "steps_per_year": steps, "batch_size": bs}, ck_final)
    write_json(run.file(f"train_log_{name}.json"), log_rows)
    return TrainResult(name, "done", total, total, last_loss, time.time() - start, ck_final)


def load_model(p: Prepared, component: str, path: Path, device: torch.device) -> torch.nn.Module:
    ck = torch.load(path, map_location=device, weights_only=False)
    if ck.get("config_digest") != p.cfg.digest():
        raise RuntimeError(f"{path} was trained under a different config")
    model = build_model(p.cfg, component).to(device)
    model.load_state_dict(ck["model"])
    return model.eval()


# ---------------------------------------------------------------------------------------------- scoring

def score_function(p: Prepared, component: str, model: torch.nn.Module, device: torch.device,
                   batch_size: Optional[int] = None, cells: Optional[np.ndarray] = None) -> Callable[[Block], np.ndarray]:
    """Score every cell-day of a block. Every land cell is readable at scoring time, as for the untrained scores.
    ``cells`` (land-cell indices) limits which cells are scored; the others stay NaN."""
    cfg = p.cfg
    bs = int(batch_size or cfg.train.infer_batch_size)
    wet = float(cfg.normalization.wet_mm)

    @torch.no_grad()
    def fn(block: Block) -> np.ndarray:
        model.eval()
        view = make_view(p, component, block.obs, block.doy, block.pad)
        T, n = block.days, p.grid.n_land
        out = np.full((T, n), np.nan, np.float32)
        sel = np.arange(n) if cells is None else np.asarray(cells)
        tt, cc = np.divmod(np.arange(T * sel.size), sel.size)
        cc = sel[cc]
        for s in range(0, tt.size, bs):
            t, cell = tt[s:s + bs], cc[s:s + bs]
            mm = view.target(t, cell)
            ok = np.isfinite(mm)
            if not ok.any():
                continue
            t, cell, mm = t[ok], cell[ok], mm[ok]
            batch = to_torch(get_batch(view, component, cfg, t, cell), device)
            raw = forward(model, component, batch)
            if component == "plain_gru":
                pred = raw.float().cpu().numpy()
                sc = p.stats.scale[cell]
                score = np.abs(np.log1p(np.clip(mm, 0, None)) / sc - pred)
            else:
                mm_t = torch.from_numpy(mm).to(device)
                unit = torch.from_numpy(view.unit(cell)).to(device)
                score = surprise(raw, mm_t, unit, wet).cpu().numpy()
            out[t, cell] = score
        return out

    return fn


def run_component(p: Prepared, component: str, seed: int, splits: Sequence[str] = ("val",), max_years: Optional[int] = None,
                  time_cap_hours: Optional[float] = None, overwrite_scores: bool = False, pinned: bool = True) -> Dict:
    """Train (or resume), then score the benchmark and the clean threshold years, then evaluate."""
    cfg = p.cfg
    run = RunDir(paths.out_dir(cfg) / str(cfg.name), run_name(component, seed))
    run.start(cfg, seed, {"split_manifest_hash": p.manifest["hash"], "component": component})
    res = train_component(p, component, seed, run, max_years, time_cap_hours)
    out = {"train": res, "metrics": {}}
    if res.status != "done":
        return out
    device = resolve_device(cfg)
    name = run_name(component, seed)
    fn = score_function(p, component, load_model(p, component, res.checkpoint, device), device)
    store = score_store(p)
    compute_scores(p, name, fn, splits, store, overwrite_scores)
    for split in splits:
        groups = ("seen",) if split == "val" else ("seen", "unseen")
        m = evaluate_component(p, name, split, cfg.evaluation.budgets, groups, store, pinned)
        m["seed"], m["component_kind"] = seed, component
        write_json(run.file("metrics", f"{name}_{split}.json"), m)
        out["metrics"][split] = m
    return out
