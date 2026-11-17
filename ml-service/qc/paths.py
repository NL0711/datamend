"""Where data, prepared state and run outputs live. Nothing here is specific to Kaggle or to one machine."""

from __future__ import annotations

import os
from pathlib import Path

from training.paths import ML_SERVICE, resolve_data_dir, resolve_out_dir

ASSETS = Path(__file__).resolve().parent / "assets"
CLIENT_MAP_ASSET = ASSETS / "client_map.json"


def rf25_dir(cfg) -> Path:
    """RF25 folder: ``paths.rf25``, ``$DATAMEND_RF25_DIR``, then the training package's search order."""
    explicit = cfg.paths.rf25 or os.environ.get("DATAMEND_RF25_DIR")
    if cfg.paths.rf25:
        # a folder named in the config is used or reported missing; it never falls back to another dataset (the UK study)
        from training.paths import _has_data
        d = Path(explicit)
        for c in (d, d / "rf25"):
            if _has_data(c):
                return c
        raise FileNotFoundError(f"no RF25-format files in {d} (paths.rf25 is set in the config). "
                                "For the UK study run `python -m qc uk-grid` first.")
    return resolve_data_dir(str(explicit) if explicit else None)


def work_dir(cfg) -> Path:
    """Root for ``splits/``, ``benchmarks/`` and ``cache/``: ``paths.work``, ``$DATAMEND_DATA_DIR``, else ``ml-service/data``."""
    root = cfg.paths.work or os.environ.get("DATAMEND_DATA_DIR") or (ML_SERVICE / "data")
    return Path(root)


def out_dir(cfg) -> Path:
    return Path(resolve_out_dir(str(cfg.paths.out)))
