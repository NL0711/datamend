"""Synthetic faults applied to whole daily fields.

A fault has a kind, a centre cell, a start day, a duration, a footprint radius and a strength:

  footprint  radius 0 = the centre cell only. Otherwise every land cell closer than the radius is affected,
             with weight ``(1 - distance / radius) ** 2`` (1 at the centre, 0 at the radius), like one bad
             gauge spreading through inverse-distance interpolation.
  blending   corrupted = original + weight * (faulty - original), per cell.
  strength   a number in [0, 1]. For kinds with a size (spike, scale, phantom_rain, drift) it sets the size;
             for kinds without one (stuck, zeroed, repeat) it sets the duration. Low strength = subtle fault.

Kinds: spike, stuck, scale, phantom_rain, zeroed, repeat, drift, edge, combination.
  edge         a base kind centred on a coastline or data-boundary cell, always with a footprint
  combination  two different base kinds applied one after the other on the same cells and days

Synthetic faults are a controlled stress test. They are not real QC labels.
Only cell-days whose value actually changed are labelled. Nothing here modifies the input array.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.ndimage import binary_erosion

from qc.grid import Grid

BASE_KINDS: Tuple[str, ...] = ("spike", "stuck", "scale", "phantom_rain", "zeroed", "repeat", "drift")
KINDS: Tuple[str, ...] = BASE_KINDS + ("edge", "combination")
_EDGE_BASES = ("spike", "stuck", "scale", "zeroed")
_DURATION: Dict[str, Tuple[int, int]] = {          # days, inclusive
    "spike": (1, 2), "stuck": (3, 10), "scale": (1, 7), "phantom_rain": (7, 20),
    "zeroed": (1, 7), "repeat": (3, 10), "drift": (21, 60),
}
_DURATION_IS_STRENGTH = ("stuck", "zeroed", "repeat")
WET_MM = 0.1
CHANGED_MM = 1e-3


@dataclass(frozen=True)
class FaultSettings:
    kinds: Tuple[str, ...]
    rate: float = 0.01                 # target share of land cell-days carrying a fault
    footprint_share: float = 0.5       # share of faults that get a footprint (radius > 0)
    radius_min: float = 1.5
    radius_max: float = 4.0
    strength_min: float = 0.25
    strength_max: float = 1.0
    combination_bases: Tuple[str, ...] = ("spike", "stuck", "scale", "phantom_rain", "zeroed", "drift")


@dataclass
class FaultSet:
    """Faults for one block of days, stored sparsely: one row per changed cell-day."""
    shape: Tuple[int, int]                     # (T, n_land)
    t: np.ndarray                              # (m,) day index
    cell: np.ndarray                           # (m,) land-cell index
    value: np.ndarray                          # (m,) corrupted value, mm
    weight: np.ndarray                         # (m,) footprint weight = local strength of the fault there
    event: np.ndarray                          # (m,) index into ``events``
    events: List[Dict] = field(default_factory=list)

    def apply(self, series: np.ndarray) -> np.ndarray:
        out = series.astype(np.float32, copy=True)
        out[self.t, self.cell] = self.value
        return out

    def labels(self) -> np.ndarray:
        lab = np.zeros(self.shape, bool)
        lab[self.t, self.cell] = True
        return lab

    def event_ids(self) -> np.ndarray:
        ev = np.full(self.shape, -1, np.int32)
        ev[self.t, self.cell] = self.event
        return ev


class FaultGenerator:
    def __init__(self, grid: Grid):
        self.grid = grid
        h, w = grid.shape
        self.index = np.full((h, w), -1, np.int32)
        self.index[grid.rows, grid.cols] = np.arange(grid.n_land)
        interior = binary_erosion(grid.land, structure=np.ones((3, 3), bool), border_value=0)
        self.edge_cells = np.nonzero(grid.to_series(grid.land & ~interior))[0]

    def footprint(self, centre: int, radius: float) -> Tuple[np.ndarray, np.ndarray]:
        """Land cells affected by a fault centred on ``centre`` and their weights (centre first, weight 1)."""
        if radius <= 0:
            return np.array([centre]), np.ones(1, np.float32)
        r0, c0 = int(self.grid.rows[centre]), int(self.grid.cols[centre])
        k = int(np.floor(radius))
        dr, dc = np.mgrid[-k:k + 1, -k:k + 1]
        dist = np.hypot(dr, dc)
        rr, cc = r0 + dr, c0 + dc
        h, w = self.grid.shape
        ok = (dist < radius) & (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
        idx = self.index[rr[ok], cc[ok]]
        wgt = (1.0 - dist[ok] / radius) ** 2
        keep = idx >= 0
        idx, wgt = idx[keep], wgt[keep].astype(np.float32)
        order = np.argsort(-wgt, kind="stable")
        return idx[order], wgt[order]

    # ------------------------------------------------------------------ kinds

    @staticmethod
    def _faulty(kind: str, orig: np.ndarray, prev: Optional[np.ndarray], s: float, rng: np.random.Generator) -> Optional[np.ndarray]:
        """Full-strength faulty values for ``orig`` (days, cells). None = this draw cannot be applied."""
        if kind == "spike":
            return orig * (2.0 + 13.0 * s) + (10.0 + 190.0 * s)
        if kind == "stuck":
            return np.full_like(orig, rng.uniform(1.0, 30.0))
        if kind == "scale":                          # unit-style error; weak = factor near 1
            f = 1.5 + 8.5 * s
            return orig * (f if rng.random() < 0.5 else 1.0 / f)
        if kind == "phantom_rain":                   # drizzle on dry days
            return np.where(orig <= WET_MM, 0.3 + 4.7 * s, orig)
        if kind == "zeroed":
            return np.zeros_like(orig)
        if kind == "repeat":
            return None if prev is None else prev.copy()
        if kind == "drift":                          # slow ramp from no error to the full error
            ramp = np.linspace(0.0, 1.0, orig.shape[0], dtype=np.float32)[:, None]
            if rng.random() < 0.5:
                f = 1.3 + 1.2 * s
                f = f if rng.random() < 0.5 else 1.0 / f
                return orig * (1.0 + ramp * (f - 1.0))
            return np.where(orig > WET_MM, orig + ramp * (1.0 + 9.0 * s), orig)
        raise ValueError(f"unknown fault kind {kind!r}")

    def _draw(self, series: np.ndarray, st: FaultSettings, rng: np.random.Generator, kind: str) -> Optional[Dict]:
        T = series.shape[0]
        s = float(rng.uniform(st.strength_min, st.strength_max))
        if kind == "edge":
            bases = [_EDGE_BASES[int(rng.integers(len(_EDGE_BASES)))]]
        elif kind == "combination":
            pick = rng.choice(len(st.combination_bases), size=2, replace=False)
            bases = [st.combination_bases[int(i)] for i in pick]
        else:
            bases = [kind]
        lo, hi = max(_DURATION[b][0] for b in bases), max(_DURATION[b][1] for b in bases)
        if any(b in _DURATION_IS_STRENGTH for b in bases):
            dur = lo + int(round(s * (hi - lo)))
        else:
            dur = int(rng.integers(lo, hi + 1))
        dur = min(dur, T)
        start = int(rng.integers(0, T - dur + 1))
        has_footprint = kind == "edge" or rng.random() < st.footprint_share
        radius = float(rng.uniform(st.radius_min, st.radius_max)) if has_footprint else 0.0
        if kind == "edge":
            if self.edge_cells.size == 0:
                return None
            centre = int(self.edge_cells[int(rng.integers(self.edge_cells.size))])
        else:
            centre = int(rng.integers(self.grid.n_land))
        cells, wgt = self.footprint(centre, radius)
        orig = series[start:start + dur][:, cells].astype(np.float32)
        new = orig
        for b in bases:
            prev = series[start - dur:start][:, cells].astype(np.float32) if start >= dur else None
            new = self._faulty(b, new, prev, s, rng)
            if new is None:
                return None
        new = np.clip(orig + wgt[None, :] * (new - orig), 0.0, None).astype(np.float32)
        changed = np.isfinite(orig) & np.isfinite(new) & (np.abs(new - orig) > CHANGED_MM)
        if not changed[:, 0].any():                 # the fault must be visible at its own centre
            return None
        tt, cc = np.nonzero(changed)
        return {"kind": kind, "bases": bases, "strength": s, "radius": radius, "centre": centre, "start": start,
                "duration": dur, "t": (tt + start).astype(np.int32), "cell": cells[cc].astype(np.int32),
                "value": new[tt, cc], "weight": wgt[cc]}

    def generate(self, series: np.ndarray, st: FaultSettings, rng: np.random.Generator,
                 forbidden: Optional[np.ndarray] = None, max_tries: int = 200_000) -> FaultSet:
        """Draw faults until about ``st.rate`` of the land cell-days carry one.

        ``forbidden`` (T, n_land) bool marks cell-days no fault may touch (protected extremes). A draw that
        would touch one, or that overlaps an earlier fault, is rejected and redrawn.
        """
        T, n = series.shape
        taken = np.zeros((T, n), bool) if forbidden is None else forbidden.copy()
        target = int(round(st.rate * np.isfinite(series).sum()))
        rows: Dict[str, List[np.ndarray]] = {k: [] for k in ("t", "cell", "value", "weight", "event")}
        events: List[Dict] = []
        total = tries = 0
        while total < target and tries < max_tries:
            # The kind is chosen first and then redrawn until it fits, so kinds that are often impossible
            # at a random place (zeroing a dry spell, scaling zero rain) are not under-represented.
            kind = st.kinds[int(rng.integers(len(st.kinds)))]
            d = None
            for _ in range(500):
                tries += 1
                cand = self._draw(series, st, rng, kind)
                if cand is not None and not taken[cand["t"], cand["cell"]].any():
                    d = cand
                    break
            if d is None:
                continue
            taken[d["t"], d["cell"]] = True
            for k in ("t", "cell", "value", "weight"):
                rows[k].append(d[k])
            rows["event"].append(np.full(d["t"].size, len(events), np.int32))
            events.append({"kind": d["kind"], "bases": d["bases"], "strength": d["strength"], "radius": d["radius"],
                           "centre": d["centre"], "start": d["start"], "duration": d["duration"], "n_changed": int(d["t"].size)})
            total += d["t"].size
        if total < target:
            raise RuntimeError(f"could not place enough faults ({total} of {target} cell-days after {tries} draws)")
        cat = lambda k, dt: np.concatenate(rows[k]).astype(dt) if rows[k] else np.zeros(0, dt)
        return FaultSet((T, n), cat("t", np.int32), cat("cell", np.int32), cat("value", np.float32),
                        cat("weight", np.float32), cat("event", np.int32), events)


def settings_from_config(cfg, which: str) -> FaultSettings:
    """``which``: ``seen`` (training and validation settings) or ``all`` (test: seen plus test-only settings)."""
    b = cfg.benchmark
    if which == "seen":
        return FaultSettings(tuple(b.kinds_seen), b.rate, b.footprint_share, b.radius.min, b.radius.max_seen,
                             b.min_strength_seen, 1.0, tuple(k for k in b.kinds_seen if k in BASE_KINDS))
    if which == "all":
        return FaultSettings(tuple(b.kinds_seen) + tuple(b.kinds_test_only), b.rate, b.footprint_share, b.radius.min,
                             b.radius.max, 0.0, 1.0, tuple(k for k in b.kinds_seen if k in BASE_KINDS))
    raise ValueError(f"unknown settings {which!r}")


def is_unseen_setting(event: Dict, cfg) -> bool:
    """True if a fault uses any setting reserved for the test benchmark."""
    b = cfg.benchmark
    return (event["kind"] in set(b.kinds_test_only) or event["radius"] > b.radius.max_seen
            or event["strength"] < b.min_strength_seen)
