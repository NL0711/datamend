import os
import tempfile
import warnings
from pathlib import Path
import pytest

# Tests never touch a developer's configured database: pin a throwaway SQLite file BEFORE the app (and its settings) load.
# Environment variables outrank .env in pydantic-settings.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + (Path(tempfile.gettempdir()) / "datamend_tests.db").as_posix()
# ...and a throwaway file for dashboard-saved settings, so tests never read or write the developer's real data/runtime_settings.json
os.environ["RUNTIME_SETTINGS_PATH"] = (Path(tempfile.gettempdir()) / "datamend_tests_runtime_settings.json").as_posix()
os.environ["REQUIRE_LOGIN"] = "false"     # most tests call the API without a session; tests/test_auth.py switches it on where it matters
os.environ["NARRATOR_EMBEDDED"] = "false"       # most tests expect "no narrator"; the embedded narrator's own tests switch it on
for _name in ("ANTHROPIC_API_KEY", "WEATHER_PROVIDER", "WEATHER_UNION_API_KEY", "WEATHER_UNION_CITY", "NARRATOR_URL", "NARRATOR_TOKEN", "ADMIN_TOKEN", "GEMINI_API_KEY",
              "FEED_HISTORY_URL"):
    os.environ[_name] = ""           # a developer's real .env values must not leak into a test run (environment outranks .env)
try:
    import pytest_asyncio
except ImportError:
    pytest_asyncio = None

try:
    from httpx import AsyncClient, ASGITransport
    from backend.app.main import app
    from backend.app.db.database import init_db
except ImportError:
    AsyncClient = None
    ASGITransport = None
    app = None
    init_db = None
# Ignore third-party deprecation warnings from upstream SHAP and matplotlib
warnings.filterwarnings("ignore", category=PendingDeprecationWarning, module="shap.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="shap.*")
warnings.filterwarnings("ignore", category=UserWarning, module="shap.*")

# No test trains models. The legacy tests that need artifacts read the committed ones in models/
# (slice 9 deletes both); the rainfall tests need no models at all.

if pytest_asyncio is not None:
    @pytest_asyncio.fixture(autouse=True)
    async def initialize_test_database():
        """Ensures database tables and default stations exist before each test."""
        if init_db is not None:
            await init_db()

    @pytest_asyncio.fixture
    async def async_client():
        if ASGITransport is not None and app is not None and AsyncClient is not None:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client
