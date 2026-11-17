"""LocalTrainer: the one training seam. Central today, a Flower/FLARE client tomorrow.

``get_weights`` / ``set_weights`` / ``fit`` / ``validate`` are what a federated client
needs, so adding FL later means wrapping this class, not rewriting it. GPU-ready:
device auto-select, AMP, AdamW + warmup/cosine schedule, EMA weights, background
batch prefetch so the CPU sampler overlaps GPU compute.
"""

from __future__ import annotations

import copy
import math
import queue
import threading
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn.functional as F

from training.injection import KINDS
from training.losses import tweedie_deviance, zig_nll
from training.model import build_model
from training.sampler import Batch, WindowSampler
from training.transform import RainfallTransform


@dataclass
class TrainConfig:
    arch: str = "rainnet"          # "rainnet" | "scalenet" (multi-scale temporal) | "msnet" (multi-granularity) | "lstm_ae"
    scales: List[int] = field(default_factory=lambda: [1, 5, 30])  # scalenet aggregation scales in days (first must be 1)
    single_scale: bool = False     # scalenet ablation: keep only the daily branch
    patch: int = 3                 # scalenet neighbourhood patch size (0, 3 or 5), centre excluded
    coarse_weight: float = 0.5     # scalenet: weight of the coarse (trend) reconstruction loss
    use_elevation: bool = False    # needs an elevation array (--elevation); otherwise logged and skipped
    use_stations: bool = False     # optional station branch; stub unless station data is provided
    coarse_blocks: List[int] = field(default_factory=list)  # msnet proxy sources: block sizes in cells
    source_dropout: float = 0.0    # msnet: P(hide each granularity source) per training window
    window: int = 60
    hidden: int = 128
    layers: int = 2                # BiLSTM layers (rainnet)
    attn_layers: int = 1           # transformer encoder layers (rainnet)
    heads: int = 4
    dropout: float = 0.1
    latent: int = 16               # lstm_ae only
    lr: float = 2e-3
    weight_decay: float = 1e-2
    warmup_steps: int = 100
    batch_size: int = 256
    steps_per_epoch: int = 300
    ema: float = 0.999             # 0 disables
    amp: bool = False              # mixed precision (CUDA only)
    device: str = "auto"
    prefetch: bool = True
    loss: str = "mse"              # lstm_ae only: "mse" | "tweedie"
    tweedie_p: float = 1.6
    anomaly_weight: float = 1.0    # rainnet: weight of the supervised anomaly head
    pos_weight: float = 4.0
    corruption_rate: float = 0.5   # share of training windows with injected anomalies
    train_kinds: Optional[List[str]] = None  # None = all; exclude kinds to test generalization
    seed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def featurize(b: Batch, tf: RainfallTransform, arch: str) -> Tuple[np.ndarray, ...]:
    """Model-space inputs as the tuple of arrays the model's forward() takes.

    lstm_ae: ([x, nbr mean],). rainnet: ([x, nbr mean, nbr max, clim, sin, cos, lat, lon],).
    msnet: (target [x, clim, sin, cos, lat, lon], sources (n,S,W), source meta, source mask).
    """
    if arch == "scalenet":
        n, w = b.x_mm.shape[:2]
        ones = np.ones((n, w), bool)
        valid = ones if b.valid is None else b.valid
        patch = np.zeros((n, 0, w), np.float32) if b.patch is None else b.patch
        pvalid = np.zeros((n, 0, w), bool) if b.patch_valid is None else b.patch_valid
        stm = np.zeros(n, bool) if b.station_mask is None else b.station_mask
        st = np.zeros((n, w), np.float32) if b.station_mm is None else b.station_mm
        elev = np.zeros(n, np.float32) if b.elev is None else b.elev
        eok = np.zeros(n, bool) if b.elev_ok is None else b.elev_ok
        nbr = tf.forward(np.stack([b.x_mm[..., 1], b.aux_mm[..., 0]], 1))
        return (tf.forward(b.x_mm[..., 0]), valid, tf.forward(b.aux_mm[..., 1]), nbr,
                tf.forward(patch) * pvalid, pvalid, b.static,
                np.stack([elev, eok.astype(np.float32)], -1), tf.forward(st) * stm[:, None], stm)
    if arch == "msnet":
        tgt = np.concatenate([tf.forward(b.x_mm[..., :1]), tf.forward(b.aux_mm[..., 1:]), b.static], axis=-1)
        return tgt, tf.forward(b.src_mm) * b.src_mask[:, :, None], b.src_meta, b.src_mask
    xs = tf.forward(b.x_mm)
    if arch == "lstm_ae":
        return (xs,)
    return (np.concatenate([xs, tf.forward(b.aux_mm), b.static], axis=-1),)


class LocalTrainer:
    def __init__(self, transform: RainfallTransform, config: TrainConfig):
        torch.manual_seed(config.seed)
        self.transform, self.config = transform, config
        cuda = torch.cuda.is_available()
        self.device = torch.device(("cuda" if cuda else "cpu") if config.device == "auto" else config.device)
        self.amp = bool(config.amp and self.device.type == "cuda")
        self.model = build_model(config).to(self.device)
        self.ema = copy.deepcopy(self.model).eval() if config.ema > 0 else None
        self.opt = torch.optim.AdamW(self.model.parameters(), lr=config.lr, weight_decay=config.weight_decay)
        self.scaler = torch.amp.GradScaler("cuda", enabled=self.amp)
        self.sched: Optional[torch.optim.lr_scheduler.LambdaLR] = None
        self.step = 0

    @property
    def inference_model(self) -> torch.nn.Module:
        return self.ema if self.ema is not None else self.model

    # -- federated-ready surface ------------------------------------------------
    def get_weights(self) -> List[np.ndarray]:
        return [v.detach().cpu().numpy() for v in self.model.state_dict().values()]

    def set_weights(self, weights: List[np.ndarray]) -> None:
        keys = self.model.state_dict().keys()
        self.model.load_state_dict({k: torch.as_tensor(w) for k, w in zip(keys, weights)})
        if self.ema is not None:
            self.ema.load_state_dict(self.model.state_dict())

    def state_dict(self) -> dict:
        return self.inference_model.state_dict()

    def load_state(self, state: dict) -> None:
        self.model.load_state_dict(state)
        if self.ema is not None:
            self.ema.load_state_dict(state)

    # -- internals -----------------------------------------------------------------
    def _forward(self, model, x: Tuple[torch.Tensor, ...]):
        with torch.autocast(device_type=self.device.type, enabled=self.amp):
            out = model(*x)
        return {k: v.float() for k, v in out.items()} if isinstance(out, dict) else out.float()

    def _x(self, b: Batch) -> Tuple[torch.Tensor, ...]:
        arrays = featurize(b, self.transform, self.config.arch)
        return tuple(torch.from_numpy(np.ascontiguousarray(a)).to(self.device)
                     if a.dtype == bool else torch.from_numpy(np.ascontiguousarray(a)).float().to(self.device)
                     for a in arrays)

    def _loss(self, b: Batch, model) -> torch.Tensor:
        c, dev = self.config, self.device
        out = self._forward(model, self._x(b))
        if c.arch == "lstm_ae":
            y = torch.from_numpy(self.transform.forward(b.clean_mm)).float().to(dev)
            if c.loss == "tweedie":
                s = self.transform.scale
                return tweedie_deviance(torch.expm1(y * s), torch.expm1(out * s), c.tweedie_p)
            return F.mse_loss(out, y)
        clean = torch.from_numpy(b.clean_mm).float().to(dev)
        lab = torch.from_numpy(b.labels).float().to(dev)
        valid = torch.from_numpy(b.valid).float().to(dev) if b.valid is not None else torch.ones_like(clean)
        denom = valid.sum().clamp_min(1.0)
        nll = (zig_nll(clean, out) * valid).sum() / denom   # NaN days (valid=False) do not contribute
        bce = (F.binary_cross_entropy_with_logits(out["anom_logit"], lab, reduction="none",
                                                  pos_weight=torch.tensor(c.pos_weight, device=dev)) * valid).sum() / denom
        loss = nll + c.anomaly_weight * bce
        if c.arch == "scalenet":
            from training.multiscale import causal_mean
            clean_z = torch.from_numpy(self.transform.forward(b.clean_mm)).float().to(dev)
            low, _ = causal_mean(clean_z, valid > 0, 1 if c.single_scale else max(c.scales))
            loss = loss + c.coarse_weight * (((out["coarse_pred"] - low) ** 2) * valid).sum() / denom
        return loss

    def _make_sched(self, total_steps: int) -> None:
        w = max(self.config.warmup_steps, 1)
        fn = lambda s: min(1.0, (s + 1) / w) * (0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * min(s / total_steps, 1.0))))
        self.sched = torch.optim.lr_scheduler.LambdaLR(self.opt, fn)

    @torch.no_grad()
    def _ema_update(self) -> None:
        if self.ema is None:
            return
        d = min(self.config.ema, (1 + self.step) / (10 + self.step))
        for pe, p in zip(self.ema.parameters(), self.model.parameters()):
            pe.lerp_(p, 1 - d)
        for be, b in zip(self.ema.buffers(), self.model.buffers()):
            be.copy_(b)

    def _stream(self, sampler: WindowSampler, steps: int) -> Iterator[Batch]:
        c = self.config
        kinds = tuple(c.train_kinds) if c.train_kinds else KINDS
        make = lambda: sampler.batch(c.batch_size, c.corruption_rate, kinds, c.source_dropout)
        if not c.prefetch:
            for _ in range(steps):
                yield make()
            return
        q: queue.Queue = queue.Queue(maxsize=6)

        def work():
            for _ in range(steps):
                q.put(make())

        threading.Thread(target=work, daemon=True).start()
        for _ in range(steps):
            yield q.get()

    # -- training ------------------------------------------------------------------
    def fit(self, sampler: WindowSampler, epochs: int, total_epochs: Optional[int] = None) -> Dict[str, List[float]]:
        c, history = self.config, {"train_loss": []}
        if self.sched is None:
            self._make_sched((total_epochs or epochs) * c.steps_per_epoch)
        self.model.train()
        for _ in range(epochs):
            total = 0.0
            for b in self._stream(sampler, c.steps_per_epoch):
                loss = self._loss(b, self.model)
                self.opt.zero_grad(set_to_none=True)
                self.scaler.scale(loss).backward()
                self.scaler.unscale_(self.opt)
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                self.scaler.step(self.opt)
                self.scaler.update()
                self.sched.step()
                self.step += 1
                self._ema_update()
                total += loss.item()
            history["train_loss"].append(total / c.steps_per_epoch)
        return history

    @torch.no_grad()
    def scale_attention(self, b: Batch, chunk: int = 1024) -> np.ndarray:
        """scalenet only: (n, W, S) attention over the aggregation scales per timestep."""
        if self.config.arch != "scalenet":
            raise ValueError("scale_attention needs arch='scalenet'")
        model = self.inference_model.eval()
        return np.concatenate([
            self._forward(model, self._x(b.slice(slice(s, s + chunk))))["scale_attn"].cpu().numpy()
            for s in range(0, len(b.x_mm), chunk)])

    @torch.no_grad()
    def score(self, b: Batch, chunk: int = 1024, drop_scales: Sequence[int] = ()) -> Dict[str, np.ndarray]:
        """Raw per-timestep score streams, each (n, W). Higher = more anomalous.

        lstm_ae: ``recon``. rainnet: ``nll`` (ZIG surprise of the observed value), ``head``
        (supervised anomaly logit), ``resid`` (|log1p(expected) - log1p(observed)| in model units).
        """
        model, parts = self.inference_model.eval(), []
        if drop_scales:
            model.disabled_scales = tuple(drop_scales)  # scalenet ablation: mask scales out of the fusion
        try:
            return self._score(model, b, chunk, parts)
        finally:
            if drop_scales:
                model.disabled_scales = ()

    def _score(self, model, b: Batch, chunk: int, parts: list) -> Dict[str, np.ndarray]:
        for s in range(0, len(b.x_mm), chunk):
            sub = b.slice(slice(s, s + chunk))
            out = self._forward(model, self._x(sub))
            obs = torch.from_numpy(sub.x_mm[..., 0]).float().to(self.device)
            if self.config.arch == "lstm_ae":
                x0 = torch.from_numpy(self.transform.forward(sub.x_mm[..., 0])).float().to(self.device)
                parts.append({"recon": (out - x0).abs().cpu().numpy()})
                continue
            mean = torch.sigmoid(-out["pi_logit"]) * out["log_alpha"].clamp(-3, 4).exp() / out["log_beta"].clamp(-6, 3).exp()
            resid = (torch.log1p(mean) - torch.log1p(obs.clamp_min(0))).abs() / self.transform.scale
            ok = torch.from_numpy(sub.valid).to(self.device) if sub.valid is not None else torch.ones_like(obs, dtype=torch.bool)
            nll = torch.where(ok, zig_nll(obs, out), torch.zeros_like(obs))   # NaN days score as "normal"
            head = torch.where(ok, out["anom_logit"], torch.full_like(obs, -10.0))
            parts.append({"nll": nll.cpu().numpy(), "head": head.cpu().numpy(),
                          "resid": torch.where(ok, resid, torch.zeros_like(obs)).cpu().numpy()})
        return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}

    @torch.no_grad()
    def source_attention(self, b: Batch, chunk: int = 1024) -> np.ndarray:
        """msnet only: (n, W, S+1) attention on [null, source_0, ...] per timestep, i.e. which
        granularity the model relied on. Rows sum to 1; unavailable sources get ~0."""
        if self.config.arch != "msnet":
            raise ValueError("source_attention needs arch='msnet'")
        model = self.inference_model.eval()
        return np.concatenate([
            self._forward(model, self._x(b.slice(slice(s, s + chunk))))["src_attn"].cpu().numpy()
            for s in range(0, len(b.x_mm), chunk)])

    @torch.no_grad()
    def validate(self, sampler: WindowSampler, batches: int = 10) -> float:
        """Loss on clean validation windows (uses the inference/EMA weights)."""
        model = self.inference_model.eval()
        return float(np.mean([self._loss(sampler.batch(self.config.batch_size, 0.0), model).item()
                              for _ in range(batches)]))
