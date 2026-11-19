"""Build the evidence-v1 payload (docs/contracts/evidence-v1.schema.json) for one fired check on one row.

Every number carries a basis (measured, assumed, derived). The window is capped at the last 24 readings or 14 days and the whole payload
at 64 KB; a cut payload says so (``truncated``) and links to the full row record (``next``).
"""
from __future__ import annotations

import json
from typing import Any, Dict

from backend.app.validation.models import ValidationCheckHit, ValidationResult, ValidationRun

SCHEMA = "evidence-v1"
MAX_PAYLOAD_BYTES = 64 * 1024
WINDOW_READINGS = 24
WINDOW_DAYS = 14
_COPIED = ("observed", "threshold", "window", "neighbours", "history", "tail_probability", "issue")


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
