"""The STNet architecture candidate: a frozen fusion of the untrained rules with the STNet fault head, an optional regional calibration, and the
selection rule that decides, on VALIDATION data only, whether it replaces the old daily pipeline.

STATUS: new, unit-tested on a generated world only; nothing here has run on real RF25. SYNTHETIC faults, not real QC labels. Not a novelty claim.

Candidate  fused score of (rules, <prefix>_fault_s<seed>), fitted on the synthetic faults of ``years.fusion_fit`` (same fusion code as the daily
           pipeline; variants ``boosted`` and ``logistic``), saved to ``<run>/fusion/models_stnet``. Optionally a regional calibration on top: each
           client's fused scores are mapped to -log10(1 - F_client), F_client being the empirical distribution of that client's OWN clean cell-days
           in the threshold years (protected and ambiguous extremes left out). No label is used. It makes one global threshold act like one
           threshold per region, which is what deploying on a region with clean history means. The tables are frozen with the fusion.
Rule       (written once, ``stnet_choice.json``; the cross-scale rule plus one guard that was added after the validation results were seen and before
           any test year is scored: see the protocol). The candidate replaces the best old daily fusion only if, at the final budget on the held-out
           threshold years, ALL hold: recall at least ``min_recall_gain`` higher; false alerts per 1,000 clean cell-days not above the budget;
           protected extremes flagged not higher; and the out-of-sample false-alarm rate of EVERY client, held-out ones included, not above
           ``guard_factor`` times the budget (the global rule for the plain candidate, the regional rule for the calibrated one). Among qualifiers the
           plain candidate wins over the calibrated one, then the higher recall. If none qualifies the choice is the old daily pipeline.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from qc.calibration import check_budget, check_budget_regional
from qc.evaluate import evaluate_component, score_store, summary_row
from qc.extremes import find_extremes
from qc.fusion import FusionFit, fit_fusion, load_features
from qc.fusion_eval import holdout_years
from qc.prepare import Prepared
from qc.runs import git_commit, write_json
from qc.scoring import ScoreStore
from qc.testscore import run_root

VARIANTS = ("boosted", "logistic")
OLD_DAILY = ("fusion_logistic", "fusion_boosted")
LABEL = "SYNTHETIC faults, held-out threshold years of the validation benchmark only"


def base_names(prefix: str) -> Tuple[str, str]:
    return ("rules", f"{prefix}_fault")


def models_dir(p: Prepared) -> Path:
    return run_root(p) / "fusion" / "models_stnet"


def choice_path(p: Prepared) -> Path:
    return run_root(p) / "stnet" / "stnet_choice.json"


def fused(variant: str, seed: int, calibrated: bool = False) -> str:
    return f"stfuse_{variant}{'_cal' if calibrated else ''}_s{seed}"


# ---------------------------------------------------------------------------------------------- frozen fusion

def fit_candidate(p: Prepared, seed: int, prefix: str = "stnet", store: Optional[ScoreStore] = None) -> FusionFit:
    """Fit and save the fusion of the rules and the STNet fault head. Uses fusion-fit years of the benchmark and clean threshold years only."""
    store = store or score_store(p)
    fit = fit_fusion(p, seed, store, base=base_names(prefix))
    fit.save(models_dir(p))
    return fit


def load_candidate(p: Prepared, seed: int) -> FusionFit:
    return FusionFit.load(models_dir(p), seed)


def apply_candidate(p: Prepared, fit: FusionFit, splits: Sequence[str], store: Optional[ScoreStore] = None, overwrite: bool = False,
                    variants: Sequence[str] = VARIANTS) -> None:
    """Store the fused score of every benchmark year of ``splits`` and of the clean threshold years under ``stfuse_<variant>_s<seed>`` (a name that
    cannot collide with the daily fusion)."""
    store = store or score_store(p)
    jobs = [(s, y) for s in splits for y in p.split.years[s]] + [("clean", y) for y in p.split.years["threshold"]]
    for tag, year in jobs:
        todo = [v for v in variants if overwrite or not store.has(fused(v, fit.seed), tag, year)]
        if not todo:
            continue
        feats = load_features(store, fit.names, tag, year)
        for v in todo:
            store.save(fused(v, fit.seed), tag, year, fit.score(v, feats, p.cell_client))


# ---------------------------------------------------------------------------------------------- regional calibration

def tables_path(p: Prepared, seed: int, variant: str) -> Path:
    return models_dir(p) / f"regional_tables_{variant}_s{seed}.npz"


def build_tables(p: Prepared, name: str, store: Optional[ScoreStore] = None) -> Dict[int, np.ndarray]:
    """Per client, the sorted clean scores of ITS cells in the threshold years (protected and ambiguous extremes left out). No labels."""
    store = store or score_store(p)
    parts: Dict[int, List[np.ndarray]] = {}
    for y in p.split.years["threshold"]:
        s = store.load(name, "clean", y)
        ex = find_extremes(p.store.year(y), p.stats.heavy_mm, p.grid, int(p.cfg.extremes.min_cells))
        ok = np.isfinite(s) & ~ex.protected & ~ex.ambiguous
        for c in np.unique(p.cell_client):
            m = ok & (p.cell_client == c)[None, :]
            if m.any():
                parts.setdefault(int(c), []).append(s[m])
    return {c: np.sort(np.concatenate(v)).astype(np.float32) for c, v in parts.items()}


def save_tables(path: Path, tables: Dict[int, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **{f"c{c}": v for c, v in tables.items()})


def load_tables(path: Path) -> Dict[int, np.ndarray]:
    z = np.load(path)
    return {int(k[1:]): z[k] for k in z.files}


def calibrate_scores(s: np.ndarray, cell_client: np.ndarray, tables: Dict[int, np.ndarray]) -> np.ndarray:
    """(T, n) fused scores -> -log10(1 - F_client(score)); NaN where the score is NaN or the client has no table. Monotone within a client."""
    out = np.full(s.shape, np.nan, np.float32)
    for c, ref in tables.items():
        sel = cell_client == c
        if not sel.any():
            continue
        x = s[:, sel]
        f = np.searchsorted(ref, np.nan_to_num(x, nan=-np.inf), side="right") / ref.size
        lvl = -np.log10(np.maximum(1.0 - f, 0.5 / ref.size))
        out[:, sel] = np.where(np.isfinite(x), lvl, np.nan)
    return out


def apply_calibration(p: Prepared, seed: int, splits: Sequence[str], store: Optional[ScoreStore] = None, overwrite: bool = False,
                      variants: Sequence[str] = VARIANTS) -> None:
    """Store ``stfuse_<variant>_cal_s<seed>`` for the benchmark years of ``splits`` and the clean threshold years, from the frozen tables."""
    store = store or score_store(p)
    jobs = [(s, y) for s in splits for y in p.split.years[s]] + [("clean", y) for y in p.split.years["threshold"]]
    for v in variants:
        tables = load_tables(tables_path(p, seed, v))
        for tag, year in jobs:
            if not overwrite and store.has(fused(v, seed, True), tag, year):
                continue
            store.save(fused(v, seed, True), tag, year, calibrate_scores(store.load(fused(v, seed), tag, year), p.cell_client, tables))


def prepare_validation(p: Prepared, seed: int, prefix: str = "stnet", store: Optional[ScoreStore] = None) -> Dict:
    """Fit and freeze the fusion, build the regional tables, and store every candidate score for the validation and clean years. A frozen fit is
    never refitted: delete ``<run>/fusion/models_stnet`` to start over."""
    store = store or score_store(p)
    want = ["rules", f"{prefix}_fault_s{seed}"]
    if (models_dir(p) / f"logistic_s{seed}.json").is_file():
        fit = load_candidate(p, seed)
        if fit.names != want:
            raise RuntimeError(f"the frozen fusion in {models_dir(p)} was fitted on {fit.names}, not on {want}; delete that folder to start over")
    else:
        fit = fit_candidate(p, seed, prefix, store)
    apply_candidate(p, fit, ("val",), store)
    for v in VARIANTS:
        if not tables_path(p, seed, v).is_file():
            save_tables(tables_path(p, seed, v), build_tables(p, fused(v, seed), store))
    apply_calibration(p, seed, ("val",), store)
    return {"names": fit.names, "fit_years": fit.fit_years, "n_rows": fit.n_rows, "n_positive": fit.n_positive}


# ---------------------------------------------------------------------------------------------- the selection rule

def choose(rows: Dict[str, Dict], guards: Dict[str, Optional[float]], ref_name: str, final_budget: float = 1.0, min_recall_gain: float = 0.02,
           guard_factor: float = 2.0) -> Dict:
    """Pure decision. ``rows[name]`` holds recall, false_per_1000, protected_flagged and the flags ``calibrated`` for candidates; ``ref_name`` is the
    best old daily fusion in ``rows``; ``guards[name]`` is the worst client's out-of-sample false alerts per 1,000 (None = not computable)."""
    ref = rows[ref_name]
    val = lambda r, k, d=0.0: d if r.get(k) is None else float(r[k])
    checks: Dict[str, Dict[str, bool]] = {}
    qual: List[str] = []
    for name, r in rows.items():
        if name == ref_name or "candidate" not in r:
            continue
        g = guards.get(name)
        c = {"recall_gain": val(r, "recall", -1.0) >= val(ref, "recall") + min_recall_gain - 1e-12,
             "false_within_budget": val(r, "false_per_1000", 1e9) <= final_budget + 1e-12,
             "protected_not_higher": val(r, "protected_flagged", 1e9) <= val(ref, "protected_flagged") + 1e-12,
             "every_client_guard": g is not None and g <= guard_factor * final_budget + 1e-12}
        checks[name] = c
        if all(c.values()):
            qual.append(name)
    rule = {"final_budget": final_budget, "min_recall_gain": min_recall_gain, "guard_factor": guard_factor}
    if not qual:
        return {"chosen": {"architecture": "daily_only", "component": ref_name}, "checks": checks, "rule": rule,
                "reason": "no STNet candidate passed every check: the old daily pipeline stays"}
    qual.sort(key=lambda n: (bool(rows[n]["calibrated"]), -val(rows[n], "recall")))
    n = qual[0]
    return {"chosen": {"architecture": "stnet", "component": n, "variant": rows[n]["variant"], "calibrated": bool(rows[n]["calibrated"])},
            "checks": checks, "qualifying": qual, "rule": rule,
            "reason": f"{n}: recall {val(rows[n], 'recall'):.3f} against {val(ref, 'recall'):.3f} for {ref_name}"}


def worst_client(rows: Sequence[Dict]) -> Optional[float]:
    rates = [r["false_per_1000"] for r in rows if r.get("false_per_1000") is not None]
    return float(max(rates)) if rates else None


def decide(p: Prepared, seed: int, prefix: str = "stnet", final_budget: float = 1.0, min_recall_gain: float = 0.02, guard_factor: float = 2.0,
           baselines: Optional[Sequence[str]] = None, store: Optional[ScoreStore] = None, n_boot: int = 200) -> Dict:
    """Evaluate the candidates and the old daily fusions on the held-out threshold years of the validation benchmark, apply ``choose`` and write the
    result ONCE to ``stnet_choice.json``. No test or stress year is read."""
    cp = choice_path(p)
    if cp.is_file():
        raise RuntimeError(f"{cp} already exists: the choice is made once and frozen before any test year is scored. Delete it only if starting the "
                           "whole evaluation over, and say so in the protocol.")
    store = store or score_store(p)
    years = holdout_years(p)
    first = p.split.years["val"][0]
    base = [n for n in (baselines or tuple(f"{b}_s{seed}" for b in OLD_DAILY)) if store.has(n, "val", first)]
    if not base:
        raise RuntimeError("no old daily fusion scores found for validation: run phase 1 (fusion) first, or pass baselines")
    row = lambda comp: summary_row(evaluate_component(p, comp, "val", [final_budget], ("seen",), store, True, years), "seen", final_budget)
    rows: Dict[str, Dict] = {n: row(n) for n in base}
    ref_name = max(base, key=lambda n: -1.0 if rows[n]["recall"] is None else rows[n]["recall"])
    guards: Dict[str, Optional[float]] = {}
    for v in VARIANTS:
        plain = fused(v, seed)
        glob = [r for r in check_budget(p, plain, final_budget, store, n_boot) if r["rule"] == "global"]
        reg = check_budget_regional(p, plain, final_budget, store, n_boot)
        for cal, rws in ((False, glob), (True, reg)):
            name = fused(v, seed, cal)
            rows[name] = {**row(name), "candidate": True, "variant": v, "calibrated": cal}
            guards[name] = worst_client(rws)
    doc = choose(rows, guards, ref_name, final_budget, min_recall_gain, guard_factor)
    doc.update({"label": LABEL, "prefix": prefix, "seed": seed, "reference": ref_name, "rows": rows, "client_guard_worst_false_per_1000": guards,
                "evaluation_years": list(years), "commit": git_commit(), "chosen_on": datetime.date.today().isoformat(),
                "fusion_models": str(models_dir(p))})
    write_json(cp, doc)
    return doc


def format_choice(doc: Dict) -> str:
    f = lambda v: "n/a" if v is None else f"{v:.3f}"
    o = [f"STNet selection ({doc['label']}); reference: {doc['reference']}", "",
         f"{'score':<34} {'recall':>7} {'event':>7} {'false':>7} {'prot':>7} {'worst client':>13}  checks"]
    for n, r in doc["rows"].items():
        g = doc["client_guard_worst_false_per_1000"].get(n)
        ch = doc["checks"].get(n)
        o.append(f"{n:<34} {f(r['recall']):>7} {f(r['event_recall']):>7} {f(r['false_per_1000']):>7} {f(r['protected_flagged']):>7} "
                 f"{f(g):>13}  " + ("-" if ch is None else ("PASS" if all(ch.values()) else "fail: " + ", ".join(k for k, v in ch.items() if not v))))
    o += ["", f"CHOICE: {doc['chosen']}", doc["reason"]]
    return "\n".join(o)
