"""qc.score_export: schema 1 file on GENERATED arrays (no model, no real data)."""
import json
from pathlib import Path

import jsonschema
import numpy as np
import pytest

from qc import score_export as S

SCHEMA = json.loads((Path(__file__).resolve().parents[3] / "docs/contracts/score-export-v1.schema.json").read_text(encoding="utf8"))


def base(**kw):
    rng = np.random.default_rng(0)
    sc = rng.random((3, 4)).astype(np.float32)
    sc[1, 2] = np.nan
    args = dict(scores=sc, periods=["2016-06-01", "2016-06-02", "2016-06-03"], lat=[8.1, 8.1, 8.4, 8.4], lon=[76.9, 77.2, 76.9, 77.2], scale="daily",
                model_id="stnet-test", config_digest="abc123")
    args.update(kw)
    return args


def test_round_trip_keeps_arrays_nan_and_validates_against_the_schema(tmp_path):
    f = tmp_path / "s.npz"
    m = S.write_score_export(f, **base(fault_scores={"drift": np.ones((3, 4))}, threshold=1.0, false_alarm_budget_per_1000=5.0))
    jsonschema.validate({k: v for k, v in m.items()}, SCHEMA)
    got = S.read_score_export(f)
    assert got["manifest"]["calibrated"] is True and got["manifest"]["label_tier"] == "synthetic" and m["sha256"]
    assert got["scores"].shape == (3, 4) and np.isnan(got["scores"][1, 2]) and set(got["faults"]) == {"drift"}


def test_uncalibrated_without_a_budget(tmp_path):
    m = S.write_score_export(tmp_path / "s.npz", **base())
    assert m["calibrated"] is False and m["threshold"] is None


@pytest.mark.parametrize("kw,needle", [
    ({"threshold": 1.0}, "budget"),
    ({"scale": "hourly"}, "scale"),
    ({"scores": np.zeros((2, 4))}, "P x n"),
    ({"fault_scores": {"made_up": np.zeros((3, 4))}}, "unknown fault kind"),
    ({"fault_scores": {"drift": np.zeros((2, 4))}}, "shape"),
    ({"periods": ["2016-06-01", "nope", "2016-06-03"]}, "ISO"),
    ({"scores": np.full((3, 4), np.inf)}, "infinite"),
])
def test_rules_are_enforced_and_nothing_is_written(tmp_path, kw, needle):
    f = tmp_path / "s.npz"
    with pytest.raises(S.ExportError) as e:
        S.write_score_export(f, **base(**kw))
    assert needle in str(e.value) and not f.exists()


def test_locked_test_years_are_refused_unless_the_single_pass_is_open(tmp_path):
    f = tmp_path / "s.npz"
    with pytest.raises(S.ExportError, match="locked test years"):
        S.write_score_export(f, **base(periods=["2019-06-01", "2019-06-02", "2019-06-03"]))
    assert not f.exists()
    m = S.write_score_export(f, **base(periods=["2019-06-01", "2019-06-02", "2019-06-03"], test_pass_open=True))
    assert m["test_years_included"] is True


def test_a_file_that_is_not_an_export_is_refused(tmp_path):
    f = tmp_path / "x.npz"
    np.savez(f, a=np.zeros(3))
    with pytest.raises(S.ExportError):
        S.read_score_export(f)
    with pytest.raises(S.ExportError):
        S.read_score_export(tmp_path / "missing.npz")
