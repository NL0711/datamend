"""A second phase1 run (for example after a smoke run) must reuse an identical frozen benchmark, and refuse a different one."""
import pytest

from qc import benchmark as B
from qc.grid import ContractError


@pytest.fixture()
def own_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "bench_dir", lambda cfg: tmp_path / "bench")
    return tmp_path / "bench"


def test_nothing_to_reuse_before_a_build(prepared, own_dir):
    assert B.reusable_benchmark(prepared) is None


def test_identical_benchmark_is_reused_and_nothing_is_regenerated(prepared, own_dir):
    built = B.build_benchmark(prepared)
    stamp = (own_dir / "manifest.json").stat().st_mtime_ns
    m = B.reusable_benchmark(prepared)
    assert m is not None and m["hash"] == built["hash"]
    assert (own_dir / "manifest.json").stat().st_mtime_ns == stamp
    with pytest.raises(ContractError):                    # building again without --overwrite is still refused
        B.build_benchmark(prepared)


def test_changed_settings_are_not_reusable(prepared, own_dir):
    B.build_benchmark(prepared)
    path = own_dir / "manifest.json"
    import json
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["config"]["rate"] = doc["config"]["rate"] * 2          # as if it had been built with another fault rate
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert B.reusable_benchmark(prepared) is None
