"""Locate the RF25 archive and a writable output root on a laptop, Kaggle, Colab or any server.

Data dir resolution (first hit wins):
  1. an explicit ``--data-dir`` that exists and contains ``RF25_ind*_rfp25.nc``
  2. ``$DATAMEND_DATA_DIR``
  3. ``../data``, ``./data`` and ``ml-service/data`` (repo layout)
  Each of 1-3 may be the RF25 folder itself or a data root that holds it in ``rf25/``
  (the layout described in ``ml-service/data/README.md``).
  4. a recursive search under ``/kaggle/input`` (Kaggle datasets mount at a version-dependent depth)

Output root: ``$DATAMEND_OUT_DIR``, else ``/kaggle/working`` when running on Kaggle, else the
current directory. Relative ``--out`` values are placed under it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_GLOB = "RF25_ind*_rfp25.nc"
KAGGLE_INPUT = Path("/kaggle/input")
KAGGLE_WORKING = Path("/kaggle/working")
ML_SERVICE = Path(__file__).resolve().parent.parent


def _has_data(p: Path) -> bool:
    return p.is_dir() and any(p.glob(_GLOB))


def resolve_data_dir(explicit: Optional[str] = None) -> Path:
    cands = []
    if explicit:
        cands.append(Path(explicit))
    if os.environ.get("DATAMEND_DATA_DIR"):
        cands.append(Path(os.environ["DATAMEND_DATA_DIR"]))
    cands += [Path("../data"), Path("data"), ML_SERVICE / "data"]
    for c in cands:
        # each candidate may be the RF25 folder itself or a data root holding ``rf25/``
        for d in (c, c / "rf25"):
            if _has_data(d):
                return d
    if KAGGLE_INPUT.is_dir():
        for f in sorted(KAGGLE_INPUT.rglob(_GLOB)):
            return f.parent
    raise FileNotFoundError(
        f"No {_GLOB} files found. Tried: {[str(c) for c in cands]}"
        f"{' and /kaggle/input' if KAGGLE_INPUT.is_dir() else ''}. "
        "Pass --data-dir or set DATAMEND_DATA_DIR."
    )


def resolve_out_dir(out: str) -> str:
    p = Path(out)
    if p.is_absolute():
        return str(p)
    root = os.environ.get("DATAMEND_OUT_DIR")
    if root:
        return str(Path(root) / p)
    if KAGGLE_WORKING.is_dir():
        return str(KAGGLE_WORKING / p)
    return str(p)
