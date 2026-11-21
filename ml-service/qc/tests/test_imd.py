"""qc.imd_merged and qc.imd_regions on generated files (and, if present, IMD's real boundary file)."""

import json
import os
from pathlib import Path

import numpy as np
import pytest

from qc import imd_merged as M
from qc import imd_regions as IR
from qc.grid import Grid

CTL = """DSET p:\\ddmmyyyy.grd
TITLE 0.25 degranalyzed normal grids
UNDEF -999.0
XDEF  241  LINEAR  50.0 0.25
YDEF  281  LINEAR  -30.0 0.25
ZDEF   1 linear 1 1
TDEF 1 LINEAR 1jun2014 1DY
VARS  1
rf 0 99 GRIDDED RAINFALL
ENDVARS
"""


def test_parse_control_reads_the_published_text():
    g = M.parse_control(CTL)
    assert (g.nx, g.ny, g.x0, g.y0, g.dx, g.dy, g.undef, g.var) == (241, 281, 50.0, -30.0, 0.25, 0.25, -999.0, "rf")
    assert g.nbytes == 241 * 281 * 4
    with pytest.raises(ValueError, match="unsupported control option"):
        M.parse_control(CTL.replace("UNDEF", "OPTIONS yrev\nUNDEF"))
    with pytest.raises(ValueError, match="exactly one variable"):
        M.parse_control(CTL.replace("ENDVARS", "tt 0 99 TEMP\nENDVARS"))
    with pytest.raises(ValueError, match="no XDEF"):
        M.parse_control(CTL.replace("XDEF  241  LINEAR  50.0 0.25\n", ""))
    with pytest.raises(ValueError, match="LINEAR"):
        M.parse_control(CTL.replace("LINEAR  50.0", "LEVELS  50.0"))


def _write(path, field, dtype="<f4"):
    Path(path).write_bytes(np.asarray(field, dtype=dtype).tobytes())


def test_read_grd_row_orders_and_undefined_values(tmp_path):
    g = M.parse_control(CTL)
    f = np.arange(g.ny * g.nx, dtype=np.float32).reshape(g.ny, g.nx) / 100.0
    f[3, 4] = -999.0
    p = tmp_path / "d.grd"
    _write(p, f)
    south = M.read_grd(p, g, "south_first")
    north = M.read_grd(p, g, "north_first")
    assert south.shape == (281, 241) and np.isnan(south[3, 4]) and np.array_equal(north[::-1], south, equal_nan=True)
    assert south[0, 1] == pytest.approx(0.01)
    with pytest.raises(ValueError, match="not guessed"):
        M.read_grd(p, g, "whatever")


def test_read_grd_refuses_wrong_size_and_wrong_byte_order(tmp_path):
    g = M.parse_control(CTL)
    (tmp_path / "short.grd").write_bytes(b"\0" * 100)
    with pytest.raises(ValueError, match="bytes, expected"):
        M.read_grd(tmp_path / "short.grd", g, "south_first")
    f = np.random.default_rng(0).gamma(1.0, 5.0, (g.ny, g.nx))
    _write(tmp_path / "big.grd", f, ">f4")                         # big-endian rainfall read as little-endian is garbage
    with pytest.raises(ValueError, match="little-endian"):
        M.read_grd(tmp_path / "big.grd", g, "south_first")


def test_rf25_window_is_an_exact_subwindow():
    g = M.parse_control(CTL)
    rs, cs = M.rf25_window(g)
    assert (rs.start, rs.stop, cs.start, cs.stop) == (146, 275, 66, 201)
    with pytest.raises(ValueError, match="exact sub-window"):
        M.rf25_window(g, lat0=6.6)
    with pytest.raises(ValueError, match="does not fit"):
        M.rf25_window(g, lat0=35.0)
    with pytest.raises(ValueError, match="spacing"):
        M.rf25_window(M.MergedGrid(241, 281, 50.0, -30.0, 0.5, 0.5, -999.0, "rf"))


def _rf25_like(seed, H=129, W=135):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    base = 10 * np.exp(-((yy - 30 - 40 * (seed % 2)) / 25.0) ** 2 - ((xx - 40 - 30 * (seed % 3)) / 30.0) ** 2)
    return (base + rng.gamma(0.8, 2.0, (H, W))).astype(np.float32)


def _embed(rf, g, order):
    full = np.zeros((g.ny, g.nx), np.float32)
    rs, cs = M.rf25_window(g)
    full[rs, cs] = rf                                              # south-first layout
    return full[::-1] if order == "north_first" else full


def test_verify_orientation_finds_the_row_order_from_rf25():
    g = M.parse_control(CTL)
    land = np.ones((129, 135), bool)
    days = [_rf25_like(s) for s in range(4)]
    for order in ("south_first", "north_first"):
        res = M.verify_orientation([_embed(d, g, order) for d in days], days, g, land)
        assert res["row_order"] == order and res["correlation"][order] > 0.9
    noise = [np.random.default_rng(i).gamma(1.0, 3.0, (g.ny, g.nx)).astype(np.float32) for i in range(3)]
    with pytest.raises(ValueError, match="could not be established"):
        M.verify_orientation(noise, days[:3], g, land)
    with pytest.raises(ValueError, match="same, non-zero"):
        M.verify_orientation([], [], g, land)


# ------------------------------------------------------------------------------------------ regions
def _poly(x0, x1, y0, y1):
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]


def _geojson(tmp_path):
    feats = [
        {"type": "Feature", "properties": {"name": "WEST", "region_cod": "ALPHA", "uorder": 1, "subdivisio": "WEST"},
         "geometry": {"type": "MultiPolygon", "coordinates": [_poly(70, 76.3, 8, 30)]}},
        {"type": "Feature", "properties": {"name": "EAST", "region_cod": "ALPHA", "uorder": 2},
         "geometry": {"type": "Polygon", "coordinates": _poly(76.3, 82, 8, 30)}},
        {"type": "Feature", "properties": {"name": "FAR EAST", "region_cod": "BETA", "uorder": 3},
         "geometry": {"type": "Polygon", "coordinates": _poly(82, 90, 8, 30)}},
    ]
    p = tmp_path / "sd.json"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    return p


def _small_grid():
    lat, lon = np.linspace(8, 30, 12), np.linspace(70, 90, 14)
    return Grid.from_land(lat, lon, np.ones((12, 14), bool))


def test_locator_assigns_points_and_honours_holes(tmp_path):
    ring = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
    feats = [{"id": 1, "name": "A", "region": "R", "polygons": [[ring, hole]]}]
    loc = IR.make_locator(feats)
    out = loc(np.array([1.0, 5.0, 20.0]), np.array([1.0, 5.0, 5.0]))
    assert out.tolist() == [1, 0, 0]                                # inside, inside the hole, outside


def test_build_maps_uses_area_share_and_derives_regions_from_the_file(tmp_path):
    p = _geojson(tmp_path)
    grid = _small_grid()
    sub, reg = IR.build_imd_maps(grid, p)
    assert sub.names == {1: "WEST", 2: "EAST", 3: "FAR EAST"} and "area-share" in sub.label
    assert (sub.cell_region > 0).all()
    assert set(sub.cell_region[grid.lon[grid.cols] < 76.0]) == {1}
    assert reg.names == {1: "ALPHA", 2: "BETA"}
    assert set(reg.cell_region[np.isin(sub.cell_region, [1, 2])]) == {1} and set(reg.cell_region[sub.cell_region == 3]) == {2}


def test_load_features_validates(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"features": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="no features"):
        IR.load_features(bad)
    bad.write_text(json.dumps({"features": [{"properties": {"name": "x"}, "geometry": {"type": "Polygon", "coordinates": []}}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="without 'region_cod'"):
        IR.load_features(bad)
    dup = {"features": [{"properties": {"name": n, "region_cod": "R", "uorder": 1}, "geometry": {"type": "Polygon", "coordinates": _poly(0, 1, 0, 1)}}
                        for n in ("a", "b")]}
    bad.write_text(json.dumps(dup), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        IR.load_features(bad)


def test_acceptance_known_points_passes_and_fails_as_it_should(tmp_path):
    p = _geojson(tmp_path)
    grid = _small_grid()
    sub, _ = IR.build_imd_maps(grid, p)
    ok = IR.acceptance_known_points(grid, p, sub, (("a", 20.0, 72.0, "WEST"), ("b", 15.0, 79.0, "EAST"), ("c", 12.0, 88.0, "FAR EAST")))
    assert ok["passed"] and ok["polygon_ok"] == 3 and ok["cell_ok"] == ok["cell_testable"] == 3
    wrong = IR.acceptance_known_points(grid, p, sub, (("a", 20.0, 72.0, "EAST"),))
    assert not wrong["passed"] and not wrong["points"][0]["polygon_ok"]
    flipped = IR.acceptance_known_points(grid, p, sub, (("a", 20.0, 72.0, "NO SUCH NAME"),))
    assert not flipped["passed"]


REAL = Path(os.environ.get("DATAMEND_DATA_DIR", Path(__file__).resolve().parents[2] / "data")) / "regions" / "sd_boundary_rainfall.json"


@pytest.mark.skipif(not REAL.is_file(), reason="IMD boundary file not fetched (python scripts/fetch_imd_regions.py)")
def test_real_imd_file_acceptance_on_the_rf25_land_grid():
    cm = json.loads((Path(__file__).resolve().parents[1] / "assets" / "client_map.json").read_text())
    land = np.array([[ch != "0" for ch in r] for r in cm["rows"]])
    grid = Grid.from_land(6.5 + 0.25 * np.arange(129), 66.5 + 0.25 * np.arange(135), land)
    sub, reg = IR.build_imd_maps(grid, REAL)
    acc = IR.acceptance_known_points(grid, REAL, sub)
    assert acc["passed"] and acc["polygon_ok"] == acc["n"] == 10
    assert len(reg.names) == 4 and len(sub.names) == 36
