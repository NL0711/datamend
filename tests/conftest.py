import warnings
from pathlib import Path
import pytest
try:
    import pytest_asyncio
except ImportError:
    pytest_asyncio = None


# Ignore third-party deprecation warnings from upstream SHAP and matplotlib
warnings.filterwarnings("ignore", category=PendingDeprecationWarning, module="shap.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="shap.*")
warnings.filterwarnings("ignore", category=UserWarning, module="shap.*")

@pytest.fixture(scope="session")
def ensure_trained_models():
    """Opt-in legacy fixture; rainfall tests must never train unrelated models."""
    from scripts.train_models import train_all_models
    models_dir = Path("models")
    train_file = Path("data/train_clean.csv")
    val_file = Path("data/val_mixed.csv")

    required_artifacts = [
        models_dir / "preprocessor.joblib",
        models_dir / "scaler.joblib",
        models_dir / "isolation_forest.joblib",
        models_dir / "temporal_autoencoder.pt",
        models_dir / "autoencoder.pt",
        models_dir / "mahalanobis.joblib",
        models_dir / "fault_classifier.joblib",
        models_dir / "model_metadata.json",
    ]

    if not all(p.exists() for p in required_artifacts) and train_file.exists():
        train_all_models(
            train_path=train_file,
            val_path=val_file,
            output_dir=models_dir,
            seq_len=30,
            epochs=15,
        )

if pytest_asyncio is not None:
    @pytest_asyncio.fixture
    async def initialize_test_database():
        """Ensures database tables and default stations exist before each test."""
        from backend.app.db.database import init_db
        await init_db()

    @pytest_asyncio.fixture
    async def async_client(initialize_test_database):
        from httpx import AsyncClient, ASGITransport
        from backend.app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
