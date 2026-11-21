import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app as scorer  # noqa: E402


class StubInput:
    name = "input"


class StubSession:
    """Reconstructs every window as zeros, so the error is the mean absolute value of the window."""

    def get_inputs(self):
        return [StubInput()]

    def run(self, _, feeds):
        return [np.zeros_like(feeds["input"])]


def client(secret="s3cret"):
    return TestClient(scorer.create_app(session=StubSession(), secret=secret))


def test_health():
    r = client().get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["model"]["format"] == "onnx"


def test_auth():
    c = client()
    body = {"windows": [[0.0] * 288]}
    assert c.post("/score", json=body).status_code == 401
    assert c.post("/score", json=body, headers={"X-Scorer-Secret": "bad"}).status_code == 401
    assert c.post("/score", json=body, headers={"X-Scorer-Secret": "s3cret"}).status_code == 200


def test_score_shape_and_values():
    h = {"X-Scorer-Secret": "s3cret"}
    r = client().post("/score", json={"windows": [[1.0] * 288, [-2.0] * 288]}, headers=h)
    assert r.json()["errors"] == pytest.approx([1.0, 2.0])


@pytest.mark.parametrize("windows", [[], [[0.0] * 287], [[0.0] * 289], [[0.0] * 288] * 9])
def test_rejects_bad_shape(windows):
    r = client().post("/score", json={"windows": windows}, headers={"X-Scorer-Secret": "s3cret"})
    assert r.status_code == 422


def test_rejects_non_finite():
    r = client().post("/score", content='{"windows": [[' + ",".join(["0"] * 5 + ["Infinity"] + ["0"] * 282) + "]]}",
                      headers={"X-Scorer-Secret": "s3cret", "Content-Type": "application/json"})
    assert r.status_code == 422


def test_refuses_to_start_without_secret(monkeypatch):
    monkeypatch.delenv("SCORER_SECRET", raising=False)
    monkeypatch.delenv("SCORER_ALLOW_NO_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        scorer.create_app(session=StubSession())
    monkeypatch.setenv("SCORER_ALLOW_NO_SECRET", "1")
    assert scorer.create_app(session=StubSession()) is not None


@pytest.mark.skipif(not (ROOT / "weights" / "model.onnx").exists(), reason="weights/model.onnx not built")
def test_real_model_spike_scores_higher_and_is_deterministic():
    c = TestClient(scorer.create_app(secret="x"))
    t = np.linspace(0, 8 * np.pi, 288)
    flat = np.zeros(288)
    spike = np.zeros(288)
    spike[140:150] = 6.0
    sine = np.sin(t)
    body = {"windows": [flat.tolist(), spike.tolist(), sine.tolist()]}
    h = {"X-Scorer-Secret": "x"}
    a = c.post("/score", json=body, headers=h).json()["errors"]
    b = c.post("/score", json=body, headers=h).json()["errors"]
    assert a == b
    assert a[1] > a[0]
    assert all(np.isfinite(a))
