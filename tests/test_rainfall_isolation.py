"""The rainfall path must not import the legacy temperature/pressure/humidity packages (spec slice 2)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_PREFIXES = (
    "backend.app.spatial", "backend.app.sources", "backend.app.ml", "backend.app.services",
    "backend.app.db", "backend.simulator", "scripts.",
)

SNIPPET = """
import json, sys, importlib
for m in ("backend.app.geo", "backend.app.rainfall.catalog", "backend.app.rainfall.daily", "backend.app.rainfall.scorer",
          "backend.app.rainfall.service", "backend.app.rainfall.weather_union",
          "backend.app.validation.records", "backend.app.validation.ingest", "backend.app.validation.adapters"):
    importlib.import_module(m)
print(json.dumps(sorted(m for m in sys.modules if m.startswith(("backend", "scripts")))))
"""


def test_rainfall_modules_import_no_legacy_package():
    out = subprocess.run([sys.executable, "-c", SNIPPET], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    loaded = json.loads(out.stdout.strip().splitlines()[-1])
    legacy = [m for m in loaded if m.startswith(LEGACY_PREFIXES)]
    assert legacy == [], f"rainfall path imports legacy modules: {legacy}"


def test_station_catalogue_lives_in_the_rainfall_package():
    from backend.app.rainfall.catalog import CATALOG_PATH
    assert CATALOG_PATH.exists()
    assert CATALOG_PATH.parent.parent.name == "rainfall"


def test_haversine_known_distance_and_zero():
    from backend.app.geo import haversine_distance_km
    assert abs(haversine_distance_km(18.5204, 73.8567, 19.0760, 72.8777) - 120.0) < 5.0   # Pune to Mumbai, about 120 km
    assert haversine_distance_km(19.0, 72.8, 19.0, 72.8) == 0.0
