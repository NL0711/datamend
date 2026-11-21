"""Download ONLY the model files of keras-io/timeseries-anomaly-detection into ./weights.

Skips logs/. Records the repo revision in weights/SOURCE.json. Weights are used as is, never retrained.
Needs: pip install huggingface_hub
"""
import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

REPO = "keras-io/timeseries-anomaly-detection"
PINNED = "57126012e02dcab3a653501f12cb599c4a51db7a"
OUT = Path(__file__).parent / "weights"
PATTERNS = ["saved_model.pb", "keras_metadata.pb", "variables/*", "README.md", "history.json"]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    path = snapshot_download(REPO, revision=PINNED, allow_patterns=PATTERNS, local_dir=OUT)
    sha = HfApi().model_info(REPO, revision=PINNED).sha
    files = sorted(str(p.relative_to(OUT)).replace("\\", "/") for p in OUT.rglob("*") if p.is_file() and p.name != "SOURCE.json" and ".cache" not in p.parts)
    (OUT / "SOURCE.json").write_text(json.dumps({"repo": REPO, "revision": sha, "files": files}, indent=2))
    print("downloaded to", path, "revision", sha)
    print("\n".join(files))


if __name__ == "__main__":
    main()
