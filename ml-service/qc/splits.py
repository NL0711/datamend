"""Leakage-safe splits by time and by client, and the audit that proves them.

Cell roles (one per land cell):
  train     belongs to a training client and is more than ``buffer_cells`` away from every held-out cell
  buffer    belongs to a training client but lies within ``buffer_cells`` (Chebyshev distance) of a held-out
            cell: never a training target
  heldout   belongs to an unseen client: never read during training, in any role
Year roles come from ``cfg.years``. Statistics are fit on training years, fusion and thresholds on
validation years, and test years are scored once.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy.ndimage import binary_dilation

from qc.clients import map_hash
from qc.config import year_range

OFF, TRAIN, BUFFER, HELDOUT = 0, 1, 2, 3
ROLE_NAMES = {OFF: "off_land", TRAIN: "train", BUFFER: "buffer", HELDOUT: "heldout"}


class LeakageError(AssertionError):
    pass


def cell_roles(client_map: np.ndarray, heldout: Sequence[int], buffer_cells: int) -> np.ndarray:
    """(H, W) int8 role grid."""
    held = np.isin(client_map, list(heldout))
    land = client_map > 0
    near = binary_dilation(held, structure=np.ones((3, 3), bool), iterations=int(buffer_cells)) if buffer_cells > 0 else held
    roles = np.zeros(client_map.shape, np.int8)
    roles[land] = TRAIN
    roles[land & near & ~held] = BUFFER
    roles[held] = HELDOUT
    return roles


@dataclass(frozen=True)
class Split:
    client_map: np.ndarray       # (H, W) int8, 0 = off land
    roles: np.ndarray            # (H, W) int8
    heldout: List[int]
    buffer_cells: int
    years: Dict[str, List[int]]  # train, val, test, fusion_fit, threshold, stress

    @property
    def train_clients(self) -> List[int]:
        return [c for c in range(1, int(self.client_map.max()) + 1) if c not in self.heldout]

    def input_mask(self, client: Optional[int] = None) -> np.ndarray:
        """Cells whose values may be READ as model input during training.

        Centralized (``client=None``): every cell of a training client, buffer included. Federated or
        local-only (``client=c``): only that client's cells. Held-out cells are never readable.
        """
        m = (self.roles == TRAIN) | (self.roles == BUFFER)
        return m if client is None else m & (self.client_map == client)

    def target_mask(self, client: Optional[int] = None) -> np.ndarray:
        """Cells that may be training TARGETS: role ``train`` only (buffer cells are excluded)."""
        m = self.roles == TRAIN
        return m if client is None else m & (self.client_map == client)

    def eval_mask(self, group: str) -> np.ndarray:
        """``seen`` = cells of training clients (buffer included); ``unseen`` = cells of held-out clients."""
        if group == "seen":
            return (self.roles == TRAIN) | (self.roles == BUFFER)
        if group == "unseen":
            return self.roles == HELDOUT
        raise ValueError(f"unknown evaluation group {group!r}")

    def manifest(self) -> Dict:
        counts = {}
        for c in range(1, int(self.client_map.max()) + 1):
            sel = self.client_map == c
            counts[str(c)] = {ROLE_NAMES[r]: int((self.roles[sel] == r).sum()) for r in (TRAIN, BUFFER, HELDOUT)}
        doc = {
            "years": {k: [v[0], v[-1]] for k, v in self.years.items()},
            "heldout_clients": list(self.heldout), "train_clients": self.train_clients,
            "buffer_cells": int(self.buffer_cells),
            "client_map_hash": map_hash(self.client_map),
            "roles_hash": hashlib.sha256(np.ascontiguousarray(self.roles).tobytes()).hexdigest()[:16],
            "cells_per_client": counts,
        }
        doc["hash"] = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:16]
        return doc


def make_split(cfg, client_map: np.ndarray) -> Split:
    years = {k: year_range(cfg.years[k]) for k in ("train", "val", "test", "fusion_fit", "threshold", "stress")}
    split = Split(client_map, cell_roles(client_map, cfg.clients.heldout, cfg.clients.buffer_cells),
                  [int(c) for c in cfg.clients.heldout], int(cfg.clients.buffer_cells), years)
    audit_split(split)
    return split


def audit_split(split: Split, reach_cells: Optional[int] = None) -> None:
    """Raise ``LeakageError`` unless the split is leakage-safe.

    ``reach_cells`` is how far (in cells) any trained component reads from its target; it must not exceed
    the buffer, otherwise a training target could read a held-out cell.
    """
    y = split.years
    for a, b in (("train", "val"), ("train", "test"), ("val", "test"), ("stress", "train"), ("stress", "val"), ("stress", "test")):
        both = set(y[a]) & set(y[b])
        if both:
            raise LeakageError(f"years {sorted(both)} are in both {a} and {b}")
    for sub in ("fusion_fit", "threshold"):
        if not set(y[sub]) <= set(y["val"]):
            raise LeakageError(f"{sub} years {y[sub]} must lie inside the validation years")
    if set(y["fusion_fit"]) & set(y["threshold"]):
        raise LeakageError("fusion_fit and threshold years overlap; thresholds must be set on years the fusion was not fitted on")
    present = set(np.unique(split.client_map)) - {0}
    missing = set(split.heldout) - present
    if missing:
        raise LeakageError(f"held-out clients {sorted(missing)} do not exist in the client map (clients: {sorted(present)})")
    if not split.train_clients:
        raise LeakageError("no training clients left")
    if reach_cells is not None and reach_cells > split.buffer_cells:
        raise LeakageError(f"component reach of {reach_cells} cells exceeds the {split.buffer_cells}-cell buffer")
    held = split.roles == HELDOUT
    if (split.input_mask() & held).any():
        raise LeakageError("a held-out cell is readable as training input")
    if split.buffer_cells > 0 and held.any():
        near = binary_dilation(held, structure=np.ones((3, 3), bool), iterations=split.buffer_cells)
        if (split.target_mask() & near).any():
            raise LeakageError("a training target lies inside the buffer around a held-out client")
    for c in split.train_clients:
        if (split.input_mask(c) & (split.client_map != c)).any():
            raise LeakageError(f"client {c} can read a cell outside itself")


def assert_years_allowed(name: str, used: Sequence[int], split: Split, allowed: str) -> None:
    """Guard for fitted statistics: ``used`` years must all lie in ``split.years[allowed]``."""
    bad = sorted(set(int(v) for v in used) - set(split.years[allowed]))
    if bad:
        raise LeakageError(f"{name} used years {bad[:5]}{'...' if len(bad) > 5 else ''} outside the {allowed} years")
