"""Gate 4 networks: the spatial component, the temporal component and the plain GRU baseline.

Every network sees only what its component is allowed to see:

spatial    one day, a (2R+1) x (2R+1) patch around the target cell. The target cell and every cell closer than
           ``hidden_radius`` are multiplied by zero INSIDE ``forward`` (value and validity channels), so no
           caller can leak them, whatever it puts in those positions.
temporal   the target cell's own previous ``H`` days (never the target day) plus season and climatology.
plain GRU  the target cell's own previous ``H`` days only; a point forecast.

Spatial and temporal output a zero-inflated Gamma for the day's rainfall: a probability of rain and, if wet,
a Gamma shape and scale. Rainfall is measured in units of ``unit`` mm (the client's normalization scale
turned back into mm), so one set of weights serves every client. The score is the surprise (negative log
tail probability) of the observed value under that distribution; see ``surprise``.
"""

from __future__ import annotations

import math
from typing import Tuple

import torch
from torch import nn
import torch.nn.functional as F

STATIC_DIM = 4        # sin(doy), cos(doy), log1p(climatology)/scale, log1p(heavy threshold)/scale


def hidden_keep_mask(radius: int, hidden_radius: float) -> torch.Tensor:
    """(P, P) float: 0 inside ``hidden_radius`` of the centre (the centre included), 1 elsewhere."""
    k = torch.arange(-radius, radius + 1, dtype=torch.float32)
    d = torch.sqrt(k[:, None] ** 2 + k[None, :] ** 2)
    return (d > hidden_radius).float()


class SpatialNet(nn.Module):
    def __init__(self, radius: int = 6, hidden_radius: float = 2.0, width: int = 32, dense: int = 128):
        super().__init__()
        self.radius, self.hidden_radius = int(radius), float(hidden_radius)
        p = 2 * self.radius + 1
        self.register_buffer("keep", hidden_keep_mask(self.radius, self.hidden_radius)[None, None])
        self.conv = nn.Sequential(
            nn.Conv2d(2, width, 3, padding=1), nn.GELU(),
            nn.Conv2d(width, width, 3, padding=1), nn.GELU(),
            nn.Conv2d(width, width, 3, padding=1), nn.GELU(),
        )
        self.fc = nn.Sequential(nn.Linear(width * p * p + STATIC_DIM, dense), nn.GELU(), nn.Linear(dense, dense), nn.GELU())
        self.head = nn.Linear(dense, 3)
        nn.init.zeros_(self.head.weight)
        with torch.no_grad():
            self.head.bias.copy_(torch.tensor([0.0, 0.0, 0.0]))

    def forward(self, patch: torch.Tensor, valid: torch.Tensor, static: torch.Tensor) -> torch.Tensor:
        """patch, valid: (B, P, P); static: (B, STATIC_DIM). Returns raw (B, 3) head outputs."""
        x = torch.stack([patch, valid], dim=1) * self.keep
        h = self.conv(x).flatten(1)
        return self.head(self.fc(torch.cat([h, static], dim=1)))


class TemporalGRU(nn.Module):
    def __init__(self, hidden: int = 64, dense: int = 64):
        super().__init__()
        self.gru = nn.GRU(2, hidden, batch_first=True)               # one direction, reads days oldest -> newest
        self.fc = nn.Sequential(nn.Linear(hidden + STATIC_DIM, dense), nn.GELU())
        self.head = nn.Linear(dense, 3)
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)

    def forward(self, hist: torch.Tensor, valid: torch.Tensor, static: torch.Tensor) -> torch.Tensor:
        """hist, valid: (B, H) previous H days of the cell, oldest first. Returns raw (B, 3)."""
        _, h = self.gru(torch.stack([hist, valid], dim=2))
        return self.head(self.fc(torch.cat([h[-1], static], dim=1)))


class PlainGRU(nn.Module):
    """Baseline: a GRU over the cell's own previous days and nothing else; a point forecast of log1p(rain)/scale."""

    def __init__(self, hidden: int = 64):
        super().__init__()
        self.gru = nn.GRU(2, hidden, batch_first=True)
        self.out = nn.Linear(hidden, 1)

    def forward(self, hist: torch.Tensor, valid: torch.Tensor, static: torch.Tensor = None) -> torch.Tensor:
        _, h = self.gru(torch.stack([hist, valid], dim=2))
        return self.out(h[-1])[:, 0]


# ---------------------------------------------------------------------------------------------- zero-inflated Gamma

def zig_params(raw: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """raw (B, 3) -> (logit of P(wet), Gamma shape k, Gamma scale theta), in units of ``unit`` mm."""
    return raw[:, 0], F.softplus(raw[:, 1]) + 0.05, F.softplus(raw[:, 2]) + 1e-3


def nll(raw: torch.Tensor, mm: torch.Tensor, unit: torch.Tensor, wet_mm: float = 0.1) -> torch.Tensor:
    """Negative log likelihood (B,) of observed rainfall ``mm`` (B,) under the head output."""
    logit, k, theta = zig_params(raw.float())
    wet = mm > wet_mm
    y = (mm / unit).clamp_min(wet_mm / 1e3)
    log_gamma = (k - 1.0) * torch.log(y) - y / theta - torch.lgamma(k) - k * torch.log(theta)
    ll = torch.where(wet, F.logsigmoid(logit) + log_gamma, F.logsigmoid(-logit))
    return -ll


@torch.no_grad()
def surprise(raw: torch.Tensor, mm: torch.Tensor, unit: torch.Tensor, wet_mm: float = 0.1) -> torch.Tensor:
    """Anomaly score (B,) = -log of the two-sided tail probability of the observation. Higher = more surprising.

    Dry observation (<= wet_mm): the probability of a day this dry, ``1 - P(wet)``.
    Wet observation: the smaller of P(rain at least this heavy) and P(rain at most this heavy).
    """
    logit, k, theta = zig_params(raw.float())
    p_wet, p_dry = torch.sigmoid(logit), torch.sigmoid(-logit)
    y = (mm / unit).clamp_min(wet_mm / 1e3)
    z = y / theta
    upper = p_wet * torch.special.gammaincc(k, z)
    lower = p_dry + p_wet * torch.special.gammainc(k, z)
    tail = torch.where(mm > wet_mm, torch.minimum(upper, lower), p_dry)
    return -torch.log(tail.clamp_min(1e-30))


def season_features(doy: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
    ang = 2 * math.pi * doy.float() / 365.25
    return torch.sin(ang), torch.cos(ang)
