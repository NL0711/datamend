import pytest
from fastapi import HTTPException

from detectors.registry import DETECTOR_FACTORIES, DetectorUnavailable, get_detector


def test_registry_names_and_errors(monkeypatch):
    assert set(DETECTOR_FACTORIES) == {"rainfall_ae", "rainfall_ensemble"}
    with pytest.raises(KeyError):
        get_detector("timercd")  # the zero-shot detector is gone
    monkeypatch.delenv("RAINFALL_AE_ARTIFACT", raising=False)
    with pytest.raises(DetectorUnavailable):
        get_detector("rainfall_ae")


def test_api_maps_registry_errors_to_http_codes(monkeypatch):
    import main
    monkeypatch.delenv("RAINFALL_AE_ARTIFACT", raising=False)
    with pytest.raises(HTTPException) as unknown:
        main._get_detector("timercd")
    assert unknown.value.status_code == 400 and "rainfall_ae" in unknown.value.detail
    with pytest.raises(HTTPException) as unavailable:
        main._get_detector("rainfall_ae")
    assert unavailable.value.status_code == 503
