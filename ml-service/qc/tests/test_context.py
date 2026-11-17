"""Event-coherence context features: corroboration by neighbours, no reading of the hidden disc, no future."""

import numpy as np
import pytest

from qc.context import CONTEXT, WET_MM, context_functions
from qc.scoring import make_block


@pytest.fixture(scope="module")
def fns(prepared):
    return context_functions(prepared)


@pytest.fixture(scope="module")
def block(prepared):
    return make_block(prepared, prepared.split.years["val"][1], None, pad=prepared.cfg.components.history_days)


def _with(block, t, cell, value):
    b = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    b.obs[b.pad + t, cell] = value
    return b


def _cell(p, r, c):
    return int(np.argmax((p.grid.rows == r) & (p.grid.cols == c)))


def test_values_are_shares_and_missing_own_value_is_nan(prepared, fns, block):
    b = _with(block, 30, _cell(prepared, 12, 8), np.nan)
    for name in CONTEXT:
        s = fns[name](b)
        assert s.shape == b.target.shape and s.dtype == np.float32
        assert np.nanmin(s) >= 0.0 and np.nanmax(s) <= 1.0
        assert np.isnan(s[30, _cell(prepared, 12, 8)])


def test_isolated_spike_is_uncorroborated_and_a_widespread_event_is_corroborated(prepared, fns, block):
    g, t = prepared.grid, 20
    cell = _cell(prepared, 12, 8)
    dry = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    dry.obs[dry.pad + t] = 0.0                                              # every cell dry that day
    spike = _with(dry, t, cell, 900.0)
    wide = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    wide.obs[wide.pad + t] = 5000.0                                         # every cell very wet that day
    assert fns["nbr_wet"](spike)[t, cell] == 0.0 and fns["nbr_heavy"](spike)[t, cell] == 0.0
    assert fns["nbr_wet"](wide)[t, cell] == 1.0 and fns["nbr_heavy"](wide)[t, cell] == 1.0


def test_hidden_disc_is_not_read_and_the_outside_is(prepared, fns, block):
    target, inside, outside = _cell(prepared, 12, 8), _cell(prepared, 13, 9), _cell(prepared, 12, 11)
    t = 200
    dry = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    dry.obs[dry.pad + t] = 0.0
    base = fns["nbr_wet"](dry)[t, target]
    assert fns["nbr_wet"](_with(dry, t, inside, 900.0))[t, target] == base
    assert fns["nbr_wet"](_with(dry, t, outside, 900.0))[t, target] > base


def test_context_is_causal_and_uses_only_the_same_day(prepared, fns, block):
    t = 180
    future = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    future.obs[future.pad + t + 1:] = 500.0
    past = type(block)(block.year, block.split, block.obs.copy(), block.pad, block.doy, block.bench)
    past.obs[:past.pad + t] = 500.0
    for name in CONTEXT:
        assert np.array_equal(fns[name](block)[t], fns[name](future)[t], equal_nan=True)
        assert np.array_equal(fns[name](block)[t], fns[name](past)[t], equal_nan=True)
