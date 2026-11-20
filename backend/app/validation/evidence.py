"""Build the evidence-v1 payload (docs/contracts/evidence-v1.schema.json) for one fired check on one row.

Every number carries a basis (measured, assumed, derived). The window is capped at the last 24 readings or 14 days and the whole payload
at 64 KB; a cut payload says so (``truncated``) and links to the full row record (``next``).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from backend.app.validation.models import ValidationCheckHit, ValidationResult, ValidationRun

SCHEMA = "evidence-v1"
MAX_PAYLOAD_BYTES = 64 * 1024
WINDOW_READINGS = 24
WINDOW_DAYS = 14
_COPIED = ("observed", "threshold", "window", "neighbours", "history", "tail_probability", "issue")


def limitations(run: ValidationRun, ev: Dict[str, Any]) -> List[str]:
    """What the reader must not over-read in this evidence (an idea taken from the rf pull request's per-decision limitations). Fixed sentences,
    chosen by facts of the run and the payload, never by a model."""
    out = ["The rule score is an uncalibrated ordering of suspicion, not a probability."]
    if ev.get("time_basis") == "received":
        out.append("Times are when this platform received the readings, not when they were observed, so gaps and neighbour comparisons are weaker.")
    if (ev.get("observed") or {}).get("basis") == "assumed":
        out.append("The unit of the observed value is assumed, not confirmed.")
    if run.synthetic:
        out.append("This run holds synthetic data.")
    if ev.get("kind") == "uncertain":
        out.append("This check gives UNCERTAIN, which is not a diagnosed fault: nearby gauges can differ in real rain.")
    out.append("No real labelled faults support an accuracy claim.")
    return out


def not_run_for(run: ValidationRun, station_id: str, cap: int = 8) -> List[str]:
    """The checks of this run that did NOT run for this station (or for the whole run), each with its reason."""
    items = [n for n in (run.not_run or []) if isinstance(n, dict) and n.get("station_id") in (None, station_id)]
    return [f"{n.get('check', '?')}: {n.get('reason', 'no reason recorded')}"[:200] for n in items[:cap]]


def digest(evidence: Any) -> str:
    """A stable SHA-256 of an evidence payload (or a list of them): the same evidence always gives the same hash, a changed row gives another.
    A caller that sends it back with an explain request lets the server refuse an explanation of evidence that has since changed."""
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()


def evidence_v1(run: ValidationRun, row: ValidationResult, hit: ValidationCheckHit) -> Dict[str, Any]:
    ev = hit.evidence or {}
    profile = ev.get("profile") or run.profile
    out: Dict[str, Any] = {
        "schema": SCHEMA,
        "run": {"id": run.id, "profile": run.profile, "source": run.source, "synthetic": bool(run.synthetic)},
        "row": {"id": row.id, "row_ref": row.row_ref, "station_id": row.station_id, "time": row.time_key, "verdict": row.verdict,
                "rule_score": row.rule_score, "severity": row.severity},
        "check": hit.check, "layer": hit.layer, "kind": hit.kind, "weight": hit.weight, "profile": profile,
        "time_basis": ev.get("time_basis") or ("received" if run.source == "live" else "observed"),
        "reason": hit.reason,
    }
    for k in _COPIED:
        if k in ev:
            out[k] = ev[k]
    out["limitations"] = limitations(run, out)
    out["not_run"] = not_run_for(run, row.station_id)
    cap = WINDOW_DAYS if run.profile == "daily" else WINDOW_READINGS
    if isinstance(out.get("window"), list) and len(out["window"]) > cap:
        out["window"] = out["window"][-cap:]
        out["window_truncated"] = True
    # stay under the size cap: shed neighbours, then the window, and say so
    link = f"/api/validation/runs/{run.id}/rows/{row.id}"
    while len(json.dumps(out, default=str).encode()) > MAX_PAYLOAD_BYTES:
        out["truncated"], out["next"] = True, link
        if out.get("neighbours"):
            out["neighbours"] = out["neighbours"][: len(out["neighbours"]) // 2]
        elif out.get("window"):
            out["window"] = out["window"][len(out["window"]) // 2:]
            out["window_truncated"] = True
        else:
            break
    return out
