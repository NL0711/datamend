"""How well does a false-alarm budget hold on data the threshold was not set on, per client?

Thresholds are set on clean cell-days (``years.threshold``). Here each threshold year is used to set thresholds and the *other* threshold
year (uncorrupted data) is used to check them, so the realised false-alarm rate is out-of-sample in time. Two threshold rules are compared:

  global      one threshold from all training-client cells (what the pipeline uses)
  per_client  one threshold per training client from that client's own cells; held-out clients, which have no calibration data of their
              own, use the global threshold (a region never seen in training has no data to calibrate on)

Cell-days are dependent in space and time, so no formal guarantee is claimed: the report gives a block bootstrap interval (blocks of
consecutive days) around each realised rate, which is the honest measure of how much the number moves. Validation data only.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

from qc.evaluate import group_cells, score_store
from qc.extremes import find_extremes
from qc.metrics import budget_thresholds
from qc.prepare import Prepared
from qc.scoring import ScoreStore

BLOCK_DAYS = 30


def _usable(p: Prepared, name: str, year: int, store: ScoreStore):
    s = store.load(name, "clean", year)
    ex = find_extremes(p.store.year(year), p.stats.heavy_mm, p.grid, int(p.cfg.extremes.min_cells))
    return s, np.isfinite(s) & ~ex.protected & ~ex.ambiguous


def _rate_ci(exceed: np.ndarray, total: np.ndarray, rng: np.random.Generator, n_boot: int):
    """Per-day exceedance and totals -> (rate per 1,000, [low, high] by a block bootstrap over days)."""
    if total.sum() == 0:
        return None, None
    rate = 1000.0 * exceed.sum() / total.sum()
    starts = np.arange(0, len(total), BLOCK_DAYS)
    blocks_e = np.array([exceed[s:s + BLOCK_DAYS].sum() for s in starts], float)
    blocks_t = np.array([total[s:s + BLOCK_DAYS].sum() for s in starts], float)
    idx = rng.integers(0, len(starts), (n_boot, len(starts)))
    te = blocks_t[idx].sum(axis=1)
    boot = 1000.0 * blocks_e[idx].sum(axis=1) / np.where(te > 0, te, np.nan)
    lo, hi = np.nanpercentile(boot, [2.5, 97.5])
    return float(rate), [float(lo), float(hi)]


def check_budget(p: Prepared, name: str, budget: float, store: Optional[ScoreStore] = None, n_boot: int = 200) -> List[Dict]:
    """One row per client (training and held-out) and threshold rule, pooled over the calibrate-on-one-year, check-on-the-other pairs."""
    store = store or score_store(p)
    years = list(p.split.years["threshold"])
    if len(years) < 2:
        raise ValueError("need at least two threshold years to check thresholds out of sample")
    seen = group_cells(p, "seen")
    clients = sorted(int(c) for c in np.unique(p.cell_client))
    heldout = {int(c) for c in p.split.heldout}
    rng = np.random.default_rng([int(p.cfg.seed), 11])
    data = {y: _usable(p, name, y, store) for y in years}
    acc: Dict = {}                                            # (client, rule) -> (per-day exceed, per-day total) lists
    for cal in years:
        s_c, k_c = data[cal]
        g_thr = budget_thresholds(s_c[k_c & seen[None, :]], [budget])[float(budget)]
        c_thr = {}
        for c in clients:
            if c in heldout:
                continue
            ref = s_c[k_c & (p.cell_client == c)[None, :] & seen[None, :]]
            if ref.size:
                c_thr[c] = budget_thresholds(ref, [budget])[float(budget)]
        for chk in (y for y in years if y != cal):
            s, k = data[chk]
            for c in clients:
                m = k & (p.cell_client == c)[None, :]
                for rule, thr in (("global", g_thr), ("per_client", c_thr.get(c, g_thr))):
                    e = ((s > thr) & m).sum(axis=1)
                    t = m.sum(axis=1)
                    acc.setdefault((c, rule), ([], []))
                    acc[(c, rule)][0].append(e)
                    acc[(c, rule)][1].append(t)
    rows = []
    for (c, rule), (es, ts) in sorted(acc.items()):
        rate, ci = _rate_ci(np.concatenate(es), np.concatenate(ts), rng, n_boot)
        rows.append({"client": c, "role": "held-out" if c in heldout else "training", "rule": rule, "budget": budget,
                     "false_per_1000": rate, "ci95": ci, "clean_cell_days": int(np.concatenate(ts).sum())})
    return rows


def _cell(r: Dict) -> str:
    if r["false_per_1000"] is None:
        return "n/a".rjust(9) + " " * 22
    ci = "" if not r["ci95"] else f"[{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}]"
    return f"{r['false_per_1000']:9.3f} {ci:>21}"


def format_rows(rows: Sequence[Dict]) -> str:
    by: Dict = {}
    for r in rows:
        by.setdefault(r["client"], {})[r["rule"]] = r
    out = [f"{'client':>6} {'role':<9} {'cell-days':>11} {'global':>9} {'95% interval':>21} {'per-client':>10} {'95% interval':>21}"]
    for c, d in sorted(by.items()):
        g, pc = d["global"], d["per_client"]
        out.append(f"{c:>6} {g['role']:<9} {g['clean_cell_days']:>11} {_cell(g)} {_cell(pc)}")
    return "\n".join(out)
