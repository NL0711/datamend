"""The score provider: reads an exported score file (docs/contracts/score-export-v1.schema.json, written by ml-service/qc/score_export.py) and
answers "what did the trained model score for this place on this day", as the ``provider`` block of the evidence.

Nothing is invented: a station with no coordinates, a day the file does not cover, a place farther than half a grid cell from any cell centre,
or a NaN score gives no block. The platform imports nothing from ``ml-service``; the file is the contract. Standard library and numpy only.

ASSUMED: a station is mapped to the nearest cell centre within MAX_OFFSET_DEG. The proper station-to-cell mapping is an open research
ticket (docs/wayfinder, station-to-cell); this is a stand-in that says so in the block's ``cell_offset_deg``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

MAX_OFFSET_DEG = 0.13           # half of the 0.25 degree RF25 cell, with a little slack


class ScoreFileError(ValueError):
    pass


class ScoreProvider:
    def __init__(self, path: str) -> None:
        p = Path(path)
        try:
            z = np.load(p, allow_pickle=False)
            self.manifest: Dict[str, Any] = json.loads(str(z["manifest"]))
            self.periods = [str(x) for x in z["periods"]]
            self.lat, self.lon, self.scores = z["lat"].astype(float), z["lon"].astype(float), z["scores"]
            self.faults = {k[len("fault_"):]: z[k] for k in z.files if k.startswith("fault_")}
        except (OSError, KeyError, ValueError) as e:
            raise ScoreFileError(f"cannot read the score export file ({type(e).__name__})")
        m = self.manifest
        if m.get("schema") != "score-export-v1" or m.get("label_tier") != "synthetic":
            raise ScoreFileError("not a score-export-v1 file")
        if self.scores.shape != (len(self.periods), len(self.lat)):
            raise ScoreFileError("the scores do not match periods and cells")
        self._index = {p: i for i, p in enumerate(self.periods)}

    def lookup(self, lat: Optional[float], lon: Optional[float], day: Optional[str]) -> Optional[Dict[str, Any]]:
        if lat is None or lon is None or not day:
            return None
        i = self._index.get(day[:10])
        if i is None:
            return None
        d2 = (self.lat - lat) ** 2 + (self.lon - lon) ** 2
        j = int(np.argmin(d2))
        if abs(self.lat[j] - lat) > MAX_OFFSET_DEG or abs(self.lon[j] - lon) > MAX_OFFSET_DEG:
            return None
        s = float(self.scores[i, j])
        if np.isnan(s):
            return None
        out: Dict[str, Any] = {"model_id": str(self.manifest["model_id"]), "model_kind": "stnet", "score": s,
                               "calibrated": bool(self.manifest.get("calibrated")), "label_tier": "synthetic"}
        thr = self.manifest.get("threshold")
        if thr is not None and out["calibrated"]:
            out["flagged"] = s >= float(thr)               # a flag only exists with a threshold fixed under a clean-period budget
        fs = {k: float(v[i, j]) for k, v in self.faults.items() if not np.isnan(v[i, j])}
        if fs:
            out["fault_scores"] = fs
        return out


_cache: Dict[str, Any] = {}


def get_provider(path: str) -> Optional[ScoreProvider]:
    """The provider for a configured path, or None when none is configured. A bad file raises ScoreFileError (the caller shows it, never hides it)."""
    if not path.strip():
        return None
    p = Path(path)
    stamp = (str(p), p.stat().st_mtime_ns if p.exists() else None)
    if _cache.get("stamp") != stamp:
        _cache["stamp"], _cache["provider"] = stamp, ScoreProvider(path)
    return _cache["provider"]
