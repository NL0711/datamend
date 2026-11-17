"""Gate 2: the frozen corruption benchmark.

For every validation, test and stress year this writes one file holding the synthetic faults (sparse), the
protected-extreme and ambiguous-extreme masks, and the fault table. Every method is scored on these files.

  validation years   seen settings only (the fusion is fitted on them, so test-only settings must not appear)
  test, stress years all settings; each fault records whether it uses a setting reserved for test

The benchmark has one hash over all files. A scoring run compares it with ``benchmark.expected_hash``.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np

from qc import paths
from qc.extremes import Extremes, find_extremes
from qc.faults import FaultGenerator, FaultSet, is_unseen_setting, settings_from_config
from qc.grid import ContractError
from qc.prepare import Prepared
from qc.runs import read_json, write_json

log = logging.getLogger(__name__)
SPLITS = ("val", "test", "stress")
_SPLIT_ID = {"val": 1, "test": 2, "stress": 3}


@dataclass
class BenchYear:
    year: int
    split: str
    clean: np.ndarray            # (T, n_land) original values, mm
    faults: FaultSet
    extremes: Extremes
    unseen_setting: np.ndarray   # (n_events,) bool

    @property
    def corrupted(self) -> np.ndarray:
        return self.faults.apply(self.clean)


def bench_dir(cfg) -> Path:
    return paths.work_dir(cfg) / "benchmarks" / str(cfg.benchmark.name)


def _year_file(cfg, split: str, year: int) -> Path:
    return bench_dir(cfg) / f"{split}_{year}.npz"


def _digest(h, *arrays) -> None:
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())


def _summary(events: List[Dict], unseen: np.ndarray) -> Dict:
    def radius_bin(r):
        return "single cell" if r == 0 else ("1.5-4" if r <= 4 else "4-6")

    def strength_bin(s):
        return "weak (<0.25)" if s < 0.25 else ("0.25-0.6" if s < 0.6 else "0.6-1")

    out = {"events": len(events), "cell_days": int(sum(e["n_changed"] for e in events)),
           "events_unseen_setting": int(unseen.sum())}
    for name, key in (("by_kind", lambda e: e["kind"]), ("by_radius", lambda e: radius_bin(e["radius"])),
                      ("by_strength", lambda e: strength_bin(e["strength"]))):
        ev, cd = Counter(), Counter()
        for e in events:
            ev[key(e)] += 1
            cd[key(e)] += e["n_changed"]
        out[name] = {k: {"events": ev[k], "cell_days": cd[k]} for k in sorted(ev)}
    return out


def build_benchmark(p: Prepared, splits=SPLITS, overwrite: bool = False) -> Dict:
    cfg = p.cfg
    out = bench_dir(cfg)
    if (out / "manifest.json").is_file() and not overwrite:
        raise ContractError(f"{out} already holds a frozen benchmark. It must not be regenerated silently; "
                            "pass --overwrite to replace it (every result scored on the old one is then invalid).")
    out.mkdir(parents=True, exist_ok=True)
    gen = FaultGenerator(p.grid)
    h = hashlib.sha256()
    h.update(p.manifest["hash"].encode())
    summary: Dict[str, Dict] = {}
    for split in splits:
        settings = settings_from_config(cfg, "seen" if split == "val" else "all")
        all_events: List[Dict] = []
        all_unseen: List[np.ndarray] = []
        tot = Counter()
        for year in p.split.years[split]:
            clean = p.store.year(year)
            ex = find_extremes(clean, p.stats.heavy_mm, p.grid, cfg.extremes.min_cells)
            rng = np.random.default_rng([int(cfg.benchmark.seeds[split]), _SPLIT_ID[split], int(year)])
            fs = gen.generate(clean, settings, rng, forbidden=ex.protected)
            unseen = np.array([is_unseen_setting(e, cfg) for e in fs.events], bool)
            if (ex.protected[fs.t, fs.cell]).any():
                raise RuntimeError("a fault touched a protected extreme")          # cannot happen; guard anyway
            np.savez_compressed(
                _year_file(cfg, split, year), t=fs.t, cell=fs.cell, value=fs.value, weight=fs.weight, event=fs.event,
                shape=np.array(fs.shape), protected=np.packbits(ex.protected), ambiguous=np.packbits(ex.ambiguous),
                group=ex.group, unseen_setting=unseen,
                counts=np.array([ex.n_protected_events, ex.n_small_groups]),
                ev_kind=np.array([e["kind"] for e in fs.events]), ev_bases=np.array(["+".join(e["bases"]) for e in fs.events]),
                ev_strength=np.array([e["strength"] for e in fs.events], np.float32),
                ev_radius=np.array([e["radius"] for e in fs.events], np.float32),
                ev_centre=np.array([e["centre"] for e in fs.events], np.int32),
                ev_start=np.array([e["start"] for e in fs.events], np.int32),
                ev_duration=np.array([e["duration"] for e in fs.events], np.int32),
                ev_n=np.array([e["n_changed"] for e in fs.events], np.int32))
            _digest(h, fs.t, fs.cell, fs.value, fs.event, np.packbits(ex.protected), np.packbits(ex.ambiguous))
            all_events += fs.events
            all_unseen.append(unseen)
            tot["land_cell_days"] += int(np.isfinite(clean).sum())
            tot["protected_cell_days"] += int(ex.protected.sum())
            tot["ambiguous_cell_days"] += int(ex.ambiguous.sum())
            tot["protected_events"] += ex.n_protected_events
            tot["small_heavy_groups"] += ex.n_small_groups
            log.info("%s %d: %d faults, %d fault cell-days", split, year, len(fs.events), fs.t.size)
        s = _summary(all_events, np.concatenate(all_unseen) if all_unseen else np.zeros(0, bool))
        s.update(dict(tot))
        s["fault_share_of_cell_days"] = round(s["cell_days"] / max(tot["land_cell_days"], 1), 5)
        s["years"] = [p.split.years[split][0], p.split.years[split][-1]]
        summary[split] = s
    manifest = {"name": str(cfg.benchmark.name), "hash": h.hexdigest()[:16], "split_manifest_hash": p.manifest["hash"],
                "config": cfg.to_dict()["benchmark"], "extremes": cfg.to_dict()["extremes"], "splits": list(splits),
                "label_tier": "synthetic faults (stress test; not real QC labels)", "summary": summary}
    write_json(out / "manifest.json", manifest)
    return manifest


def check_benchmark(p: Prepared, require_pinned: bool = True) -> Dict:
    """Load the manifest and refuse to continue if the benchmark is not the one the config expects."""
    cfg = p.cfg
    path = bench_dir(cfg) / "manifest.json"
    if not path.is_file():
        raise ContractError(f"no frozen benchmark at {path.parent}. Build it first: python -m qc benchmark --config <config>")
    m = read_json(path)
    if m["split_manifest_hash"] != p.manifest["hash"]:
        raise ContractError("the frozen benchmark was built for a different split; rebuild it with --overwrite")
    expected = cfg.benchmark.expected_hash
    if expected:
        if m["hash"] != expected:
            raise ContractError(f"benchmark hash is {m['hash']} but the config expects {expected}. "
                                "This is not the benchmark the results were defined on; refusing to score.")
    elif require_pinned and not cfg.benchmark.allow_unpinned:
        raise ContractError(f"benchmark.expected_hash is not set. Put the hash {m['hash']} into the config "
                            "(benchmark.expected_hash) so that every run scores the same benchmark.")
    return m


def load_bench_year(p: Prepared, split: str, year: int) -> BenchYear:
    z = np.load(_year_file(p.cfg, split, year))
    shape = tuple(int(v) for v in z["shape"])
    n = shape[0] * shape[1]
    events = [{"kind": str(k), "bases": str(b).split("+"), "strength": float(s), "radius": float(r), "centre": int(c),
               "start": int(st), "duration": int(d), "n_changed": int(m)}
              for k, b, s, r, c, st, d, m in zip(z["ev_kind"], z["ev_bases"], z["ev_strength"], z["ev_radius"],
                                                 z["ev_centre"], z["ev_start"], z["ev_duration"], z["ev_n"])]
    fs = FaultSet(shape, z["t"], z["cell"], z["value"], z["weight"], z["event"], events)
    unpack = lambda a: np.unpackbits(a)[:n].reshape(shape).astype(bool)
    ex = Extremes(unpack(z["protected"]), unpack(z["ambiguous"]), z["group"], int(z["counts"][0]), int(z["counts"][1]))
    clean = p.store.year(year)
    if clean.shape != shape:
        raise ContractError(f"benchmark file for {year} has shape {shape}, data has {clean.shape}")
    return BenchYear(int(year), split, clean, fs, ex, z["unseen_setting"])
