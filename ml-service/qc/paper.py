"""Gate 9: paper tables, figures and the claim check, all computed from saved outputs of earlier gates.

Nothing here trains, scores or draws a random number. Tables read ``test/metrics_<split>.json`` and
``test/test_report.json`` (written by the single test-scoring pass); figures read the same files, the validation
curves, the frozen benchmark and the client map. A table or figure whose input does not exist is reported as
NOT RUN, with what is missing; it is never filled in.

Claims (spec section 13) are each tied to one table and checked against it by ``check_claims``. The bars used by the
check (``BARS``) are fixed here, in plain sight, and are printed with every verdict.
"""

from __future__ import annotations

import csv
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from qc.runs import read_json, write_json
from qc.testscore import _stat, base_name

SINGLE = ("rules", "slow", "neighbour_baseline", "spatial", "temporal", "plain_gru")
FUSIONS = ("fusion_logistic", "fusion_mean", "fusion_or", "fusion_boosted", "fusion_per_client", "fusion_logistic_fed")
FED_VARIANTS = ("fedpers", "fedavg", "fedft", "local")
FED_COMPONENTS = ("spatial", "temporal")
KERALA_BBOX = (8.2, 12.8, 74.8, 77.4)            # lat_min, lat_max, lon_min, lon_max: a rough box, not a boundary
BARS = {
    # The check's own bars, set before any result existed. They are judgement calls, printed with every verdict.
    "protected_flagged_max": 0.10,               # at most this share of protected-extreme cell-days may be flagged
    "federated_recall_gap": 0.05,                # personalized federated recall may trail centralized by at most this
}
LABEL_NOTE = {"synthetic faults": "Synthetic faults: recall is the share of injected-fault cell-days flagged. "
              "No real labels exist for RF25."}


# ---------------------------------------------------------------------------------------------- loading

@dataclass
class Run:
    report: Dict
    metrics: Dict[str, Dict[str, Dict]]          # split -> name_sN -> per-model metrics
    test_dir: Path

    @property
    def final(self) -> str:
        return str(float(self.report["budgets"]["final_per_1000"]))

    @property
    def review(self) -> str:
        return str(float(self.report["budgets"]["review_per_1000"]))

    def runs(self, split: str, family: str) -> List[Dict]:
        return [v for n, v in self.metrics.get(split, {}).items() if base_name(n) == family]

    def families(self, split: str) -> List[str]:
        return list(dict.fromkeys(base_name(n) for n in self.metrics.get(split, {})))


def load_run(test_dir: Path) -> Optional[Run]:
    test_dir = Path(test_dir)
    f = test_dir / "test_report.json"
    if not f.is_file():
        return None
    report = read_json(f)
    metrics = {s: read_json(test_dir / f"metrics_{s}.json") for s in report["splits"] if (test_dir / f"metrics_{s}.json").is_file()}
    return Run(report, metrics, test_dir)


def _walk(d, keys):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def metric(run: Run, split: str, family: str, group: str, budget: str, *keys) -> Optional[Dict]:
    """Mean and range over seeds of one number at one budget; None if no seed has it."""
    vals = [_walk(r, ["groups", group, "by_budget", budget, *keys]) for r in run.runs(split, family)]
    return _stat(vals)


def pr_auc(run: Run, split: str, family: str, group: str) -> Optional[Dict]:
    return _stat([_walk(r, ["groups", group, "pr_auc"]) for r in run.runs(split, family)])


def _f(s: Optional[Dict], pct: bool = False, na: str = "n/a") -> str:
    if not s:
        return na
    g = (lambda v: f"{100 * v:.1f}%") if pct else (lambda v: f"{v:.3f}")
    return g(s["mean"]) if s["n_seeds"] == 1 else f"{g(s['mean'])} [{g(s['min'])}-{g(s['max'])}]"


# ---------------------------------------------------------------------------------------------- table objects

@dataclass
class Table:
    key: str
    title: str
    columns: List[str]
    rows: List[List[str]]
    notes: List[str] = field(default_factory=list)

    def markdown(self) -> str:
        out = [f"### {self.title}", "", "| " + " | ".join(self.columns) + " |", "|" + "---|" * len(self.columns)]
        out += ["| " + " | ".join(r) + " |" for r in self.rows]
        out += [""] + [f"- {n}" for n in self.notes] + [""]
        return "\n".join(out)

    def write(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / f"{self.key}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(self.columns)
            w.writerows(self.rows)
        (out_dir / f"{self.key}.md").write_text(self.markdown(), encoding="utf-8")


def _not_run(key: str, title: str, why: str) -> Table:
    return Table(key, title, ["status"], [[f"NOT RUN: {why}"]])


def _tier(run: Run) -> str:
    return str(run.report.get("label_tier", "unknown"))


# ---------------------------------------------------------------------------------------------- tables

def main_results(run: Run, split: str = "test", family: str = "fusion_logistic") -> Table:
    """Main results per fault kind for the main fusion, seen and unseen clients, at the final budget."""
    title = f"Main results per fault kind: {family}, {split} years, final flag"
    runs = run.runs(split, family)
    if not runs:
        return _not_run("main_results", title, f"no {family} scores for {split}")
    kinds = sorted({k for r in runs for g in r["groups"].values() for k in _walk(g, ["by_budget", run.final, "by_kind"]) or {}})
    rows = []

    def add(label, keys):
        cells = [label]
        for group in ("seen", "unseen"):
            n = _walk(runs[0], ["groups", group, "by_budget", run.final, *keys, "events"])
            cells += [str(n) if n is not None else "n/a",
                      _f(metric(run, split, family, group, run.final, *keys, "recall"), True),
                      _f(metric(run, split, family, group, run.final, *keys, "event_recall"), True)]
        rows.append(cells)

    add("all faults", ["faults"])
    for k in kinds:
        add(k, ["by_kind", k])
    for s in ("seen settings", "test-only settings"):
        if any(_walk(r, ["groups", "seen", "by_budget", run.final, "by_setting", s]) for r in runs):
            add(f"setting: {s}", ["by_setting", s])
    fa = [f"{g}: {_f(metric(run, split, family, g, run.final, 'false_alerts', 'per_1000_clean'))}" for g in ("seen", "unseen")]
    return Table("main_results", title,
                 ["fault kind", "events (seen)", "recall (seen)", "event recall (seen)", "events (unseen)", "recall (unseen)", "event recall (unseen)"],
                 rows, [f"Labels: {_tier(run)}. Mean over seeds with the range in brackets.",
                        f"False alerts per 1,000 clean cell-days at this budget: {'; '.join(fa)} (budget {run.final}).",
                        LABEL_NOTE.get(_tier(run), "")])


def ablation(run: Run, split: str = "test", key: str = "ablation", title: Optional[str] = None,
             notes: Sequence[str] = ()) -> Table:
    """Every single component, every fusion variant, at the final budget."""
    title = title or f"Component ablation, {split} years, final flag"
    fams = [f for f in SINGLE + FUSIONS if run.runs(split, f)]
    if not fams:
        return _not_run(key, title, f"no scores for {split}")
    rows = []
    for fam in fams:
        rows.append([fam, _f(pr_auc(run, split, fam, "seen")), _f(metric(run, split, fam, "seen", run.final, "faults", "recall"), True),
                     _f(metric(run, split, fam, "seen", run.final, "faults", "event_recall"), True),
                     _f(metric(run, split, fam, "seen", run.final, "false_alerts", "per_1000_clean")),
                     _f(metric(run, split, fam, "unseen", run.final, "faults", "recall"), True)])
    missing = [f for f in SINGLE + FUSIONS if f not in fams]
    nt = [f"Labels: {_tier(run)}. Final false-alert budget {run.final} per 1,000 clean cell-days. Mean over seeds [range].", *notes]
    if missing:
        nt.append("Not in this table (no scores): " + ", ".join(missing))
    return Table(key, title, ["model", "PR-AUC (seen)", "recall (seen)", "event recall (seen)", "false alerts /1000 (seen)", "recall (unseen)"], rows, nt)


def federated(run: Run, split: str = "test") -> Table:
    """Centralized against each federated variant, per component, seen and unseen clients."""
    title = f"Federated variants, {split} years, final flag"
    rows, absent = [], []
    for comp in FED_COMPONENTS:
        wanted = [f"{v}_{comp}" for v in FED_VARIANTS]
        extra = [f for f in run.families(split) if f.endswith("_" + comp) and f.split("_")[0] in FED_VARIANTS and f not in wanted]
        cands = [(f"central {comp}", comp)] + [(f.replace("_", " ", 1) if "_prox_" not in f else f.replace("_", " "), f) for f in wanted + extra]
        for lab, fam in cands:
            if not run.runs(split, fam):
                absent.append(lab)
                continue
            cells = [lab]
            for group in ("seen", "unseen"):
                if fam.startswith("local") and not metric(run, split, fam, group, run.final, "faults", "recall"):
                    cells += ["NOT AVAILABLE", "NOT AVAILABLE", "NOT AVAILABLE"]
                    continue
                cells += [_f(pr_auc(run, split, fam, group)), _f(metric(run, split, fam, group, run.final, "faults", "recall"), True),
                          _f(metric(run, split, fam, group, run.final, "false_alerts", "per_1000_clean"))]
            rows.append(cells)
    for lab, fam in (("fusion of central components", "fusion_logistic"), ("fusion of federated-averaged logistic", "fusion_logistic_fed")):
        if run.runs(split, fam):
            rows.append([lab] + [x for g in ("seen", "unseen") for x in (_f(pr_auc(run, split, fam, g)),
                                 _f(metric(run, split, fam, g, run.final, "faults", "recall"), True),
                                 _f(metric(run, split, fam, g, run.final, "false_alerts", "per_1000_clean")))])
    if not rows:
        return _not_run("federated", title, f"no federated or central scores for {split}")
    notes = [f"Labels: {_tier(run)}. Federation is simulated on one machine: this is a comparison of training schemes, not a privacy result.",
             "Unseen clients never contributed a gradient. 'local' has no model for them and is NOT AVAILABLE there.",
             "Fusion over federated components was NOT RUN (see the not-run list in the test report)."]
    if absent:
        notes.append("NOT RUN: " + ", ".join(absent))
    hdr = ["model"] + [f"{m} ({g})" for g in ("seen", "unseen") for m in ("PR-AUC", "recall", "false alerts /1000")]
    return Table("federated", title, hdr, rows, notes)


def protected_extremes(run: Run, split: str = "test") -> List[Table]:
    """False removals of the plausible-but-unverified heavy rainfall: share of protected cell-days flagged."""
    title = f"Protected extremes flagged, {split} years"
    fams = [f for f in SINGLE + FUSIONS if run.runs(split, f)]
    if not fams:
        return [_not_run("protected_extremes", title, f"no scores for {split}")]
    rows = []
    for fam in fams:
        cells = [fam]
        for b in (run.final, run.review):
            for g in ("seen", "unseen"):
                cells.append(_f(metric(run, split, fam, g, b, "protected_extremes", "flagged_share_of_cell_days"), True))
        cells.append(_f(metric(run, split, fam, "seen", run.final, "ambiguous_extremes", "flagged_share"), True))
        rows.append(cells)
    t1 = Table("protected_extremes", title,
               ["model", "final, seen", "final, unseen", "review, seen", "review, unseen", "ambiguous, final, seen"], rows,
               ["Protected extremes are large, spatially coherent heavy-rain events kept out of the fault set. They are "
                "PLAUSIBLE BUT UNVERIFIED: a flagged share is a false-removal rate only if they are genuine.",
                f"Share of protected-extreme cell-days above the threshold. Bar used by the claim check: at most {BARS['protected_flagged_max']:.0%}.",
                "Ambiguous extremes are listed separately and are neither faults nor clean."])
    main = "fusion_logistic"
    out = [t1]
    if run.runs(split, main):
        rows2 = []
        for dim in ("client", "season", "size"):
            keys = sorted({k for r in run.runs(split, main) for k in (_walk(r, ["groups", "seen", "by_budget", run.final, "protected_extremes",
                                                                                  "cell_days_flagged_by", dim]) or {})})
            for k in keys:
                rows2.append([dim, k] + [_f(metric(run, split, main, g, run.final, "protected_extremes", "cell_days_flagged_by", dim, k, "flagged_share"), True)
                                         for g in ("seen", "unseen")])
        out.append(Table("protected_extremes_breakdown", f"Protected extremes flagged by {main}, by client, season and size",
                         ["dimension", "group", "seen", "unseen"], rows2,
                         ["Same labelling caveat. Empty cells mean no protected cell-days in that group."]))
    return out


def uk_table(run: Run, caveats: Sequence[str], split: str = "test") -> Table:
    return ablation(run, split, key="uk_study", title=f"UK MIDAS real-label study (separate study, never pooled with India), {split} years",
                    notes=["CAVEATS (printed with every UK number):"] + [f"  {c}" for c in caveats])


def build_tables(run: Optional[Run], uk_caveats: Optional[Sequence[str]] = None) -> List[Table]:
    if run is None:
        return [_not_run(k, k, "no test_report.json: the test-scoring pass has not been run")
                for k in ("main_results", "ablation", "federated", "protected_extremes")]
    if uk_caveats is not None:
        return [uk_table(run, uk_caveats)]
    return [main_results(run), ablation(run), federated(run)] + protected_extremes(run)


# ---------------------------------------------------------------------------------------------- claims

@dataclass
class Claim:
    key: str
    text: str
    table: str
    status: str
    evidence: List[str]

    def markdown(self) -> str:
        return "\n".join([f"### {self.text}", "", f"Table: {self.table}. **{self.status}**", ""] + [f"- {e}" for e in self.evidence] + [""])


def _mean(s: Optional[Dict]) -> Optional[float]:
    return None if not s else s["mean"]


def claim_combined(run: Run, split: str = "test") -> Claim:
    text, tab = "Combined components beat any single component", "ablation"
    fusion = "fusion_logistic"
    missing = [f for f in (fusion,) + SINGLE if not run.runs(split, f)]
    if missing:
        return Claim("combined", text, tab, "CANNOT CHECK", [f"no scores for: {', '.join(missing)}"])
    rec = {f: metric(run, split, f, "seen", run.final, "faults", "recall") for f in (fusion,) + SINGLE}
    pr = {f: pr_auc(run, split, f, "seen") for f in (fusion,) + SINGLE}
    ok_rec = {f: _mean(rec[f]) for f in rec if _mean(rec[f]) is not None}
    ok_pr = {f: _mean(pr[f]) for f in pr if _mean(pr[f]) is not None}
    if fusion not in ok_rec or fusion not in ok_pr or len(ok_rec) < 2:
        return Claim("combined", text, tab, "CANNOT CHECK", ["a needed number is undefined (no clean or fault cell-days)"])
    best_r = max((f for f in ok_rec if f != fusion), key=ok_rec.get)
    best_p = max((f for f in ok_pr if f != fusion), key=ok_pr.get)
    gain_r, gain_p = ok_rec[fusion] - ok_rec[best_r], ok_pr[fusion] - ok_pr[best_p]
    multi = rec[fusion]["n_seeds"] > 1
    separate = (not multi) or (rec[fusion]["min"] > rec[best_r]["max"] and pr[fusion]["min"] > pr[best_p]["max"])
    ev = [f"recall at the final budget: {fusion} {_f(rec[fusion], True)} against best single {best_r} {_f(rec[best_r], True)}",
          f"PR-AUC: {fusion} {_f(pr[fusion])} against best single {best_p} {_f(pr[best_p])}",
          f"false alerts per 1,000 clean cell-days for {fusion}: {_f(metric(run, split, fusion, 'seen', run.final, 'false_alerts', 'per_1000_clean'))} (budget {run.final})",
          f"seed ranges {'separate' if separate and multi else 'overlap' if multi else 'not available (one seed)'}",
          "Seen clients, synthetic faults. This is a claim about synthetic faults only."]
    if gain_r > 0 and gain_p > 0 and separate:
        status = "SUPPORTED" if multi else "SUPPORTED (one seed: no spread to judge)"
    elif gain_r > 0 or gain_p > 0:
        status = "MIXED"
    else:
        status = "NOT SUPPORTED"
    return Claim("combined", text, tab, status, ev)


def claim_protected(run: Run, split: str = "test") -> Claim:
    text, tab = "Protected extremes are kept", "protected_extremes"
    fam = "fusion_logistic"
    if not run.runs(split, fam):
        return Claim("protected", text, tab, "CANNOT CHECK", [f"no {fam} scores for {split}"])
    bar = BARS["protected_flagged_max"]
    got = {g: metric(run, split, fam, g, run.final, "protected_extremes", "flagged_share_of_cell_days") for g in ("seen", "unseen")}
    vals = {g: _mean(s) for g, s in got.items() if _mean(s) is not None}
    if not vals:
        return Claim("protected", text, tab, "CANNOT CHECK", ["no protected-extreme cell-days were scored"])
    ev = [f"{fam} flags {_f(got[g], True)} of protected cell-days on {g} clients at the final budget (bar: at most {bar:.0%})" for g in vals]
    ev += ["Protected extremes are plausible but UNVERIFIED; the bar is this check's own and was set before the results.",
           "Worst case across seeds: " + ", ".join(f"{g} {100 * got[g]['max']:.1f}%" for g in vals)]
    return Claim("protected", text, tab, "SUPPORTED" if all(v <= bar for v in vals.values()) and all(got[g]["max"] <= bar for g in vals)
                 else "NOT SUPPORTED", ev)


def claim_federated(run: Run, split: str = "test") -> Claim:
    text, tab = "The personalized federated variant holds up against centralized training, including on unseen regions", "federated"
    gap = BARS["federated_recall_gap"]
    verdicts, ev = [], []
    for comp in FED_COMPONENTS:
        fam = f"fedpers_{comp}"
        if not run.runs(split, fam) or not run.runs(split, comp):
            ev.append(f"{comp}: NOT RUN (needs both central {comp} and {fam})")
            continue
        for g in ("seen", "unseen"):
            c, f_ = metric(run, split, comp, g, run.final, "faults", "recall"), metric(run, split, fam, g, run.final, "faults", "recall")
            if _mean(c) is None or _mean(f_) is None:
                ev.append(f"{comp}, {g}: recall undefined")
                continue
            ok = _mean(f_) >= _mean(c) - gap
            verdicts.append(ok)
            ev.append(f"{comp}, {g} clients: fedpers {_f(f_, True)} against central {_f(c, True)} "
                      f"({'within' if ok else 'more than'} {gap:.0%} of central)")
    ev += ["Federation is simulated; this says nothing about privacy.", f"Bar: recall no more than {gap:.0%} (absolute) below centralized; this check's own."]
    if not verdicts:
        return Claim("federated", text, tab, "CANNOT CHECK", ev)
    return Claim("federated", text, tab, "SUPPORTED" if all(verdicts) else ("MIXED" if any(verdicts) else "NOT SUPPORTED"), ev)


def check_claims(run: Optional[Run], split: str = "test") -> List[Claim]:
    if run is None:
        return [Claim(k, t, tab, "CANNOT CHECK", ["no test_report.json: the test-scoring pass has not been run"])
                for k, t, tab in (("combined", "Combined components beat any single component", "ablation"),
                                  ("protected", "Protected extremes are kept", "protected_extremes"),
                                  ("federated", "The personalized federated variant holds up against centralized training, including on unseen regions", "federated"))]
    return [claim_combined(run, split), claim_protected(run, split), claim_federated(run, split)]


def claims_markdown(claims: Sequence[Claim]) -> str:
    head = ["# Claim check", "",
            "Each claim is checked against one table. A claim is made only if its table supports it; anything else is "
            "dropped or reworded. Bars: " + "; ".join(f"{k} = {v}" for k, v in BARS.items()) + ".", ""]
    return "\n".join(head + [c.markdown() for c in claims])


# ---------------------------------------------------------------------------------------------- figures

Result = Tuple[Optional[Path], Optional[str]]


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    _plt().close(fig)
    return path


def fig_client_map(p, out: Path) -> Result:
    from qc.splits import BUFFER, HELDOUT

    plt = _plt()
    lat, lon = p.grid.lat[p.grid.rows], p.grid.lon[p.grid.cols]
    fig, ax = plt.subplots(figsize=(5.5, 6))
    sc = ax.scatter(lon, lat, c=p.cell_client, cmap="tab10", s=6, marker="s")
    roles = np.asarray(p.cell_role)
    for role, mk, lab in ((HELDOUT, "x", "held-out (unseen) cells"), (BUFFER, ".", "buffer cells (unused in training)")):
        m = roles == role
        if m.any():
            ax.scatter(lon[m], lat[m], c="k", s=7 if mk == "x" else 3, marker=mk, label=lab)
    for c in np.unique(p.cell_client):
        m = p.cell_client == c
        ax.text(lon[m].mean(), lat[m].mean(), str(int(c)), ha="center", va="center", fontsize=11, weight="bold",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", alpha=0.8, lw=0))
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude"); ax.legend(fontsize=7, loc="lower right")
    ax.set_title(f"Client map: {int(p.cell_client.max())} clients, held-out {sorted(p.split.heldout)}", fontsize=10)
    return _save(fig, out / "fig_client_map.png"), None


def fig_example_faults(p, out: Path, split: str = "val", window: int = 12) -> Result:
    from qc.benchmark import load_bench_year

    year = p.split.years[split][0]
    try:
        b = load_bench_year(p, split, year)
    except FileNotFoundError:
        return None, f"NOT RUN: no frozen benchmark file for {split} {year}"
    first: Dict[str, Dict] = {}
    for e in b.faults.events:
        first.setdefault(e["kind"], e)
    if not first:
        return None, "NOT RUN: the benchmark has no fault events"
    plt = _plt()
    kinds = list(first)
    cols = min(3, len(kinds))
    rows = int(np.ceil(len(kinds) / cols))
    fig, axs = plt.subplots(rows, cols, figsize=(4.2 * cols, 2.6 * rows), squeeze=False)
    bad = b.corrupted
    T = b.clean.shape[0]
    for ax, k in zip(axs.ravel(), kinds):
        e = first[k]
        a, z = max(0, e["start"] - window), min(T, e["start"] + e["duration"] + window)
        d = np.arange(a, z)
        ax.plot(d, b.clean[a:z, e["centre"]], color="tab:blue", label="original")
        ax.plot(d, bad[a:z, e["centre"]], color="tab:red", ls="--", label="with fault")
        ax.axvspan(e["start"], e["start"] + e["duration"] - 1, color="tab:red", alpha=0.1)
        ax.set_title(f"{k} (radius {e['radius']:.1f} cells)", fontsize=9); ax.set_xlabel("day of year"); ax.set_ylabel("mm/day")
    for ax in axs.ravel()[len(kinds):]:
        ax.axis("off")
    axs.ravel()[0].legend(fontsize=7)
    fig.text(0.01, 0.005, f"SYNTHETIC faults injected into {split} {year}; one example per kind at the event's centre cell", fontsize=7)
    return _save(fig, out / "fig_example_faults.png"), None


def fig_recall_budget(curves_path: Path, out: Path) -> Result:
    from qc.fusion_eval import plot_curves

    if not Path(curves_path).is_file():
        return None, f"NOT RUN: {curves_path} does not exist (run the fusion command first)"
    plot_curves(read_json(curves_path), out / "fig_recall_budget.png",
                "Recall against false-alarm budget (validation years)")
    return out / "fig_recall_budget.png", None


def fig_reliability(run: Optional[Run], out: Path) -> Result:
    cal = (run.report["splits"].get("test") or {}).get("calibration_main_fusion") if run else None
    if not cal:
        return None, "NOT RUN: no calibration in the test report (test split not scored)"
    plt = _plt()
    fig, axs = plt.subplots(1, 2, figsize=(9, 4), sharex=True, sharey=True)
    for ax, g in zip(axs, ("seen", "unseen")):
        for s, doc in cal.items():
            bins = doc[g]["bins"]
            ax.plot([b["mean_predicted"] for b in bins], [b["observed_fault_rate"] for b in bins], marker="o", ms=3,
                    label=f"seed {s} (ECE {doc[g]['expected_calibration_error']:.3f})")
        ax.plot([0, 1], [0, 1], color="grey", ls=":")
        ax.set_xscale("symlog", linthresh=1e-3); ax.set_yscale("symlog", linthresh=1e-3)
        ax.set_xlabel("mean predicted fault probability"); ax.set_title(f"{g} clients", fontsize=10); ax.legend(fontsize=7)
    axs[0].set_ylabel("observed synthetic-fault rate")
    fig.text(0.01, 0.005, "Equal-count bins; calibrated to the synthetic fault rate, which says nothing about real error probability", fontsize=7)
    return _save(fig, out / "fig_reliability.png"), None


def fig_kerala(p, run: Optional[Run], out: Path, seed: int = 0, year: int = 2018, month: int = 8,
               bbox: Tuple[float, float, float, float] = KERALA_BBOX) -> Result:
    """Rain and alerts over a box and a month. Only RF25 values and this system's alerts appear: no external
    reference figures are used, because the case-study values are unverified (spec section 15)."""
    import pandas as pd

    if year not in p.split.years.get("test", []):
        return None, f"NOT RUN: {year} is not a test year in this configuration"
    f = (run.test_dir / "alerts" / f"alerts_test_s{seed}.parquet") if run else None
    if f is None or not f.is_file():
        return None, f"NOT RUN: no alert records ({f}); the test-scoring pass has not been run"
    lat, lon = p.grid.lat[p.grid.rows], p.grid.lon[p.grid.cols]
    box = (lat >= bbox[0]) & (lat <= bbox[1]) & (lon >= bbox[2]) & (lon <= bbox[3])
    if not box.any():
        return None, f"NOT RUN: no grid cell inside the box {bbox}"
    d0 = datetime.date(year, month, 1).timetuple().tm_yday - 1
    d1 = d0 + (datetime.date(year + (month == 12), month % 12 + 1, 1) - datetime.date(year, month, 1)).days
    rain = p.store.year(year)[d0:d1][:, box]
    al = pd.read_parquet(f)
    al = al[(al["year"] == year) & al["cell"].isin(np.nonzero(box)[0]) & al["day_of_year"].between(d0, d1 - 1)]
    days = np.arange(d0, d1)
    plt = _plt()
    fig, ax = plt.subplots(2, 1, figsize=(8, 5.5), sharex=True)
    ax[0].plot(days - d0 + 1, np.nanmean(rain, axis=1), label="box mean")
    ax[0].plot(days - d0 + 1, np.nanmax(rain, axis=1), label="box maximum", alpha=0.7)
    ax[0].set_ylabel("RF25 rainfall (mm/day)"); ax[0].legend(fontsize=8)
    bottom = np.zeros(len(days))
    for lab, sel, col in (("alerts on cell-days with an injected synthetic fault", al["synthetic_fault"].to_numpy(bool), "tab:red"),
                          ("alerts on unmodified cell-days (false alerts)", ~al["synthetic_fault"].to_numpy(bool), "tab:orange")):
        cnt = np.bincount(al["day_of_year"].to_numpy()[sel] - d0, minlength=len(days)).astype(float)
        ax[1].bar(days - d0 + 1, cnt, bottom=bottom, color=col, label=lab)
        bottom += cnt
    ax[1].set_ylabel("alerts (review flag or above)"); ax[1].set_xlabel(f"day of {datetime.date(year, month, 1):%B %Y}"); ax[1].legend(fontsize=8)
    fig.suptitle(f"Case study {datetime.date(year, month, 1):%B %Y}, box lat {bbox[0]}-{bbox[1]}, lon {bbox[2]}-{bbox[3]}", fontsize=10)
    fig.text(0.01, 0.005, "Event values from outside RF25 are UNVERIFIED and are not shown. Faults here are synthetic.", fontsize=7)
    return _save(fig, out / "fig_kerala_case.png"), None


# ---------------------------------------------------------------------------------------------- driver

def build_all(p, out: Path, run: Optional[Run], curves_path: Path, uk_caveats: Optional[Sequence[str]] = None,
              seed: int = 0) -> Dict:
    """Write every table, figure and the claim check under ``out``; return and save a manifest with what was not run."""
    out = Path(out)
    tables = build_tables(run, uk_caveats)
    for t in tables:
        t.write(out / "tables")
    (out / "tables" / "all_tables.md").write_text("\n".join(t.markdown() for t in tables), encoding="utf-8")
    claims = check_claims(run) if uk_caveats is None else []
    if claims:
        (out / "claims.md").write_text(claims_markdown(claims), encoding="utf-8")
    figs = {"client_map": fig_client_map(p, out / "figures"), "example_faults": fig_example_faults(p, out / "figures"),
            "recall_budget": fig_recall_budget(curves_path, out / "figures")}
    if uk_caveats is None:
        figs["reliability"] = fig_reliability(run, out / "figures")
        figs["kerala_case"] = fig_kerala(p, run, out / "figures", seed)
    manifest = {"tables": {t.key: ("NOT RUN" if t.columns == ["status"] else "written") for t in tables},
                "claims": {c.key: c.status for c in claims},
                "figures": {k: (str(v[0]) if v[0] else v[1]) for k, v in figs.items()}}
    write_json(out / "paper_manifest.json", manifest)
    return manifest
