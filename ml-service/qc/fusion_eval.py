"""Gate 5: validation curves, calibration, the fusion comparison table, and the logged choice of the two budgets.

Everything here reads validation data only. Components are compared on the *threshold years* of the
validation benchmark (``years.threshold``, default 2016-2017): the fusion was not fitted on them, and the
false-alarm thresholds come from the clean versions of the same years.

``set_budgets`` is the only place a budget becomes final. It refuses to run if any test or stress year has
already been scored, writes ``fusion_budgets.json`` and logs the choice in ``docs/qc-evaluation-protocol.md``.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from qc import paths
from qc.benchmark import check_benchmark
from qc.evaluate import evaluate_component, group_cells, load_years, score_store, thresholds_for
from qc.fusion import FusionFit, VARIANTS, fused_name, load_features
from qc.metrics import calibration
from qc.prepare import Prepared
from qc.runs import git_commit, read_json, write_json
from qc.scoring import ScoreStore

PROTOCOL = Path(__file__).resolve().parents[2] / "docs" / "qc-evaluation-protocol.md"


def holdout_years(p: Prepared) -> List[int]:
    return list(p.split.years["threshold"])


def curve_grid(p: Prepared) -> List[float]:
    return [float(b) for b in p.cfg.fusion.curve_budgets]


def validation_curves(p: Prepared, names: Sequence[str], store: Optional[ScoreStore] = None,
                      grid: Optional[Sequence[float]] = None) -> Dict:
    """For each score: at every false-alarm budget, the share of fault cell-days flagged and the share of
    protected-extreme cell-days flagged. Thresholds come from clean threshold years (training-client cells)."""
    store, grid = store or score_store(p), list(grid or curve_grid(p))
    cells = group_cells(p, "seen")
    out: Dict = {"label_tier": "synthetic faults", "years": holdout_years(p), "budgets": grid, "scores": {}}
    for name in names:
        thr = thresholds_for(p, name, grid, store)
        faults, prot, clean = [], [], []
        for y in load_years(p, name, "val", holdout_years(p), store):
            sc, b = y.score, y.bench
            ok = np.isfinite(sc) & cells[None, :]
            lab = b.faults.labels()
            faults.append(sc[ok & lab])
            prot.append(sc[ok & b.extremes.protected])
            clean.append(sc[ok & ~lab & ~b.extremes.protected & ~b.extremes.ambiguous])
        f, pr, c = np.concatenate(faults), np.concatenate(prot), np.concatenate(clean)
        rows = []
        for b in grid:
            t = thr[float(b)]
            rows.append({"budget": b, "threshold": t,
                         "fault_recall": float((f > t).mean()) if f.size else None,
                         "protected_flagged": float((pr > t).mean()) if pr.size else None,
                         "false_per_1000_in_benchmark": float(1000.0 * (c > t).mean()) if c.size else None})
        out["scores"][name] = rows
    return out


def plot_curves(curves: Dict, path: Path, title: str = "Validation: recall against false-alarm budget") -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    for name, rows in curves["scores"].items():
        b = [r["budget"] for r in rows]
        ax[0].plot(b, [r["fault_recall"] for r in rows], marker="o", ms=3, label=name)
        ax[1].plot(b, [r["protected_flagged"] for r in rows], marker="o", ms=3, label=name)
    for a, t in zip(ax, ("share of fault cell-days flagged", "share of protected-extreme cell-days flagged")):
        a.set_xscale("log"); a.set_xlabel("false alerts per 1,000 clean cell-days (budget)"); a.set_ylabel(t); a.grid(alpha=0.3)
    ax[0].set_title(title, fontsize=10); ax[1].set_title("Protected extremes (plausible, unverified)", fontsize=10)
    ax[0].legend(fontsize=7)
    fig.text(0.01, 0.01, f"synthetic faults; years {curves['years'][0]}-{curves['years'][-1]}; not real QC labels", fontsize=7)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def calibration_report(p: Prepared, fit: FusionFit, store: Optional[ScoreStore] = None) -> Dict:
    """Reliability table of the shared logistic fusion on the held-out validation years (threshold years)."""
    store = store or score_store(p)
    cells = group_cells(p, "seen")
    probs, labs = [], []
    for y in load_years(p, fused_name("logistic", fit.seed, fit.source), "val", holdout_years(p), store):
        sc = y.score
        ok = np.isfinite(sc) & cells[None, :] & ~y.bench.extremes.ambiguous
        probs.append(1.0 / (1.0 + np.exp(-sc[ok].astype(np.float64))))
        labs.append(y.bench.faults.labels()[ok])
    return calibration(np.concatenate(probs), np.concatenate(labs))


def comparison(p: Prepared, names: Sequence[str], budgets: Sequence[float], store: Optional[ScoreStore] = None) -> Dict:
    """Full metrics (qc.evaluate) for each score on the held-out validation years."""
    store = store or score_store(p)
    return {n: evaluate_component(p, n, "val", budgets, ("seen",), store, True, holdout_years(p)) for n in names}


def untrained_and_trained_names(seed: int, source: str = "central", prox_mu: float = 0.0) -> List[str]:
    from qc.fusion import component_names
    c = component_names(seed, ("rules", "slow", "spatial", "temporal"), source, prox_mu)
    return [c[0], c[1], "neighbour_baseline", c[2], c[3]] + ([f"plain_gru_s{seed}"] if source == "central" else [])


def run_fusion_validation(p: Prepared, fit: FusionFit, out_dir: Path, store: Optional[ScoreStore] = None) -> Dict:
    """Curves, plot, calibration and the comparison table, written into ``out_dir``."""
    store = store or score_store(p)
    names = (untrained_and_trained_names(fit.seed, fit.source, float(p.cfg.federated.prox_mu))
             + [fused_name(v, fit.seed, fit.source) for v in VARIANTS + ("logistic_fed",)])
    names = [n for n in names if store.has(n, "val", holdout_years(p)[0])]
    curves = validation_curves(p, names, store)
    write_json(out_dir / f"curves{fit.tag}_s{fit.seed}.json", curves)
    plot_curves(curves, out_dir / f"curves{fit.tag}_s{fit.seed}.png")
    cal = calibration_report(p, fit, store)
    write_json(out_dir / f"calibration{fit.tag}_s{fit.seed}.json", cal)
    table = comparison(p, names, [float(b) for b in p.cfg.evaluation.budgets], store)
    write_json(out_dir / f"comparison{fit.tag}_s{fit.seed}.json", table)
    write_json(out_dir / f"fusion_weights{fit.tag}_s{fit.seed}.json",
               {"names": fit.names, "standardizer_mu": fit.mu, "standardizer_sd": fit.sd,
                "logistic": {"coef": fit.logistic["coef"], "intercept": fit.logistic["intercept"]},
                "fit_years": fit.fit_years, "fit_rows": fit.n_rows, "fit_positive_rows": fit.n_positive})
    return {"curves": curves, "calibration": cal, "comparison": table}


# ---------------------------------------------------------------------------------------------- the two budgets

def scored_after_validation(p: Prepared, store: Optional[ScoreStore] = None) -> List[str]:
    """Score files of test or stress years in the score store. Must be empty when the budgets are fixed."""
    store = store or score_store(p)
    return sorted(str(f.relative_to(store.root)) for pat in ("test_*.npy", "stress_*.npy") for f in store.root.glob(f"*/{pat}"))


def budgets_path(p: Prepared) -> Path:
    return paths.out_dir(p.cfg) / str(p.cfg.name) / "fusion_budgets.json"


def load_budgets(p: Prepared) -> Dict:
    """The fixed budgets. Raises if they have not been chosen: test scoring must not start without them."""
    path = budgets_path(p)
    if not path.is_file():
        raise RuntimeError(f"the fusion budgets are not fixed ({path} missing). Look at the validation curves, then run "
                           "`python -m qc set-budgets --final X --review Y` before any test-year scoring.")
    return read_json(path)


def set_budgets(p: Prepared, final: float, review: float, curves_file: Path, protocol: Path = PROTOCOL,
                store: Optional[ScoreStore] = None, today: Optional[str] = None, component: Optional[str] = None) -> Dict:
    """Fix the final-flag and review-flag budgets (false alerts per 1,000 clean cell-days) and log them in the protocol.
    ``component`` names the fused score the budgets apply to (the chosen architecture); it is recorded in the budgets file and the log."""
    if not 0 < final < review:
        raise ValueError("the final-flag budget must be positive and smaller than the review-flag budget")
    late = scored_after_validation(p, store)
    if late:
        raise RuntimeError(f"budgets must be fixed before any test or stress year is scored, but scores exist: {late[:3]}")
    if budgets_path(p).is_file():
        raise RuntimeError(f"{budgets_path(p)} already exists: the budgets are fixed and must not be changed. "
                           "Delete it only if you are starting the whole evaluation over, and say so in the protocol.")
    if not Path(curves_file).is_file():
        raise RuntimeError(f"no validation curves at {curves_file}; the budgets must be chosen from them")
    today = today or datetime.date.today().isoformat()
    doc = {"final_per_1000": float(final), "review_per_1000": float(review), "chosen": today,
           "commit": git_commit(), "curves_file": str(curves_file),
           "curves_sha256": hashlib.sha256(Path(curves_file).read_bytes()).hexdigest()[:16],
           "benchmark_hash": check_benchmark(p, require_pinned=False)["hash"], "split_manifest_hash": p.manifest["hash"],
           "no_test_scores_at_choice": True}
    if component:
        doc["applies_to"] = component
    write_json(budgets_path(p), doc)
    _log_in_protocol(protocol, doc)
    return doc


def _log_in_protocol(path: Path, doc: Dict) -> None:
    text = path.read_text(encoding="utf-8")
    row = (f"| {doc['chosen']} | {doc['final_per_1000']:g} / {doc['review_per_1000']:g} | "
           f"{doc['commit'][:12]} (curves {doc['curves_sha256']}"
           + (f"; applies to {doc['applies_to']}" if doc.get("applies_to") else "")
           + ") | yes: no test or stress score files existed |")
    lines = text.splitlines()
    blank = next((i for i, l in enumerate(lines) if l.strip() == "| | | | |"), None)
    if blank is not None:
        lines[blank] = row
    else:
        head = next(i for i, l in enumerate(lines) if l.startswith("| date |"))
        end = head
        while end + 1 < len(lines) and lines[end + 1].startswith("|"):
            end += 1
        lines.insert(end + 1, row)
    text = chr(10).join(lines) + chr(10)
    text = re.sub(r"^\*\*Status \(.*?\):.*$", f"**Status ({doc['chosen']}): fixed.** Final flag {doc['final_per_1000']:g}, review flag "
                  f"{doc['review_per_1000']:g} false alerts per 1,000 clean cell-days. Logged below; do not change.", text, count=1, flags=re.M)
    path.write_text(text, encoding="utf-8")
