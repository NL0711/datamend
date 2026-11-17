"""Federated clients: geographic blobs from k-means on cell latitude/longitude over the land mask.

The map is generated once, saved as ``qc/assets/client_map.json`` and committed. Every run loads that
file; it is never recomputed during a run, because k-means labels can differ between library versions.
Client ids are 1-based and ordered north to south, then west to east (as in the client-map prototype).
0 means "not land".
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


def build_client_map(land: np.ndarray, lat: np.ndarray, lon: np.ndarray, k: int = 8, seed: int = 0) -> np.ndarray:
    from sklearn.cluster import KMeans

    rows, cols = np.nonzero(land)
    la, lo = np.asarray(lat, float)[rows], np.asarray(lon, float)[cols]
    labels = KMeans(k, n_init=10, random_state=seed).fit_predict(np.column_stack([la, lo]))
    order = sorted(range(k), key=lambda c: (-round(la[labels == c].mean() / 4), lo[labels == c].mean()))
    out = np.zeros(land.shape, np.int8)
    for new, old in enumerate(order, start=1):
        sel = labels == old
        out[rows[sel], cols[sel]] = new
    return out


def map_hash(client_map: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(client_map, dtype=np.int8).tobytes()).hexdigest()[:16]


def save_client_map(path: Path, client_map: np.ndarray, k: int, seed: int) -> None:
    if client_map.max() > 9:
        raise ValueError("the text format stores one digit per cell; k must be at most 9")
    doc = {
        "k": int(k), "seed": int(seed), "shape": list(client_map.shape), "hash": map_hash(client_map),
        "note": "0 = not land; 1..k = client id, ordered north to south then west to east. Row 0 is the southernmost latitude.",
        "rows": ["".join(str(int(v)) for v in row) for row in client_map],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=0), encoding="utf-8")


def load_client_map(path: Path) -> np.ndarray:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    cm = np.array([[int(ch) for ch in row] for row in doc["rows"]], dtype=np.int8)
    if list(cm.shape) != doc["shape"] or map_hash(cm) != doc["hash"]:
        raise ValueError(f"{path} is corrupt: shape or hash does not match its contents")
    return cm
