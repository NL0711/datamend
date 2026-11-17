"""Gate 5: fuse four component scores into one score per cell-day.

Features  rules, slow, spatial_s<seed>, temporal_s<seed>. Each score is mapped with log1p (scores are >= 0
          and heavy-tailed) and standardized with the mean and standard deviation of the fit rows. A missing
          component score becomes 0 after standardizing (the average case), never a fault signal.
Fit data  Synthetic faults of the validation years ``years.fusion_fit``, cells of training clients only.
          Positives: fault cell-days. Negatives: every other scored cell-day, protected extremes included (so
          the fusion learns that agreement among components, not a large value alone, signals a fault);
          ambiguous extremes are left out. Thresholds are NOT set here: see ``thresholds_for`` in qc.evaluate,
          which uses clean threshold-year scores.

Variants (spec section 7), all fitted on the same rows:
  logistic    one shared logistic regression (the main fusion). Score = the log-odds.
  mean        plain average of the four standardized scores (no fitting beyond the standardization).
  or          OR of component flags: every component's score becomes the tail probability of that score on
              clean threshold years; the fused score is the smallest tail probability, as -log10. A cell-day
              is flagged when any component is that rare.
  boosted     histogram gradient-boosted trees on the four standardized scores. Score = log-odds.
  per_client  one logistic regression per training client; unseen clients use the shared one.

Fitted fusions are saved to ``<run>/fusion/<variant>_s<seed>.*``; fused scores go in the score store as
``fusion_<variant>_s<seed>`` so every metric in qc.evaluate applies unchanged.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

from qc.evaluate import group_cells, score_store
from qc.extremes import find_extremes
from qc.prepare import Prepared
from qc.scoring import ScoreStore
from qc.splits import assert_years_allowed

log = logging.getLogger(__name__)
BASE = ("rules", "slow", "spatial", "temporal")
VARIANTS = ("logistic", "mean", "or", "boosted", "per_client")


def component_names(seed: int, base: Sequence[str] = BASE) -> List[str]:
    """Store names of the four inputs: rules and slow are untrained; spatial and temporal carry the seed."""
    return [b if b in ("rules", "slow") else f"{b}_s{seed}" for b in base]


def load_features(store: ScoreStore, names: Sequence[str], tag: str, year: int) -> np.ndarray:
    """(T, n_land, F) log1p of the component scores of one year; NaN where a component did not score."""
    return np.log1p(np.stack([store.load(n, tag, year) for n in names], axis=-1))


@dataclass
class FusionFit:
    seed: int
    names: List[str]
    mu: np.ndarray
    sd: np.ndarray
    fit_years: List[int]
    n_rows: int
    n_positive: int
    logistic: Dict                       # coef (F,), intercept
    boosted: HistGradientBoostingClassifier
    per_client: Dict[int, Dict]          # client -> coef, intercept
    tail_sorted: List[np.ndarray]        # per component, sorted clean threshold-year scores (the "or" variant)
    scale_limit: float = 50.0

    def standardize(self, feats: np.ndarray) -> np.ndarray:
        z = (feats - self.mu) / self.sd
        return np.nan_to_num(z, nan=0.0)

    def score(self, variant: str, feats: np.ndarray, cell_client: Optional[np.ndarray] = None) -> np.ndarray:
        """feats (T, n, F) from ``load_features``. Returns (T, n) float32; NaN where no component scored."""
        z = self.standardize(feats)
        if variant == "logistic":
            out = z @ self.logistic["coef"] + self.logistic["intercept"]
        elif variant == "mean":
            out = z.mean(axis=-1)
        elif variant == "or":
            u = []
            for f in range(feats.shape[-1]):
                s = self.tail_sorted[f]
                raw = np.expm1(feats[..., f])
                frac = 1.0 - np.searchsorted(s, np.nan_to_num(raw, nan=0.0), side="left") / s.size
                u.append(-np.log10(np.maximum(frac, 0.5 / s.size)))
            out = np.max(u, axis=0)
        elif variant == "boosted":
            flat = z.reshape(-1, z.shape[-1])
            p = np.clip(self.boosted.predict_proba(flat)[:, 1], 1e-6, 1 - 1e-6)
            out = np.log(p / (1 - p)).reshape(z.shape[:-1])
        elif variant == "per_client":
            if cell_client is None:
                raise ValueError("per_client fusion needs cell_client")
            out = z @ self.logistic["coef"] + self.logistic["intercept"]          # unseen clients: the shared fusion
            for c, m in self.per_client.items():
                sel = cell_client == c
                out[:, sel] = z[:, sel] @ m["coef"] + m["intercept"]
        else:
            raise ValueError(f"unknown variant {variant!r}")
        out = np.asarray(out, np.float32)
        out[~np.isfinite(feats).any(axis=-1)] = np.nan
        return out

    def probability(self, feats: np.ndarray) -> np.ndarray:
        """Fault probability of the shared logistic fusion, calibrated to the synthetic fault rate only."""
        return 1.0 / (1.0 + np.exp(-self.score("logistic", feats).astype(np.float64)))

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        doc = {"seed": self.seed, "names": self.names, "mu": self.mu.tolist(), "sd": self.sd.tolist(),
               "fit_years": self.fit_years, "n_rows": self.n_rows, "n_positive": self.n_positive,
               "logistic": {"coef": self.logistic["coef"].tolist(), "intercept": float(self.logistic["intercept"])},
               "per_client": {str(c): {"coef": m["coef"].tolist(), "intercept": float(m["intercept"])} for c, m in self.per_client.items()}}
        (folder / f"logistic_s{self.seed}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
        joblib.dump({"boosted": self.boosted, "tail_sorted": self.tail_sorted}, folder / f"other_s{self.seed}.joblib")

    @classmethod
    def load(cls, folder: Path, seed: int) -> "FusionFit":
        doc = json.loads((folder / f"logistic_s{seed}.json").read_text(encoding="utf-8"))
        other = joblib.load(folder / f"other_s{seed}.joblib")
        return cls(seed, doc["names"], np.array(doc["mu"]), np.array(doc["sd"]), doc["fit_years"], doc["n_rows"], doc["n_positive"],
                   {"coef": np.array(doc["logistic"]["coef"]), "intercept": doc["logistic"]["intercept"]}, other["boosted"],
                   {int(c): {"coef": np.array(m["coef"]), "intercept": m["intercept"]} for c, m in doc["per_client"].items()},
                   other["tail_sorted"])


def _logit_fit(x, y, w, C):
    m = LogisticRegression(C=C, max_iter=500).fit(x, y, sample_weight=w)
    return {"coef": m.coef_[0].astype(np.float64), "intercept": float(m.intercept_[0])}


def fit_fusion(p: Prepared, seed: int, store: Optional[ScoreStore] = None, base: Sequence[str] = BASE) -> FusionFit:
    """Fit every variant on the synthetic faults of ``years.fusion_fit``. Uses no test-year or threshold-year benchmark data
    (the "or" variant uses clean threshold-year scores, never labels)."""
    from qc.benchmark import load_bench_year
    cfg, store = p.cfg, store or score_store(p)
    years = list(p.split.years["fusion_fit"])
    assert_years_allowed("fusion fit", years, p.split, "val")
    if set(years) & set(p.split.years["threshold"]):
        raise RuntimeError("fusion fit years overlap the threshold years")
    names = component_names(seed, base)
    cells = group_cells(p, "seen")
    rng = np.random.default_rng([int(cfg.seed), seed, 5])
    xs, ys, ws, cl = [], [], [], []
    max_rows = int(cfg.fusion.max_rows)
    per_year = max(max_rows // len(years), 1)
    for y in years:
        feats = load_features(store, names, "val", y)
        bench = load_bench_year(p, "val", y)
        lab = bench.faults.labels()
        keep = np.isfinite(feats).any(axis=-1) & ~bench.extremes.ambiguous & cells[None, :]
        pos = np.nonzero((keep & lab).ravel())[0]
        neg = np.nonzero((keep & ~lab).ravel())[0]
        take = min(neg.size, max(per_year - pos.size, 1))
        neg_s = rng.choice(neg, take, replace=False) if take < neg.size else neg
        w_neg = neg.size / max(neg_s.size, 1)                    # undo the subsampling so probabilities stay calibrated
        flat = feats.reshape(-1, feats.shape[-1])
        for idx, label, w in ((pos, 1, 1.0), (neg_s, 0, w_neg)):
            xs.append(flat[idx]); ys.append(np.full(idx.size, label, np.int8)); ws.append(np.full(idx.size, w, np.float32))
            cl.append(p.cell_client[idx % feats.shape[1]])
    x, yv, w, client = np.concatenate(xs), np.concatenate(ys), np.concatenate(ws), np.concatenate(cl)
    if yv.sum() == 0:
        raise RuntimeError("no fault cell-days in the fusion fit years")
    mu, sd = np.nanmean(x, axis=0, dtype=np.float64), np.nanstd(x, axis=0, dtype=np.float64) + 1e-6
    z = np.nan_to_num((x - mu) / sd, nan=0.0)
    C = float(cfg.fusion.C)
    shared = _logit_fit(z, yv, w, C)
    boosted = HistGradientBoostingClassifier(max_iter=int(cfg.fusion.boosted_iter), learning_rate=0.1, max_depth=4,
                                             random_state=seed).fit(z, yv, sample_weight=w)
    per_client = {}
    for c in p.split.train_clients:
        m = client == c
        if yv[m].sum() >= 10 and (yv[m] == 0).any():
            per_client[c] = _logit_fit(z[m], yv[m], w[m], C)
    tails = []
    for f, n in enumerate(names):
        ref = []
        for y in p.split.years["threshold"]:
            ex = find_extremes(p.store.year(y), p.stats.heavy_mm, p.grid, int(cfg.extremes.min_cells))
            s = store.load(n, "clean", y)
            keep = ~ex.protected & ~ex.ambiguous & cells[None, :] & np.isfinite(s)
            ref.append(s[keep])
        tails.append(np.sort(np.concatenate(ref)))
    return FusionFit(seed, names, mu, sd, years, int(yv.size), int(yv.sum()), shared, boosted, per_client, tails)


def fused_name(variant: str, seed: int) -> str:
    return f"fusion_{variant}_s{seed}"


def apply_fusion(p: Prepared, fit: FusionFit, splits: Sequence[str] = ("val",), variants: Sequence[str] = VARIANTS,
                 store: Optional[ScoreStore] = None, overwrite: bool = False) -> None:
    """Write fused scores for the benchmark years of ``splits`` and for the clean threshold years."""
    store = store or score_store(p)
    jobs = [(s, y) for s in splits for y in p.split.years[s]] + [("clean", y) for y in p.split.years["threshold"]]
    for tag, year in jobs:
        todo = [v for v in variants if overwrite or not store.has(fused_name(v, fit.seed), tag, year)]
        if not todo:
            continue
        feats = load_features(store, fit.names, tag, year)
        for v in todo:
            store.save(fused_name(v, fit.seed), tag, year, fit.score(v, feats, p.cell_client))
