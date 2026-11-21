"""STNet: a multi-task spatiotemporal fault detector for gridded daily rainfall, with short-range and long-range memory.

Built from a design note; NOT an established method. No paper has shown it on rainfall QC (docs/research/spatiotemporal-memory-
architectures-for-rainfall-qc.md says so). Every part has a switch so it can be removed and measured (ablation), and the whole thing is
judged on synthetic faults, including a held-out fault-TYPE split (``holdout_kinds``: the kind is removed from training, then scored on the
validation benchmark, which contains it).

What it is
  inputs   per day and cell: log1p(rain)/scale, valid, land, the cell minus a neighbourhood centre at radii 2, 4 (median), 8, 16 (mean),
           climatology, heavy-rain threshold, day-of-year sin and cos. Terrain is NOT used (no elevation data in this project).
  encoder  a 3-level U-Net over each day's grid; the 2 coarser levels carry a ConvGRU (short-range memory: days to weeks, storm movement).
  heads    1. fault map, 7 logits (any fault, and one per kind: spike, stuck, scale, phantom_rain, zeroed, drift), supervised;
           2. clean value (log1p/scale), scored as |observed - predicted|;
           3. masked disc: a disc of radius 4.5 to 6.5 cells is hidden in training and the model predicts the clean value inside it; scored as
              |observed - predicted| with every cell hidden once per pass (4 lattice passes, discs of radius 5 every 12 cells).
  long     a per-cell LSTM over the encoder features of the whole year plus its pre-history (causal), trained in a second stage on FROZEN
           encoder features, because the encoder cannot be back-propagated through 365+ days. It adds a correction to the fault logits. At
           scoring the memory starts ``history_days`` (90) days before the year, as in training, so it is shorter early in the year.
  fusion   NOT inside this module: the stored scores (fault, clean, disc) go through the existing calibrated fusion (``ablate --subset``).
  ensemble NOT IMPLEMENTED (several seeds can be trained and compared by hand; there is no disagreement score yet).

Training sees only training years, readable cells (held-out clients and buffer are NaN in every input) and targets on training cells; faults
are injected fresh per year visit by the generator with the benchmark's 'seen' settings, so neighbours carry footprints too (contamination
is part of the training). Genuine protected extremes are negatives weighted more; ambiguous heavy-rain cell-days too.
Known limits: at scoring several discs are hidden in one frame (spacing 12), in training one; the masked-disc head is only as good as that
shift allows. Scores are stored positive (softplus of a logit, or 10 x an absolute residual in log1p/scale units), because the fusion takes
log1p of them.
"""
from __future__ import annotations

import dataclasses
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from qc import paths, telemetry
from qc.batches import mask_unreadable
from qc.evaluate import compute_scores_many, evaluate_component, score_store
from qc.extremes import find_extremes
from qc.faults import FaultGenerator, settings_from_config
from qc.prepare import Prepared
from qc.runs import RunDir, write_json
from qc.scoring import Block
from qc.trained import resolve_device, train_block

log = logging.getLogger(__name__)

KINDS = ("spike", "stuck", "scale", "phantom_rain", "zeroed", "drift")
N_OUT = 1 + len(KINDS)                   # index 0 = any fault
IN_CH = 11
MARGIN = 16                              # context around a training crop: the largest feature radius
DISC_R_TRAIN = (4.5, 6.5)
DISC_R_SCORE, DISC_SPACING = 5.0, 12     # 4 phases of this lattice hide every cell once
PHASES = ((0, 0), (6, 0), (0, 6), (6, 6))
RESID_SCALE = 10.0
LONG_VAL_STEPS = 10                      # stage 2: validation-loss samples (of long_cells cells each) at the end of every long-memory epoch


@dataclass
class STConfig:
    width: int = 32
    c_feat: int = 16
    long_hidden: int = 64
    use_gru: bool = True
    use_long: bool = True
    use_disc: bool = True
    use_robust: bool = True
    holdout_kinds: Tuple[str, ...] = ()
    epochs: int = 3
    steps: int = 40                       # gradient steps per year visit, stage 1
    batch: int = 2                        # every day of a window keeps its activations for backprop: batch x window x crop^2 sets the GPU memory
    window: int = 16                      # days per training window
    burn: int = 6                         # first days of a window: memory warm-up, no loss
    crop: int = 48                        # side of the loss region; the input crop adds MARGIN on every side
    long_epochs: int = 1
    long_steps: int = 20
    long_cells: int = 1024
    long_years: int = 3                   # the LAST training years go to stage 2 only, so it never sees features the encoder was fitted on
    long_skip: bool = True                # feed the raw residual channels to the long memory, next to the frozen features
    probe: bool = True                    # after training: per-kind linear probe of the frozen features on two validation years
    lr: float = 1e-3
    pos_weight: float = 10.0
    protected_weight: float = 3.0
    ambiguous_weight: float = 2.0
    p_disc: float = 0.5
    prefix: str = "stnet"

    def signature(self) -> Dict:
        d = dataclasses.asdict(self)
        d["holdout_kinds"] = list(self.holdout_kinds)
        return d


# ---------------------------------------------------------------------------------------------- features (torch, any device)

def _disc_index(r: int, device) -> torch.Tensor:
    k = 2 * r + 1
    dy, dx = torch.meshgrid(torch.arange(-r, r + 1), torch.arange(-r, r + 1), indexing="ij")
    keep = ((dy ** 2 + dx ** 2) <= r * r) & ~((dy == 0) & (dx == 0))
    return (torch.arange(k * k).view(k, k)[keep]).to(device)


def masked_median(z: torch.Tensor, v: torch.Tensor, r: int, min_n: int = 3) -> torch.Tensor:
    """(N, H, W) values and validity -> median of the valid neighbours within radius r (centre excluded); NaN with fewer than min_n."""
    n, h, w = z.shape
    k = 2 * r + 1
    sel = _disc_index(r, z.device)
    zz = F.unfold(z[:, None], k, padding=r)[:, sel]
    vv = F.unfold(v[:, None].float(), k, padding=r)[:, sel] > 0.5
    cnt = vv.sum(1)
    srt = torch.where(vv, zz, torch.full_like(zz, float("inf"))).sort(dim=1).values
    lo = srt.gather(1, ((cnt - 1) // 2).clamp(min=0)[:, None])
    hi = srt.gather(1, (cnt // 2).clamp(min=0)[:, None])
    med = (0.5 * (lo + hi))[:, 0]
    return torch.where(cnt >= min_n, med, torch.full_like(med, float("nan"))).view(n, h, w)


def masked_mean(z: torch.Tensor, v: torch.Tensor, r: int, min_n: int = 3) -> torch.Tensor:
    """Mean of the valid neighbours in the (2r+1) square, the centre excluded; NaN with fewer than min_n."""
    k = 2 * r + 1
    vf = v.float()
    zv = (z * vf)[:, None]
    s = F.avg_pool2d(zv, k, stride=1, padding=r, divisor_override=1)[:, 0] - zv[:, 0]
    c = F.avg_pool2d(vf[:, None], k, stride=1, padding=r, divisor_override=1)[:, 0] - vf
    return torch.where(c >= min_n, s / c.clamp(min=1.0), torch.full_like(s, float("nan")))


def build_features(x: torch.Tensor, scale: torch.Tensor, land: torch.Tensor, heavy: torch.Tensor, clim: torch.Tensor,
                   sin: torch.Tensor, cos: torch.Tensor, robust: bool = True, chunk: int = 32) -> torch.Tensor:
    """x (N, H, W) raw mm, NaN where unreadable or missing; scale, land, heavy, clim (N, H, W); sin, cos (N,) -> (N, IN_CH, H, W)."""
    outs = []
    for s in range(0, x.shape[0], chunk):
        xs, sc = x[s:s + chunk], scale[s:s + chunk]
        v = torch.isfinite(xs) & (land[s:s + chunk] > 0.5)
        z = torch.where(v, torch.log1p(torch.nan_to_num(xs).clamp(min=0)) / sc, torch.zeros_like(xs))
        chans = [z, v.float(), land[s:s + chunk]]
        for r, fn in ((2, masked_median), (4, masked_median), (8, masked_mean), (16, masked_mean)):
            if robust:
                ref = fn(z, v, r)
                chans.append(torch.where(v & torch.isfinite(ref), z - ref, torch.zeros_like(z)))
            else:
                chans.append(torch.zeros_like(z))
        n = xs.shape[0]
        chans += [clim[s:s + chunk], heavy[s:s + chunk],
                  sin[s:s + chunk].view(n, 1, 1).expand_as(z), cos[s:s + chunk].view(n, 1, 1).expand_as(z)]
        outs.append(torch.nan_to_num(torch.stack(chans, dim=1), nan=0.0, posinf=0.0, neginf=0.0))    # last guard: the network never sees NaN or inf
    return torch.cat(outs, dim=0)


# ---------------------------------------------------------------------------------------------- network

def _block(i: int, o: int) -> nn.Sequential:
    return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.GroupNorm(8, o), nn.GELU(),
                         nn.Conv2d(o, o, 3, padding=1), nn.GroupNorm(8, o), nn.GELU())


class ConvGRUCell(nn.Module):
    def __init__(self, c: int):
        super().__init__()
        self.gates = nn.Conv2d(2 * c, 2 * c, 3, padding=1)
        self.cand = nn.Conv2d(2 * c, c, 3, padding=1)

    def forward(self, x: torch.Tensor, h: Optional[torch.Tensor]) -> torch.Tensor:
        h = torch.zeros_like(x) if h is None else h
        z, r = torch.sigmoid(self.gates(torch.cat([x, h], 1))).chunk(2, 1)
        n = torch.tanh(self.cand(torch.cat([x, r * h], 1)))
        return (1 - z) * h + z * n


class STNet(nn.Module):
    def __init__(self, width: int = 32, c_feat: int = 16, use_gru: bool = True, in_ch: int = IN_CH, n_out: int = N_OUT):
        super().__init__()
        w = width
        self.use_gru = use_gru
        self.e0 = _block(in_ch, w)
        self.d1, self.e1 = nn.Conv2d(w, 2 * w, 3, stride=2, padding=1), _block(2 * w, 2 * w)
        self.d2, self.e2 = nn.Conv2d(2 * w, 4 * w, 3, stride=2, padding=1), _block(4 * w, 4 * w)
        self.g1, self.g2 = (ConvGRUCell(2 * w), ConvGRUCell(4 * w)) if use_gru else (None, None)
        self.u2, self.dec1 = nn.ConvTranspose2d(4 * w, 2 * w, 2, stride=2), _block(4 * w, 2 * w)
        self.u1, self.dec0 = nn.ConvTranspose2d(2 * w, w, 2, stride=2), _block(2 * w, w)
        self.feat = nn.Conv2d(w, c_feat, 1)
        self.fault, self.clean, self.disc = nn.Conv2d(c_feat, n_out, 1), nn.Conv2d(c_feat, 1, 1), nn.Conv2d(c_feat, 1, 1)
        nn.init.constant_(self.fault.bias, -4.0)             # faults are rare: start from a low probability

    def step(self, x: torch.Tensor, state: Tuple = (None, None)):
        """One day. x (B, IN_CH, H, W) -> dict of outputs at the input size, and the new memory state."""
        h, w = x.shape[-2:]
        x = F.pad(x, (0, (-w) % 4, 0, (-h) % 4))
        a0 = self.e0(x)
        a1 = self.e1(self.d1(a0))
        a2 = self.e2(self.d2(a1))
        if self.use_gru:
            s1, s2 = self.g1(a1, state[0]), self.g2(a2, state[1])
            state = (s1, s2)
        else:
            s1, s2 = a1, a2
        y = self.dec1(torch.cat([self.u2(s2), s1], 1))
        y = self.dec0(torch.cat([self.u1(y), a0], 1))
        f = self.feat(y)[..., :h, :w]
        return {"feat": f, "fault": self.fault(f), "clean": self.clean(f)[:, 0], "disc": self.disc(f)[:, 0]}, state


class LongMemory(nn.Module):
    """Per-cell LSTM over the daily encoder features (and the stage-1 fault logits): a correction to the fault logits."""

    def __init__(self, c_in: int, hidden: int = 64, n_out: int = N_OUT):
        super().__init__()
        self.lstm = nn.LSTM(c_in, hidden, batch_first=True)
        self.out = nn.Linear(hidden, n_out)
        nn.init.zeros_(self.out.weight)
        nn.init.zeros_(self.out.bias)                         # starts as "no correction"

    def forward(self, x: torch.Tensor) -> torch.Tensor:        # (cells, days, c_in) -> (cells, days, n_out)
        return self.out(self.lstm(x)[0])


N_RESID = 4


def long_input(feat: torch.Tensor, fault_logits: torch.Tensor, resid: Optional[torch.Tensor] = None) -> torch.Tensor:
    """(cells, days, c) features, (cells, days, N_OUT) logits and optionally (cells, days, N_RESID) raw residuals (cell minus its neighbourhood
    at radii 2, 4, 8, 16) -> the long memory's input. Detached; logits clamped. The residuals are a skip around the frozen encoder, so a slow
    signal does not depend on what the encoder kept."""
    parts = [feat.detach().float(), fault_logits.detach().float().clamp(-10, 10) / 5.0]
    if resid is not None:
        parts.append(resid.detach().float())
    return torch.cat(parts, dim=-1)


# ---------------------------------------------------------------------------------------------- statics and the data of one year

class Static:
    """Grid-shaped statics on the device: scale, land, heavy-rain threshold, climatology (log1p/scale units where relevant)."""

    def __init__(self, p: Prepared, device):
        g, st = p.grid, p.stats
        h, w = g.shape
        # The training statistics set a cell's heavy-rain threshold to +inf when it never had a wet day (it can never be a protected
        # extreme), and a climatology can hold NaN. Fed to a network these turn every output NaN, so they are made finite here.
        heavy_mm = np.asarray(st.heavy_mm, np.float64)
        finite_heavy = heavy_mm[np.isfinite(heavy_mm)]
        n_inf = int((~np.isfinite(heavy_mm)).sum())
        heavy_mm = np.where(np.isfinite(heavy_mm), heavy_mm, finite_heavy.max() if finite_heavy.size else 0.0)   # the largest threshold: "never heavy"
        clim_mm = np.asarray(st.climatology, np.float64)
        n_nan = int((~np.isfinite(clim_mm)).sum())
        clim_mm = np.nan_to_num(clim_mm, nan=0.0, posinf=0.0, neginf=0.0)
        sc = np.asarray(st.scale, np.float32)
        sc = np.where(np.isfinite(sc) & (sc > 0), sc, 1.0).astype(np.float32)
        if n_inf or n_nan:
            log.warning("statics made finite for the network: %d cells without a heavy-rain threshold, %d non-finite climatology values", n_inf, n_nan)
        scale = np.ones((h, w), np.float32)
        scale[g.rows, g.cols] = sc
        heavy = np.zeros((h, w), np.float32)
        heavy[g.rows, g.cols] = np.log1p(heavy_mm) / sc
        clim = np.zeros((366, h, w), np.float32)
        clim[:, g.rows, g.cols] = np.log1p(np.clip(clim_mm, 0, None)) / sc[None, :]
        self.shape = (h, w)
        self.scale = torch.from_numpy(scale).to(device)
        self.land = torch.from_numpy(g.land.astype(np.float32)).to(device)
        self.heavy = torch.from_numpy(heavy).to(device)
        self.clim = torch.from_numpy(clim).to(device)

    def padded(self, m: int) -> "Static":
        out = object.__new__(Static)
        h, w = self.shape
        out.shape = (h + 2 * m, w + 2 * m)
        out.scale = F.pad(self.scale, (m, m, m, m), value=1.0)
        out.land = F.pad(self.land, (m, m, m, m))
        out.heavy = F.pad(self.heavy, (m, m, m, m))
        out.clim = F.pad(self.clim, (m, m, m, m))
        return out


def to_field(grid, series: np.ndarray) -> np.ndarray:
    out = np.full((series.shape[0],) + tuple(grid.shape), np.nan, np.float32)
    out[:, grid.rows, grid.cols] = series
    return out


def sincos(doy: np.ndarray, device) -> Tuple[torch.Tensor, torch.Tensor]:
    a = 2 * np.pi * np.asarray(doy, np.float32) / 365.25
    return torch.from_numpy(np.sin(a)).to(device), torch.from_numpy(np.cos(a)).to(device)


def faults_for_training(p: Prepared, holdout: Sequence[str]):
    st = settings_from_config(p.cfg, "seen")
    if holdout:
        gone = set(holdout)
        kinds = tuple(k for k in st.kinds if k not in gone)
        bases = tuple(k for k in st.combination_bases if k not in gone)
        if not kinds or not bases:
            raise ValueError("holding out these kinds leaves nothing to train on")
        st = dataclasses.replace(st, kinds=kinds, combination_bases=bases)
    return st


@dataclass
class YearData:
    rows: int
    pad: int
    doy: np.ndarray
    seen: torch.Tensor          # (R, H, W) corrupted, unreadable cells NaN
    clean_z: torch.Tensor       # (R, H, W) clean log1p/scale at readable cells (0 elsewhere)
    clean_ok: torch.Tensor      # (R, H, W) float 1 where the clean value is readable
    labels: torch.Tensor        # (R, N_OUT, H, W) float16
    weight: torch.Tensor        # (R, H, W) per-pixel loss weight (before pos_weight)
    pos: torch.Tensor           # (R, H, W) float 1 where any fault
    wpos: torch.Tensor          # (R, H, W) footprint-based weight of a fault cell


def year_data(p: Prepared, year: int, gen: FaultGenerator, rng: np.random.Generator, cfg: STConfig, readable: np.ndarray,
              device) -> YearData:
    pad = int(p.cfg.components.history_days)
    obs, doy = train_block(p, year, pad)
    ex = find_extremes(obs, p.stats.heavy_mm, p.grid, int(p.cfg.extremes.min_cells))
    fs = gen.generate(obs, faults_for_training(p, cfg.holdout_kinds), rng, forbidden=ex.protected)
    seen = mask_unreadable(fs.apply(obs), readable, p.grid)
    clean = mask_unreadable(obs, readable, p.grid)
    R, n, g = obs.shape[0], p.grid.n_land, p.grid
    lab = np.zeros((R, N_OUT, n), np.float16)
    wpos = np.zeros((R, n), np.float32)
    if fs.t.size:
        lab[fs.t, 0, fs.cell] = 1
        wpos[fs.t, fs.cell] = 0.2 + 0.8 * fs.weight
        for i, e in enumerate(fs.event):
            ev = fs.events[int(e)]
            for k in set(ev["bases"]) | {ev["kind"]}:
                if k in KINDS:
                    lab[fs.t[i], 1 + KINDS.index(k), fs.cell[i]] = 1
    w = np.ones((R, n), np.float32)
    w[ex.ambiguous] = cfg.ambiguous_weight
    w[ex.protected] = cfg.protected_weight
    z = np.log1p(np.clip(np.nan_to_num(clean), 0, None)) / p.stats.scale[None, :]
    lab_f = np.zeros((R, N_OUT) + tuple(g.shape), np.float16)
    lab_f[:, :, g.rows, g.cols] = lab
    t = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(device)
    return YearData(R, pad, doy, t(to_field(g, seen)), t(np.nan_to_num(to_field(g, np.where(np.isfinite(clean), z, 0.0).astype(np.float32)))),
                    t(np.isfinite(to_field(g, clean)).astype(np.float32)), t(lab_f), t(np.nan_to_num(to_field(g, w), nan=1.0)),
                    t(np.nan_to_num(to_field(g, (wpos > 0).astype(np.float32)))), t(np.nan_to_num(to_field(g, wpos))))


# ---------------------------------------------------------------------------------------------- stage 1: windows

def _region(origin: int, win: int, total: int, margin: int) -> Tuple[int, int]:
    """Part of a window that carries loss: not the context margin, except where the window touches the edge of the padded field."""
    lo = 0 if origin == 0 else margin
    hi = win if origin + win == total else win - margin
    return lo, hi


def weighted_bce(logits: torch.Tensor, labels: torch.Tensor, wt: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """logits, labels (..., N_OUT, ...) with the channel axis at ``-3`` of (B, Wd, K, h, w); wt, mask (B, Wd, h, w)."""
    bce = F.binary_cross_entropy_with_logits(logits, labels, reduction="none").mean(dim=2)
    return (bce * wt * mask).sum() / mask.sum().clamp(min=1.0)


def train_windows(model: STNet, opt, d: YearData, stat_p: Static, targets_p: torch.Tensor, cfg: STConfig,
                  rng: np.random.Generator, device, steps: int) -> List[float]:
    """``steps`` gradient steps on random (crop x window) samples of one year."""
    hp, wp = stat_p.shape
    win_h, win_w = min(cfg.crop + 2 * MARGIN, hp), min(cfg.crop + 2 * MARGIN, wp)
    pad2 = (MARGIN,) * 4
    seen = F.pad(d.seen, pad2, value=float("nan"))
    clean_z, clean_ok, pos = F.pad(d.clean_z, pad2), F.pad(d.clean_ok, pad2), F.pad(d.pos, pad2)
    labels, weight, wpos = F.pad(d.labels, pad2), F.pad(d.weight, pad2, value=1.0), F.pad(d.wpos, pad2)
    Wd = min(cfg.window, d.rows)
    burn = min(cfg.burn, Wd - 1)
    yy, xx = torch.meshgrid(torch.arange(win_h, device=device), torch.arange(win_w, device=device), indexing="ij")
    sin_all, cos_all = sincos(d.doy, device)
    losses: List[float] = []
    model.train()
    for _ in range(steps):
        feats, parts = [], {k: [] for k in ("cz", "cok", "lb", "wt", "pos", "wpos", "tg", "hide", "reg", "sf", "day")}
        for _b in range(cfg.batch):
            d0 = int(rng.integers(max(0, d.pad - burn), d.rows - Wd + 1))
            oy, ox = int(rng.integers(0, hp - win_h + 1)), int(rng.integers(0, wp - win_w + 1))
            sl = (slice(d0, d0 + Wd), slice(oy, oy + win_h), slice(ox, ox + win_w))
            x = seen[sl].clone()
            sf = torch.isfinite(x)
            ly, hy = _region(oy, win_h, hp, MARGIN)
            lx, hx = _region(ox, win_w, wp, MARGIN)
            reg = torch.zeros(win_h, win_w, dtype=torch.bool, device=device)
            reg[ly:hy, lx:hx] = True
            hide = torch.zeros(win_h, win_w, dtype=torch.bool, device=device)
            if cfg.use_disc and hy > ly and hx > lx and rng.random() < cfg.p_disc:
                cy, cx = int(rng.integers(ly, hy)), int(rng.integers(lx, hx))
                r = float(rng.uniform(*DISC_R_TRAIN))
                hide = ((yy - cy) ** 2 + (xx - cx) ** 2) <= r * r
                x[:, hide] = float("nan")
            dy = d.doy[d0:d0 + Wd]
            ys = (slice(oy, oy + win_h), slice(ox, ox + win_w))
            feats.append(build_features(
                x, stat_p.scale[ys].expand(Wd, -1, -1), stat_p.land[ys].expand(Wd, -1, -1), stat_p.heavy[ys].expand(Wd, -1, -1),
                stat_p.clim[torch.from_numpy(dy.astype(np.int64)).to(device)][:, ys[0], ys[1]], sin_all[d0:d0 + Wd], cos_all[d0:d0 + Wd],
                robust=cfg.use_robust))
            day = torch.zeros(Wd, dtype=torch.bool, device=device)
            day[burn:] = True
            day &= torch.from_numpy((np.arange(d0, d0 + Wd) >= d.pad)).to(device)
            lab_crop = labels[d0:d0 + Wd, :, oy:oy + win_h, ox:ox + win_w]                      # (Wd, N_OUT, h, w): the kind axis sits in the middle
            for k, v in (("cz", clean_z[sl]), ("cok", clean_ok[sl]), ("lb", lab_crop), ("wt", weight[sl]), ("pos", pos[sl]),
                         ("wpos", wpos[sl]), ("tg", targets_p[ys]), ("hide", hide), ("reg", reg), ("sf", sf), ("day", day)):
                parts[k].append(v)
        F_ = torch.stack(feats)                                           # (B, Wd, IN_CH, h, w)
        state: Tuple = (None, None)
        fl, cl, dl = [], [], []
        for t in range(Wd):
            out, state = model.step(F_[:, t], state)
            fl.append(out["fault"]); cl.append(out["clean"]); dl.append(out["disc"])
        fault, clean, disc = torch.stack(fl, 1), torch.stack(cl, 1), torch.stack(dl, 1)     # (B, Wd, N_OUT, h, w), (B, Wd, h, w) x2
        S = {k: torch.stack(v) for k, v in parts.items()}
        hide = S["hide"][:, None]                                         # (B, 1, h, w)
        base = S["tg"][:, None] & S["reg"][:, None] & S["day"][:, :, None, None]
        m = (base & S["sf"] & ~hide).float()
        wt = torch.where(S["pos"] > 0.5, cfg.pos_weight * S["wpos"], S["wt"])
        loss = weighted_bce(fault, S["lb"].float(), wt, m)
        mc = m * S["cok"]
        loss = loss + 0.5 * (F.smooth_l1_loss(clean, S["cz"], reduction="none") * mc).sum() / mc.sum().clamp(min=1.0)
        if cfg.use_disc:
            md = (base & hide & (S["cok"] > 0.5)).float()
            loss = loss + 0.5 * ((disc - S["cz"]).abs() * md).sum() / md.sum().clamp(min=1.0)
        if not torch.isfinite(loss):                                     # stop at the first bad step, and say where it came from
            raise RuntimeError(
                "STNet loss is not finite. inputs finite: %s; outputs finite (fault, clean, disc): %s, %s, %s; weights finite: %s; "
                "masked pixels: %d. Never continue a run on a NaN loss: the weights would be NaN for good." % (
                    bool(torch.isfinite(F_).all()), bool(torch.isfinite(fault).all()), bool(torch.isfinite(clean).all()),
                    bool(torch.isfinite(disc).all()), all(bool(torch.isfinite(q).all()) for q in model.parameters()), int(m.sum())))
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        losses.append(float(loss.detach()))
    return losses


# ---------------------------------------------------------------------------------------------- whole-year sequences (no gradient)

def lattice_masks(h: int, w: int, device) -> List[torch.Tensor]:
    ii = torch.arange(h, device=device).view(-1, 1)
    jj = torch.arange(w, device=device).view(1, -1)
    out = []
    for a, b in PHASES:
        dy = ((ii - a + DISC_SPACING // 2) % DISC_SPACING) - DISC_SPACING // 2
        dx = ((jj - b + DISC_SPACING // 2) % DISC_SPACING) - DISC_SPACING // 2
        out.append((dy ** 2 + dx ** 2).float() <= DISC_R_SCORE ** 2)
    return out


@torch.no_grad()
def run_sequence(model: STNet, fields: torch.Tensor, doy: np.ndarray, stat: Static, cfg: STConfig, masks: Sequence[torch.Tensor] = (),
                 chunk: int = 8) -> Dict[str, torch.Tensor]:
    """Run the model over days in order on full-size fields (R, H, W), carrying its memory. Stream 0 is the field as it is; each mask
    adds a stream with those cells hidden. Returns feat (R, c, H, W) half, fault (R, N_OUT, H, W) half, clean (R, H, W), and the masked-disc
    prediction (R, H, W) averaged over the streams that hid each cell, with the count of such streams."""
    model.eval()
    R, H, W = fields.shape
    S = 1 + len(masks)
    dev = fields.device
    sin_all, cos_all = sincos(doy, dev)
    feat = torch.zeros(R, model.feat.out_channels, H, W, dtype=torch.float16, device=dev)
    resid = torch.zeros(R, N_RESID, H, W, dtype=torch.float16, device=dev)
    fault = torch.zeros(R, N_OUT, H, W, dtype=torch.float16, device=dev)
    clean = torch.zeros(R, H, W, device=dev)
    dsum, dcnt = torch.zeros(R, H, W, device=dev), torch.zeros(R, H, W, device=dev)
    state: Tuple = (None, None)
    for s in range(0, R, chunk):
        e = min(R, s + chunk)
        frames = fields[s:e]
        x = frames[:, None].repeat(1, S, 1, 1)
        for i, m in enumerate(masks):
            x[:, 1 + i][:, m] = float("nan")
        n = (e - s) * S
        di = torch.from_numpy(np.asarray(doy[s:e], np.int64)).to(dev).repeat_interleave(S)
        with telemetry.span("stnet.infer.features", units=e - s, unit="days"):
            feats = build_features(
                x.reshape(n, H, W), stat.scale.expand(n, -1, -1), stat.land.expand(n, -1, -1), stat.heavy.expand(n, -1, -1), stat.clim[di],
                sin_all[s:e].repeat_interleave(S), cos_all[s:e].repeat_interleave(S), robust=cfg.use_robust).view(e - s, S, IN_CH, H, W)
        with telemetry.span("stnet.infer.network", units=e - s, unit="days"):               # latency per day = mean_ms / days per chunk
            for t in range(e - s):
                out, state = model.step(feats[t], state)
                feat[s + t], fault[s + t], clean[s + t] = out["feat"][0].half(), out["fault"][0].half(), out["clean"][0]
                resid[s + t] = feats[t, 0, 3:3 + N_RESID].half()                       # channels 3..6 are the four residuals
                for i, m in enumerate(masks):
                    dsum[s + t] += torch.where(m, out["disc"][1 + i], torch.zeros_like(out["disc"][1 + i]))
                    dcnt[s + t] += m.float()
    return {"feat": feat, "resid": resid, "fault": fault, "clean": clean, "disc": dsum / dcnt.clamp(min=1.0), "disc_n": dcnt}


def long_logits(long: LongMemory, enc: Dict[str, torch.Tensor], rows: torch.Tensor, cols: torch.Tensor, skip: bool,
                cell_chunk: int = 1024) -> torch.Tensor:
    """Corrected fault logits (R, N_OUT, n_cells) at the cells given by ``rows``, ``cols``."""
    long.eval()
    outs = []
    with torch.no_grad():
        for s in range(0, rows.numel(), cell_chunk):
            r, c = rows[s:s + cell_chunk], cols[s:s + cell_chunk]
            f = enc["feat"][:, :, r, c].permute(2, 0, 1)                  # (cells, R, c_feat)
            fl = enc["fault"][:, :, r, c].permute(2, 0, 1)                # (cells, R, N_OUT)
            rs = enc["resid"][:, :, r, c].permute(2, 0, 1) if skip else None
            outs.append((fl.float() + long(long_input(f, fl, rs))).permute(1, 2, 0))
    return torch.cat(outs, dim=2)


def train_long(model: STNet, long: LongMemory, opt, d: YearData, stat: Static, cfg: STConfig, targets: Tuple[torch.Tensor, torch.Tensor],
               rng: np.random.Generator, device, steps: int) -> List[float]:
    """Stage 2 on one year: frozen encoder, per-cell LSTM over the whole year (with its pre-history), weighted BCE like stage 1."""
    enc = run_sequence(model, d.seen, d.doy, stat, cfg)
    losses: List[float] = []
    long.train()
    for _ in range(steps):
        loss = _long_loss(long, enc, d, cfg, targets, rng, device)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(long.parameters(), 1.0)
        opt.step()
        losses.append(float(loss.detach()))
    return losses


def _long_loss(long: LongMemory, enc: Dict[str, torch.Tensor], d: YearData, cfg: STConfig, targets: Tuple[torch.Tensor, torch.Tensor],
               rng: np.random.Generator, device) -> torch.Tensor:
    """The stage-2 loss on one random sample of ``cfg.long_cells`` cells of a year (the same loss for training and for the validation check)."""
    rows, cols = targets
    n = rows.numel()
    day_ok = torch.from_numpy(np.arange(d.rows) >= d.pad).to(device)
    pick = torch.from_numpy(rng.choice(n, min(cfg.long_cells, n), replace=False)).to(device)
    r, c = rows[pick], cols[pick]
    f = enc["feat"][:, :, r, c].permute(2, 0, 1)
    fl = enc["fault"][:, :, r, c].permute(2, 0, 1)
    rs = enc["resid"][:, :, r, c].permute(2, 0, 1) if cfg.long_skip else None
    logit = fl.float() + long(long_input(f, fl, rs))                    # (cells, R, N_OUT)
    lab = d.labels[:, :, r, c].permute(2, 0, 1).float()
    pos, wpos, w = d.pos[:, r, c].T, d.wpos[:, r, c].T, d.weight[:, r, c].T
    ok = torch.isfinite(d.seen[:, r, c]).T & day_ok[None, :]
    wt = torch.where(pos > 0.5, cfg.pos_weight * wpos, w)
    bce = F.binary_cross_entropy_with_logits(logit, lab, reduction="none").mean(dim=2)
    loss = (bce * wt * ok.float()).sum() / ok.float().sum().clamp(min=1.0)
    if not torch.isfinite(loss):
        raise RuntimeError("STNet stage-2 loss is not finite (encoder features finite: %s, stage-1 logits finite: %s)"
                           % (bool(torch.isfinite(enc["feat"].float()).all()), bool(torch.isfinite(enc["fault"].float()).all())))
    return loss


@torch.no_grad()
def val_long_loss(model: STNet, long: LongMemory, d: YearData, stat: Static, cfg: STConfig, targets: Tuple[torch.Tensor, torch.Tensor],
                  rng: np.random.Generator, device, steps: int = LONG_VAL_STEPS) -> float:
    """Stage-2 loss on a VALIDATION year, no gradient: the held-out signal that tells over-fitting to the few long years from learning.
    The caller passes a freshly seeded ``rng`` so every epoch sees the same faults and the same cells and the numbers are comparable."""
    enc = run_sequence(model, d.seen, d.doy, stat, cfg)
    long.eval()
    out = [float(_long_loss(long, enc, d, cfg, targets, rng, device)) for _ in range(steps)]
    long.train()
    return float(np.mean(out))


# ---------------------------------------------------------------------------------------------- scoring

def score_functions(p: Prepared, model: STNet, long: Optional[LongMemory], cfg: STConfig, device, seed: int) -> Dict:
    """name -> ScoreFn (Block -> (T, n_land)), all from one pass over the same block object."""
    g = p.grid
    stat = Static(p, device)
    masks = lattice_masks(*g.shape, device) if cfg.use_disc else []
    rows, cols = torch.from_numpy(g.rows.astype(np.int64)).to(device), torch.from_numpy(g.cols.astype(np.int64)).to(device)
    scale_cells = torch.from_numpy(p.stats.scale.astype(np.float32)).to(device)
    cache: Dict = {}

    def run(block: Block):
        if cache.get("block") is block:
            return cache["val"]
        fields = torch.from_numpy(to_field(g, block.obs)).to(device)
        enc = run_sequence(model, fields, block.doy, stat, cfg, masks)
        fault = enc["fault"][:, :, rows, cols].permute(0, 1, 2).float()                 # (R, N_OUT, n_land)
        if long is not None and cfg.use_long:
            fault = long_logits(long, enc, rows, cols, cfg.long_skip)
        z = torch.log1p(torch.from_numpy(np.nan_to_num(block.obs)).to(device).clamp(min=0)) / scale_cells[None, :]
        clean = RESID_SCALE * (z - enc["clean"][:, rows, cols]).abs()
        disc = RESID_SCALE * (z - enc["disc"][:, rows, cols]).abs() * (enc["disc_n"][:, rows, cols] > 0).float()
        cache["block"], cache["val"] = block, (fault.cpu().numpy(), clean.cpu().numpy(), disc.cpu().numpy())
        return cache["val"]

    def finish(arr: np.ndarray, block: Block) -> np.ndarray:
        out = arr[block.pad:].astype(np.float32)
        return np.where(np.isfinite(block.target), out, np.nan).astype(np.float32)

    sp = lambda a: np.logaddexp(0.0, a)
    pre = cfg.prefix
    fns = {f"{pre}_fault_s{seed}": lambda b: finish(sp(run(b)[0][:, 0]), b),
           f"{pre}_clean_s{seed}": lambda b: finish(run(b)[1], b),
           f"{pre}_disc_s{seed}": lambda b: finish(run(b)[2], b)}
    for i, k in enumerate(KINDS):
        fns[f"{pre}_{k}_s{seed}"] = (lambda i_: lambda b: finish(sp(run(b)[0][:, 1 + i_]), b))(i)
    return fns


# ---------------------------------------------------------------------------------------------- the run

def _require_finite(ck: Dict, path: Path) -> None:
    """A checkpoint from a diverged run holds NaN weights; resuming from it would score NaN for good."""
    for part in ("model", "long"):
        sd = ck.get(part)
        if sd and not all(bool(torch.isfinite(v).all()) for v in sd.values() if v.dtype.is_floating_point):
            raise RuntimeError(f"{path} holds non-finite {part} weights (a diverged earlier run). Delete the folder {path.parent.parent} and run again.")


def _record_model(model: STNet, long: Optional[LongMemory], p: Prepared, device) -> None:
    """Parameters, size and FLOPs of one forward day on the full grid, into the telemetry session (if any)."""
    n1 = sum(q.numel() for q in model.parameters())
    n2 = sum(q.numel() for q in long.parameters()) if long is not None else 0
    telemetry.record("model.stnet.parameters", n1, "count")
    telemetry.record("model.stnet_long.parameters", n2, "count")
    telemetry.record("model.stnet.size_mb", (n1 + n2) * 4 / 2 ** 20, "MB")
    if telemetry.active() is None:
        return
    try:
        from torch.utils.flop_counter import FlopCounterMode
        was = model.training
        model.eval()
        with torch.no_grad(), FlopCounterMode(display=False) as fc:
            model.step(torch.zeros(1, IN_CH, *p.grid.shape, device=device))
        model.train(was)
        telemetry.record("model.stnet.flops_per_day_full_grid", fc.get_total_flops(), "FLOPs")
    except Exception as e:                                                    # an older torch has no FlopCounterMode
        log.info("could not count FLOPs: %s", e)


def probe_kinds(p: Prepared, model: STNet, cfg: STConfig, device, seed: int, years: Optional[Sequence[int]] = None,
                neg_per_pos: int = 20, min_pos: int = 20) -> Dict[str, Dict]:
    """Can the FROZEN encoder features tell faults of one kind from clean cell-days? A logistic probe is fitted on the first validation year and
    scored (AUC) on the next. If a kind's AUC is near 0.5 the encoder has dropped what that kind needs, and the long memory, which reads the same
    features, cannot recover it (the raw residual skip is its only other input). A diagnostic on validation years; nothing is tuned on it."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from qc.scoring import make_block

    ys = list(years or p.split.years["val"][:2])
    if len(ys) < 2:
        return {k: {"auc": None, "reason": "needs two validation years"} for k in KINDS}
    g, pad = p.grid, int(p.cfg.components.history_days)
    stat = Static(p, device)
    rows, cols = torch.from_numpy(g.rows.astype(np.int64)).to(device), torch.from_numpy(g.cols.astype(np.int64)).to(device)
    rng = np.random.default_rng([seed, 99])
    per_year = []
    for y in ys[:2]:
        block = make_block(p, y, "val", pad)
        enc = run_sequence(model, torch.from_numpy(to_field(g, block.obs)).to(device), block.doy, stat, cfg)
        feat = enc["feat"][pad:, :, rows, cols].permute(0, 2, 1).float().cpu().numpy()          # (T, n_land, c)
        fs = block.bench.faults
        any_lab = fs.labels()
        ok = np.isfinite(block.target)
        kind_rows = {k: np.zeros(any_lab.shape, bool) for k in KINDS}
        for i, e in enumerate(fs.event):
            ev = fs.events[int(e)]
            for k in set(ev["bases"]) | {ev["kind"]}:
                if k in kind_rows:
                    kind_rows[k][fs.t[i], fs.cell[i]] = True
        if not np.isfinite(feat).all():
            return {k: {"auc": None, "reason": "the encoder features are not finite"} for k in KINDS}
        per_year.append((feat, any_lab, ok, kind_rows))
    out: Dict[str, Dict] = {}
    for k in KINDS:
        sets = []
        for feat, any_lab, ok, kr in per_year:
            pos = np.argwhere(kr[k] & ok)
            neg = np.argwhere(~any_lab & ok)
            if pos.shape[0] < min_pos:
                sets = None
                break
            neg = neg[rng.choice(neg.shape[0], min(neg.shape[0], neg_per_pos * pos.shape[0]), replace=False)]
            idx = np.concatenate([pos, neg])
            sets.append((feat[idx[:, 0], idx[:, 1]], np.r_[np.ones(len(pos)), np.zeros(len(neg))]))
        if sets is None:
            out[k] = {"auc": None, "reason": f"fewer than {min_pos} positive cell-days in a validation year"}
            continue
        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=300))
        clf.fit(*sets[0])
        out[k] = {"auc": float(roc_auc_score(sets[1][1], clf.predict_proba(sets[1][0])[:, 1])), "n_pos_fit": int(sets[0][1].sum()),
                  "n_pos_test": int(sets[1][1].sum()), "fit_year": ys[0], "test_year": ys[1]}
    return out


def _targets(p: Prepared, device) -> Tuple[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
    g = p.grid
    tmask = p.split.target_mask()                                          # (H, W) bool: training cells, buffer excluded
    padded = F.pad(torch.from_numpy(tmask.astype(np.float32)), (MARGIN,) * 4).to(device) > 0.5
    r, c = np.nonzero(tmask & g.land)
    return padded, (torch.from_numpy(r.astype(np.int64)).to(device), torch.from_numpy(c.astype(np.int64)).to(device))


def final_checkpoint_path(p: Prepared, prefix: str, seed: int) -> Path:
    n = f"{prefix}_s{seed}"
    return paths.out_dir(p.cfg) / str(p.cfg.name) / n / "checkpoints" / f"{n}_final.pt"


def load_final(p: Prepared, prefix: str, seed: int, device) -> Tuple[STNet, Optional[LongMemory], STConfig]:
    """A finished run's network, long memory and settings, rebuilt from the checkpoint (which carries its own settings)."""
    path = final_checkpoint_path(p, prefix, seed)
    if not path.is_file():
        raise FileNotFoundError(f"no finished STNet run at {path}")
    ck = torch.load(path, map_location=device, weights_only=False)
    _require_finite(ck, path)
    sig = dict(ck["sig"])
    sig["holdout_kinds"] = tuple(sig.get("holdout_kinds", ()))
    cfg = STConfig(**sig)
    model = STNet(cfg.width, cfg.c_feat, cfg.use_gru).to(device)
    model.load_state_dict(ck["model"])
    long = None
    if cfg.use_long and ck.get("long") is not None:
        long = LongMemory(cfg.c_feat + N_OUT + (N_RESID if cfg.long_skip else 0), cfg.long_hidden).to(device)
        long.load_state_dict(ck["long"])
    return model, long, cfg


def score_checkpoint(p: Prepared, prefix: str, seed: int, splits: Sequence[str], heads: Sequence[str] = ("fault",),
                     overwrite: bool = False) -> List[str]:
    """Score the benchmark years of ``splits`` (and the clean threshold years) with a finished run, storing the chosen heads
    (``fault``, ``clean``, ``disc`` or a kind). Nothing is trained or tuned here. Returns the stored names."""
    device = resolve_device(p.cfg)
    model, long, cfg = load_final(p, prefix, seed, device)
    fns = score_functions(p, model, long, cfg, device, seed)
    keep = {n: f for n, f in fns.items() if any(n == f"{cfg.prefix}_{h}_s{seed}" for h in heads)}
    compute_scores_many(p, keep, tuple(splits), score_store(p), overwrite)
    return sorted(keep)


INIT_MUST_MATCH = ("width", "c_feat", "use_gru", "use_robust", "use_disc", "use_long", "holdout_kinds", "long_years")


def _load_stage1(p: Prepared, run_root: Path, init_from: str, seed: int, sig: Dict, device) -> Dict:
    """The finished stage-1 encoder of another run (same seed, prefix ``init_from``). Everything that shapes the encoder or the years it saw
    must match, otherwise stage 2 would train on features of years the encoder was fitted on."""
    src = run_root / f"{init_from}_s{seed}" / "checkpoints" / f"{init_from}_s{seed}_final.pt"
    if not src.is_file():
        raise FileNotFoundError(f"--init-from {init_from}: no finished run at {src}")
    ck = torch.load(src, map_location=device, weights_only=False)
    bad = [k for k in INIT_MUST_MATCH if ck["sig"].get(k) != sig.get(k)]
    if bad:
        raise ValueError(f"--init-from {init_from} was trained with different {', '.join(bad)}: {[ck['sig'].get(k) for k in bad]} against "
                         f"{[sig.get(k) for k in bad]}")
    _require_finite(ck, src)
    return ck


def run_stnet(p: Prepared, seed: int, cfg: STConfig, splits: Sequence[str] = ("val",), max_years: Optional[int] = None,
              time_cap_hours: Optional[float] = None, overwrite_scores: bool = False, pinned: bool = True,
              init_from: Optional[str] = None) -> Dict:
    """Train (stage 1 then stage 2, resumable), score the benchmark and clean threshold years, evaluate like every other component.
    ``init_from`` takes the finished stage-1 encoder of another run and trains only stage 2 (new long-memory settings, minutes, not hours)."""
    device = resolve_device(p.cfg)
    torch.manual_seed(seed)
    name = f"{cfg.prefix}_s{seed}"
    run = RunDir(paths.out_dir(p.cfg) / str(p.cfg.name), name)
    run.start(p.cfg, seed, {"split_manifest_hash": p.manifest["hash"], "component": cfg.prefix, "stnet": cfg.signature()})
    ck_last, ck_final = run.path / "checkpoints" / f"{name}_last.pt", run.path / "checkpoints" / f"{name}_final.pt"
    ck_last.parent.mkdir(parents=True, exist_ok=True)

    model = STNet(cfg.width, cfg.c_feat, cfg.use_gru).to(device)
    years = list(p.split.years["train"])
    if max_years:
        years = years[:int(max_years)]
    k_long = min(cfg.long_years, len(years) // 2) if cfg.use_long else 0           # the last years are for stage 2 only
    if cfg.use_long and k_long == 0:
        raise ValueError("too few training years to keep some back for the long memory; use use_long=False or more years")
    years1, years2 = (years[:-k_long], years[-k_long:]) if k_long else (years, [])
    long = LongMemory(cfg.c_feat + N_OUT + (N_RESID if cfg.long_skip else 0), cfg.long_hidden).to(device) if cfg.use_long else None
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=1e-4)
    opt_long = torch.optim.AdamW(long.parameters(), lr=cfg.lr, weight_decay=1e-4) if long is not None else None
    _record_model(model, long, p, device)
    total1 = cfg.epochs * len(years1)
    total2 = (cfg.long_epochs * len(years2)) if long is not None else 0
    done, log_rows = 0, []
    sig = cfg.signature()
    if ck_final.is_file():
        ck = torch.load(ck_final, map_location=device, weights_only=False)
        _require_finite(ck, ck_final)
        model.load_state_dict(ck["model"])
        if long is not None:
            long.load_state_dict(ck["long"])
        done = total1 + total2
    elif ck_last.is_file():
        ck = torch.load(ck_last, map_location=device, weights_only=False)
        if ck["sig"] != sig or ck["seed"] != seed or ck["total"] != (total1, total2) or ck["config_digest"] != p.cfg.digest():
            raise RuntimeError(f"{ck_last} was made under a different config, seed or run length; use another prefix or delete it")
        _require_finite(ck, ck_last)
        model.load_state_dict(ck["model"]); opt.load_state_dict(ck["opt"])
        if long is not None:
            long.load_state_dict(ck["long"]); opt_long.load_state_dict(ck["opt_long"])
        done, log_rows = ck["done"], ck["log"]
        log.info("%s: resuming at step %d of %d + %d", name, done, total1, total2)
    elif init_from:
        ck = _load_stage1(p, run.path.parent, init_from, seed, sig, device)
        model.load_state_dict(ck["model"])
        done = total1                                                          # stage 1 is the other run's; only stage 2 trains here
        log.info("%s: stage-1 encoder taken from %s_s%d; training stage 2 only (%d visits)", name, init_from, seed, total2)

    gen = FaultGenerator(p.grid)
    stat = Static(p, device)
    stat_p = stat.padded(MARGIN)
    readable = p.split.input_mask()
    targets_p, targets = _targets(p, device)
    start, cap, status = time.time(), time_cap_hours, "done"
    while done < total1 + total2:
        phase = 1 if done < total1 else 2
        k = done if phase == 1 else done - total1
        ys = years1 if phase == 1 else years2
        epoch, i = divmod(k, len(ys))
        order = np.random.default_rng([seed, phase, epoch]).permutation(len(ys))
        year = ys[int(order[i])]
        rng = np.random.default_rng([seed, phase, epoch, year])
        with telemetry.span("stnet.data.year_data", sync=False):                  # fault injection and tensors; CPU work
            d = year_data(p, year, gen, rng, cfg, readable, device)
        if phase == 1:
            with telemetry.span("stnet.train.stage1_year_visit", units=cfg.steps * cfg.batch * cfg.window, unit="frames"):
                losses = train_windows(model, opt, d, stat_p, targets_p, cfg, rng, device, cfg.steps)
        else:
            with telemetry.span("stnet.train.stage2_year_visit", units=cfg.long_steps * cfg.long_cells, unit="cell-sequences"):
                losses = train_long(model, long, opt_long, d, stat, cfg, targets, rng, device, cfg.long_steps)
        telemetry.gpu_peak(f"stnet.stage{phase}")
        del d
        done += 1
        log_rows.append({"phase": phase, "epoch": epoch, "year": year, "loss": float(np.mean(losses)) if losses else None})
        log.info("%s: stage %d epoch %d year %d loss %.4f (%d/%d)", name, phase, epoch, year, log_rows[-1]["loss"] or float("nan"),
                 done, total1 + total2)
        if phase == 2 and i == len(ys) - 1 and p.split.years["val"]:                       # end of a long-memory epoch: the held-out check
            vy = int(p.split.years["val"][0])
            with telemetry.span("stnet.train.stage2_val_loss", sync=False):
                vd = year_data(p, vy, gen, np.random.default_rng([seed, 7, vy]), cfg, readable, device)
                vl = val_long_loss(model, long, vd, stat, cfg, targets, np.random.default_rng([seed, 8, vy]), device)
            del vd
            log_rows[-1]["val_loss"], log_rows[-1]["val_year"] = vl, vy
            best = min([r["val_loss"] for r in log_rows[:-1] if r.get("val_loss") is not None], default=float("inf"))
            log.info("%s: long-memory epoch %d: train loss (mean of its visits) vs validation-year loss %.4f (best before: %s)", name, epoch, vl,
                     "none" if best == float("inf") else f"{best:.4f}")
            if vl < best:                                                                  # the best epoch by validation loss is kept next to the final one
                torch.save({"model": model.state_dict(), "long": long.state_dict(), "sig": sig, "seed": seed, "epoch": epoch, "val_loss": vl,
                            "config_digest": p.cfg.digest()}, ck_last.with_name(f"{name}_best.pt"))
        torch.save({"model": model.state_dict(), "long": long.state_dict() if long is not None else None, "opt": opt.state_dict(),
                    "opt_long": opt_long.state_dict() if opt_long is not None else None, "done": done, "total": (total1, total2),
                    "log": log_rows, "seed": seed, "sig": sig, "config_digest": p.cfg.digest()}, ck_last.with_suffix(".tmp"))
        ck_last.with_suffix(".tmp").replace(ck_last)
        if cap and (time.time() - start) / 3600.0 >= float(cap) and done < total1 + total2:
            log.warning("%s: stopped at the time cap (%.2f h); run again to resume", name, cap)
            return {"status": "stopped", "done": done, "total": total1 + total2}
    if not ck_final.is_file():
        torch.save({"model": model.state_dict(), "long": long.state_dict() if long is not None else None, "sig": sig, "seed": seed,
                    "config_digest": p.cfg.digest()}, ck_final)
        write_json(run.file(f"train_log_{name}.json"), log_rows)

    if cfg.probe:
        with telemetry.span("stnet.probe"):
            probe = probe_kinds(p, model, cfg, device, seed)
        write_json(run.file(f"probe_{name}.json"), probe)
        log.info("%s: linear probe of the frozen features (AUC, fit on one validation year, scored on the next): %s", name,
                 {k: (None if v["auc"] is None else round(v["auc"], 3)) for k, v in probe.items()})
    fns = score_functions(p, model, long, cfg, device, seed)
    store = score_store(p)
    compute_scores_many(p, fns, tuple(splits), store, overwrite_scores)
    metrics = {}
    for key in (f"{cfg.prefix}_fault_s{seed}", f"{cfg.prefix}_clean_s{seed}", f"{cfg.prefix}_disc_s{seed}"):
        for split in splits:
            groups = ("seen",) if split == "val" else ("seen", "unseen")
            m = evaluate_component(p, key, split, p.cfg.evaluation.budgets, groups, store, pinned)
            m["stnet"], m["seed"] = cfg.signature(), seed
            write_json(run.file("metrics", f"{key}_{split}.json"), m)
            metrics[(key, split)] = m
    return {"status": "done", "metrics": metrics}
