"""Experiment configuration: YAML files with ``extends``, a compute profile and command-line overrides.

Merge order (later wins): the file named by ``extends`` (recursively) -> the compute profile
(``qc/configs/profiles/<name>.yaml``, merged under ``compute``) -> the experiment file -> ``--set`` overrides.
The same experiment config must give the same splits, seeds and benchmark under either profile, so
profiles may only set keys under ``compute``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

CONFIG_DIR = Path(__file__).resolve().parent / "configs"
PROFILE_DIR = CONFIG_DIR / "profiles"


class ConfigError(ValueError):
    pass


class Config:
    """Read-only nested mapping with attribute access: ``cfg.years.train``."""

    def __init__(self, data: Dict[str, Any]):
        object.__setattr__(self, "_d", data)

    def __getattr__(self, key: str) -> Any:
        try:
            v = self._d[key]
        except KeyError:
            raise ConfigError(f"missing config key {key!r}; known keys: {sorted(self._d)}") from None
        return Config(v) if isinstance(v, dict) else v

    __getitem__ = __getattr__

    def __setattr__(self, key, value):
        raise ConfigError("config is read-only; use --set or edit the YAML file")

    def __contains__(self, key: str) -> bool:
        return key in self._d

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key) if key in self._d else default

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self._d)

    def digest(self, exclude: Iterable[str] = ("compute", "paths", "name")) -> str:
        """Hash of everything that affects results. Compute profile, paths and the run name are excluded."""
        d = {k: v for k, v in self._d.items() if k not in set(exclude)}
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def _merge(base: Dict[str, Any], top: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in top.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def _read_chain(path: Path) -> Dict[str, Any]:
    data = _read(path)
    parent = data.pop("extends", None)
    if parent is None:
        return data
    p = Path(parent)
    for cand in (p, path.parent / p, CONFIG_DIR / p):
        if cand.is_file():
            return _merge(_read_chain(cand), data)
    raise ConfigError(f"{path}: 'extends: {parent}' not found")


def _set(d: Dict[str, Any], dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
        if not isinstance(d, dict):
            raise ConfigError(f"cannot set {dotted!r}: {k!r} is not a mapping")
    d[keys[-1]] = value


def parse_overrides(pairs: Optional[Iterable[str]]) -> Dict[str, Any]:
    """``["a.b=3", "name=x"]`` -> nested dict. Values are parsed as YAML (so ``[1,2]``, ``true``, ``1e-3`` work)."""
    out: Dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ConfigError(f"override {pair!r} must look like key.sub=value")
        key, raw = pair.split("=", 1)
        _set(out, key.strip(), yaml.safe_load(raw))
    return out


def available_profiles() -> List[str]:
    return sorted(p.stem for p in PROFILE_DIR.glob("*.yaml"))


def load_config(path: str | Path, overrides: Optional[Iterable[str]] = None, profile: Optional[str] = None) -> Config:
    exp = _read_chain(Path(path))
    over = parse_overrides(overrides)
    if profile:
        _set(over, "compute.profile", profile)
    name = _merge(exp, over).get("compute", {}).get("profile")
    if not name:
        raise ConfigError("compute.profile is not set (choose one of: %s)" % ", ".join(available_profiles()))
    prof_path = PROFILE_DIR / f"{name}.yaml"
    if not prof_path.is_file():
        raise ConfigError(f"unknown compute profile {name!r}; available: {', '.join(available_profiles())}")
    prof = _read(prof_path)
    if set(prof) - {"compute"}:
        raise ConfigError(f"profile {name!r} may only set keys under 'compute', found {sorted(set(prof) - {'compute'})}")
    return Config(_merge(_merge(prof, exp), over))


def year_range(pair) -> List[int]:
    """``[1951, 2012]`` -> every year from 1951 to 2012 inclusive."""
    lo, hi = int(pair[0]), int(pair[1])
    if hi < lo:
        raise ConfigError(f"year range {pair} is reversed")
    return list(range(lo, hi + 1))
