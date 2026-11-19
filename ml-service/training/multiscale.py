"""Multi-scale temporal model (arch ``scalenet``).

Daily window -> parallel branches at several aggregation scales (default daily / pentad / monthly)
-> attention-weighted scale fusion -> intermediate fusion with neighbourhood, static and optional
station embeddings -> the shared trunk (BiLSTM + attention + zero-inflated Gamma head + anomaly head).

Trend/seasonal decomposition: the seasonal climatology and a causal low-frequency component feed a
*coarse* stream that is trained to reconstruct the clean low-frequency component; the residual
(daily - low-frequency) feeds the fine branches.

Leakage safety: every aggregate is a *causal trailing mean* (position t uses days <= t only, within
the window), and NaN-masked (mean over valid days, plus a valid-fraction channel).

[unvalidated] That this beats the single-scale RainNet on real anomalies is a hypothesis to test with
the ablations (``--single-scale`` vs ``--scales 1 5 30``); nothing here is evidence of that.
"""

from __future__ import annotations

from typing import Sequence, Tuple

import torch
import torch.nn.functional as F
from torch import nn

from training.model import _Trunk


def causal_mean(x: torch.Tensor, valid: torch.Tensor, k: int) -> Tuple[torch.Tensor, torch.Tensor]:
    """Trailing mean over the last ``k`` days (inclusive) along the last dim, ignoring invalid days.

    ``x``, ``valid`` have the same shape (..., W). Returns ``(mean, valid_fraction)``; the mean is 0
    where no valid day falls in the window. Position t never sees days after t (left-padded).
    """
    shape = x.shape
    flat = x.reshape(-1, 1, shape[-1])
    m = valid.to(x.dtype).reshape(-1, 1, shape[-1])
    s = F.avg_pool1d(F.pad(flat * m, (k - 1, 0)), k, stride=1) * k
    c = F.avg_pool1d(F.pad(m, (k - 1, 0)), k, stride=1) * k
    return (s / c.clamp_min(1e-6)).reshape(shape), (c / k).reshape(shape)


class _MultiKernel(nn.Module):
    """Parallel 1D convolutions with several kernel sizes, concatenated and projected."""

    def __init__(self, c_in: int, hidden: int, kernels: Sequence[int] = (3, 5, 7)):
        super().__init__()
        self.convs = nn.ModuleList([nn.Conv1d(c_in, hidden, k, padding=k // 2) for k in kernels])
        self.proj = nn.Linear(hidden * len(kernels), hidden)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # (B, C, W) -> (B, W, h)
        return F.gelu(self.proj(torch.cat([c(x) for c in self.convs], 1).transpose(1, 2)))


class ScaleNet(nn.Module):
    """forward(x, valid, clim, nbr, patch, pvalid, static, elev, station, smask), all in model space.

    x, clim: (B, W);  valid: (B, W) bool;  nbr: (B, 2, W) [neighbour mean, max];
    patch: (B, P, W) neighbourhood excluding the centre, pvalid: (B, P, W) bool (P may be 0);
    static: (B, W, 4);  elev: (B, 2) [elevation, available];  station: (B, W), smask: (B,) bool.
    Returns the _Trunk heads plus ``coarse_pred`` (B, W) and ``scale_attn`` (B, W, S).
    """

    def __init__(self, hidden: int = 128, layers: int = 2, attn_layers: int = 1, heads: int = 4,
                 dropout: float = 0.1, scales: Sequence[int] = (1, 5, 30), n_patch: int = 8):
        super().__init__()
        self.scales = tuple(int(s) for s in scales)
        if not self.scales or self.scales[0] != 1 or min(self.scales) < 1:
            raise ValueError("scales must start with 1 (the daily branch) and be positive")
        self.k_low, self.n_patch, self.hidden = max(self.scales), n_patch, hidden
        self.disabled_scales: Tuple[int, ...] = ()  # indices masked out of the scale fusion (ablation)
        self.branches = nn.ModuleList([_MultiKernel(6, hidden) for _ in self.scales])
        self.scale_emb = nn.Embedding(len(self.scales), hidden)
        self.q = nn.Linear(hidden, hidden)
        self.kv = nn.Linear(hidden, hidden)
        self.patch_emb = nn.Sequential(nn.Linear(2 * n_patch, hidden), nn.GELU()) if n_patch else None
        self.nbr_emb = nn.Linear(2, hidden)
        self.static_emb = nn.Linear(4 + 2, hidden)
        self.station_emb = nn.Linear(2, hidden)
        self.gate = nn.Linear(2 * hidden, hidden)
        self.coarse_in = nn.Sequential(nn.Linear(3 + 4 + 2, hidden), nn.GELU())
        self.coarse_head = nn.Linear(hidden, 1)
        self.trunk = _Trunk(hidden, layers, attn_layers, heads, dropout)

    def forward(self, x, valid, clim, nbr, patch, pvalid, static, elev, station, smask):
        b, w = x.shape
        vm = valid.to(x.dtype)
        x = x * vm
        low, low_frac = causal_mean(x, valid, self.k_low)
        resid = (x - low) * vm
        nmean, nmax = nbr[:, 0], nbr[:, 1]

        # --- multi-scale branches (causal trailing aggregates at each scale) ---------------------
        outs = []
        for s, branch in zip(self.scales, self.branches):
            cols = []
            for series in (x, clim, nmean, nmax, resid):
                agg, _ = causal_mean(series, valid if series is x or series is resid else torch.ones_like(valid), s)
                cols.append(agg)
            _, frac = causal_mean(x, valid, s)
            cols.append(frac)
            outs.append(branch(torch.stack(cols, 1)))                          # (B, W, h)
        feats = torch.stack(outs, 2) + self.scale_emb.weight[None, None]       # (B, W, S, h)
        logits = (self.q(feats[:, :, 0:1]) * self.kv(feats)).sum(-1) / self.hidden ** 0.5   # (B, W, S)
        if self.disabled_scales:
            keep = torch.ones(len(self.scales), dtype=torch.bool, device=x.device)
            keep[list(self.disabled_scales)] = False
            if keep.any():
                logits = logits.masked_fill(~keep, float("-inf"))
        attn = torch.softmax(logits, -1)
        fused = (attn.unsqueeze(-1) * feats).sum(2)                            # (B, W, h)

        # --- intermediate fusion of neighbourhood / static / station embeddings --------------------
        ctx = self.nbr_emb(nbr.transpose(1, 2))
        if self.patch_emb is not None:
            pv = pvalid.to(x.dtype)
            ctx = ctx + self.patch_emb(torch.cat([patch * pv, pv], 1).transpose(1, 2))
        ctx = ctx + self.static_emb(torch.cat([static, elev.unsqueeze(1).expand(b, w, 2)], -1))
        sm = smask.to(x.dtype).unsqueeze(1).expand(b, w)
        ctx = ctx + self.station_emb(torch.stack([station * sm, sm], -1))
        gate = torch.sigmoid(self.gate(torch.cat([fused, ctx], -1)))
        h = fused + gate * ctx

        # --- coarse (trend + seasonal) stream feeds the fine stream; also reconstructs the clean trend
        coarse_h = self.coarse_in(torch.cat(
            [torch.stack([clim, low, low_frac], -1), static, elev.unsqueeze(1).expand(b, w, 2)], -1))
        out = self.trunk(h + coarse_h)
        out["coarse_pred"] = F.softplus(self.coarse_head(coarse_h).squeeze(-1))
        out["scale_attn"] = attn
        return out
