"""The ONLY module that talks to the datamend library.

If your copy of datamend has slightly different function names or return
types, this is the single file to edit - the security layer, tools and MCP
server do not need to change.

datamend is imported lazily (inside functions) so the rest of the package can
be imported and tested without it.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .security import ToolInputError, sanitize_text

MAX_ITEMS = 50  # cap on list sizes returned to the LLM (keeps responses small)


# ----------------------------- helpers ------------------------------------ #
def _num(x: Any) -> Optional[float]:
    """float -> JSON-safe float (NaN/inf/None -> None)."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else round(f, 6)


def _enum_value(x: Any) -> Any:
    return getattr(x, "value", x)


def _datamend():
    try:
        import datamend  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("The 'datamend' package is not installed. Run: pip install datamend") from exc
    return datamend


# ----------------------------- file I/O ----------------------------------- #
def load_dataframe(path: Path):
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)  # needs pyarrow
    if suffix == ".xlsx":
        return pd.read_excel(path)  # needs openpyxl
    raise ToolInputError(f"Unsupported file type: {sanitize_text(suffix)}")


def save_dataframe(df, path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df.to_csv(path, index=False)
    elif suffix == ".json":
        df.to_json(path, orient="records", indent=2)
    elif suffix == ".parquet":
        df.to_parquet(path, index=False)
    elif suffix == ".xlsx":
        df.to_excel(path, index=False)
    else:
        raise ToolInputError(f"Unsupported output type: {sanitize_text(suffix)}")


# ----------------------------- Pillar 1: repair --------------------------- #
def _actions(report) -> List[Dict[str, Any]]:
    out = []
    for a in list(getattr(report, "actions", []) or [])[:MAX_ITEMS]:
        out.append(
            {
                "column": sanitize_text(getattr(a, "column", "")),
                "issue_type": sanitize_text(_enum_value(getattr(a, "issue_type", "")), 40),
                "description": sanitize_text(getattr(a, "description", ""), 200),
                "rows_affected": getattr(a, "rows_affected", None),
            }
        )
    return out


def repair_dataframe(df, strategy: str) -> Tuple[Any, Dict[str, Any]]:
    dm = _datamend()
    repaired, report = dm.repair(df.copy(), strategy=strategy)
    summary = {
        "mend_score_before": _num(getattr(report, "mend_score_before", None)),
        "mend_score_after": _num(getattr(report, "mend_score_after", None)),
        "issues_fixed": len(getattr(report, "actions", []) or []),
        "rows_before": int(len(df)),
        "rows_after": int(len(repaired)),
        "actions": _actions(report),
    }
    return repaired, summary


def score_dataframe(df) -> Dict[str, Any]:
    """Read-only health score: runs repair on a copy and discards the result."""
    dm = _datamend()
    _, report = dm.repair(df.copy())
    counts = Counter(
        sanitize_text(_enum_value(getattr(a, "issue_type", "UNKNOWN")), 40)
        for a in (getattr(report, "actions", []) or [])
    )
    return {
        "mend_score": _num(getattr(report, "mend_score_before", None)),
        "issue_counts": dict(counts),
        "total_issues": int(sum(counts.values())),
    }


# ----------------------------- Pillar 2: contract ------------------------- #
def fit_contract(df, null_threshold: float):
    from datamend import DataContract

    contract = DataContract(null_threshold=null_threshold)
    contract.fit(df)
    return contract


def save_contract(contract, path: Path) -> None:
    if hasattr(contract, "save"):
        contract.save(str(path))
    else:
        path.write_text(contract.to_json(), encoding="utf-8")


def load_contract(path: Path):
    from datamend import DataContract

    return DataContract.load(str(path))


def validate_dataframe(df, contract) -> Dict[str, Any]:
    dm = _datamend()
    report = dm.validate(df, contract)
    violations = []
    for v in list(getattr(report, "violations", []) or [])[:MAX_ITEMS]:
        violations.append(
            {
                "severity": sanitize_text(_enum_value(getattr(v, "severity", "")), 20),
                "column": sanitize_text(getattr(v, "column", "")),
                "message": sanitize_text(getattr(v, "message", ""), 200),
                "expected": sanitize_text(getattr(v, "expected", ""), 80),
                "observed": sanitize_text(getattr(v, "observed", ""), 80),
            }
        )
    total = len(getattr(report, "violations", []) or [])
    return {"passed": bool(getattr(report, "passed", total == 0)), "violation_count": total, "violations": violations}


# ----------------------------- Pillar 3: drift ---------------------------- #
def drift_dataframes(train, prod, columns: Optional[List[str]]) -> Dict[str, Any]:
    dm = _datamend()
    report = dm.drift(train, prod, columns=columns) if columns else dm.drift(train, prod)
    results = []
    for col, r in list((getattr(report, "column_results", {}) or {}).items())[:100]:
        results.append(
            {
                "column": sanitize_text(col),
                "drifted": bool(getattr(r, "drifted", False)),
                "psi": _num(getattr(r, "psi", None)),
                "ks_pvalue": _num(getattr(r, "ks_pvalue", None)),
                "jsd": _num(getattr(r, "jsd", None)),
                "severity": sanitize_text(_enum_value(getattr(r, "severity", "")), 20),
            }
        )
    drifted = [r["column"] for r in results if r["drifted"]]
    return {"columns_checked": len(results), "columns_drifted": len(drifted), "drifted_columns": drifted, "results": results}


def contract_text(path: Path) -> str:
    """Return a contract JSON file as text (validated to be JSON)."""
    text = path.read_text(encoding="utf-8")
    json.loads(text)
    return text
