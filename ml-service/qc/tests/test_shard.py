"""--shard splits the (component, seed) units between processes (one per GPU) with no overlap and no gaps."""

import pytest

from qc.__main__ import main, shard_units
from qc.benchmark import build_benchmark
from qc.config import ConfigError, load_config
from qc.prepare import load_prepared
from qc.runs import RunDir
from qc import paths
from qc.tests.test_gate4 import TINY


def test_shards_partition_the_units_in_order():
    units = [(c, s) for c in ("spatial", "temporal", "plain_gru") for s in (0, 1, 2)]
    for n in (1, 2, 3, 4):
        parts = [shard_units(units, f"{i}/{n}") for i in range(n)]
        flat = [u for part in parts for u in part]
        assert sorted(flat) == sorted(units) and len(flat) == len(set(flat)), n          # every unit exactly once
        assert all(part == [u for u in units if u in part] for part in parts)             # order inside a shard is kept
    assert shard_units(units, None) == units
    assert shard_units(units, "0/2") == units[0::2] and shard_units(units, "1/2") == units[1::2]
    assert shard_units([], "0/2") == []
    for bad in ("2/2", "-1/2", "1", "a/b", "0/0", "1/2/3"):
        with pytest.raises(ConfigError):
            shard_units(units, bad)


def test_cli_trains_only_the_units_of_its_shard(world, prepared):
    over = TINY + ["name=shardtest", "benchmark.name=shardbench"]
    cfg = load_config(world / "test.yaml", over)
    p = load_prepared(cfg)
    build_benchmark(p, splits=("val",), overwrite=True)
    args = ["train", "--config", str(world / "test.yaml"), "--seeds", "0", "--max-train-years", "2"] + \
           [x for s in over for x in ("--set", s)]
    assert main(args + ["--shard", "1/2"]) == 0                                           # units: spatial, temporal, plain_gru -> temporal
    root = paths.out_dir(cfg) / "shardtest"
    ran = sorted(d.name for d in root.iterdir() if d.is_dir() and (d / "meta.json").is_file())
    assert ran == ["temporal_s0"]
    assert main(args + ["--shard", "0/2"]) == 0                                           # the other shard: spatial and plain_gru
    ran = sorted(d.name for d in root.iterdir() if d.is_dir() and (d / "meta.json").is_file())
    assert ran == ["plain_gru_s0", "spatial_s0", "temporal_s0"]
