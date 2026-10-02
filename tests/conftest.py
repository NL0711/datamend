import warnings
import pytest
import pytest_asyncio
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.db.database import init_db
from scripts.train_models import train_all_models

# Ignore third-party deprecation warnings from upstream SHAP and matplotlib
warnings.filterwarnings("ignore", category=PendingDeprecationWarning, module="shap.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="shap.*")
warnings.filterwarnings("ignore", category=UserWarning, module="shap.*")

@pytest.fixture(scope="session", autouse=True)
def ensure_trained_models():
    """Ensure genuine production model artifacts exist in models/."""
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

@pytest_asyncio.fixture(autouse=True)
async def initialize_test_database():
    """Ensures database tables and default stations exist before each test."""
    await init_db()

@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
