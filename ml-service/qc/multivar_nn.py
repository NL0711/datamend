"""Neural masked-target experts for temperature, humidity and pressure (GPU if available, CPU otherwise).

One network predicts the cell's three anomalies at once from what is around it, and the score is how surprising the real
values are under its Gaussian prediction:
  input   a (2R+1) x (2R+1) patch of the three anomaly fields around the cell, with the centre (radius ``hide``) HIDDEN, plus
          a valid flag per value; the cell's own previous two days; season (sin, cos) and position.
          The cell's own current value is never an input, so a fault cannot hide itself or leak into another variable.
  output  mean and log standard deviation for each variable (heteroscedastic Gaussian).
  loss    Gaussian negative log-likelihood against the clean anomaly. Training uses clean data, with neighbours randomly
          dropped so the network copes with missing or bad neighbours.
  score   |real - mean| / sd per variable (``nn_<variable>``), NaN where the value is missing.

``fit_nn`` can tune: a small seeded random search over width, learning rate and patch radius, scored by validation
negative log-likelihood on clean held-out years (never on the fault benchmark), then the best setting is trained for the
full number of steps. Everything is seeded.

Used by ``qc.multivar`` as extra experts for the fusion. NOT done here: footprint faults, genuine-extreme protection.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
from torch import nn

from qc.era5 import Era5Daily

log = logging.getLogger(__name__)
NN_VARS = ("temperature", "humidity", "pressure")                  # same order as qc.multivar.NAMES
NN_NAMES = tuple(f"nn_{v}" for v in NN_VARS)


def pick_device(device: Optional[str] = None) -> torch.device:
    return torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))


class MaskedPatchNet(nn.Module):
    def __init__(self, radius: int = 4, width: int = 32, hidden: int = 128, extra: int = 10, dropout: float = 0.0):
        super().__init__()
        p = 2 * radius + 1
        self.conv = nn.Sequential(nn.Conv2d(6, width, 3, padding=1), nn.ReLU(), nn.Conv2d(width, width, 3, padding=1), nn.ReLU())
        self.head = nn.Sequential(nn.Linear(width * p * p + extra, hidden), nn.ReLU(), nn.Dropout(dropout),
                                  nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 6))

    def forward(self, patch: torch.Tensor, extra: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """patch (B, 3, P, P) with NaN where unknown; extra (B, 10): own lag1 (3), lag2 (3), sin, cos, lat, lon."""
        valid = torch.isfinite(patch)
        x = torch.cat([torch.nan_to_num(patch, nan=0.0), valid.float()], dim=1)
        e = torch.nan_to_num(extra, nan=0.0)
        h = self.conv(x).flatten(1)
        out = self.head(torch.cat([h, e], dim=1))
        return out[:, :3], out[:, 3:].clamp(-4.0, 3.0)                 # mean, log sd (anomaly units)


def _hide(patch: torch.Tensor, radius: int, hide: int) -> torch.Tensor:
    c = radius
    patch = patch.clone()
    patch[:, :, c - hide:c + hide + 1, c - hide:c + hide + 1] = float("nan")
    return patch


def _anomaly_stack(st, fields: Dict[str, np.ndarray]) -> np.ndarray:
    from qc.multivar import anomalies
    a = anomalies(st, fields)
    return np.stack([a[v] for v in NN_VARS], axis=-1).astype(np.float32)            # (T, H, W, 3)


@dataclass
class NnConfig:
    radius: int = 4
    hide: int = 1
    width: int = 32
    hidden: int = 128
    lr: float = 2e-3
    steps: int = 3000
    batch: int = 1024
    drop_neighbours: float = 0.1


@dataclass
class NnExperts:
    st: object
    net: MaskedPatchNet
    cfg: NnConfig
    plane: Tuple[np.ndarray, np.ndarray]
    device: torch.device
    history: Dict = field(default_factory=dict)

    @torch.no_grad()
    def scores(self, fields: Dict[str, np.ndarray], chunk_days: int = 6) -> Dict[str, np.ndarray]:
        self.net.eval()
        A = torch.from_numpy(_anomaly_stack(self.st, fields)).to(self.device)           # (T, H, W, 3)
        T, H, W, _ = A.shape
        R, P = self.cfg.radius, 2 * self.cfg.radius + 1
        nan = float("nan")
        Ap = torch.full((T + 2, 3, H + 2 * R, W + 2 * R), nan, device=self.device)
        Ap[2:, :, R:R + H, R:R + W] = A.permute(0, 3, 1, 2)                             # two NaN days in front for the lags
        la = torch.from_numpy(self.plane[0]).to(self.device).reshape(-1)
        lo = torch.from_numpy(self.plane[1]).to(self.device).reshape(-1)
        out = np.full((3, T, H, W), np.nan, np.float32)
        for t0 in range(0, T, chunk_days):
            t1 = min(T, t0 + chunk_days)
            d = t1 - t0
            cur = Ap[2 + t0:2 + t1]                                                     # (d, 3, Hp, Wp)
            patch = torch.nn.functional.unfold(cur, kernel_size=P).transpose(1, 2).reshape(d * H * W, 3, P, P)
            patch = _hide(patch, R, self.cfg.hide)
            lag1 = Ap[1 + t0:1 + t1, :, R:R + H, R:R + W].permute(0, 2, 3, 1).reshape(d * H * W, 3)
            lag2 = Ap[t0:t1, :, R:R + H, R:R + W].permute(0, 2, 3, 1).reshape(d * H * W, 3)
            ang = 2 * np.pi * torch.arange(t0, t1, device=self.device, dtype=torch.float32) / 365.25
            sin = torch.sin(ang)[:, None].expand(d, H * W).reshape(-1, 1)
            cos = torch.cos(ang)[:, None].expand(d, H * W).reshape(-1, 1)
            extra = torch.cat([lag1, lag2, sin, cos, la.repeat(d)[:, None], lo.repeat(d)[:, None]], dim=1)
            mu, logsd = self.net(patch, extra)
            tgt = A[t0:t1].reshape(d * H * W, 3)
            z = ((tgt - mu).abs() / logsd.exp()).reshape(d, H, W, 3)
            z = torch.where(torch.isfinite(A[t0:t1]), z, torch.full_like(z, nan))
            out[:, t0:t1] = z.permute(3, 0, 1, 2).cpu().numpy()
        return {f"nn_{v}": out[i] for i, v in enumerate(NN_VARS)}


def _gather_batch(Ap: torch.Tensor, y: torch.Tensor, t: torch.Tensor, r: torch.Tensor, c: torch.Tensor, cfg: NnConfig,
                  la: torch.Tensor, lo: torch.Tensor, R: int, drop: float):
    P = 2 * R + 1
    ar = torch.arange(P, device=Ap.device)
    yy, tt = y[:, None, None], t[:, None, None]
    rr, cc = (r[:, None, None] + ar[None, :, None]), (c[:, None, None] + ar[None, None, :])
    patch = Ap[yy, tt, rr, cc].float().permute(0, 3, 1, 2)                              # (B, 3, P, P)
    target = Ap[y, t, r + R, c + R].float()                                              # (B, 3)
    lag1, lag2 = Ap[y, t - 1, r + R, c + R].float(), Ap[y, t - 2, r + R, c + R].float()
    ang = 2 * np.pi * t.float() / 365.25
    extra = torch.cat([lag1, lag2, torch.sin(ang)[:, None], torch.cos(ang)[:, None], la[r, c][:, None], lo[r, c][:, None]], dim=1)
    patch = _hide(patch, R, cfg.hide)
    if drop > 0:
        patch = torch.where(torch.rand(patch.shape[0], 1, P, P, device=patch.device) < drop, torch.full_like(patch, float("nan")), patch)
    return patch, extra, target


def _nll(mu, logsd, target):
    ok = torch.isfinite(target)
    z = torch.where(ok, (target - mu) / logsd.exp(), torch.zeros_like(target))
    nll = 0.5 * z ** 2 + logsd
    return (nll * ok).sum() / ok.sum().clamp(min=1)


def _train(Ap, cfg: NnConfig, la, lo, R, steps: int, seed: int, device, valid_fn=None, time_cap_s: Optional[float] = None) -> Tuple[MaskedPatchNet, List[float]]:
    torch.manual_seed(seed)
    gen = torch.Generator(device="cpu").manual_seed(seed)
    net = MaskedPatchNet(R, cfg.width, cfg.hidden).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=cfg.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=max(steps, 2), pct_start=0.1)
    Ny, Tn, Hp, Wp, _ = Ap.shape
    H, W = Hp - 2 * R, Wp - 2 * R
    losses, t_start = [], time.time()
    net.train()
    for step in range(steps):
        y = torch.randint(0, Ny, (cfg.batch,), generator=gen).to(device)
        t = torch.randint(2, Tn, (cfg.batch,), generator=gen).to(device)
        r = torch.randint(0, H, (cfg.batch,), generator=gen).to(device)
        c = torch.randint(0, W, (cfg.batch,), generator=gen).to(device)
        patch, extra, target = _gather_batch(Ap, y, t, r, c, cfg, la, lo, R, cfg.drop_neighbours)
        mu, logsd = net(patch, extra)
        loss = _nll(mu, logsd, target)
        if not torch.isfinite(loss):
            continue
        opt.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        opt.step()
        sched.step()
        if step % 50 == 0:
            losses.append(float(loss))
        if time_cap_s and time.time() - t_start > time_cap_s:
            log.warning("nn training stopped at step %d by the time cap", step)
            break
    return net, losses


def _stack_years(data: Era5Daily, st, years: Sequence[int], R: int, device) -> torch.Tensor:
    """(years, 366, H + 2R, W + 2R, 3) float16 on the device; NaN padding outside the grid and for missing days."""
    from qc.multivar import _fields
    mats = []
    for y in years:
        a = _anomaly_stack(st, _fields(data, y))
        T, H, W, _ = a.shape
        full = np.full((366, H + 2 * R, W + 2 * R, 3), np.nan, np.float16)
        full[:T, R:R + H, R:R + W] = a.astype(np.float16)
        mats.append(full)
    return torch.from_numpy(np.stack(mats)).to(device)


@torch.no_grad()
def _validation_nll(net: MaskedPatchNet, Ap: torch.Tensor, cfg: NnConfig, la, lo, R, n: int, seed: int) -> float:
    net.eval()
    gen = torch.Generator(device="cpu").manual_seed(seed)
    Ny, Tn, Hp, Wp, _ = Ap.shape
    H, W = Hp - 2 * R, Wp - 2 * R
    tot, cnt = 0.0, 0
    for _ in range(max(1, n // 4096)):
        b = 4096
        y = torch.randint(0, Ny, (b,), generator=gen).to(Ap.device)
        t = torch.randint(2, Tn, (b,), generator=gen).to(Ap.device)
        r = torch.randint(0, H, (b,), generator=gen).to(Ap.device)
        c = torch.randint(0, W, (b,), generator=gen).to(Ap.device)
        patch, extra, target = _gather_batch(Ap, y, t, r, c, cfg, la, lo, R, 0.0)
        mu, logsd = net(patch, extra)
        ok = torch.isfinite(target)
        z = torch.where(ok, (target - mu) / logsd.exp(), torch.zeros_like(target))
        tot += float(((0.5 * z ** 2 + logsd) * ok).sum())
        cnt += int(ok.sum())
    return tot / max(cnt, 1)


SEARCH = [dict(width=32, hidden=128, lr=2e-3, radius=4), dict(width=32, hidden=256, lr=1e-3, radius=4),
          dict(width=64, hidden=128, lr=2e-3, radius=4), dict(width=32, hidden=128, lr=2e-3, radius=3),
          dict(width=64, hidden=256, lr=1e-3, radius=5), dict(width=16, hidden=64, lr=3e-3, radius=4),
          dict(width=64, hidden=256, lr=2e-3, radius=4), dict(width=32, hidden=128, lr=5e-4, radius=4)]


def fit_nn(data: Era5Daily, st, train_years: Sequence[int], valid_years: Sequence[int], base: Optional[NnConfig] = None,
           trials: int = 0, tune_steps: int = 600, max_years: int = 8, seed: int = 0, device: Optional[str] = None,
           time_cap_hours: Optional[float] = None) -> NnExperts:
    """Train the experts on at most ``max_years`` evenly spaced ``train_years``. With ``trials`` > 0, try that many
    settings from ``SEARCH`` for ``tune_steps`` steps each and keep the one with the lowest negative log-likelihood on
    clean ``valid_years``; then train that setting for ``base.steps``. The fault benchmark is never used for tuning."""
    dev = pick_device(device)
    base = base or NnConfig()
    years = list(train_years)[::max(1, len(train_years) // max_years)][:max_years]
    lat, lon = data.grid(years[0])
    la_np = np.broadcast_to(((lat - lat.min()) / max(float(np.ptp(lat)), 1e-6))[:, None], (lat.size, lon.size)).astype(np.float32)
    lo_np = np.broadcast_to(((lon - lon.min()) / max(float(np.ptp(lon)), 1e-6))[None, :], (lat.size, lon.size)).astype(np.float32)
    la, lo = torch.from_numpy(np.ascontiguousarray(la_np)).to(dev), torch.from_numpy(np.ascontiguousarray(lo_np)).to(dev)
    t0 = time.time()
    cap = None if time_cap_hours is None else time_cap_hours * 3600
    history: Dict = {"device": str(dev), "train_years": years, "trials": []}
    best, best_v = base, float("inf")
    tuned: Dict[int, torch.Tensor] = {}
    if trials > 0:
        for i, s in enumerate(SEARCH[:trials]):
            cfg = NnConfig(**{**base.__dict__, **s, "steps": tune_steps})
            R = cfg.radius
            if R not in tuned:
                tuned[R] = (_stack_years(data, st, years, R, dev), _stack_years(data, st, valid_years, R, dev))
            tr_ap, va_ap = tuned[R]
            net, _ = _train(tr_ap, cfg, la, lo, R, tune_steps, seed + i, dev, time_cap_s=None if cap is None else max(cap / (trials + 2), 30))
            v = _validation_nll(net, va_ap, cfg, la, lo, R, 40000, seed)
            history["trials"].append({**s, "validation_nll": v})
            log.info("nn trial %d %s: validation NLL %.4f", i, s, v)
            if v < best_v:
                best_v, best = v, NnConfig(**{**base.__dict__, **s})
        tuned.clear()
    R = best.radius
    Ap = _stack_years(data, st, years, R, dev)
    net, losses = _train(Ap, best, la, lo, R, best.steps, seed, dev, time_cap_s=None if cap is None else max(cap - (time.time() - t0), 60))
    history.update({"chosen": best.__dict__, "train_loss": losses, "seconds": round(time.time() - t0, 1)})
    return NnExperts(st, net, best, (la_np, lo_np), dev, history)
