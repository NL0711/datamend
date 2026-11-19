"""The overview (command centre): what the platform holds right now, read from the stored run reports. Measured counts only; no grade."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.validation.models import ValidationRun
from backend.app.validation.runs import STORAGE_LABEL, run_dict


async def overview(session: AsyncSession) -> Dict[str, Any]:
    runs = list((await session.execute(select(ValidationRun).order_by(ValidationRun.id.desc()))).scalars())
    done = [r for r in runs if r.status != "failed"]
    verdicts: Counter = Counter()
    checks: Counter = Counter()
    real_rows = synthetic_rows = 0
    for r in done:
        rep = r.report or {}
        verdicts.update(rep.get("verdicts", {}))
        checks.update(rep.get("checks", {}))
        if r.synthetic:
            synthetic_rows += r.n_rows
        else:
            real_rows += r.n_rows
    live = next((r for r in runs if r.source == "live" and r.status == "open"), None)
    return {
        "storage": STORAGE_LABEL,
        "runs": {"total": len(runs), "completed": sum(1 for r in runs if r.status == "completed"), "open_live": 1 if live else 0,
                 "rejected_uploads": sum(1 for r in runs if r.status == "failed")},
        "rows": {"total": real_rows + synthetic_rows, "uploaded_or_live": real_rows, "synthetic": synthetic_rows},
        "verdicts": {v: verdicts.get(v, 0) for v in ("OK", "SUSPECT", "UNCERTAIN", "NO_DATA")},
        "checks_fired": dict(checks.most_common(12)),
        "latest_run": run_dict(done[0]) if done else None,
        "live_run": run_dict(live) if live else None,
        "note": "counts of rows in the stored runs; synthetic rows are counted separately and labelled; nothing here is an accuracy figure",
    }
