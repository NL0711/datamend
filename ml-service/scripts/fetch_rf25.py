"""Download the RF25 dataset from Kaggle onto this machine and print the folder that holds the files.

Usage (from ml-service/):
    python scripts/fetch_rf25.py                       # default dataset, expects 125 files (1901-2025)
    python scripts/fetch_rf25.py --slug owner/name --expected 125

Credentials (needed even for a public dataset): set KAGGLE_API_TOKEN (new-style KGAT_ token), or KAGGLE_USERNAME and
KAGGLE_KEY, or put ~/.kaggle/kaggle.json in place (Kaggle -> Settings -> API -> Create New Token). They can also be
written in ml-service/.env (see .env.example); real environment variables win over the file. Nothing is stored in this
repository.

The files stay in the kagglehub cache; the script prints the folder, and ``scripts/run_qc.py`` sets
DATAMEND_RF25_DIR to it. Pass --copy-to <dir> to copy them into another folder instead (existing files are kept).
Reuses ``qc.kaggle_data.locate_rf25``, which checks that every expected year is present.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qc.kaggle_data import PATTERN, DatasetNotFound, locate_rf25   # noqa: E402

DEFAULT_SLUG = "nathashalewis/majorproj-rainfall"
DEFAULT_EXPECTED = 125


def load_kaggle_env(env_files: tuple[Path, ...] | None = None) -> list[str]:
    """Copy KAGGLE_* settings from .env files into os.environ when they are not already set. Returns the names set.
    Only KAGGLE_ names are read, values are never printed, and a real environment variable always wins."""
    import os
    files = env_files if env_files is not None else (Path.cwd() / ".env", ROOT / ".env")
    done: list[str] = []
    for f in files:
        if not f.is_file():
            continue
        for raw in f.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            name, _, value = raw.partition("=")
            name, value = name.strip(), value.strip().strip('"').strip("'")
            if name.startswith("KAGGLE_") and value and not os.environ.get(name):
                os.environ[name] = value
                done.append(name)
    return done


def _download(slug: str) -> str:
    load_kaggle_env()
    try:
        import kagglehub
    except ImportError:
        raise DatasetNotFound("kagglehub is not installed: pip install kagglehub") from None
    try:
        return kagglehub.dataset_download(slug)
    except Exception as e:                                           # auth, network and 404 errors come in many types
        raise DatasetNotFound(
            f"could not download {slug}: {e}\nKaggle needs a login even for a public dataset: set KAGGLE_API_TOKEN (KGAT_ token) "
            "or KAGGLE_USERNAME and KAGGLE_KEY, in the environment or in ml-service/.env (see .env.example), or create "
            "~/.kaggle/kaggle.json (Kaggle -> Settings -> API -> Create New Token). Check the slug is owner/name.") from None


def fetch(slug: str = DEFAULT_SLUG, expected: int = DEFAULT_EXPECTED, copy_to: Path | None = None) -> Path:
    folder = locate_rf25(slug, input_root=Path("/nonexistent"), expected_files=expected, download=_download)
    if copy_to is None:
        return folder
    copy_to = Path(copy_to)
    copy_to.mkdir(parents=True, exist_ok=True)
    for f in sorted(folder.glob(PATTERN)):
        dst = copy_to / f.name
        if dst.is_file() and dst.stat().st_size == f.stat().st_size:
            continue
        shutil.copy2(f, dst)
    return copy_to


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--slug", default=DEFAULT_SLUG, help="Kaggle dataset: owner/name or its link")
    ap.add_argument("--expected", type=int, default=DEFAULT_EXPECTED, help="number of RF25 files that must be present")
    ap.add_argument("--copy-to", default=None, help="copy the files into this folder instead of using the kagglehub cache")
    a = ap.parse_args(argv)
    try:
        folder = fetch(a.slug, a.expected, Path(a.copy_to) if a.copy_to else None)
    except DatasetNotFound as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    n = sum(1 for _ in folder.glob(PATTERN))
    print(f"RF25 folder: {folder}\nfiles: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
