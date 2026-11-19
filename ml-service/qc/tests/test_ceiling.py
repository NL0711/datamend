"""qc.ceiling on the generated QC world: the table agrees with the standard evaluation and the groups partition the faults."""
import numpy as np
import pytest

from qc import ceiling as C
from qc.baselines import run_untrained
from qc.evaluate import evaluate_component
from qc.fusion_eval import holdout_years


@pytest.fixture(scope="module")
def ready(prepared, bench):
    run_untrained(prepared, ("val",))
    return prepared


def test_overall_recall_equals_the_standard_evaluation(ready):
    p = ready
    tab = C.fault_table(p, "rules", 1.0)
    res = C.analyse(tab, 1.0)
    std = evaluate_component(p, "rules", "val", [1.0], ("seen",), years=holdout_years(p))
    row = std["groups"]["seen"]["by_budget"]["1.0"]["faults"]
    assert res["overall"]["recall"] == pytest.approx(row["recall"], abs=1e-9)


def test_bins_partition_the_fault_cell_days(ready):
    res = C.analyse(C.fault_table(ready, "rules", 1.0), 1.0)
    n = res["overall"]["n"]
    assert n > 0
    assert sum(v["n"] for v in res["by_change_mm"].values()) == n
    assert sum(v["n"] for v in res["by_weight"].values()) == n
    assert sum(v["all"]["n"] for v in res["by_kind"].values()) == n
    for v in res["by_kind"].values():
        assert v["centre_cells"]["n"] <= v["all"]["n"] and v["strong"]["n"] <= v["all"]["n"]


def test_strong_group_is_defined_and_inside_the_whole(ready):
    res = C.analyse(C.fault_table(ready, "rules", 1.0), 1.0)
    assert 0 < res["strong"]["n"] <= res["overall"]["n"] and res["strong"]["recall"] is not None


def test_run_writes_json_and_markdown(ready):
    from qc import paths
    out = C.run_ceiling(ready, ["rules"], 1.0)
    d = paths.out_dir(ready.cfg) / str(ready.cfg.name) / "ceiling"
    assert (d / "ceiling_rules.json").is_file() and "Ceiling check: rules" in (d / "ceiling.md").read_text(encoding="utf-8")
    assert out["rules"]["component"] == "rules"
