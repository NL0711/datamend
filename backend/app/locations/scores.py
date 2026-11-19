"""Where scores of the TRAINED models (ml-service/qc) plug in.

v1 has no trained-model scores to show, so the answer is "not available" unless a file exists. Nothing here computes or
invents a score. A score file is written by the ml-service pipeline (one per grid cell) and looks like:

    data/location_scores/<row>_<col>.json
    {"model": "fusion (qc)", "version": "...", "label_tier": "synthetic faults",
     "scores": {"2026-11-16": {"temperature": 1.2, "humidity": 0.8, "pressure": 0.4, "fused": 1.9, "flag": "none"}}}
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "data" / "location_scores"


class ScoreProvider(Protocol):
    def get(self, row: int, col: int, day: date) -> Optional[Dict[str, Any]]:
        ...


class FileScoreProvider:
    def __init__(self, root: Path = DEFAULT_DIR) -> None:
        self.root = Path(root)

    def get(self, row: int, col: int, day: date) -> Optional[Dict[str, Any]]:
        f = self.root / f"{row}_{col}.json"
        if not f.is_file():
            return None
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        s = (doc.get("scores") or {}).get(day.isoformat())
        if s is None:
            return None
        return {"model": doc.get("model"), "version": doc.get("version"), "label_tier": doc.get("label_tier"), "date": day.isoformat(), "scores": s}


def model_block(provider: Optional[ScoreProvider], row: int, col: int, day: Optional[date]) -> Dict[str, Any]:
    if provider is None or day is None:
        return {"status": "not_available", "reason": "no trained-model scores are loaded"}
    got = provider.get(row, col, day)
    if got is None:
        return {"status": "not_available", "reason": f"no saved model scores for this cell on {day.isoformat()}"}
    return {"status": "ok", **got}
