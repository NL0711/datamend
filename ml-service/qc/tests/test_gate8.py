"""Gate 8: UK MIDAS study. Reader, change categories, inverse-distance gridding, labels, and the real-label benchmark.

Everything runs on generated station files that follow the documented MIDAS Open layout. The reader has NOT been
run on real files (see the docstring of qc.uk.midas).
"""

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qc import paths
from qc.baselines import run_untrained
from qc.benchmark import load_bench_year
from qc.clients import build_client_map, save_client_map
from qc.config import load_config
from qc.prepare import load_prepared, prepare
from qc.uk.build import build_grid, build_uk_benchmark, labels_dir, spec_from_config
from qc.uk.gridding import grid_year, neighbour_table, station_matrices
from qc.uk.midas import MidasError, decode_q, load_midas, read_badc_csv

YEARS = list(range(2000, 2008))
LATLON = {f"S{i:02d}": (50.0 + 0.15 * (i % 5), -4.0 + 0.4 * (i // 5)) for i in range(1, 11)}
HEADER = "ob_end_time,id,id_type,ob_day_cnt,src_id,prcp_amt,prcp_amt_q,rec_st_ind,met_domain_name"


def _file(path, sid, rows, src=None):
    lat, lon = LATLON[sid]
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Conventions,G,BADC-CSV,1", "title,G,generated test file", f"location,G,{lat},{lon}", "data", HEADER]
    lines += [f"{d} 09:00:00,{sid},DCNN,{n},{src or sid},{a},{q},1011,DLY3208" for d, n, a, q in rows] + ["end data"]
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture(scope="module")
def midas(tmp_path_factory):
    root = tmp_path_factory.mktemp("midas")
    rng = np.random.default_rng(3)
    days = {y: pd.date_range(f"{y}-01-01", f"{y}-12-31") for y in YEARS}
    field = {y: np.where(rng.random(len(days[y])) < 0.4, rng.gamma(0.8, 9.0, len(days[y])), 0.0) for y in YEARS}
    v1 = {}
    for sid in LATLON:
        for y in YEARS:
            v1[sid, y] = [(d.strftime("%Y-%m-%d"), 1, round(float(field[y][i] * (0.8 + 0.4 * rng.random())), 1), 9)
                          for i, d in enumerate(days[y])]
    v0 = {}
    date = lambda y, k: days[y][k].strftime("%Y-%m-%d")
    # manual correction: three days at S03 in 2005 (original 400 mm; the corrected value is in version 1)
    for k in (100, 101, 102):
        v1["S03", 2005][k] = (date(2005, k), 1, 4.0, 2579)
    v0["S03", 2005] = [(date(2005, k), 1, 400.0, 9) for k in (100, 101, 102)]
    # automatic estimate replacing a placeholder zero (S05, day 50)
    v1["S05", 2005][50] = (date(2005, 50), 1, 2.0, 1209)
    v0["S05", 2005] = [(date(2005, 50), 1, 0.0, 9)]
    # multi-day total split into three daily values (S07, days 198-200)
    v0["S07", 2005] = [(date(2005, 200), 3, 30.0, 20009)]
    for k in (198, 199, 200):
        v1["S07", 2005][k] = (date(2005, k), 1, 10.0, 9)
    # flag-only change, an unflagged amount change, and an original with no current-best record
    v0["S02", 2005] = [(date(2005, 10), 1, v1["S02", 2005][10][2], 9)]
    v1["S02", 2005][10] = (date(2005, 10), 1, v1["S02", 2005][10][2], 1)
    v0["S09", 2004] = [(date(2004, 20), 1, 2.0, 9)]
    v1["S09", 2004][20] = (date(2004, 20), 1, 3.0, 9)
    v0["S08", 2005] = [(date(2005, 5), 1, 7.0, 9)]
    del v1["S08", 2005][5]
    for (sid, y), rows in v1.items():
        base = root / "testshire" / f"{sid}_name"
        _file(base / "qc-version-1" / f"midas-open_x_{sid}_qcv-1_{y}.csv", sid, rows)
        if (sid, y) in v0:
            _file(base / "qc-version-0" / f"midas-open_x_{sid}_qcv-0_{y}.csv", sid, v0[sid, y])
    # commissioning-trial records (src_id 99999) must be ignored
    _file(root / "testshire" / "S10_name" / "qc-version-1" / "midas-open_x_99999_qcv-1_2000.csv", "S10",
          [("2000-01-01", 1, 777.0, 9)], src="99999")
    return root


def test_decode_q_reads_the_five_digits():
    assert decode_q(2579) == {"marker": 0, "estimate": 2, "status": 5, "query": 7, "level": 9}
    assert decode_q("9")["level"] == 9 and decode_q(-20009)["marker"] == 2 and decode_q("x")["status"] == 0


def test_reader_parses_header_and_table_and_rejects_other_files(midas, tmp_path):
    f = next((midas / "testshire" / "S03_name" / "qc-version-1").glob("*_2005.csv"))
    meta, df = read_badc_csv(f)
    assert meta["location"] == ["50.45,-4.0"] and len(df) == 365 and "prcp_amt_q" in df
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    with pytest.raises(MidasError, match="no 'data' line"):
        read_badc_csv(bad)


def test_changes_are_classified_and_only_manual_corrections_are_labels(midas):
    sd = load_midas(midas, ["testshire"], YEARS)
    c = sd.counts
    assert c["manual_correction"] == 3 and c["auto_estimate"] == 1 and c["multiday_split"] == 1
    assert c["flag_only"] == 1 and c["unflagged_change"] == 1 and c["unmatched"] == 1
    assert len(sd.manual) == 3 and set(sd.manual["station"]) == {"S03"}
    assert "99999" not in sd.ids and len(sd.ids) == 10                      # trial records ignored
    assert "subset" in sd.subset_note
    # the original multi-day total gives no daily value for the three days it covered
    d = sd.daily[(sd.daily["station"] == "S07") & (sd.daily["date"].between("2005-07-18", "2005-07-20"))]
    assert len(d) == 3 and d["original"].isna().all() and (d["corrected"] == 10.0).all()
    m = sd.daily[(sd.daily["station"] == "S03") & (sd.daily["date"] == "2005-04-11")].iloc[0]
    assert m["original"] == 400.0 and m["corrected"] == 4.0


def test_missing_coordinates_and_counties_stop_the_reader(midas, tmp_path):
    dst = tmp_path / "m"
    shutil.copytree(midas, dst)
    for f in dst.rglob("*.csv"):
        f.write_text("\n".join(l for l in f.read_text().splitlines() if not l.startswith("location")))
    with pytest.raises(MidasError, match="no coordinates"):
        load_midas(dst, ["testshire"], [2005])
    with pytest.raises(MidasError, match="not found"):
        load_midas(midas, ["nowhere"], [2005])


# ---------------------------------------------------------------- gridding

@pytest.fixture(scope="module")
def ukcfg(midas, tmp_path_factory):
    root = tmp_path_factory.mktemp("uk")
    (root / "t.yaml").write_text(f"""
extends: uk.yaml
name: ukt
paths: {{rf25: "{(root / 'work' / 'grid').as_posix()}", work: "{(root / 'work').as_posix()}", out: "{(root / 'out').as_posix()}"}}
uk: {{midas_dir: "{midas.as_posix()}", counties: [testshire], search_radius_km: 60}}
grid: {{n_lat: 9, n_lon: 12, lat0: 49.9, lon0: -4.1, step: 0.1}}
years: {{train: [2000, 2003], val: [2004, 2005], test: [2006, 2007], fusion_fit: [2004, 2004], threshold: [2005, 2005], stress: null}}
clients: {{k: 2, seed: 0, heldout: [2], buffer_cells: 2, map: "{(root / 'work' / 'client_map.json').as_posix()}"}}
components: {{hidden_radius: 1, slow: {{ring_outer: 2}}, neighbour_baseline: {{radius: 2}}, spatial: {{radius: 2, width: 8, dense: 16}}}}
benchmark: {{name: ukt, allow_unpinned: true, expected_hash: null}}
evaluation: {{bootstrap: 20}}
""", encoding="utf-8")
    from qc.config import CONFIG_DIR
    shutil.copy(CONFIG_DIR / "uk.yaml", root / "uk.yaml")
    shutil.copy(CONFIG_DIR / "base.yaml", root / "base.yaml")
    return load_config(root / "t.yaml")


def test_idw_uses_at_most_four_gauges_nearest_first(ukcfg, midas):
    spec = spec_from_config(ukcfg)
    sd = load_midas(midas, ["testshire"], [2005])
    idx, dist = neighbour_table(spec, sd.lat, sd.lon)
    assert (np.diff(np.where(np.isfinite(dist), dist, 1e9), axis=1) >= 0).all()          # nearest first
    # one gauge only: the grid value is that gauge's value
    m = {k: np.full((2, len(sd.ids)), np.nan, np.float32) for k in ("corrected", "original")}
    m["manual"] = np.zeros((2, len(sd.ids)), bool)
    m["corrected"][:, 3] = 7.0
    m["original"][:, 3] = 7.0
    g = grid_year(m, idx, dist, spec)
    ok = np.isfinite(g["corrected"])
    assert ok.any() and np.allclose(g["corrected"][ok], 7.0) and not g["labelled"].any() and not g["excluded"].any()
    # more than four gauges available: the fifth and beyond never contribute
    m2 = {k: np.tile(np.arange(1, len(sd.ids) + 1, dtype=np.float32), (1, 1)) for k in ("corrected", "original")}
    m2["manual"] = np.zeros((1, len(sd.ids)), bool)
    g2 = grid_year(m2, idx, dist, spec)
    cell = int(np.argmax((idx >= 0).sum(1) >= 6))
    first4 = idx[cell, :4] + 1.0
    w = 1.0 / np.maximum(dist[cell, :4], 1.0) ** 2
    assert np.isclose(g2["corrected"][0, cell], (w * first4).sum() / w.sum(), rtol=1e-4)


def test_cell_days_are_labelled_only_where_a_corrected_gauge_fed_them(ukcfg, midas):
    spec = spec_from_config(ukcfg)
    sd = load_midas(midas, ["testshire"], [2005])
    idx, dist = neighbour_table(spec, sd.lat, sd.lon)
    g = grid_year(station_matrices(sd, 2005), idx, dist, spec)
    s03 = sd.ids.index("S03")
    expect = np.array([s03 in idx[c, :4] for c in range(idx.shape[0])])
    t, cells = np.nonzero(g["labelled"])
    assert set(t) <= {100, 101, 102} and set(cells) == set(np.nonzero(expect)[0])
    assert not (g["labelled"] & g["excluded"]).any()
    ex_days = set(np.nonzero(g["excluded"].any(axis=1))[0])
    assert 50 in ex_days and ex_days & {198, 199, 200}                      # auto estimate and multi-day split: excluded, not labelled
    assert (np.abs(g["original"] - g["corrected"])[g["labelled"]] > 1e-3).all()


# ---------------------------------------------------------------- the build

@pytest.fixture(scope="module")
def built(ukcfg):
    from training.data import RainfallArchive
    summary = build_grid(ukcfg)
    arch = RainfallArchive(paths.rf25_dir(ukcfg))
    cm = build_client_map(arch.land_mask, arch.lat, arch.lon, 2, 0)
    save_client_map(Path(ukcfg.clients.map), cm, 2, 0)
    return summary, prepare(ukcfg, check_data=True)


def test_grid_files_satisfy_the_data_contract_and_the_summary_is_honest(built):
    summary, p = built
    assert summary["stations"] == 10 and summary["land_cells"] == p.grid.n_land > 0
    assert summary["record_changes"]["manual_correction"] == 3 and "subset" in summary["subset_note"]
    assert summary["choices"]["max_gauges"] == 4 and summary["cell_days"]["labelled_cell_days"] > 0
    assert summary["cell_days"]["excluded_cell_days"] > 0


def test_benchmark_holds_real_labels_scored_on_the_original_series(built, ukcfg):
    _, p = built
    m = build_uk_benchmark(p, overwrite=True)
    assert m["tier_short"] == "real corrections (UK)" and any("Circularity" in c for c in m["caveats"])
    y = load_bench_year(p, "val", 2005)
    lab = y.faults.labels()
    assert lab.sum() == m["summary"]["val"]["labelled_cell_days"] > 0 and y.excluded is not None
    assert not (lab & y.excluded).any() and not (lab & y.extremes.protected).any() and not (lab & y.extremes.ambiguous).any()
    assert (y.corrupted[lab] > y.clean[lab] + 1e-3).all() and y.corrupted[lab].max() > 100   # the scored value is the original (the 400 mm gauge)
    keep = ~lab & ~y.excluded
    assert np.allclose(y.corrupted[keep], y.clean[keep], equal_nan=True)
    assert all(e["kind"] == "manual_correction" for e in y.faults.events)
    assert np.load(labels_dir(ukcfg) / "uk_2005.npz")["original"].shape[0] == 365


def test_scores_and_metrics_carry_the_real_label_tier_and_caveats(built, ukcfg, capsys):
    _, p0 = built
    build_uk_benchmark(p0, overwrite=True)
    p = load_prepared(ukcfg)
    res = run_untrained(p, ("val",))
    r = res[("rules", "val")]
    assert r["label_tier"] == "real corrections (UK)" and any("Circularity" in c for c in r["caveats"])
    from qc.__main__ import print_table
    print_table([v for (n, s), v in res.items() if s == "val"], 1.0)
    out = capsys.readouterr().out
    assert "labels: real corrections (UK)" in out and "Circularity" in out and "Subset" in out


def test_a_missing_uk_grid_never_falls_back_to_india(tmp_path):
    bad = load_config(paths.ASSETS.parent / "configs" / "uk.yaml", [f"paths.rf25={(tmp_path / 'nothing').as_posix()}"])
    with pytest.raises(FileNotFoundError, match="uk-grid"):
        paths.rf25_dir(bad)
