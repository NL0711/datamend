"""Models. ``lstm_ae``: legacy bottleneck AE. ``rainnet``: single-scale model. ``msnet``: multi-granularity model."""

from __future__ import annotations

import torch
from torch import nn


class LSTMAutoencoder(nn.Module):
    """Baseline: (target, neighbour-mean) window -> clean target, through a latent bottleneck."""

    def __init__(self, n_features: int = 2, hidden: int = 64, latent: int = 16):
        super().__init__()
        self.encoder = nn.LSTM(n_features, hidden, batch_first=True)
        self.to_latent = nn.Linear(hidden, latent)
        self.from_latent = nn.Linear(latent, hidden)
        self.decoder = nn.LSTM(hidden, hidden, batch_first=True)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h, _) = self.encoder(x)
        z = self.to_latent(h[-1])
        seq = self.from_latent(z).unsqueeze(1).expand(-1, x.shape[1], -1)
        out, _ = self.decoder(seq)
        return nn.functional.softplus(self.head(out).squeeze(-1))


class _Trunk(nn.Module):
    """Shared temporal trunk + heads: local conv -> BiLSTM stack -> self-attention -> heads.

    Per-timestep outputs, no bottleneck:
    - a zero-inflated Gamma distribution for the clean value (``pi_logit`` = P(dry),
      ``log_alpha``, ``log_beta``): a likelihood-based, heavy-tail-aware anomaly score;
    - ``anom_logit``: a supervised point-wise anomaly head trained on injected labels.
    """

    def __init__(self, hidden: int, layers: int, attn_layers: int, heads: int, dropout: float):
        super().__init__()
        self.conv = nn.Conv1d(hidden, hidden, 5, padding=2)
        self.rnn = nn.LSTM(hidden, hidden // 2, num_layers=layers, batch_first=True,
                           bidirectional=True, dropout=dropout if layers > 1 else 0.0)
        if attn_layers:
            layer = nn.TransformerEncoderLayer(hidden, heads, hidden * 2, dropout, activation="gelu",
                                               batch_first=True, norm_first=True)
            self.attn = nn.TransformerEncoder(layer, attn_layers, enable_nested_tensor=False)
        else:
            self.attn = nn.Identity()
        self.norm = nn.LayerNorm(hidden)
        self.zig = nn.Linear(hidden, 3)
        self.anom = nn.Linear(hidden, 1)

    def forward(self, h: torch.Tensor) -> dict:
        h = h + self.conv(h.transpose(1, 2)).transpose(1, 2)
        h, _ = self.rnn(h)
        h = self.norm(self.attn(h))
        z = self.zig(h)
        return {"pi_logit": z[..., 0], "log_alpha": z[..., 1], "log_beta": z[..., 2],
                "anom_logit": self.anom(h).squeeze(-1)}


class RainNet(nn.Module):
    """Single-scale: input (B, W, 8) = [target, nbr mean, nbr max, clim] (log space) + [sin, cos, lat, lon]."""

    def __init__(self, n_features: int = 8, hidden: int = 128, layers: int = 2,
                 attn_layers: int = 1, heads: int = 4, dropout: float = 0.1):
        super().__init__()
        self.inp = nn.Sequential(nn.Linear(n_features, hidden), nn.GELU())
        self.trunk = _Trunk(hidden, layers, attn_layers, heads, dropout)

    def forward(self, x: torch.Tensor) -> dict:
        return self.trunk(self.inp(x))


class MSRainNet(nn.Module):
    """Multi-granularity model: the target stream attends over S sources at every timestep.

    Each source (coarser grid, nearby stations, radar, ...) is encoded by one *shared* encoder
    from [source value, source - target], plus a source-id embedding and a metadata embedding
    (resolution, distance). Per timestep, the target queries all available sources with
    cross-attention. A learned null token is always attendable, so a window with no sources
    degrades to target + climatology instead of failing. Source dropout during training teaches
    the model to cope with any subset.

    forward(tgt (B,W,6), src (B,S,W), meta (B,S,3), mask (B,S) bool) returns the _Trunk heads plus
    ``src_attn`` (B,W,S+1): attention on [null, source_0, ...], i.e. which granularity the model
    relied on, for the explanation layer.
    """

    def __init__(self, tgt_features: int = 6, hidden: int = 128, layers: int = 2, attn_layers: int = 1,
                 heads: int = 4, dropout: float = 0.1, n_sources: int = 2):
        super().__init__()
        self.tgt_in = nn.Sequential(nn.Linear(tgt_features, hidden), nn.GELU())
        self.src_in = nn.Sequential(nn.Linear(2, hidden), nn.GELU())
        self.meta = nn.Linear(3, hidden)
        self.src_id = nn.Embedding(n_sources, hidden)
        self.src_conv = nn.Conv1d(hidden, hidden, 5, padding=2)
        self.null = nn.Parameter(torch.zeros(1, 1, hidden))
        self.xattn = nn.MultiheadAttention(hidden, heads, dropout=dropout, batch_first=True)
        self.trunk = _Trunk(hidden, layers, attn_layers, heads, dropout)

    def forward(self, tgt, src, meta, mask):
        b, w, _ = tgt.shape
        s, hid = src.shape[1], self.null.shape[-1]
        q = self.tgt_in(tgt)                                                   # (B, W, h)
        diff = src - tgt[..., 0].unsqueeze(1)                                  # (B, S, W)
        tok = self.src_in(torch.stack([src, diff], -1))                        # (B, S, W, h)
        tok = tok + self.meta(meta).unsqueeze(2) + self.src_id.weight[None, :, None, :]
        tok = tok.reshape(b * s, w, hid).transpose(1, 2)
        tok = (tok + self.src_conv(tok)).transpose(1, 2).reshape(b, s, w, hid)
        keys = tok.permute(0, 2, 1, 3).reshape(b * w, s, hid)
        keys = torch.cat([self.null.expand(b * w, 1, hid), keys], 1)           # null token first
        avail = mask.unsqueeze(1).expand(b, w, s).reshape(b * w, s)
        pad = torch.cat([torch.zeros(b * w, 1, dtype=torch.bool, device=tgt.device), ~avail], 1)
        ctx, attn = self.xattn(q.reshape(b * w, 1, hid), keys, keys, key_padding_mask=pad,
                               need_weights=True, average_attn_weights=True)
        out = self.trunk(q + ctx.reshape(b, w, hid))
        out["src_attn"] = attn.reshape(b, w, s + 1)
        return out


def build_model(cfg) -> nn.Module:
    if cfg.arch == "lstm_ae":
        return LSTMAutoencoder(2, cfg.hidden, cfg.latent)
    if cfg.arch == "rainnet":
        return RainNet(8, cfg.hidden, cfg.layers, cfg.attn_layers, cfg.heads, cfg.dropout)
    if cfg.arch == "msnet":
        return MSRainNet(6, cfg.hidden, cfg.layers, cfg.attn_layers, cfg.heads, cfg.dropout,
                         n_sources=1 + len(cfg.coarse_blocks))
    if cfg.arch == "scalenet":
        from training.multiscale import ScaleNet  # lazy: multiscale imports _Trunk from here
        scales = [1] if cfg.single_scale else list(cfg.scales)
        return ScaleNet(cfg.hidden, cfg.layers, cfg.attn_layers, cfg.heads, cfg.dropout, scales,
                        cfg.patch ** 2 - 1 if cfg.patch else 0)
    raise ValueError(f"Unknown arch {cfg.arch!r}")
