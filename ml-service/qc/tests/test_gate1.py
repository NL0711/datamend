"""Gate 0-1: configuration, data contract, client map, splits, training statistics, leakage audit."""

import dataclasses

import numpy as np
import pytest

from qc.clients import load_client_map, save_client_map
from qc.config import ConfigError, load_config
from qc.grid import ContractError, check_contract
from qc.prepare import load_prepared
from qc.splits import BUFFER, HELDOUT, TRAIN, LeakageError, audit_split, cell_roles, make_split
from qc.stats import fit_train_stats
from qc.tests.conftest import YEARS, write_year


# ---------------------------------------------------------------- config

def test_profiles_change_only_compute(world):
    a = load_config(world / "test.yaml", profile="single-gpu")
    b = load_config(world / "test.yaml", profile="kaggle")
    assert a.compute.parallel_experiments == 1 and b.compute.parallel_experiments == 2
    assert a.digest() == b.digest()                       # same splits, seeds and benchmark under either profile
    da, db = a.to_dict(), b.to_dict()
    da.pop("compute"), db.pop("compute")
    assert da == db


def test_overrides_and_errors(world):
    c = load_config(world / "test.yaml", ["clients.buffer_cells=2", "seed=7"])
    assert c.clients.buffer_cells == 2 and c.seed == 7
    assert c.digest() != load_config(world / "test.yaml").digest()
    with pytest.raises(ConfigError):
        load_config(world / "test.yaml", profile="does-not-exist")
    with pytest.raises(ConfigError):
        load_config(world / "test.yaml", ["no_equals_sign"])
    with pytest.raises(ConfigError):
        c.nonexistent_key
    with pytest.raises(ConfigError):
        c.seed = 3


# ---------------------------------------------------------------- data contract

def test_contract_passes_on_good_data(world, cfg):
    rep = check_contract(world / "rf25", YEARS, cfg.grid)
    assert rep["land_cells"] == cfg.grid.land_cells and rep["days"][1992] == 366
    assert sum(rep["missing_on_land"].values()) == 0


@pytest.mark.parametrize("kwargs, message", [({"negative": True}, "negative values"), ({"short": True}, "TIME runs")])
def test_contract_fails_loudly(tmp_path, cfg, kwargs, message):
    write_year(tmp_path / "RF25_ind1990_rfp25.nc", 1990, np.random.default_rng(1), **kwargs)
    with pytest.raises(ContractError, match=message):
        check_contract(tmp_path, [1990], cfg.grid)


def test_contract_reports_missing_year_and_wrong_grid(world, cfg):
    with pytest.raises(ContractError, match="is missing"):
        check_contract(world / "rf25", [1989], cfg.grid)
    real = load_config(world / "test.yaml", ["grid.n_lat=129"])
    with pytest.raises(ContractError, match="LATITUDE"):
        check_contract(world / "rf25", [1990], real.grid)


# ---------------------------------------------------------------- client map

def test_client_map_roundtrip_and_corruption(tmp_path):
    cm = np.array([[0, 1, 1], [2, 2, 0]], np.int8)
    save_client_map(tmp_path / "m.json", cm, 2, 0)
    assert np.array_equal(load_client_map(tmp_path / "m.json"), cm)
    text = (tmp_path / "m.json").read_text().replace('"011"', '"012"')
    (tmp_path / "m.json").write_text(text)
    with pytest.raises(ValueError, match="corrupt"):
        load_client_map(tmp_path / "m.json")


# ---------------------------------------------------------------- splits and leakage

def test_roles_and_buffer_distance(prepared):
    s = prepared.split
    held = np.argwhere(s.roles == HELDOUT)
    for r, c in np.argwhere(s.roles == TRAIN):
        assert np.abs(held - (r, c)).max(axis=1).min() > s.buffer_cells      # Chebyshev distance to every held-out cell
    for r, c in np.argwhere(s.roles == BUFFER):
        assert np.abs(held - (r, c)).max(axis=1).min() <= s.buffer_cells
    assert (s.roles == BUFFER).any() and (s.roles == TRAIN).any()
    assert not (s.input_mask() & (s.roles == HELDOUT)).any()
    assert not (s.target_mask() & (s.roles != TRAIN)).any()


def test_client_masks_read_only_own_cells(prepared):
    s = prepared.split
    for c in s.train_clients:
        assert (s.client_map[s.input_mask(c)] == c).all()
    assert s.heldout == [3] and s.train_clients == [1, 2]
    assert (s.client_map[s.eval_mask("unseen")] == 3).all()


def test_audit_rejects_bad_splits(cfg, prepared):
    s = prepared.split
    with pytest.raises(LeakageError, match="reach"):
        audit_split(s, reach_cells=s.buffer_cells + 1)
    audit_split(s, reach_cells=s.buffer_cells)
    bad_years = dict(s.years, val=s.years["val"] + [s.years["train"][-1]])
    with pytest.raises(LeakageError, match="both train and val"):
        audit_split(dataclasses.replace(s, years=bad_years))
    with pytest.raises(LeakageError, match="overlap"):
        audit_split(dataclasses.replace(s, years=dict(s.years, threshold=s.years["fusion_fit"])))
    leaky = dataclasses.replace(s, roles=np.where(s.roles == BUFFER, TRAIN, s.roles).astype(np.int8))
    with pytest.raises(LeakageError, match="inside the buffer"):
        audit_split(leaky)
    with pytest.raises(LeakageError, match="do not exist"):
        make_split(load_config(cfg.paths.work + "/../test.yaml", ["clients.heldout=[9]"]), s.client_map)


def test_zero_buffer_gives_no_buffer_cells():
    cm = np.array([[1, 1, 2, 2]], np.int8)
    assert (cell_roles(cm, [2], 0) == np.array([[TRAIN, TRAIN, HELDOUT, HELDOUT]])).all()
    assert (cell_roles(cm, [2], 1) == np.array([[TRAIN, BUFFER, HELDOUT, HELDOUT]])).all()


# ---------------------------------------------------------------- training statistics

def test_statistics_use_training_years_only(prepared):
    p = prepared
    assert p.stats.years == p.split.years["train"]
    val_year = p.split.years["val"][0]
    with pytest.raises(LeakageError, match="outside the train years"):
        fit_train_stats({val_year: p.store.year(val_year)}, [val_year], p.split, p.cell_client)


def test_normalization_is_per_client_and_never_clips(prepared):
    st = prepared.stats
    assert set(st.client_scale) == {1, 2, 3}
    assert st.client_scale[3] > st.client_scale[1]             # the eastern client is wetter in the test world
    mm = np.array([0.0, 50.0, 500.0, 5000.0, 50000.0], np.float32)[:, None] * np.ones(prepared.grid.n_land, np.float32)
    z = st.normalize(mm)
    assert (np.diff(z, axis=0) > 0).all()                      # far above the fitted percentile, order and size survive
    assert np.allclose(np.expm1(z * st.scale), mm, rtol=1e-4)  # and the value is exactly recoverable


def test_statistics_shapes(prepared):
    st, n = prepared.stats, prepared.grid.n_land
    assert st.climatology.shape == (366, n) and st.bound_mm.shape == (366, n) and st.heavy_mm.shape == (n,)
    assert np.isfinite(st.climatology).all() and (st.heavy_mm > 0).all()


def test_load_prepared_detects_a_changed_split(world, cfg, prepared):
    assert load_prepared(cfg).manifest["hash"] == prepared.manifest["hash"]
    with pytest.raises(ContractError, match="does not match"):
        load_prepared(load_config(world / "test.yaml", ["clients.buffer_cells=1"]))
