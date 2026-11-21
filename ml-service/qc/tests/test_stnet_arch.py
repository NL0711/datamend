"""qc.stnet_arch and qc.stnet_test: the selection rule, the regional calibration, the regional budget check, and the whole flow on the generated world."""
import numpy as np
import pytest

from qc import stnet as S
from qc import stnet_arch as A
from qc.baselines import run_untrained
from qc.benchmark import build_benchmark
from qc.calibration import check_budget_regional
from qc.config import load_config
from qc.evaluate import score_store
from qc.fusion_eval import budgets_path
from qc.prepare import load_prepared
from qc.runs import write_json
from qc.testscore import lock_path as daily_lock
from qc.tests.test_gate4 import TINY


# ---------------------------------------------------------------------------------------------- the rule (pure)

def _rows(**over):
    base = {"ref": {"recall": 0.47, "false_per_1000": 1.17, "protected_flagged": 0.041, "event_recall": 0.5, "pr_auc": 0.5},
            "plain": {"recall": 0.64, "false_per_1000": 0.64, "protected_flagged": 0.02, "event_recall": 0.6, "pr_auc": 0.7,
                      "candidate": True, "variant": "boosted", "calibrated": False},
            "cal": {"recall": 0.62, "false_per_1000": 0.9, "protected_flagged": 0.02, "event_recall": 0.6, "pr_auc": 0.7,
                    "candidate": True, "variant": "boosted", "calibrated": True}}
    for k, v in over.items():
        base[k] = {**base[k], **v}
    return base


def test_the_plain_candidate_wins_when_everything_passes():
    d = A.choose(_rows(), {"plain": 1.2, "cal": 1.0}, "ref")
    assert d["chosen"]["architecture"] == "stnet" and d["chosen"]["component"] == "plain" and not d["chosen"]["calibrated"]
    assert d["qualifying"] == ["plain", "cal"]


def test_a_client_over_the_guard_sends_the_choice_to_the_calibrated_candidate():
    d = A.choose(_rows(), {"plain": 4.8, "cal": 1.4}, "ref")                       # client 3 at 4.8 against a budget of 1.0
    assert d["checks"]["plain"]["every_client_guard"] is False
    assert d["chosen"]["component"] == "cal" and d["chosen"]["calibrated"]


def test_each_failed_check_keeps_the_old_pipeline_and_names_the_reason():
    for over, guards, key in (
        ({"plain": {"recall": 0.48}, "cal": {"recall": 0.48}}, {"plain": 1.0, "cal": 1.0}, "recall_gain"),
        ({"plain": {"false_per_1000": 1.4}, "cal": {"false_per_1000": 1.4}}, {"plain": 1.0, "cal": 1.0}, "false_within_budget"),
        ({"plain": {"protected_flagged": 0.06}, "cal": {"protected_flagged": 0.06}}, {"plain": 1.0, "cal": 1.0}, "protected_not_higher"),
        ({}, {"plain": None, "cal": 5.0}, "every_client_guard"),
    ):
        d = A.choose(_rows(**over), guards, "ref")
        assert d["chosen"] == {"architecture": "daily_only", "component": "ref"}
        assert d["checks"]["plain"][key] is False, key


# ---------------------------------------------------------------------------------------------- regional calibration (pure)

def test_calibration_gives_every_client_the_same_exceedance_rate_whatever_its_scale():
    rng = np.random.default_rng(0)
    client = np.repeat([1, 2], 50)
    s_clean = np.concatenate([rng.gamma(2.0, 1.0, (400, 50)), rng.gamma(2.0, 4.0, (400, 50))], axis=1)       # client 2 scores run 4 times higher
    tables = {c: np.sort(s_clean[:, client == c].ravel()).astype(np.float32) for c in (1, 2)}
    s_new = np.concatenate([rng.gamma(2.0, 1.0, (400, 50)), rng.gamma(2.0, 4.0, (400, 50))], axis=1)
    thr = float(np.quantile(s_clean[:, client == 1], 0.99))
    raw_rate = [float((s_new[:, client == c] > thr).mean()) for c in (1, 2)]
    cal = A.calibrate_scores(s_new, client, tables)
    lvl = -np.log10(0.01)                                                           # the 99th percentile of each client's own clean scores
    cal_rate = [float((cal[:, client == c] > lvl).mean()) for c in (1, 2)]
    assert raw_rate[1] > 5 * raw_rate[0]                                            # one global threshold flags the high-scoring client far more
    assert abs(cal_rate[0] - 0.01) < 0.004 and abs(cal_rate[1] - 0.01) < 0.004
    s_nan = s_new.copy()
    s_nan[0, 0] = np.nan
    assert np.isnan(A.calibrate_scores(s_nan, client, tables)[0, 0])
    order = np.argsort(s_new[:, 0])
    assert (np.diff(A.calibrate_scores(s_new, client, tables)[order, 0]) >= 0).all()    # monotone within a client


# ---------------------------------------------------------------------------------------------- the generated world

@pytest.fixture(scope="module")
def pa(world, prepared):
    cfg = load_config(world / "test.yaml", TINY + ["name=sta", "benchmark.name=stabench"])
    p = load_prepared(cfg)
    build_benchmark(p, splits=("val", "test", "stress"), overwrite=True)
    run_untrained(p, ("val", "test", "stress"))
    return p


def test_regional_check_gives_every_client_including_held_out_its_own_threshold(pa):
    rows = check_budget_regional(pa, "rules", 5.0, n_boot=20)
    clients = sorted({r["client"] for r in rows})
    assert {r["rule"] for r in rows} == {"regional"} and set(clients) >= {int(c) for c in pa.split.heldout}
    for r in rows:
        assert r["false_per_1000"] is not None and r["false_per_1000"] < 5.0 * 3          # near the budget, not wildly above it


@pytest.fixture(scope="module")
def trained(pa):
    cfg = S.STConfig(width=8, c_feat=8, long_hidden=8, epochs=1, steps=2, batch=2, window=8, burn=2, crop=24, long_epochs=1, long_steps=2,
                     long_cells=64, prefix="sta", probe=False)
    S.run_stnet(pa, 0, cfg, ("val",), max_years=2)
    return cfg


def test_frozen_fusion_candidates_and_the_choice_are_written_once(pa, trained):
    info = A.prepare_validation(pa, 0, "sta")
    assert info["names"] == ["rules", "sta_fault_s0"]
    store = score_store(pa)
    y = pa.split.years["val"][0]
    for v in A.VARIANTS:
        for cal in (False, True):
            a = store.load(A.fused(v, 0, cal), "val", y)
            assert a.shape[1] == pa.grid.n_land and np.isfinite(a).any()
    before = (A.models_dir(pa) / "logistic_s0.json").read_bytes()
    A.prepare_validation(pa, 0, "sta")                                              # idempotent: the frozen fit is not refitted
    assert (A.models_dir(pa) / "logistic_s0.json").read_bytes() == before
    doc = A.decide(pa, 0, "sta", 5.0, 0.0, 100.0, baselines=("rules",), n_boot=20)
    assert doc["chosen"]["architecture"] in ("stnet", "daily_only") and set(doc["rows"]) >= {"rules", A.fused("boosted", 0)}
    assert "SYNTHETIC" in doc["label"] and A.format_choice(doc)
    with pytest.raises(RuntimeError, match="already exists"):
        A.decide(pa, 0, "sta", 5.0, 0.0, 100.0, baselines=("rules",), n_boot=20)


def test_curves_are_written_for_the_budgets_and_the_names_skip_file_references(pa, trained):
    import json
    from qc import stnet_test as T
    A.prepare_validation(pa, 0, "sta")
    doc = json.loads(A.curves_path(pa, 0).read_text(encoding="utf-8"))
    assert set(doc["scores"]) == {A.fused(v, 0, c) for v in A.VARIANTS for c in (False, True)} and doc["budgets"]
    choice = {"chosen": {"component": "cand"}, "rows": {"cand": {"candidate": True}, "committed:x.json:boosted": {"from_file": True, "recall": 0.4},
                                                          "fusion_logistic_s0": {"recall": 0.4}, "fusion_boosted_s0": {"recall": 0.3}}}
    names = T.names_to_score(choice, lambda n: n == "fusion_logistic_s0")
    assert "old daily: fusion_logistic_s0" in names and "old daily: fusion_boosted_s0" not in names     # no test scores: not scored
    assert not any("committed" in v for v in names.values()) and names["chosen STNet candidate"] == "cand"


def test_the_rule_runs_from_a_committed_reference_without_the_old_components(pa, trained, tmp_path):
    import json
    from qc.benchmark import check_benchmark
    A.prepare_validation(pa, 0, "sta")
    row = lambda v, rec, fa, prot: {"components": "rules+slow+spatial+temporal", "variant": v, "recall": rec, "event_recall": 0.5,
                                     "false_per_1000": fa, "protected_flagged": prot, "pr_auc": 0.4}
    ref = tmp_path / "ablation_s0.json"
    ref.write_text(json.dumps({"budget": 5.0, "seed": 0, "rows": [row("logistic", 0.40, 1.0, 0.10), row("boosted", 0.47, 1.2, 0.04),
                                                                  {**row("logistic", 0.43, 1.1, 0.14), "components": "rules"}]}), encoding="utf-8")
    bh = check_benchmark(pa)["hash"]
    A.choice_path(pa).unlink(missing_ok=True)
    with pytest.raises(RuntimeError, match="not comparable"):
        A.decide(pa, 0, "sta", 5.0, 0.0, 100.0, reference_file=ref, reference_benchmark_hash="deadbeef", n_boot=20)
    with pytest.raises(ValueError, match="budget"):
        A.decide(pa, 0, "sta", 1.0, 0.0, 100.0, reference_file=ref, reference_benchmark_hash=bh, n_boot=20)
    assert not A.choice_path(pa).exists()                                                           # a refused choice writes nothing
    doc = A.decide(pa, 0, "sta", 5.0, 0.0, 100.0, reference_file=ref, reference_benchmark_hash=bh, n_boot=20)
    assert doc["reference"] == "committed:ablation_s0.json:boosted"                                  # the better of the two four-component rows
    assert doc["reference_source"]["kind"] == "committed file" and doc["reference_source"]["benchmark_hash"] == bh
    refs = {n: r for n, r in doc["rows"].items() if "candidate" not in r}
    assert set(refs) == {"committed:ablation_s0.json:logistic", "committed:ablation_s0.json:boosted"} and all(r["from_file"] for r in refs.values())
    A.choice_path(pa).unlink()


def _force_choice(p, calibrated=False):
    write_json(A.choice_path(p), {
        "chosen": {"architecture": "stnet", "component": A.fused("boosted", 0, calibrated), "variant": "boosted", "calibrated": calibrated},
        "prefix": "sta", "seed": 0, "reference": "rules", "commit": "test", "rule": {}, "reason": "forced for the test",
        "rows": {"rules": {}, A.fused("boosted", 0, calibrated): {"candidate": True}}})


def test_the_test_pass_refuses_until_its_preconditions_hold_then_runs_once(pa, trained):
    from qc import stnet_test as T
    A.prepare_validation(pa, 0, "sta")
    A.choice_path(pa).unlink(missing_ok=True)
    write_json(daily_lock(pa), {"status": "started", "started": "x"})
    with pytest.raises(RuntimeError, match="unfinished daily test pass"):                     # an unfinished daily pass stops this one
        T.run_stnet_test(pa)
    daily_lock(pa).unlink()                                                                     # no daily pass at all is fine: old components not needed
    with pytest.raises(RuntimeError, match="choice has not been made"):
        T.run_stnet_test(pa)
    write_json(A.choice_path(pa), {"chosen": {"architecture": "daily_only", "component": "rules"}, "reason": "kept", "rows": {}})
    with pytest.raises(RuntimeError, match="old daily pipeline"):
        T.run_stnet_test(pa)
    _force_choice(pa, calibrated=True)
    with pytest.raises(Exception, match="budgets"):
        T.run_stnet_test(pa)
    write_json(budgets_path(pa), {"final_per_1000": 5.0, "review_per_1000": 10.0, "chosen": "t", "commit": "t"})
    before = (A.models_dir(pa) / "logistic_s0.json").read_bytes()
    report = T.run_stnet_test(pa)
    assert report["components"]["chosen STNet candidate"] == A.fused("boosted", 0, True) and "untrained: rules" in report["components"]
    out = T.report_dir(pa)
    assert (out / "stnet_test_report.md").is_file() and (out / "stnet_test_report.json").is_file()
    rows = [r for r in report["rows"] if r["split"] == "test" and r["group"] == "seen" and r["budget_per_1000"] == 5.0]
    assert {r["architecture"] for r in rows} >= {"chosen STNet candidate", "untrained: rules"}
    assert (A.models_dir(pa) / "logistic_s0.json").read_bytes() == before                  # nothing was refitted on a test year
    with pytest.raises(RuntimeError, match="single use"):
        T.run_stnet_test(pa)
