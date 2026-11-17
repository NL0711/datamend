"""Cell partitions: the seam that lets the same trainer run centrally now and federated later.

One partition = the set of land cells a single (future) FL client owns. Real state
boundaries need a shapefile; ``lat_bands`` is a deliberately non-IID stand-in
(tropical south vs. arid north vs. Himalayan north have very different rainfall).
"""

from __future__ import annotations

from typing import List

import numpy as np


def partition_cells(
    land_mask: np.ndarray, scheme: str = "all", n_clients: int = 1, tile: int = 16
) -> List[np.ndarray]:
    """Return ``n_clients`` arrays of flat (row-major) land-cell indices.

    schemes: ``all`` (one client, centralized), ``lat_bands`` (equal-cell-count
    latitude bands), ``tiles`` (``tile``x``tile`` blocks dealt round-robin).
    """
    h, w = land_mask.shape
    rows, cols = np.nonzero(land_mask)
    flat = rows * w + cols
    if scheme == "all" or n_clients == 1:
        return [flat]
    if scheme == "lat_bands":
        order = np.argsort(rows, kind="stable")
        return [flat[idx] for idx in np.array_split(order, n_clients)]
    if scheme == "tiles":
        tile_id = (rows // tile) * ((w + tile - 1) // tile) + (cols // tile)
        owner = np.unique(tile_id, return_inverse=True)[1] % n_clients
        return [flat[owner == k] for k in range(n_clients)]
    raise ValueError(f"Unknown partition scheme {scheme!r}")
