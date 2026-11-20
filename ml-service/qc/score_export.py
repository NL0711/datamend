"""Score export, schema 1 (docs/contracts/score-export-v1.schema.json): the file the web app reads to show a trained model's scores.

One compressed .npz per scale and model: a JSON ``manifest`` plus arrays. The platform imports nothing from this package, so the contract is
the file: ``manifest`` (validated against the schema), ``periods`` (P ISO dates, the start of each period), ``lat`` and ``lon`` (n cells),
``scores`` (P x n float32, higher means more suspicious, NaN where the period is not valid for the cell) and optionally ``fault_<kind>``
arrays of the same shape.

Rules enforced on write (docs/qc-evaluation-protocol.md): the scores are STANDARDISED on clean validation years by the caller (the ratio to the
clean 99.9th percentile, as the daily components are); a period inside the locked test years (config ``splits.test``) is refused unless the
caller says the single test pass is open; a flag threshold is given only with the false-alarm budget it was fixed under, and ``calibrated`` is
true only then. Everything in a file made from generated or synthetic-fault data says ``label_tier: synthetic``.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np

SCHEMA = "score-export-v1"
SCALES = ("daily", "monthly", "seasonal", "yearly")
FAULT_KINDS = ("spike", "stuck", "scale", "phantom_rain", "zeroed", "drift")
TEST_YEARS_DEFAULT = (2018, 2025)


class ExportError(ValueError):
    pass


def _check(manifest: Dict[str, Any], periods: np.ndarray, lat: np.ndarray, lon: np.ndarray, scores: np.ndarray, faults: Mapping[str, np.ndarray]) -> None:
    if manifest.get("schema") != SCHEMA:
        raise ExportError(f"manifest.schema must be {SCHEMA!r}")
    if manifest.get("scale") not in SCALES:
        raise ExportError(f"manifest.scale must be one of {SCALES}")
    if manifest.get("label_tier") not in ("synthetic",):
        raise ExportError("manifest.label_tier must be 'synthetic' (scores of the trained models are validated on synthetic faults only)")
    if scores.ndim != 2 or scores.shape != (len(periods), len(lat)) or len(lat) != len(lon):
        raise ExportError(f"scores must be P x n ({len(periods)} x {len(lat)}), got {scores.shape}")
    if not np.isfinite(scores[~np.isnan(scores)]).all():
        raise ExportError("scores contain infinite values")
    for k, a in faults.items():
        if k not in FAULT_KINDS:
            raise ExportError(f"unknown fault kind {k!r}; allowed: {FAULT_KINDS}")
        if a.shape != scores.shape:
            raise ExportError(f"fault_{k} must have the shape of scores")
    thr, cal = manifest.get("threshold"), manifest.get("calibrated")
    if thr is not None and manifest.get("false_alarm_budget_per_1000") is None:
        raise ExportError("a threshold needs the false-alarm budget it was fixed under (false_alarm_budget_per_1000)")
    if cal is True and thr is None:
        raise ExportError("calibrated is true only with a threshold fixed under a budget")


def write_score_export(path: Path, *, scores: np.ndarray, periods: Sequence[str], lat: Sequence[float], lon: Sequence[float], scale: str, model_id: str,
                       config_digest: str, fault_scores: Optional[Mapping[str, np.ndarray]] = None, threshold: Optional[float] = None,
                       false_alarm_budget_per_1000: Optional[float] = None, test_years: Sequence[int] = TEST_YEARS_DEFAULT,
                       test_pass_open: bool = False, notes: str = "") -> Dict[str, Any]:
    """Write the file and return its manifest. Raises ExportError when a rule is broken; nothing is written then."""
    per = np.array([str(p) for p in periods])
    la, lo = np.asarray(lat, dtype=np.float32), np.asarray(lon, dtype=np.float32)
    sc = np.asarray(scores, dtype=np.float32)
    faults = {k: np.asarray(v, dtype=np.float32) for k, v in (fault_scores or {}).items()}
    for p in per:
        try:
            y = date.fromisoformat(p).year
        except ValueError:
            raise ExportError(f"period {p!r} is not an ISO date")
        if test_years[0] <= y <= test_years[1] and not test_pass_open:
            raise ExportError(f"period {p} is inside the locked test years {test_years[0]} to {test_years[1]}; the single test pass is not open")
    manifest: Dict[str, Any] = {
        "schema": SCHEMA, "scale": scale, "model_id": model_id, "config_digest": config_digest, "label_tier": "synthetic",
        "n_periods": int(len(per)), "n_cells": int(len(la)), "period_first": str(per[0]) if len(per) else None, "period_last": str(per[-1]) if len(per) else None,
        "threshold": threshold, "false_alarm_budget_per_1000": false_alarm_budget_per_1000,
        "calibrated": threshold is not None and false_alarm_budget_per_1000 is not None,
        "fault_kinds": sorted(faults), "test_years_included": bool(test_pass_open), "standardised": "ratio to the clean 99.9th percentile (caller's duty)",
        "grid": "cell centres in degrees; the station-to-cell mapping is NOT part of this file", "notes": notes[:500],
    }
    _check(manifest, per, la, lo, sc, faults)
    arrays = {"manifest": np.array(json.dumps(manifest)), "periods": per, "lat": la, "lon": lo, "scores": sc, **{f"fault_{k}": v for k, v in faults.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **arrays)
    tmp.replace(path)
    manifest["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest


def read_score_export(path: Path) -> Dict[str, Any]:
    """Load and re-validate a file. Returns manifest and arrays; raises ExportError on anything that breaks the schema."""
    try:
        z = np.load(path, allow_pickle=False)
        manifest = json.loads(str(z["manifest"]))
        per, lat, lon, scores = z["periods"], z["lat"], z["lon"], z["scores"]
        faults = {k[len("fault_"):]: z[k] for k in z.files if k.startswith("fault_")}
    except (OSError, KeyError, ValueError) as e:
        raise ExportError(f"not a score export file ({type(e).__name__})")
    _check(manifest, per, lat, lon, scores, faults)
    return {"manifest": manifest, "periods": per, "lat": lat, "lon": lon, "scores": scores, "faults": faults}
