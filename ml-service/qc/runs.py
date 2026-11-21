"""Run folders: every run records what it was, so a result can be traced and a stopped run can resume."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import yaml

from qc.config import Config


def git_commit() -> str:
    try:
        root = Path(__file__).resolve().parent
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=root.parent, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() + ("+dirty" if dirty.stdout.strip() else "") if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _plain(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_plain(obj), indent=1), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class RunDir:
    """``<out>/<name>/`` holding ``config.yaml``, ``meta.json``, ``metrics.json``, ``checkpoints/`` and outputs."""

    def __init__(self, root: Path, name: str):
        self.path = Path(root) / name
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "checkpoints").mkdir(exist_ok=True)

    def start(self, cfg: Config, seed: int, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Write the resolved config and metadata. On resume, refuse to continue under a different config."""
        meta_path = self.path / "meta.json"
        meta = {"config_digest": cfg.digest(), "seed": int(seed), "git_commit": git_commit(),
                "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": cfg.compute.profile, **(extra or {})}
        if meta_path.is_file():
            old = read_json(meta_path)
            if old.get("config_digest") != meta["config_digest"] or old.get("seed") != meta["seed"]:
                raise RuntimeError(
                    f"{self.path} already holds a run with a different config or seed. "
                    "Use a new run name, or delete the folder to start over."
                )
            meta["started"] = old.get("started", meta["started"])
            meta["resumed"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        (self.path / "config.yaml").write_text(yaml.safe_dump(cfg.to_dict(), sort_keys=False), encoding="utf-8")
        write_json(meta_path, meta)
        return meta

    def file(self, *parts: str) -> Path:
        p = self.path.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def done(self, stage: str) -> bool:
        return (self.path / f"{stage}.done").is_file()

    def mark_done(self, stage: str) -> None:
        (self.path / f"{stage}.done").write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")
