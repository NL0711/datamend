"""Configuration formats used by the example environment and deployment hosts."""
import pytest
from backend.app.config import Settings


@pytest.mark.parametrize("raw,expected", [
    ("https://example.org", ["https://example.org"]),
    ("https://a.org, https://b.org", ["https://a.org", "https://b.org"]),
    ('["https://a.org"]', ["https://a.org"]),
])
def test_cors_accepts_deployment_formats(monkeypatch, raw, expected):
    monkeypatch.setenv("CORS_ORIGINS", raw)
    assert Settings(_env_file=None).CORS_ORIGINS == expected
