"""Losses for zero-inflated, heavy-tailed rainfall."""

from __future__ import annotations

from typing import Dict

import torch


def tweedie_deviance(y: torch.Tensor, mu: torch.Tensor, p: float = 1.6) -> torch.Tensor:
    """Mean unit Tweedie deviance (1 < p < 2), y >= 0, mu > 0. Handles y == 0 exactly."""
    mu = mu.clamp_min(1e-6)
    a, b = 2 - p, 1 - p
    d = 2 * (y.clamp_min(0).pow(a) / (b * a) - y * mu.pow(b) / b + mu.pow(a) / a)
    return d.mean()


def zig_nll(x_mm: torch.Tensor, out: Dict[str, torch.Tensor], wet_threshold: float = 0.1) -> torch.Tensor:
    """Per-element negative log-likelihood under a zero-inflated Gamma (hurdle) distribution.

    ``out``: ``pi_logit`` (P(dry)), ``log_alpha`` (Gamma shape), ``log_beta`` (Gamma rate, 1/mm).
    Dry days (< threshold) contribute -log P(dry); wet days contribute -log P(wet) - log Gamma pdf.
    Used both as the training loss on clean targets and as a calibrated anomaly score on
    observed values: a heavy-tail-aware surprise, not a squared error.
    """
    log_pi = torch.nn.functional.logsigmoid(out["pi_logit"])
    log_1m = torch.nn.functional.logsigmoid(-out["pi_logit"])
    lb = out["log_beta"].clamp(-6, 3)
    a = out["log_alpha"].clamp(-3, 4).exp()
    xw = x_mm.clamp_min(wet_threshold)
    log_gamma = a * lb + (a - 1) * xw.log() - lb.exp() * xw - torch.lgamma(a)
    return torch.where(x_mm >= wet_threshold, -(log_1m + log_gamma), -log_pi)
