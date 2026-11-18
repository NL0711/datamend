"""Download the RF25 dataset from Kaggle onto this machine and print the folder that holds the files.

Usage (from ml-service/):
    python scripts/fetch_rf25.py                       # default dataset, expects 125 files (1901-2025)
    python scripts/fetch_rf25.py --slug owner/name --expected 125

Credentials (the dataset may be private): either set KAGGLE_USERNAME and KAGGLE_KEY, or put ~/.kaggle/kaggle.json in
place (Kaggle -> Settings -> API -> Create New Token). Nothing is stored in this repository.

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


def _download(slug: str) -> str:
    try:
        import kagglehub
    except ImportError:
        raise DatasetNotFound("kagglehub is not installed: pip install kagglehub") from None
    try:
        return kagglehub.dataset_download(slug)
    except Exception as e:                                           # auth, network and 404 errors come in many types
        raise DatasetNotFound(
            f"could not download {slug}: {e}\nIf the dataset is private, set KAGGLE_USERNAME and KAGGLE_KEY, or create "
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
