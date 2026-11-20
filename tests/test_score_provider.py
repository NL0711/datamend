"""The score provider reads an exported score file (built here by hand, in the documented format; the platform imports nothing from ml-service)."""
import json

import numpy as np
import pytest

from backend.app.validation import score_provider as sp


def write(path, scores=None, periods=("2016-06-01", "2016-06-02"), lat=(8.1, 8.4), lon=(76.9, 77.2), threshold=None, budget=None, faults=None, tier="synthetic"):
    scores = np.array([[0.5, 2.0], [np.nan, 4.0]], dtype=np.float32) if scores is None else scores
    manifest = {"schema": "score-export-v1", "scale": "daily", "model_id": "stnet-x", "config_digest": "d", "label_tier": tier, "n_periods": len(periods),
                "n_cells": len(lat), "calibrated": threshold is not None and budget is not None, "threshold": threshold, "false_alarm_budget_per_1000": budget}
    arrays = {"manifest": np.array(json.dumps(manifest)), "periods": np.array(periods), "lat": np.array(lat, dtype=np.float32),
              "lon": np.array(lon, dtype=np.float32), "scores": scores}
    for k, v in (faults or {}).items():
        arrays[f"fault_{k}"] = v
    np.savez_compressed(path, **arrays)
    return str(path)


def test_lookup_returns_the_block_for_the_nearest_cell(tmp_path):
    p = sp.ScoreProvider(write(tmp_path / "s.npz", threshold=1.0, budget=5.0, faults={"drift": np.array([[0.1, 0.9], [0.2, 0.3]], dtype=np.float32)}))
    b = p.lookup(8.42, 77.18, "2016-06-01T00:00:00Z")
    assert b["score"] == pytest.approx(2.0) and b["flagged"] is True and b["calibrated"] is True and b["label_tier"] == "synthetic"
    assert b["fault_scores"] == {"drift": pytest.approx(0.9)} and b["model_kind"] == "stnet"


def test_no_flag_without_a_calibrated_threshold(tmp_path):
    b = sp.ScoreProvider(write(tmp_path / "s.npz")).lookup(8.1, 76.9, "2016-06-01")
    assert b["calibrated"] is False and "flagged" not in b


@pytest.mark.parametrize("lat,lon,day", [(None, 76.9, "2016-06-01"), (8.1, None, "2016-06-01"), (8.1, 76.9, None), (8.1, 76.9, "2016-07-01"),
                                         (12.0, 76.9, "2016-06-01"), (8.1, 90.0, "2016-06-01"), (8.1, 76.9, "2016-06-02")])
def test_nothing_is_invented(tmp_path, lat, lon, day):
    # last case: the nearest cell's score on that day is NaN
    assert sp.ScoreProvider(write(tmp_path / "s.npz")).lookup(lat, lon, day) is None


def test_bad_files_raise_a_plain_error(tmp_path):
    np.savez(tmp_path / "x.npz", a=np.zeros(2))
    with pytest.raises(sp.ScoreFileError):
        sp.ScoreProvider(str(tmp_path / "x.npz"))
    with pytest.raises(sp.ScoreFileError):
        sp.ScoreProvider(str(tmp_path / "missing.npz"))
    with pytest.raises(sp.ScoreFileError):
        sp.ScoreProvider(write(tmp_path / "t.npz", tier="reviewer_labels"))
    with pytest.raises(sp.ScoreFileError):
        sp.ScoreProvider(write(tmp_path / "u.npz", scores=np.zeros((3, 2), dtype=np.float32)))


def test_get_provider_is_none_when_unset_and_reloads_on_change(tmp_path):
    assert sp.get_provider("") is None
    f = write(tmp_path / "s.npz")
    first = sp.get_provider(f)
    assert sp.get_provider(f) is first
