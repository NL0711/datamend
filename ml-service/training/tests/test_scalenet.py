import logging

import numpy as np
import pytest
import torch

from training.elevation import load_elevation
from training.multiscale import ScaleNet, causal_mean
from training.presets import make_config
from training.sampler import Batch, NullStationProvider, WindowSampler, YearCube
from training.stations import Station, StationCalibrator, fit_affine, idw_weights, load_stations
from training.trainer import LocalTrainer, featurize
from training.transform import RainfallTransform
from training import artifact
from training.calibration import Calibration


def _cube(seed=0, t=80, nan_cells=False):
    rng = np.random.default_rng(seed)
    cube = rng.gamma(0.3, 8.0, size=(t, 8, 9)).astype("float32")
    cube[rng.random(cube.shape) < 0.5] = 0.0
    cube[:, :2] = np.nan
    if nan_cells:
        cube[5:70, 4, 4] = np.nan          # a long data gap inside an otherwise valid land cell
    return cube


def _sampler(cube, **kw):
    mask = ~np.isnan(cube).all(0)
    return WindowSampler([YearCube.build(cube)], mask, window=40, seed=0, patch_size=3, **kw)


# ---------------------------------------------------------------- causality ----------------------------
def test_causal_mean_never_sees_future_days():
    x = torch.rand(3, 30)
    valid = torch.ones(3, 30, dtype=torch.bool)
    base, _ = causal_mean(x, valid, 5)
    t = 17
    x2 = x.clone()
    x2[:, t + 1:] = 1e6                      # change only days after t
    changed, _ = causal_mean(x2, valid, 5)
    assert torch.equal(base[:, : t + 1], changed[:, : t + 1])   # aggregates at or before t are untouched
    assert not torch.equal(base[:, t + 1:], changed[:, t + 1:])
    # and changing a day inside the trailing window of position t does change it
    x3 = x.clone()
    x3[:, t - 2] += 10
    assert not torch.equal(base[:, t], causal_mean(x3, valid, 5)[0][:, t])


def test_causal_mean_ignores_invalid_days_and_reports_fraction():
    x = torch.tensor([[1.0, 100.0, 3.0, 5.0]])
    valid = torch.tensor([[True, False, True, True]])
    mean, frac = causal_mean(x, valid, 3)
    assert mean[0, 2].item() == pytest.approx(2.0)          # (1 + 3) / 2, the invalid 100 is ignored
    assert frac[0, 2].item() == pytest.approx(2 / 3)
    assert mean[0, 0].item() == pytest.approx(1.0) and frac[0, 0].item() == pytest.approx(1 / 3)


def test_sampler_windows_stay_inside_one_year():
    s = _sampler(_cube(t=80))
    b = s.batch(64)
    assert b.doy.min() >= 0 and b.doy.max() < 80
    assert (np.diff(b.doy, axis=1) == 1).all()


# ---------------------------------------------------------------- patch / NaN masks ---------------------
def test_patch_excludes_centre_cell_and_marks_out_of_bounds():
    cube = _cube()
    s = _sampler(cube)
    b = s.batch(32, inject_rate=1.0)
    assert b.patch.shape == (32, 8, 40) and b.patch_valid.shape == (32, 8, 40)
    for k in range(5):                                       # no patch channel equals the clean centre series
        r, c = b.cell[k]
        centre = b.clean_mm[k]
        if centre.any():
            assert not any(np.allclose(b.patch[k, p], centre) for p in range(8))
    assert b.patch_valid.mean() < 1.0                        # edge cells have out-of-grid neighbours


def test_nan_gap_shapes_valid_mask_and_finite_forward():
    s = _sampler(_cube(nan_cells=True))
    b = s.batch(600, inject_rate=0.5)
    assert b.valid.shape == b.labels.shape == (600, 40)
    assert (~b.valid).any()                                  # the gap shows up in the mask
    assert not (b.labels & ~b.valid).any()                   # never a label on a missing day
    assert np.isfinite(b.x_mm).all() and np.isfinite(b.patch).all()
    t = LocalTrainer(RainfallTransform(3.0), make_config("smoke", arch="scalenet", scales=[1, 5], patch=3, attn_layers=1, heads=4))
    out = t._forward(t.model, t._x(b))
    assert out["pi_logit"].shape == (600, 40) and out["scale_attn"].shape == (600, 40, 2)
    assert all(torch.isfinite(v).all() for v in out.values())
    streams = t.score(b)
    assert all(v.shape == (600, 40) and np.isfinite(v).all() for v in streams.values())
    assert (streams["nll"][~b.valid] == 0).all()             # missing days score as normal, not as NaN


def test_loss_ignores_invalid_days():
    s = _sampler(_cube(nan_cells=True))
    b = s.batch(600, inject_rate=0.5)
    assert (~b.valid).any()
    t = LocalTrainer(RainfallTransform(3.0), make_config("smoke", arch="scalenet", scales=[1, 5], patch=3, dropout=0.0))
    t.model.eval()
    with torch.no_grad():
        base = t._loss(b, t.model).item()
        b2 = Batch(**{**b.__dict__})
        b2.clean_mm = np.where(b.valid, b.clean_mm, 123.0)   # garbage under the mask must not matter
        assert t._loss(b2, t.model).item() == pytest.approx(base, rel=1e-5)


# ---------------------------------------------------------------- forward / train / reload --------------
@pytest.mark.parametrize("kw", [
    dict(scales=[1, 5, 30]),
    dict(scales=[1], single_scale=True),
    dict(scales=[1, 7], patch=0),
    dict(scales=[1, 5], patch=5, attn_layers=1, heads=4, use_elevation=True),
])
def test_scalenet_forward_two_steps_and_checkpoint_reload(tmp_path, kw):
    cube = _cube()
    elev = (np.random.default_rng(1).random((8, 9)).astype("float32")) if kw.get("use_elevation") else None
    mask = ~np.isnan(cube).all(0)
    cfg = make_config("smoke", arch="scalenet", **{"patch": 3, **kw})
    s = WindowSampler([YearCube.build(cube)], mask, window=cfg.window, seed=0, patch_size=cfg.patch,
                      elevation=elev)
    t = LocalTrainer(RainfallTransform(3.0), cfg)
    hist = t.fit(s, 2)["train_loss"]                          # steps_per_epoch=4 -> 8 optimizer steps
    assert len(hist) == 2 and np.isfinite(hist).all()
    b = s.batch(16, 0.5)
    cal = Calibration.fit(t, s, n=64)
    artifact.save(artifact.Artifact(t, cal, {"m": 1}), tmp_path / "a")
    t2 = artifact.load(tmp_path / "a").trainer
    for k, v in t.score(b).items():
        np.testing.assert_allclose(v, t2.score(b)[k], atol=1e-5)
    assert t2.config.scales == t.config.scales and t2.config.single_scale == cfg.single_scale


def test_scale_ablation_masks_scales_and_attention_sums_to_one():
    s = _sampler(_cube())
    cfg = make_config("smoke", arch="scalenet", scales=[1, 5, 30], patch=3, dropout=0.0)
    t = LocalTrainer(RainfallTransform(3.0), cfg)
    b = s.batch(32, 0.3)
    att = t.scale_attention(b)
    assert att.shape == (32, 40, 3) and np.allclose(att.sum(-1), 1, atol=1e-5)
    full = t.score(b)["nll"]
    dropped = t.score(b, drop_scales=[2])["nll"]
    assert not np.allclose(full, dropped)
    model = t.inference_model
    assert model.disabled_scales == ()                       # ablation state is restored
    with pytest.raises(ValueError):
        ScaleNet(scales=(5, 30))                            # first scale must be the daily branch


def test_single_scale_flag_means_one_branch():
    t = LocalTrainer(RainfallTransform(3.0), make_config("smoke", arch="scalenet", scales=[1, 5, 30], single_scale=True))
    assert t.model.scales == (1,) and len(t.model.branches) == 1


def test_featurize_scalenet_tuple_shapes():
    s = _sampler(_cube())
    b = s.batch(8, 0.5)
    arrs = featurize(b, RainfallTransform(3.0), "scalenet")
    assert [a.shape for a in arrs] == [(8, 40), (8, 40), (8, 40), (8, 2, 40), (8, 8, 40), (8, 8, 40), (8, 40, 4), (8, 2), (8, 40), (8,)]


# ---------------------------------------------------------------- optional inputs: stubs & warnings ----
def test_missing_elevation_and_stations_warn_instead_of_failing(caplog):
    with caplog.at_level(logging.WARNING):
        assert load_elevation(None, (8, 9)) is None
        assert load_elevation("does_not_exist.npy", (8, 9)) is None
        assert load_stations(None) == []
        NullStationProvider._warned = False
        mm, ok = NullStationProvider().get(np.zeros(3, int), np.zeros(3, int), None, None, 5)
    assert not ok.any() and mm.shape == (3, 5)
    text = caplog.text
    assert "elevation" in text and "station" in text


def test_elevation_loads_and_normalizes(tmp_path):
    e = np.arange(72, dtype="float32").reshape(8, 9) * 10
    np.save(tmp_path / "e.npy", e)
    out = load_elevation(str(tmp_path / "e.npy"), (8, 9))
    assert out.min() == 0 and out.max() == 1
    assert load_elevation(str(tmp_path / "e.npy"), (4, 4)) is None   # shape mismatch -> unavailable


def test_station_affine_and_idw_blending_toy():
    g = np.arange(30, dtype=float)
    assert fit_affine(g, 2 * g + 1) == pytest.approx((2.0, 1.0))
    assert fit_affine(np.ones(30), g) == (1.0, 0.0)          # no grid variance -> identity
    w = idw_weights(np.array([1.0, 2.0]), power=2)
    assert w == pytest.approx([0.8, 0.2])
    near = Station("a", 19.0, 72.8, 2 * g, g)
    far = Station("b", 28.0, 77.0, 0.5 * g, g)
    cal = StationCalibrator([near, far], k=2)
    at_near = cal.calibrate(g, 19.0, 72.8)
    assert np.allclose(at_near, 2 * g, rtol=0.05, atol=0.5)  # the co-located station dominates
    assert (cal.calibrate(g, 19.0, 72.8) >= 0).all()
