"""run_offline_validation: offline reference models scored on validation years only, with the same budget thresholds."""
import numpy as np
import pytest

from qc.benchmark import build_benchmark
from qc.config import load_config
from qc.evaluate import score_store
from qc.offline import offline_name, run_offline_validation
from qc.prepare import load_prepared
from qc.tests.test_gate4 import TINY
from qc.tests.test_gate9 import _old_model


@pytest.fixture(scope="module")
def pv(world, prepared, tmp_path_factory):       # `prepared` writes the splits this config then loads
    old = tmp_path_factory.mktemp("old_models_val")
    over = [f"offline.artifacts.lstm_ae={_old_model(old / 'lstm', 'lstm_ae', [1990, 1991])}",       # trained before every scored year
            f"offline.artifacts.rainnet={_old_model(old / 'rainnet', 'rainnet', [1997, 1998])}"]   # 1997-1998 are validation years here
    cfg = load_config(world / "test.yaml", TINY + ["name=offval", "benchmark.name=offvalbench"] + over)
    p = load_prepared(cfg)
    build_benchmark(p, splits=("val", "test", "stress"), overwrite=True)
    return p


def test_scores_validation_only_and_labels_it_non_causal(pv):
    results, not_run = run_offline_validation(pv)
    assert list(results) == [offline_name("lstm_ae")]
    res = results[offline_name("lstm_ae")]
    assert res["split"] == "val" and res["label"].startswith("non-causal") and "seen" in res["groups"]
    store = score_store(pv)
    y = pv.split.years["val"][0]
    assert store.has(offline_name("lstm_ae"), "val", y)
    for split in ("test", "stress"):                      # the single-use years are never read or written
        assert not any(store.has(offline_name("lstm_ae"), split, yy) for yy in pv.split.years[split])
    s = store.load(offline_name("lstm_ae"), "val", y)
    assert np.isfinite(s).any()


def test_a_model_trained_on_scored_years_is_refused_by_name(pv):
    _, not_run = run_offline_validation(pv)
    why = " ".join(v for k, v in not_run.items() if "rainnet" in k)
    assert "NOT RUN" in why and "1997" in why
    assert any("no artifact configured" in v for k, v in not_run.items() if "msnet" in k)
