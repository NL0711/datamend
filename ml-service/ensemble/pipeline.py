"""FusionPipeline: branches -> label-free normalization -> fusion rule -> clean-validation threshold.

Data discipline (enforced by tests): normalizers are fit on clean windows from **training years**, the
operating threshold on clean windows from **validation years**, and nothing here ever sees test data.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from ensemble.branches import Branch, RuleBranch, StatBranch, TrainerBranch
from ensemble.fusion import RULES, LikelihoodNormalizer, RankNormalizer, calibrate_threshold, fuse
from ensemble.statbaseline import StatBaseline
from training import artifact
from training.sampler import Batch

log = logging.getLogger(__name__)


@dataclass
class FusionConfig:
    rule: str = "mean_rank"            # mean_rank | max | prob_avg | owa
    owa_orness: float = 0.7
    threshold_method: str = "fpr"      # fpr | events
    target_fpr: float = 0.01
    max_events_per_1000: float = 5.0


class FusionPipeline:
    def __init__(self, branches: Sequence[Branch], config: Optional[FusionConfig] = None):
        names = [b.name for b in branches]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate branch names: {names}")
        self.branches, self.config = list(branches), config or FusionConfig()
        if self.config.rule not in RULES:
            raise ValueError(f"Unknown fusion rule {self.config.rule!r}; choose from {RULES}")
        self.rank: Dict[str, RankNormalizer] = {}
        self.lik: Dict[str, LikelihoodNormalizer] = {}
        self.threshold_info: Optional[dict] = None
        self._warned: set = set()

    # -- scoring --------------------------------------------------------------------------------
    def raw(self, b: Batch) -> Dict[str, np.ndarray]:
        cache: Dict = {}
        out = {}
        for br in self.branches:
            r = br.raw(b, cache)
            if r is None:
                if br.name not in self._warned:
                    log.warning("branch %r is unavailable for this batch and is skipped", br.name)
                    self._warned.add(br.name)
                continue
            out[br.name] = np.asarray(r, float)
        return out

    def fit_normalizers(self, batches: Iterable[Batch]) -> None:
        """Fit every branch's normalizer on **clean** calibration windows (call with training years)."""
        raws: Dict[str, List[np.ndarray]] = {}
        valids: List[np.ndarray] = []
        for b in batches:
            if b.labels.any():
                raise ValueError("calibration batches must be clean (inject_rate=0)")
            for k, v in self.raw(b).items():
                raws.setdefault(k, []).append(v)
            valids.append(b.valid if b.valid is not None else np.ones(b.labels.shape, bool))
        valid = np.concatenate(valids)
        for br in self.branches:
            if br.name not in raws:
                continue
            clean = np.concatenate(raws[br.name])
            self.rank[br.name] = RankNormalizer().fit(clean, valid)
            if br.norm == "likelihood":
                self.lik[br.name] = LikelihoodNormalizer().fit(clean, valid)

    def normalized(self, b: Batch, raw: Optional[Dict[str, np.ndarray]] = None) -> Tuple[Dict, Dict]:
        """Per active branch: percentile rank, and probability (likelihood branches) or rank."""
        raw = raw if raw is not None else self.raw(b)
        ranks, probs = {}, {}
        for name, r in raw.items():
            if name not in self.rank:
                raise RuntimeError(f"branch {name!r} was not fit; call fit_normalizers first")
            ranks[name] = self.rank[name].transform(r)
            probs[name] = self.lik[name].transform(r) if name in self.lik else ranks[name]
        return ranks, probs

    def fuse_normalized(self, ranks: Dict, probs: Dict, rule: Optional[str] = None, drop: Sequence[str] = ()) -> np.ndarray:
        keep = [k for k in ranks if k not in drop]
        return fuse({k: ranks[k] for k in keep}, {k: probs[k] for k in keep}, rule or self.config.rule,
                    self.config.owa_orness)

    def fuse(self, b: Batch, rule: Optional[str] = None, drop: Sequence[str] = ()) -> np.ndarray:
        ranks, probs = self.normalized(b)
        return self.fuse_normalized(ranks, probs, rule, drop)

    # -- threshold ------------------------------------------------------------------------------
    def fit_threshold(self, batches: Iterable[Batch], rule: Optional[str] = None, drop: Sequence[str] = ()) -> dict:
        """Operating threshold from **clean validation-year** windows."""
        fused, valid = [], []
        for b in batches:
            if b.labels.any():
                raise ValueError("threshold calibration batches must be clean (inject_rate=0)")
            fused.append(self.fuse(b, rule, drop))
            valid.append(b.valid if b.valid is not None else np.ones(b.labels.shape, bool))
        c = self.config
        info = calibrate_threshold(np.concatenate(fused), np.concatenate(valid), c.threshold_method,
                                   c.target_fpr, c.max_events_per_1000)
        if rule is None and not drop:
            self.threshold_info = info
        return info

    def flags(self, b: Batch) -> np.ndarray:
        if self.threshold_info is None:
            raise RuntimeError("call fit_threshold on clean validation windows first")
        return self.fuse(b) >= self.threshold_info["threshold"]

    # -- persistence ----------------------------------------------------------------------------
    def save(self, out_dir: str | Path) -> Path:
        root = Path(out_dir)
        root.mkdir(parents=True, exist_ok=True)
        specs, saved = [], set()
        for br in self.branches:
            if isinstance(br, TrainerBranch):
                if br.dirname not in saved:
                    artifact.save(br.art, root / br.dirname)
                    saved.add(br.dirname)
                specs.append({"type": "trainer", "name": br.name, "dir": br.dirname, "stream": br.stream, "norm": br.norm})
            elif isinstance(br, StatBranch):
                np.save(root / "stat_bound.npy", br.baseline.bound)
                specs.append({"type": "stat", "name": br.name, "years": br.baseline.years})
            elif isinstance(br, RuleBranch):
                specs.append({"type": "rule", "name": br.name})
            else:
                raise TypeError(f"cannot persist branch type {type(br).__name__}")
        arrays = {f"rank__{k}": v.ref for k, v in self.rank.items()}
        arrays.update({f"lik__{k}": np.array([v.ref, v.temperature]) for k, v in self.lik.items()})
        np.savez(root / "normalizers.npz", **arrays)
        (root / "fusion.json").write_text(json.dumps(
            {"config": asdict(self.config), "branches": specs, "threshold": self.threshold_info}, indent=2))
        return root

    @classmethod
    def load(cls, path: str | Path, device: str = "cpu") -> "FusionPipeline":
        root = Path(path)
        meta = json.loads((root / "fusion.json").read_text())
        arts: Dict[str, artifact.Artifact] = {}
        branches: List[Branch] = []
        for sp in meta["branches"]:
            if sp["type"] == "trainer":
                if sp["dir"] not in arts:
                    arts[sp["dir"]] = artifact.load(root / sp["dir"], device)
                branches.append(TrainerBranch(sp["name"], arts[sp["dir"]], sp["stream"], sp["norm"], sp["dir"]))
            elif sp["type"] == "stat":
                branches.append(StatBranch(StatBaseline(np.load(root / "stat_bound.npy"), sp["years"])))
            elif sp["type"] == "rule":
                branches.append(RuleBranch())
        pipe = cls(branches, FusionConfig(**meta["config"]))
        z = np.load(root / "normalizers.npz")
        for k in z.files:
            kind, name = k.split("__", 1)
            if kind == "rank":
                pipe.rank[name] = RankNormalizer(z[k])
            else:
                pipe.lik[name] = LikelihoodNormalizer(float(z[k][0]), float(z[k][1]))
        pipe.threshold_info = meta["threshold"]
        return pipe
