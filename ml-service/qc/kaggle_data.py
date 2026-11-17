"""Find the RF25 files on Kaggle from a dataset link (used by ``notebooks/datamend_qc_kaggle.ipynb``).

A Kaggle notebook cannot download its input data by itself; the dataset has to be attached ("Add Input"). Given the
link of the dataset, this module works out where Kaggle mounted it and returns the folder holding the RF25 files.
Where the mount point lives has changed between Kaggle versions, so the search does not assume one layout: it looks
at the likely places for the link's name first, then at every folder under the input root that holds RF25 files.
If nothing is found and ``download`` is allowed (internet on), it falls back to ``kagglehub``. Nothing here is
specific to RF25 beyond the file pattern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

PATTERN = "RF25_ind*_rfp25.nc"
KAGGLE_INPUT = Path("/kaggle/input")


class DatasetNotFound(RuntimeError):
    """The dataset is not attached (or not downloadable). The message says how to fix it."""


@dataclass(frozen=True)
class Handle:
    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


_URL = re.compile(r"^(?:https?://)?(?:www\.)?kaggle\.com/(?:datasets/)?([\w.-]+)/([\w.-]+)", re.I)
_SLUG = re.compile(r"^([\w.-]+)/([\w.-]+)$")


def parse_dataset_link(link: str) -> Optional[Handle]:
    """Handle from a Kaggle dataset link or ``owner/name``. A local path (``/kaggle/input/...``) gives None.

    Accepts ``https://www.kaggle.com/datasets/owner/name``, with or without ``/versions/3``, ``/data`` or a query,
    ``https://www.kaggle.com/owner/name`` and ``owner/name``.
    """
    link = (link or "").strip().strip('"').strip("'")
    if not link:
        raise DatasetNotFound("no dataset link given: paste the Kaggle dataset link into DATASET_LINK")
    if link.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", link):
        return None
    m = _URL.match(link.split("?")[0].split("#")[0])
    if m:
        if m.group(1).lower() in ("datasets", "code", "competitions", "models"):
            raise DatasetNotFound(f"{link!r} is not a dataset link; it should look like https://www.kaggle.com/datasets/<owner>/<name>")
        return Handle(m.group(1), m.group(2))
    m = _SLUG.match(link)
    if m:
        return Handle(m.group(1), m.group(2))
    raise DatasetNotFound(f"cannot read {link!r} as a Kaggle dataset link; use https://www.kaggle.com/datasets/<owner>/<name>")


def rf25_dirs(root: Path) -> List[Path]:
    """Every folder under ``root`` that holds RF25 files, most files first."""
    root = Path(root)
    if not root.is_dir():
        return []
    counts = {}
    for f in root.rglob(PATTERN):
        counts[f.parent] = counts.get(f.parent, 0) + 1
    return [d for d, _ in sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))]


def _count(d: Path) -> int:
    return sum(1 for _ in Path(d).glob(PATTERN))


def locate_rf25(link: str, input_root: Path = KAGGLE_INPUT, expected_files: Optional[int] = None,
                download: Optional[Callable[[str], str]] = None) -> Path:
    """Folder with the RF25 files for ``link``.

    Order: a local path given as the link; folders named after the dataset under ``input_root``; any other folder under
    ``input_root`` holding RF25 files (only if exactly one such folder exists, so another attached dataset is never
    picked by accident); then ``download(slug)`` if given (for example ``kagglehub.dataset_download``).
    ``expected_files`` (for example 123 for 1901-2023) only produces a clear error when fewer files are present.
    """
    input_root = Path(input_root)
    handle = parse_dataset_link(link)
    found: Optional[Path] = None
    if handle is None:
        p = Path(link.strip())
        hits = rf25_dirs(p)
        found = hits[0] if hits else None
        if found is None:
            raise DatasetNotFound(f"no {PATTERN} files under {p}")
    else:
        named = [input_root / handle.name, input_root / handle.owner / handle.name,
                 input_root / "datasets" / handle.owner / handle.name]
        for base in named:
            hits = rf25_dirs(base)
            if hits:
                found = hits[0]
                break
        if found is None:
            everything = rf25_dirs(input_root)
            if len(everything) == 1:
                found = everything[0]
            elif len(everything) > 1:
                raise DatasetNotFound(
                    f"{handle.slug} is not mounted under {input_root}, but {len(everything)} other folders there hold RF25 files "
                    f"({[str(d) for d in everything[:4]]}). Attach {handle.slug} (Add Input, paste the link) so it can be told apart.")
        if found is None and download is not None:
            root = Path(download(handle.slug))
            hits = rf25_dirs(root)
            found = hits[0] if hits else None
        if found is None:
            raise DatasetNotFound(
                f"{handle.slug} is not attached to this notebook and nothing under {input_root} holds {PATTERN}. "
                f"In the notebook sidebar choose Add Input, paste the dataset link, attach it, and run this cell again "
                f"(or turn Internet on so it can be downloaded).")
    n = _count(found)
    if expected_files is not None and n < expected_files:
        raise DatasetNotFound(f"{found} holds {n} RF25 files, expected {expected_files}. The dataset must contain every year "
                              "of the configured ranges (1901-2023 is 123 files); attach the full dataset.")
    return found


def find_saved_outputs(link: str, input_root: Path = KAGGLE_INPUT) -> Optional[Path]:
    """Root of a previous notebook's output (the folder that holds ``artifacts/qc``), attached as input, to resume from.
    Returns None if none is found."""
    handle = parse_dataset_link(link) if not str(link).startswith("/") else None
    roots = [Path(link)] if handle is None else [input_root / handle.name, input_root / handle.owner / handle.name, input_root]
    for root in roots:
        if not root.is_dir():
            continue
        for d in sorted(root.rglob("qc")):
            if d.is_dir() and d.parent.name == "artifacts":
                return d.parent.parent
    return None
