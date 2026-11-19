"""qc.stnet: features against brute force, the network's memory and causality, the lattice, and a tiny end-to-end run."""
import numpy as np
import pytest
import torch

from qc import stnet as S
from qc.evaluate import score_store
from qc.faults import FaultGenerator


def _brute_median(z, v, y, x, r):
    vals = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if (dy, dx) == (0, 0) or dy * dy + dx * dx > r * r:
                continue
            yy, xx = y + dy, x + dx
            if 0 <= yy < z.shape[0] and 0 <= xx < z.shape[1] and v[yy, xx]:
                vals.append(z[yy, xx])
    return np.median(vals) if len(vals) >= 3 else np.nan


def test_masked_median_and_mean_match_brute_force():
    rng = np.random.default_rng(0)
    z = rng.random((2, 20, 22)).astype(np.float32)
    v = rng.random((2, 20, 22)) < 0.8
    zt, vt = torch.from_numpy(z), torch.from_numpy(v)
    for r in (2, 4):
        med = S.masked_median(zt, vt, r).numpy()
        for b, y, x in [(0, 0, 0), (1, 5, 7), (0, 10, 21), (1, 19, 3)]:
            exp = _brute_median(z[b], v[b], y, x, r)
            assert (np.isnan(exp) and np.isnan(med[b, y, x])) or med[b, y, x] == pytest.approx(exp, abs=1e-6)
    mean = S.masked_mean(zt, vt, 8).numpy()
    for b, y, x in [(0, 3, 3), (1, 10, 10)]:
        vals = [z[b, yy, xx] for yy in range(max(0, y - 8), min(20, y + 9)) for xx in range(max(0, x - 8), min(22, x + 9))
                if v[b, yy, xx] and (yy, xx) != (y, x)]
        assert mean[b, y, x] == pytest.approx(np.mean(vals), abs=1e-5)


def test_network_shapes_memory_and_causality():
    torch.manual_seed(0)
    net = S.STNet(8, 8, use_gru=True).eval()
    x = torch.randn(3, 5, S.IN_CH, 24, 30)                                  # 30 is not a multiple of 4
    state, outs = (None, None), []
    with torch.no_grad():
        for t in range(5):
            o, state = net.step(x[:, t], state)
            outs.append(o)
    assert outs[0]["fault"].shape == (3, S.N_OUT, 24, 30) and outs[0]["clean"].shape == (3, 24, 30)
    with torch.no_grad():
        fresh, _ = net.step(x[:, 4], (None, None))
    assert not torch.allclose(outs[4]["fault"], fresh["fault"], atol=1e-5)    # earlier days change today's output: memory
    x2 = x.clone()
    x2[:, 4] += 5.0
    state, outs2 = (None, None), []
    with torch.no_grad():
        for t in range(5):
            o, state = net.step(x2[:, t], state)
            outs2.append(o)
    for t in range(4):
        assert torch.allclose(outs[t]["fault"], outs2[t]["fault"]), "a later day changed an earlier output"
    nog = S.STNet(8, 8, use_gru=False).eval()
    with torch.no_grad():
        a, st = nog.step(x[:, 0], (None, None))
        b, _ = nog.step(x[:, 1], st)
        c, _ = nog.step(x[:, 1], (None, None))
    assert torch.allclose(b["fault"], c["fault"], atol=1e-6)                  # without the ConvGRU there is no memory between days


def test_lattice_hides_every_cell_once_per_set_of_phases():
    masks = S.lattice_masks(40, 44, "cpu")
    assert len(masks) == 4
    assert torch.stack(masks).any(0).all()                                    # together they hide every cell
    for m in masks:
        assert 0.1 < float(m.float().mean()) < 0.9


def test_long_memory_starts_as_no_correction():
    lm = S.LongMemory(S.IN_CH, 8)
    assert torch.count_nonzero(lm(torch.randn(4, 30, S.IN_CH))) == 0


def test_holdout_removes_the_kind_from_the_generator_settings(prepared):
    st = S.faults_for_training(prepared, ("zeroed", "drift"))
    assert "zeroed" not in st.kinds and "drift" not in st.kinds and "zeroed" not in st.combination_bases
    assert "spike" in st.kinds
    with pytest.raises(ValueError):
        S.faults_for_training(prepared, tuple(S.faults_for_training(prepared, ()).kinds))


@pytest.fixture(scope="module")
def tiny_cfg():
    return S.STConfig(width=8, c_feat=8, long_hidden=8, epochs=1, steps=2, batch=2, window=8, burn=2, crop=24,
                      long_epochs=1, long_steps=2, long_cells=64, prefix="stt")


def test_year_data_never_reads_held_out_cells_and_labels_match_the_faults(prepared, tiny_cfg):
    p = prepared
    readable = p.split.input_mask()
    d = S.year_data(p, p.split.years["train"][1], FaultGenerator(p.grid), np.random.default_rng(0), tiny_cfg, readable, "cpu")
    hid = ~readable
    assert torch.isnan(d.seen[:, torch.from_numpy(hid)]).all()                 # held-out and buffer cells are never an input
    for name in ("clean_z", "clean_ok", "labels", "weight", "pos", "wpos"):               # only `seen` may hold NaN (unreadable cells);
        assert torch.isfinite(getattr(d, name).float()).all(), f"{name} has non-finite values (NaN times a zero mask is still NaN)"
    assert d.labels.shape == (d.rows, S.N_OUT) + tuple(p.grid.shape)
    anyl = d.labels[:, 0] > 0
    for k in range(1, S.N_OUT):
        assert not ((d.labels[:, k] > 0) & ~anyl).any()                        # a per-kind label implies the any-fault label
    assert int(anyl.sum()) > 0


def test_end_to_end_tiny_run_trains_scores_evaluates_and_resumes(prepared, bench, tiny_cfg):
    p = prepared
    out = S.run_stnet(p, 0, tiny_cfg, ("val",), max_years=2)
    assert out["status"] == "done"
    store = score_store(p)
    y = p.split.years["val"][0]
    for nm in ("fault", "clean", "disc", "spike", "drift"):
        a = store.load(f"stt_{nm}_s0", "val", y)
        assert a.shape[1] == p.grid.n_land and np.isfinite(a).any() and (a[np.isfinite(a)] >= 0).all()
    assert ("stt_fault_s0", "val") in out["metrics"]
    import json
    from qc import paths
    rd = paths.out_dir(p.cfg) / str(p.cfg.name) / "stt_s0"
    ck = torch.load(rd / "checkpoints" / "stt_s0_final.pt", weights_only=False)
    for part in ("model", "long"):
        assert all(torch.isfinite(v).all() for v in ck[part].values() if v.dtype.is_floating_point), f"{part} weights are not finite"
    losses = [r["loss"] for r in json.loads((rd / "train_log_stt_s0.json").read_text(encoding="utf-8"))]
    assert losses and all(l is not None and np.isfinite(l) for l in losses), "a training loss was NaN"
    again = S.run_stnet(p, 0, tiny_cfg, ("val",), max_years=2)                 # finished: loads the final checkpoint, scores exist
    assert again["status"] == "done"


def test_stage_two_trains_on_years_the_encoder_never_saw_and_the_probe_reports_per_kind(prepared, bench, tiny_cfg):
    import json
    from qc import paths
    p = prepared
    S.run_stnet(p, 0, tiny_cfg, ("val",), max_years=2)
    log_file = paths.out_dir(p.cfg) / str(p.cfg.name) / "stt_s0" / "train_log_stt_s0.json"
    rows = json.loads(log_file.read_text(encoding="utf-8"))
    y1 = {r["year"] for r in rows if r["phase"] == 1}
    y2 = {r["year"] for r in rows if r["phase"] == 2}
    assert y1 and y2 and not (y1 & y2)                                           # disjoint: stage 2 never sees features the encoder was fitted on
    probe = json.loads((log_file.parent / "probe_stt_s0.json").read_text(encoding="utf-8"))
    assert set(probe) == set(S.KINDS)
    assert all(v["auc"] is None or 0.0 <= v["auc"] <= 1.0 for v in probe.values())


def test_too_few_years_for_the_long_memory_is_refused(prepared, bench):
    cfg = S.STConfig(width=8, c_feat=8, long_hidden=8, epochs=1, steps=1, batch=2, window=6, burn=2, crop=24, prefix="stfew")
    with pytest.raises(ValueError, match="too few training years"):
        S.run_stnet(prepared, 0, cfg, ("val",), max_years=1)


def test_ablation_switches_run(prepared, bench):
    cfg = S.STConfig(width=8, c_feat=8, long_hidden=8, epochs=1, steps=1, batch=2, window=6, burn=2, crop=24, long_steps=1,
                     long_cells=32, use_gru=False, use_long=False, use_disc=False, use_robust=False, holdout_kinds=("zeroed",),
                     prefix="stabl")
    out = S.run_stnet(prepared, 0, cfg, ("val",), max_years=2)
    assert out["status"] == "done"
