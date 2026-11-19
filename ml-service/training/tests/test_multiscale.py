import numpy as np
import pytest
import torch

from detectors.ensemble import EnsembleDetector
from detectors.rainfall_ae import RainfallAEDetector
from detectors.scoring import api_score
from training.model import MSRainNet
from training.pipeline import run
from training.presets import make_config
from training.sampler import Batch, WindowSampler, YearCube
from training.sources import KM_PER_CELL, coarse_cube, meta_array, proxy_specs
from training.trainer import LocalTrainer
from training.transform import RainfallTransform

MS = dict(arch="msnet", coarse_blocks=[2], source_dropout=0.3, attn_layers=1, heads=4)


def test_coarse_cube_is_block_mean_and_ignores_nan():
    cube = np.arange(2 * 4 * 6, dtype="float32").reshape(2, 4, 6)
    cube[:, 0, 0] = np.nan
    c = coarse_cube(cube, 2)
    assert c.shape == cube.shape
    np.testing.assert_allclose(c[0, 0:2, 0:2], np.nanmean(cube[0, 0:2, 0:2]))  # NaN excluded
    assert (c[:, 2:4, 4:6] == c[:, 2:4, 4:6][:, :1, :1]).all()                  # constant within a block


def test_proxy_specs_and_meta():
    specs = proxy_specs([4, 8])
    assert [s.name for s in specs] == ["nbr8", "coarse4", "coarse8"]
    assert specs[2].resolution_km == pytest.approx(KM_PER_CELL * 8)
    m = meta_array(specs, {"coarse4": 50.0})
    assert m.shape == (3, 3) and m[1, 1] == pytest.approx(0.5) and (m[:, 2] == 1).all()


def test_sampler_sources_dropout_and_ablation_helper():
    rng = np.random.default_rng(0)
    cube = rng.gamma(0.3, 8, size=(60, 8, 9)).astype("float32")
    cube[:, :2] = np.nan
    s = WindowSampler([YearCube.build(cube, [2])], ~np.isnan(cube).all(0), window=20, seed=0)
    assert [sp.name for sp in s.specs] == ["nbr8", "coarse2"]
    b = s.batch(400, source_dropout=0.5)
    assert b.src_mm.shape == (400, 2, 20) and b.src_mask.shape == (400, 2)
    assert 0.3 < b.src_mask.mean() < 0.7
    assert (b.src_mm[~b.src_mask] == 0).all()
    none = s.batch(50).with_sources([False, False])
    assert not none.src_mask.any() and (none.src_mm == 0).all()


def test_msnet_handles_missing_sources_and_reports_attention():
    m = MSRainNet(6, 16, 1, 1, 4, 0.0, n_sources=3).eval()
    tgt, src, meta = torch.rand(5, 12, 6), torch.rand(5, 3, 12), torch.rand(5, 3, 3)
    for mask in (torch.ones(5, 3, dtype=torch.bool), torch.zeros(5, 3, dtype=torch.bool),
                 torch.tensor([[True, False, True]] * 5)):
        out = m(tgt, src, meta, mask)
        assert all(torch.isfinite(v).all() for v in out.values())
        a = out["src_attn"]
        assert a.shape == (5, 12, 4) and torch.allclose(a.sum(-1), torch.ones(5, 12), atol=1e-5)
        assert (a[:, :, 1:][~mask.unsqueeze(1).expand(5, 12, 3)] < 1e-6).all()  # masked sources get no attention


def test_msnet_pipeline_ablation_detector_and_ensemble(archive_dir, tmp_path):
    cfg = make_config("smoke", **MS)
    out = tmp_path / "ms"
    res = run(archive_dir, out, cfg, epochs=2, val_years=2, test_years=2, log=lambda *_: None)
    abl = res["test"]["source_ablation"]
    assert set(abl) == {"all", "none", "drop:nbr8", "drop:coarse2"}
    det = RainfallAEDetector(str(out))
    assert [s.name for s in det.specs] == ["nbr8", "coarse2"]
    series = np.zeros(70, dtype=np.float32)
    series[33] = 300.0
    full = det.detect_detailed(series, {"nbr_mean": np.zeros(70), "sources": {"coarse2": np.zeros(70)}})
    bare = det.detect_detailed(series)  # no context at all must still work
    assert np.isfinite(full["scores"]).all() and np.isfinite(bare["scores"]).all()

    single = tmp_path / "single"
    run(archive_dir, single, make_config("smoke"), epochs=1, val_years=2, test_years=2, log=lambda *_: None)
    ens = EnsembleDetector([("ms", det, 2.0), ("single", RainfallAEDetector(str(single)), 1.0)])
    d = ens.detect_detailed(series, {"nbr_mean": np.zeros(70)})
    assert d["scores"].shape == (70,) and set(d["member_scores"]) == {"ms", "single"}
    assert d["votes"].max() <= 2 and abs(sum(ens.weights.values()) - 1) < 1e-9
    api = ens.detect(series)
    assert api.shape == (70,) and ((api >= 0) & (api <= 1)).all()


def test_source_attention_needs_msnet():
    t = LocalTrainer(RainfallTransform(3.0), make_config("smoke"))
    with pytest.raises(ValueError):
        t.source_attention(Batch.from_windows(np.zeros((2, 20), np.float32)))
    t2 = LocalTrainer(RainfallTransform(3.0), make_config("smoke", **MS))
    sources = np.zeros((2, 2, 20), np.float32)
    b = Batch.from_windows(np.zeros((2, 20), np.float32), sources=sources, source_mask=np.array([[1, 0], [1, 1]], bool))
    assert t2.source_attention(b).shape == (2, 20, 3)


def test_api_score_maps_threshold_to_point_eight():
    s = api_score(np.array([0.0, 10.0, 20.0]), 10.0)
    assert s[1] == pytest.approx(0.8) and s[0] < 0.8 < s[2] and ((s > 0) & (s < 1)).all()
