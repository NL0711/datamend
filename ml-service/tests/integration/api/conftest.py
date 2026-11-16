import pytest


@pytest.fixture(autouse=True)
def plumbing_detector(monkeypatch):
    """API tests exercise request/response plumbing with generic ETT data, not a trained rainfall
    model, so the ``rainfall_ae`` name resolves to a statistical test detector here."""
    from detectors import registry
    from tests.support import ZScoreDetector

    monkeypatch.setitem(registry.DETECTOR_FACTORIES, "rainfall_ae", ZScoreDetector)
    monkeypatch.setattr(registry, "_cache", {})
