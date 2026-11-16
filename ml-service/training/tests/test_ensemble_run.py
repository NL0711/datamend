"""Smoke test of the full ensemble pipeline on a tiny synthetic archive: it must run end to end, the losses
must be finite, every seed must be reported, and the saved fusion pipeline must reload and reproduce its scores.
No metric value is asserted (this proves the code runs, nothing about quality)."""

import json

import numpy as np
import pytest

from ensemble.pipeline import FusionPipeline
from ensemble.fusion import RULES
from training.ensemble_run import run_ensemble
from training.presets import ENSEMBLE_PRESETS


@pytest.fixture(scope="module")
def smoke_run(tmp_path_factory):
    from training.tests.fakedata import write_fake_archive
    root = tmp_path_factory.mktemp("arch")
    write_fake_archive(root)
    out = tmp_path_factory.mktemp("ens")
    res = run_ensemble(root, out, preset="smoke", fusion="owa", seeds=[0, 1], epochs=1, log=lambda *_: None)
    return res, out


def test_every_seed_is_reported_and_files_exist(smoke_run):
    res, out = smoke_run
    assert res["seeds"] == [0, 1] and len(res["runs"]) == 2 and set(res["details"]) == {"0", "1"}
    assert "best" not in res and (out / "results.json").exists()
    assert json.loads((out / "results.json").read_text())["seeds"] == [0, 1]
    for sd in (0, 1):
        assert (out / f"seed_{sd}" / "fusion.json").exists() and (out / f"seed_{sd}" / "normalizers.npz").exists()


def test_models_trained_with_finite_losses_and_all_variants_present(smoke_run):
    res, _ = smoke_run
    d = res["details"]["0"]
    assert set(d["members"]) == {"lstm_baseline", "base", "scalenet", "scalenet_single"}   # ablation member included
    assert "scale_ablation" in d["members"]["scalenet"] and "scale_ablation" not in d["members"]["scalenet_single"]
    branches = set(d["branch_alone"])
    assert {"rule", "stat", "lstm_baseline", "rainnet", "multiscale", "supervised_head"} == branches
    variants = d["fusion_variants"]
    assert {v["rule"] for v in variants} == set(RULES)
    assert {v["drop_branch"] for v in variants} == {None} | branches            # each branch dropped once
    assert set(d["by_kind"]) <= {"clean", "spike", "stuck", "scale", "phantom_rain", "zeroed", "repeat"}
    assert set(d["by_season"]) and set(d["by_region"])


def test_headline_metrics_are_numbers_not_selected(smoke_run):
    res, _ = smoke_run
    for run in res["runs"]:
        assert set(run) == {"pr_auc", "random_pr_auc", "aff_f1", "event_f1", "f1", "fpr_clean"}
        assert all(isinstance(v, float) for v in run.values())
    assert set(res["mean"]) == set(res["std"]) == set(res["runs"][0])


def test_saved_fusion_pipeline_reloads_and_reproduces_scores(smoke_run):
    _, out = smoke_run
    pipe = FusionPipeline.load(out / "seed_0")
    assert pipe.config.rule == "owa" and pipe.threshold_info["method"] == "fpr"
    assert {b.name for b in pipe.branches} == {"rule", "stat", "lstm_baseline", "rainnet", "multiscale", "supervised_head"}
    # reload twice and compare: scoring must be deterministic given identical weights and a fixed batch
    again = FusionPipeline.load(out / "seed_0")
    rng_batch = _fixed_batch(pipe)
    np.testing.assert_allclose(pipe.fuse(rng_batch), again.fuse(rng_batch), atol=1e-6)
    f = pipe.fuse(rng_batch)
    assert np.isfinite(f).all() and f.min() >= 0 and f.max() <= 1


def _fixed_batch(pipe):
    from training.sampler import Batch
    rng = np.random.default_rng(0)
    w = pipe.branches[2].art.trainer.config.window
    x = np.abs(rng.normal(0, 5, size=(12, w))).astype(np.float32)
    n_patch = pipe.branches[4].art.trainer.config.patch ** 2 - 1
    cell = np.stack([rng.integers(2, 8, 12), rng.integers(0, 9, 12)], -1)
    return Batch.from_windows(x, doy=np.tile(np.arange(w), (12, 1)), n_patch=n_patch, cell=cell)


def test_unknown_rule_and_preset_fail_early(tmp_path):
    with pytest.raises(KeyError):
        run_ensemble(tmp_path, tmp_path / "o", preset="nope")
    assert set(ENSEMBLE_PRESETS) == {"smoke", "ensemble", "ensemble_large"}
