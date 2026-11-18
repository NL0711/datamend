"""fetch_rf25.load_kaggle_env: reads only KAGGLE_ names from .env files and never overrides real environment variables."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from fetch_rf25 import load_kaggle_env   # noqa: E402


def test_sets_only_missing_kaggle_names(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nCEDA_TOKEN=abc\nKAGGLE_API_TOKEN="tok123"\nKAGGLE_USERNAME=\nKAGGLE_KEY=fromfile\n', encoding="utf-8")
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.setenv("KAGGLE_KEY", "fromenv")
    monkeypatch.delenv("CEDA_TOKEN", raising=False)
    done = load_kaggle_env((env,))
    import os
    assert done == ["KAGGLE_API_TOKEN"]
    assert os.environ["KAGGLE_API_TOKEN"] == "tok123"
    assert os.environ["KAGGLE_KEY"] == "fromenv"          # a real variable wins
    assert "KAGGLE_USERNAME" not in os.environ             # empty value is ignored
    assert "CEDA_TOKEN" not in os.environ                  # non-Kaggle names are never read


def test_missing_file_is_fine(tmp_path):
    assert load_kaggle_env((tmp_path / "nope.env",)) == []
