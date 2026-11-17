import json

import numpy as np
import pytest
import torch

from detectors.rainfall_ae import RainfallAEDetector
from training.climatology import ClimatologyAccumulator
from training.data import RainfallArchive
from training.experiments import sweep
from training.injection import KINDS, inject
from training.losses import zig_nll
from training.partition import partition_cells
from training.pipeline import prepare, run, train_prepared
from training.presets import make_config
from training.sampler import Batch, WindowSampler, YearCube
from training.splits import split_years
from training.trainer import LocalTrainer, featurize
from training.transform import RainfallTransform

def test_archive_reports_gap_and_masks_land(archive_dir):
    a = RainfallArchive(archive_dir)
    assert a.missing_years == [2002]
    assert a.land_mask.sum() == 6 * 9
    assert a.load(2000).shape == (60, 8, 9)
    with pytest.raises(KeyError):
        a.load(2002)


def test_split_is_chronological_and_skips_gaps():
    s = split_years([1990, 1991, 1993, 1994, 1995, 1996, 1997, 1998, 1999, 2000], 2, 3)
    assert s.train == [1990, 1991, 1993, 1994, 1995]
    assert s.val == [1996, 1997] and s.test == [1998, 1999, 2000]
    assert max(s.train) < min(s.val) < min(s.test)


def test_transform_roundtrip_and_clips_negative():
    x = np.array([0, 0.5, 10, 200], dtype=np.float32)
    t = RainfallTransform.fit(x)
    np.testing.assert_allclose(t.inverse(t.forward(x)), x, rtol=1e-4, atol=1e-5)
    assert t.forward(np.array([-5.0]))[0] == 0


def test_injection_labels_only_changed_points_for_every_kind():
    rng = np.random.default_rng(1)
    clean = np.abs(rng.normal(0, 5, size=(2000, 30))).astype(np.float32)
    clean[rng.random(clean.shape) < 0.6] = 0
    out, labels, kind = inject(clean, rng, rate=1.0)
    assert set(kind[kind >= 0]) == set(range(len(KINDS)))  # every kind actually fires
    assert (np.abs(out - clean)[labels] > 1e-3).all()
    np.testing.assert_array_equal(out[~labels], clean[~labels])


def test_injection_respects_kind_subset():
    rng = np.random.default_rng(2)
    clean = np.abs(rng.normal(0, 5, size=(300, 30))).astype(np.float32)
    _, _, kind = inject(clean, rng, rate=1.0, kinds=("spike", "stuck"))
    assert set(kind[kind >= 0]) <= {KINDS.index("spike"), KINDS.index("stuck")}


def test_partitions_cover_land_cells_disjointly():
    mask = np.zeros((20, 30), bool)
    mask[3:18, 4:28] = True
    for scheme in ("lat_bands", "tiles"):
        parts = partition_cells(mask, scheme, 3)
        allc = np.concatenate(parts)
        assert len(allc) == mask.sum() == len(set(allc.tolist()))


def test_climatology_shape_and_land_mask():
    acc = ClimatologyAccumulator((4, 5))
    cube = np.random.default_rng(0).random((365, 4, 5)).astype("float32")
    cube[:, 0, :] = np.nan
    acc.add(cube)
    clim = acc.result()
    assert clim.shape == (366, 4, 5)
    assert np.isnan(clim[:, 0]).all() and np.isfinite(clim[:, 1:]).all()


def test_sampler_batch_shapes_and_context():
    rng = np.random.default_rng(0)
    cube = rng.gamma(0.3, 8, size=(60, 8, 9)).astype("float32")
    cube[:, :2] = np.nan
    mask = ~np.isnan(cube).all(0)
    s = WindowSampler([YearCube.build(cube)], mask, window=20, seed=0, clim=np.zeros((366, 8, 9), "float32"))
    b = s.batch(32, inject_rate=1.0)
    assert b.x_mm.shape == (32, 20, 2) and b.aux_mm.shape == (32, 20, 2) and b.static.shape == (32, 20, 4)
    assert featurize(b, RainfallTransform(3.0), "rainnet")[0].shape == (32, 20, 8)
    assert featurize(b, RainfallTransform(3.0), "lstm_ae")[0].shape == (32, 20, 2)
    tgt, src, meta, mask = featurize(b, RainfallTransform(3.0), "msnet")
    assert tgt.shape == (32, 20, 6) and src.shape == (32, 1, 20) and meta.shape == (32, 1, 3) and mask.dtype == bool
    assert np.isfinite(b.x_mm).all() and np.isfinite(b.aux_mm).all()


def test_zig_nll_prefers_correct_distribution():
    x = torch.tensor([0.0, 0.0, 20.0, 20.0])
    good = {"pi_logit": torch.tensor([4.0, 4.0, -4.0, -4.0]),
            "log_alpha": torch.zeros(4), "log_beta": torch.full((4,), -3.0)}
    bad = {"pi_logit": torch.tensor([-4.0, -4.0, 4.0, 4.0]),
           "log_alpha": torch.zeros(4), "log_beta": torch.full((4,), -3.0)}
    assert zig_nll(x, good).mean() < zig_nll(x, bad).mean()


def test_weights_roundtrip():
    a = LocalTrainer(RainfallTransform(3.0), make_config("smoke"))
    b = LocalTrainer(RainfallTransform(3.0), make_config("smoke", seed=7))
    b.set_weights(a.get_weights())
    x = np.random.default_rng(0).random((4, 20)).astype("float32") * 20
    ba = Batch.from_windows(x)
    for k, v in a.score(ba).items():
        np.testing.assert_allclose(v, b.score(ba)[k], atol=1e-5)


@pytest.mark.parametrize("preset,over", [
    ("smoke", {}),
    ("smoke", {"attn_layers": 1, "layers": 2, "amp": True}),   # amp silently off on CPU
    ("lstm_baseline", {"steps_per_epoch": 10, "batch_size": 32, "window": 20, "hidden": 16}),
    ("lstm_baseline", {"steps_per_epoch": 10, "batch_size": 32, "window": 20, "hidden": 16, "loss": "tweedie"}),
])
def test_pipeline_trains_saves_and_detector_loads(archive_dir, tmp_path, preset, over):
    cfg = make_config(preset, **over)
    out = tmp_path / "art"
    res = run(archive_dir, out, cfg, epochs=2, val_years=2, test_years=2, log=lambda *_: None)
    assert 0.0 <= res["test"]["primary"]["roc_auc"] <= 1.0
    assert "baseline" in res["test"]["scores"] and "fused" in res["test"]["scores"]
    det = RainfallAEDetector(str(out))
    series = np.zeros(70, dtype=np.float32)
    series[33] = 300.0
    res = det.detect_detailed(series, {"clim": np.zeros(70), "nbr_mean": np.zeros(70), "nbr_max": np.zeros(70)})
    assert res["scores"].shape == (70,) and np.isfinite(res["scores"]).all()
    assert res["flags"].dtype == bool
    assert det.detect_detailed(np.zeros(5))["scores"].shape == (5,)  # shorter than one window
    api = det.detect(np.stack([series, series], axis=1))             # API contract: (T, C) -> (T,) in [0, 1]
    assert api.shape == (70,) and ((api >= 0) & (api <= 1)).all()


def test_holdout_kinds_marks_unseen(archive_dir):
    cfg = make_config("smoke", train_kinds=[k for k in KINDS if k not in ("zeroed", "repeat")])
    prep = prepare(archive_dir, 2, 2, log=lambda *_: None)
    res = train_prepared(prep, cfg, 1, eval_windows=1500, log=lambda *_: None)
    pk = res["test"]["per_kind_roc_auc"]
    assert pk and all(v["seen"] == (k not in ("zeroed", "repeat")) for k, v in pk.items())


def test_sweep_picks_best_by_validation(archive_dir, tmp_path):
    rows = sweep(archive_dir, tmp_path / "sw", {"hidden": [8, 16], "lr": [1e-3]}, base="smoke",
                 epochs=1, log=lambda *_: None)
    assert len(rows) == 2
    best = json.loads((tmp_path / "sw" / "best.json").read_text())
    assert best["val_pr_auc"] == max(r["val_pr_auc"] for r in rows)
    assert (tmp_path / "sw" / "trial_000" / "model.pt").exists()
