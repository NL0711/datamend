"""Gate 2: synthetic faults, protected and ambiguous extremes, the frozen benchmark."""

import numpy as np
import pytest

from qc.benchmark import build_benchmark, check_benchmark, load_bench_year
from qc.config import load_config
from qc.extremes import find_extremes
from qc.faults import BASE_KINDS, KINDS, FaultGenerator, FaultSettings, is_unseen_setting, settings_from_config
from qc.grid import ContractError, Grid


@pytest.fixture(scope="module")
def year(prepared):
    y = prepared.split.years["val"][0]
    return prepared.store.year(y)


# ---------------------------------------------------------------- extremes

def test_extremes_rule_on_a_hand_made_field():
    land = np.ones((5, 6), bool)
    grid = Grid.from_land(np.arange(5), np.arange(6), land)
    f = np.zeros((2, 5, 6), np.float32)
    f[0, 0:2, 0:2] = 50          # day 0: a 2x2 block of heavy rain -> protected (4 cells)
    f[0, 4, 5] = 50              # day 0: one isolated heavy cell -> ambiguous
    f[1, 2, 2:4] = 50            # day 1: a pair -> neither
    f[1, 0, 0] = 50              # day 1: same place as the block but a different day: isolated -> ambiguous
    ex = find_extremes(grid.to_series(f), np.full(30, 10.0, np.float32), grid, min_cells=4)
    assert ex.protected.sum() == 4 and ex.n_protected_events == 1
    assert grid.to_field(ex.protected, fill=False)[0, 0:2, 0:2].all()
    assert ex.ambiguous.sum() == 2 and ex.n_small_groups == 1
    assert not (ex.protected & ex.ambiguous).any()


def test_diagonal_cells_are_connected():
    grid = Grid.from_land(np.arange(4), np.arange(4), np.ones((4, 4), bool))
    f = np.zeros((1, 4, 4), np.float32)
    for i in range(4):
        f[0, i, i] = 99
    ex = find_extremes(grid.to_series(f), np.full(16, 10.0, np.float32), grid, min_cells=4)
    assert ex.protected.sum() == 4


# ---------------------------------------------------------------- faults

def test_footprint_weights(prepared):
    gen = FaultGenerator(prepared.grid)
    centre = int(np.argmax((prepared.grid.rows == 12) & (prepared.grid.cols == 15)))
    cells, w = gen.footprint(centre, 0.0)
    assert cells.tolist() == [centre] and w.tolist() == [1.0]
    cells, w = gen.footprint(centre, 3.0)
    assert cells[0] == centre and w[0] == 1.0 and (w > 0).all() and (np.diff(w) <= 0).all()
    d = np.hypot(prepared.grid.rows[cells] - 12, prepared.grid.cols[cells] - 15)
    assert d.max() < 3.0 and np.allclose(w, (1 - d / 3.0) ** 2, atol=1e-6)
    assert cells.size == 25                      # all cells strictly closer than 3 on a full interior patch


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_produces_labelled_changes(prepared, year, kind):
    gen = FaultGenerator(prepared.grid)
    st = FaultSettings(kinds=(kind,), rate=0.002, combination_bases=tuple(k for k in BASE_KINDS if k != "repeat"))
    fs = gen.generate(year, st, np.random.default_rng(3))
    assert fs.events and all(e["kind"] == kind for e in fs.events)
    out = fs.apply(year)
    lab = fs.labels()
    assert np.array_equal(np.abs(np.nan_to_num(out) - np.nan_to_num(year)) > 1e-3, lab)    # labelled <=> changed
    assert (out[np.isfinite(out)] >= 0).all()
    assert np.array_equal(year, prepared.store.year(prepared.split.years["val"][0]))       # input not modified
    if kind == "edge":
        assert all(e["radius"] > 0 and e["centre"] in set(gen.edge_cells.tolist()) for e in fs.events)
    if kind == "combination":
        assert all(len(e["bases"]) == 2 and e["bases"][0] != e["bases"][1] for e in fs.events)
    if kind == "zeroed":
        assert (out[lab] < year[lab]).all()                   # rain is removed everywhere in the footprint ...
        full = fs.weight == 1.0
        assert (fs.value[full] == 0).all()                    # ... and completely at the centre


def test_generation_is_reproducible_and_hits_the_rate(prepared, year, cfg):
    gen = FaultGenerator(prepared.grid)
    st = settings_from_config(cfg, "seen")
    a = gen.generate(year, st, np.random.default_rng(5))
    b = gen.generate(year, st, np.random.default_rng(5))
    c = gen.generate(year, st, np.random.default_rng(6))
    assert np.array_equal(a.t, b.t) and np.array_equal(a.value, b.value)
    assert not (a.t.size == c.t.size and np.array_equal(a.t, c.t))
    share = a.t.size / np.isfinite(year).sum()
    assert st.rate <= share < st.rate * 1.5
    assert np.unique(np.stack([a.t, a.cell]), axis=1).shape[1] == a.t.size       # faults never overlap


def test_faults_never_touch_forbidden_cell_days(prepared, year, cfg):
    ex = find_extremes(year, prepared.stats.heavy_mm, prepared.grid, 2)
    assert ex.protected.any()
    fs = FaultGenerator(prepared.grid).generate(year, settings_from_config(cfg, "seen"), np.random.default_rng(1), forbidden=ex.protected)
    assert not ex.protected[fs.t, fs.cell].any()


def test_seen_settings_exclude_everything_reserved_for_test(prepared, year, cfg):
    gen = FaultGenerator(prepared.grid)
    seen = gen.generate(year, settings_from_config(cfg, "seen"), np.random.default_rng(2))
    assert not any(is_unseen_setting(e, cfg) for e in seen.events)
    assert not {e["kind"] for e in seen.events} & set(cfg.benchmark.kinds_test_only)
    assert not any("repeat" in e["bases"] for e in seen.events)
    everything = gen.generate(year, settings_from_config(cfg, "all"), np.random.default_rng(2))
    flags = [is_unseen_setting(e, cfg) for e in everything.events]
    assert any(flags) and not all(flags)
    assert {e["kind"] for e in everything.events} & set(cfg.benchmark.kinds_test_only)


# ---------------------------------------------------------------- frozen benchmark

def test_benchmark_files_round_trip(prepared, bench):
    p = prepared
    y = p.split.years["test"][0]
    by = load_bench_year(p, "test", y)
    assert by.corrupted.shape == by.clean.shape
    assert not by.extremes.protected[by.faults.t, by.faults.cell].any()
    assert by.unseen_setting.size == len(by.faults.events) and by.unseen_setting.any()
    val = load_bench_year(p, "val", p.split.years["val"][0])
    assert not val.unseen_setting.any()                       # validation holds seen settings only
    s = bench["summary"]["test"]
    assert 0.01 <= s["fault_share_of_cell_days"] < 0.015
    assert set(s["by_kind"]) <= set(KINDS)
    assert "synthetic" in bench["label_tier"]


def test_benchmark_is_deterministic_and_guarded(world, cfg, prepared, bench):
    with pytest.raises(ContractError, match="already holds"):
        build_benchmark(prepared, splits=("val", "test"))
    again = build_benchmark(prepared, splits=("val", "test"), overwrite=True)
    assert again["hash"] == bench["hash"]
    assert check_benchmark(prepared)["hash"] == bench["hash"]              # unpinned is allowed in the test config

    from qc.prepare import load_prepared
    pinned = load_prepared(load_config(world / "test.yaml", [f"benchmark.expected_hash={bench['hash']}", "benchmark.allow_unpinned=false"]))
    assert check_benchmark(pinned)["hash"] == bench["hash"]
    wrong = load_prepared(load_config(world / "test.yaml", ["benchmark.expected_hash=deadbeef"]))
    with pytest.raises(ContractError, match="refusing to score"):
        check_benchmark(wrong)
    unpinned = load_prepared(load_config(world / "test.yaml", ["benchmark.allow_unpinned=false"]))
    with pytest.raises(ContractError, match="expected_hash is not set"):
        check_benchmark(unpinned)
