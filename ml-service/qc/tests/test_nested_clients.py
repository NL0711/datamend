"""Clients made of whole IMD sub-divisions (qc.clients.nest_in_subdivisions) on generated geometry, and on the real file if it was fetched."""

import json
import os
from pathlib import Path

import numpy as np
import pytest

from qc import clients as CL
from qc import imd_regions as IR
from qc.grid import Grid

H, W = 6, 12


def _cells():
    rows, cols = np.mgrid[0:H, 0:W]
    return rows.ravel(), cols.ravel()


def _strips(widths):
    rows, cols = _cells()
    edges = np.cumsum(widths)
    return np.searchsorted(edges, cols, side="right") + 1          # sub-division id 1..len(widths), vertical strips


def _components(labels, rows, cols, c):
    sel = labels == c
    pts = set(zip(rows[sel].tolist(), cols[sel].tolist()))
    seen, n = set(), 0
    for p in pts:
        if p in seen:
            continue
        n += 1
        todo = [p]
        seen.add(p)
        while todo:
            r, q = todo.pop()
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    t = (r + dr, q + dc)
                    if t in pts and t not in seen:
                        seen.add(t)
                        todo.append(t)
    return n


def test_every_sub_division_ends_up_whole_in_one_client_even_when_the_start_cuts_through_it():
    rows, cols = _cells()
    sub = _strips([2, 2, 2, 2, 2, 2])
    base = np.where(cols < 5, 1, np.where(cols < 9, 2, 3))         # the start cuts strips 3 and 5 in the middle
    lab = CL.nest_in_subdivisions(rows, cols, sub, base, k=3, anchors=[1, 6])
    for s in np.unique(sub):
        assert len(np.unique(lab[sub == s])) == 1
    assert sorted(np.unique(lab)) == [1, 2, 3] and lab[sub == 1][0] != lab[sub == 6][0]
    for c in (1, 2, 3):
        assert _components(lab, rows, cols, c) == 1
    again = CL.nest_in_subdivisions(rows, cols, sub, base, k=3, anchors=[1, 6])
    assert np.array_equal(lab, again)                                # deterministic


def test_the_search_rebalances_client_sizes():
    rows, cols = _cells()
    sub = _strips([4, 3, 1, 1, 1, 2])                                 # sizes 24, 18, 6, 6, 6, 12
    base = np.where(cols < 7, 1, np.where(cols < 10, 2, 3))           # plurality start: {1,2}, {3,4,5}, {6}: sizes 42, 18, 12
    start = np.array([int(np.bincount(base[sub == s]).argmax()) for s in sub])
    lab = CL.nest_in_subdivisions(rows, cols, sub, base, k=3)
    spread = lambda a: max(np.bincount(a)[1:]) - min(np.bincount(a)[1:])
    assert spread(lab) < spread(start)


def test_a_start_that_leaves_a_client_without_a_whole_sub_division_is_refused():
    rows, cols = _cells()
    sub = _strips([6, 6])
    base = np.where(cols < 6, 1, 2)
    with pytest.raises(ValueError, match="without a whole sub-division"):
        CL.nest_in_subdivisions(rows, cols, sub, base, k=3)


def test_anchors_are_kept_apart():
    rows, cols = _cells()
    sub = _strips([3, 3, 3, 3])
    base = np.where(cols < 6, 1, 2)
    lab = CL.nest_in_subdivisions(rows, cols, sub, base, k=2, anchors=[1, 4])
    assert lab[sub == 1][0] != lab[sub == 4][0]


def test_order_clients_runs_north_to_south_then_west_to_east():
    rows, cols = _cells()
    labels = np.where(rows < 3, np.where(cols < 6, 1, 2), np.where(cols < 6, 3, 4))
    lat = 10.0 + rows.astype(float) * 4.0                              # larger row = further north
    lon = 70.0 + cols.astype(float)
    out = CL.order_clients(labels, lat, lon, 4)
    assert out[(rows == 5) & (cols == 0)][0] == 1 and out[(rows == 5) & (cols == 11)][0] == 2        # northern band first, west before east
    assert out[(rows == 0) & (cols == 0)][0] == 3 and out[(rows == 0) & (cols == 11)][0] == 4


def _geo(tmp_path):
    def poly(x0, x1):
        return {"type": "Polygon", "coordinates": [[[x0, 8], [x1, 8], [x1, 30], [x0, 30], [x0, 8]]]}
    feats = [{"type": "Feature", "properties": {"name": n, "region_cod": "R", "uorder": i + 1}, "geometry": poly(70 + 5 * i, 75 + 5 * i)}
             for i, n in enumerate(["ONE", "TWO", "THREE", "FOUR"])]
    p = tmp_path / "sd.json"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    return p


def test_nested_client_map_from_a_boundary_file(tmp_path):
    lat, lon = np.linspace(8.5, 29.5, 8), np.linspace(70.5, 89.5, 12)
    land = np.ones((8, 12), bool)
    grid = Grid.from_land(lat, lon, land)
    old = np.where(np.arange(12)[None, :] < 6, 1, 2) * np.ones((8, 1), int)
    new, rep = IR.nested_client_map(old.astype(np.int8), grid, _geo(tmp_path), k=2, anchors=("ONE", "FOUR"))
    assert new.shape == old.shape and sorted(np.unique(new)) == [1, 2]
    assert sum(len(v) for v in rep["clients"].values()) == 4 and rep["anchors"]["ONE"] != rep["anchors"]["FOUR"]
    assert sum(rep["cells_per_client"].values()) == grid.n_land
    with pytest.raises(ValueError, match="not in the boundary file"):
        IR.nested_client_map(old.astype(np.int8), grid, _geo(tmp_path), k=2, anchors=("ONE", "NOPE"))


REAL = Path(os.environ.get("DATAMEND_DATA_DIR", Path(__file__).resolve().parents[2] / "data")) / "regions" / "sd_boundary_rainfall.json"
ASSET = Path(__file__).resolve().parents[1] / "assets" / "client_map.json"


@pytest.mark.skipif(not REAL.is_file(), reason="IMD boundary file not fetched (python scripts/fetch_imd_regions.py)")
def test_committed_client_map_is_made_of_whole_imd_sub_divisions():
    doc = json.loads(ASSET.read_text())
    if "imd_boundary_sha256" not in doc:
        pytest.skip("the committed client map is still the k-means map")
    cm = CL.load_client_map(ASSET)
    grid = Grid.from_land(6.5 + 0.25 * np.arange(129), 66.5 + 0.25 * np.arange(135), cm > 0)
    sub, _ = IR.build_imd_maps(grid, REAL)
    cl = cm[grid.rows, grid.cols]
    sid = sub.cell_region
    split = [sub.names[s] for s in sub.names if (sid == s).any() and len(np.unique(cl[sid == s])) > 1]
    assert not split, f"sub-divisions split across clients: {split}"
    sizes = np.bincount(cl)[1:]
    assert sizes.max() / sizes.min() < 1.5
    assert doc["anchors"] == {"ASSAM & MEGHALAYA": 3, "KONKAN & GOA": 6}
