"""Offline comparison (spec section 6): the existing rainnet, scalenet, msnet and lstm_ae models, scored on the QC benchmark.

What this is, and is not:
  * NON-CAUSAL. These models read a window of days on both sides of the day they score, so the score of a day uses
    later days. Every number carries the label "non-causal"; they are a reference, not a competitor under the QC rules.
  * They are trained by the ``training`` package, not by this system, on their own year split and on ALL land cells
    (no held-out clients). So: (1) a model whose training or validation years overlap any year scored here is refused
    with the years named; (2) held-out (unseen) cells are left unscored, because the model has seen them.
  * No granularity sources are supplied, so such models see them as unavailable (the detector handles that).
  * Their own calibrated threshold is NOT used. The score goes through the same false-alarm budget thresholds as every
    other component, taken from clean threshold years.

Artifacts are listed in the config under ``offline.artifacts`` (name -> artifact folder); none exist in this repository.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from qc.neighbours import gather, ring_index
from qc.prepare import Prepared
from qc.scoring import Block
from qc.splits import HELDOUT

log = logging.getLogger(__name__)
ARCHS = ("rainnet", "scalenet", "msnet", "lstm_ae")
LABEL = "non-causal reference"


def offline_name(arch: str) -> str:
    return f"offline_{arch}"


def configured(p: Prepared) -> Dict[str, str]:
    """name -> artifact folder, from ``offline.artifacts`` in the config (empty if not set)."""
    doc = p.cfg.to_dict().get("offline") or {}
    return {str(k): str(v) for k, v in (doc.get("artifacts") or {}).items() if v}


def years_scored(p: Prepared, splits) -> List[int]:
    ys = set(p.split.years["threshold"])
    for s in splits:
        ys |= set(p.split.years[s])
    return sorted(ys)


def overlap(meta: Dict, years: List[int]) -> List[int]:
    """Years the model was trained or tuned on that are also years being scored."""
    used = set(int(y) for y in (meta.get("train_years") or [])) | set(int(y) for y in (meta.get("val_years") or []))
    return sorted(used & set(int(y) for y in years))


def score_function(p: Prepared, detector, device_note: str = "cpu"):
    """ScoreFn for one loaded ``RainfallAEDetector``: Block -> (T, n_land) float32 scores, NaN where unscored."""
    ring8 = ring_index(p.grid, 0.5, 1.5)
    lat = (p.grid.lat - p.grid.lat.min()) / max(float(np.ptp(p.grid.lat)), 1e-6)
    lon = (p.grid.lon - p.grid.lon.min()) / max(float(np.ptp(p.grid.lon)), 1e-6)
    la, lo = lat[p.grid.rows], lon[p.grid.cols]
    unseen = p.cell_role == HELDOUT                                    # the model saw these cells in training

    def fn(block: Block) -> np.ndarray:
        obs = np.where(np.isfinite(block.obs), np.clip(block.obs, 0, None), np.nan).astype(np.float32)
        nb = gather(obs, ring8)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            nmean, nmax = np.nanmean(nb, axis=2), np.nanmax(nb, axis=2)
        nmean, nmax = np.where(np.isfinite(nmean), nmean, np.nan_to_num(obs)), np.where(np.isfinite(nmax), nmax, np.nan_to_num(obs))
        clim = p.stats.climatology[np.minimum(block.doy, 365)]           # (pad + T, n_land) mm, training years only
        out = np.full((block.days, obs.shape[1]), np.nan, np.float32)
        for c in range(obs.shape[1]):
            if unseen[c]:
                continue
            x = np.nan_to_num(obs[:, c])
            ctx = {"nbr_mean": nmean[:, c], "nbr_max": nmax[:, c], "clim": np.nan_to_num(clim[:, c]), "doy0": int(block.doy[0]),
                   "lat": float(la[c]), "lon": float(lo[c])}
            s = detector.detect_detailed(x, ctx)["scores"][block.pad:]
            out[:, c] = s
        out[~np.isfinite(block.target)] = np.nan
        bad = ~np.isfinite(out) & np.isfinite(block.target) & ~unseen[None, :]
        if bad.any():
            low = np.nanmin(np.where(np.isfinite(out), out, np.nan)) if np.isfinite(out).any() else 0.0
            out[bad] = low
        return out

    return fn


def offline_scorers(p: Prepared, splits, device: str = "cpu") -> Tuple[Dict, Dict[str, str]]:
    """(name -> score function, name -> reason not run). Nothing is invented: no artifact, no score."""
    from detectors.rainfall_ae import RainfallAEDetector

    fns, not_run = {}, {}
    cfg = configured(p)
    years = years_scored(p, splits)
    for arch in ARCHS:
        label = f"offline comparison: {arch} ({LABEL})"
        folder = cfg.get(arch)
        if not folder:
            not_run[label] = "NOT RUN: no artifact configured (offline.artifacts." + arch + ")"
            continue
        if not (Path(folder) / "manifest.json").is_file():
            not_run[label] = f"NOT RUN: no artifact at {folder}"
            continue
        det = RainfallAEDetector(folder, device)
        found = det._art.trainer.config.arch
        if found != arch:
            raise ValueError(f"offline.artifacts.{arch} points at a {found} artifact")
        bad = overlap(det._art.meta, years)
        if bad:
            not_run[label] = (f"NOT RUN: the model was trained or tuned on years that are scored here "
                              f"({bad[:6]}{'...' if len(bad) > 6 else ''}); scoring them would leak")
            continue
        fns[offline_name(arch)] = score_function(p, det)
    return fns, not_run


def run_offline_validation(p: Prepared, device: str = "cpu", overwrite: bool = False, pinned: bool = True) -> Tuple[Dict, Dict[str, str]]:
    """Score the configured offline models on the VALIDATION years only and evaluate them like every other component
    (thresholds from the clean threshold years, same budgets). Test and stress years are never read here, so this is a
    development comparison that does not use up the single test pass. Still NON-CAUSAL: the numbers are a reference.
    Returns (results[name] = metrics, not_run[label] = reason). Metrics are written to <run>/offline/metrics/."""
    from qc import paths
    from qc.evaluate import compute_scores_many, evaluate_component, score_store
    from qc.runs import RunDir, write_json

    fns, not_run = offline_scorers(p, ("val",), device)
    results: Dict[str, Dict] = {}
    if not fns:
        return results, not_run
    run = RunDir(paths.out_dir(p.cfg) / str(p.cfg.name), "offline")
    run.start(p.cfg, int(p.cfg.seed), {"split_manifest_hash": p.manifest["hash"], "components": sorted(fns), "label": LABEL})
    store = score_store(p)
    compute_scores_many(p, fns, ("val",), store, overwrite)
    for name in fns:
        res = evaluate_component(p, name, "val", p.cfg.evaluation.budgets, ("seen",), store, pinned)
        res["label"] = LABEL
        write_json(run.file("metrics", f"{name}_val.json"), res)
        results[name] = res
    return results, not_run
