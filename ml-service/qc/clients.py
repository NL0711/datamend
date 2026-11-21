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
from typing import Sequence

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


def _adjacent_pairs(rows: np.ndarray, cols: np.ndarray, sub: np.ndarray):
    """Pairs of sub-divisions that touch (8-neighbourhood) somewhere on the grid."""
    key = {(int(r), int(c)): int(s) for r, c, s in zip(rows, cols, sub)}
    pairs = set()
    for (r, c), s in key.items():
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                t = key.get((r + dr, c + dc))
                if t is not None and t != s:
                    pairs.add((min(s, t), max(s, t)))
    return pairs


def nest_in_subdivisions(rows: np.ndarray, cols: np.ndarray, sub: np.ndarray, base: np.ndarray, k: int = 8,
                         anchors: Sequence[int] = (), compactness: float = 0.15, max_moves: int = 500) -> np.ndarray:
    """Clients that are unions of WHOLE sub-divisions (so no sub-division is split between trained and unseen cells).

    ``rows``, ``cols`` (n,) are the land cells, ``sub`` (n,) the positive sub-division id of every cell, ``base`` (n,) the 1..k labels of a
    starting partition (for example the k-means blobs). Start: each sub-division goes to the client holding most of its cells. Then a
    deterministic local search moves one sub-division at a time to a touching client while that lowers

        sum_c ((size_c - mean) / mean)**2  +  compactness * sum_c (mean squared distance of c's cells to its centre / mean size),

    and never leaves a client empty or disconnected (connected through touching sub-divisions). ``anchors`` are sub-divisions that must stay
    in different clients (the ones that define the held-out clients). Returns (n,) labels 1..k, not yet re-ordered."""
    n = rows.size
    subs = np.unique(sub)
    idx = {int(s): np.nonzero(sub == s)[0] for s in subs}
    size = {s: len(i) for s, i in idx.items()}
    sx = {s: float(rows[i].sum()) for s, i in idx.items()}
    sy = {s: float(cols[i].sum()) for s, i in idx.items()}
    sq = {s: float((rows[i].astype(float) ** 2 + cols[i].astype(float) ** 2).sum()) for s, i in idx.items()}
    adj: dict = {int(s): set() for s in subs}
    for a, b in _adjacent_pairs(rows, cols, sub):
        adj[a].add(b)
        adj[b].add(a)
    owner = {s: int(np.bincount(base[i], minlength=k + 1).argmax()) for s, i in idx.items()}
    mean = n / k

    def stats(members):
        S = sum(size[m] for m in members)
        if S == 0:
            return 0, 0.0
        cx, cy = sum(sx[m] for m in members) / S, sum(sy[m] for m in members) / S
        return S, sum(sq[m] for m in members) / S - cx * cx - cy * cy

    def members_of(own, c):
        return [s for s, o in own.items() if o == c]

    def cost(own):
        tot = 0.0
        for c in range(1, k + 1):
            S, msd = stats(members_of(own, c))
            tot += ((S - mean) / mean) ** 2 + compactness * msd / mean
        return tot

    def connected(members):
        if not members:
            return False
        seen, todo = {members[0]}, [members[0]]
        ms = set(members)
        while todo:
            for t in adj[todo.pop()] & ms:
                if t not in seen:
                    seen.add(t)
                    todo.append(t)
        return len(seen) == len(ms)

    for c in range(1, k + 1):
        if not members_of(owner, c):
            raise ValueError(f"the starting partition leaves client {c} without a whole sub-division")
    anchors = [int(a) for a in anchors]
    cur = cost(owner)
    for _ in range(max_moves):
        best = None
        for s in sorted(owner):
            src = owner[s]
            for dst in sorted({owner[t] for t in adj[s]} - {src}):
                trial = dict(owner)
                trial[s] = dst
                rest = members_of(trial, src)
                if not rest or not connected(rest) or not connected(members_of(trial, dst)):
                    continue
                if len({trial[a] for a in anchors}) < len(anchors):
                    continue
                c = cost(trial)
                if c < cur - 1e-12 and (best is None or c < best[0]):
                    best = (c, s, dst)
        if best is None:
            break
        cur, s, dst = best
        owner[s] = dst
    out = np.zeros(n, np.int64)
    for s, i in idx.items():
        out[i] = owner[s]
    return out


def order_clients(labels: np.ndarray, lat: np.ndarray, lon: np.ndarray, k: int) -> np.ndarray:
    """Renumber clients north to south then west to east, as the k-means map does. ``lat``, ``lon`` are per cell."""
    order = sorted(range(1, k + 1), key=lambda c: (-round(float(lat[labels == c].mean()) / 4), float(lon[labels == c].mean())))
    out = np.zeros_like(labels)
    for new, old in enumerate(order, start=1):
        out[labels == old] = new
    return out


def map_hash(client_map: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(client_map, dtype=np.int8).tobytes()).hexdigest()[:16]


def save_client_map(path: Path, client_map: np.ndarray, k: int, seed: int, extra: dict = None) -> None:
    if client_map.max() > 9:
        raise ValueError("the text format stores one digit per cell; k must be at most 9")
    doc = {
        "k": int(k), "seed": int(seed), "shape": list(client_map.shape), "hash": map_hash(client_map),
        "note": "0 = not land; 1..k = client id, ordered north to south then west to east. Row 0 is the southernmost latitude.",
        "rows": ["".join(str(int(v)) for v in row) for row in client_map],
    }
    if extra:
        doc.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=0), encoding="utf-8")


def load_client_map(path: Path) -> np.ndarray:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    cm = np.array([[int(ch) for ch in row] for row in doc["rows"]], dtype=np.int8)
    if list(cm.shape) != doc["shape"] or map_hash(cm) != doc["hash"]:
        raise ValueError(f"{path} is corrupt: shape or hash does not match its contents")
    return cm
