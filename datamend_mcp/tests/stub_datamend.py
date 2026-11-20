"""A minimal stand-in for the `datamend` library, mirroring the public API
documented on PyPI (repair / DataContract / validate / drift). It lets the test
suite exercise OUR code (security, adapters, tools) without installing datamend.
It is NOT a re-implementation of datamend's algorithms."""
import json
import types

import numpy as np


class _Action:
    def __init__(self, column, issue_type, description, rows_affected):
        self.column, self.issue_type = column, issue_type
        self.description, self.rows_affected = description, rows_affected


class _RepairReport:
    def __init__(self, actions, before, after):
        self.actions, self.mend_score_before, self.mend_score_after = actions, before, after


def repair(df, strategy="auto", verbose=False, **kw):
    actions = []
    out = df.drop_duplicates().copy()
    dup = len(df) - len(out)
    if dup:
        actions.append(_Action("*", "DUPLICATE", f"Removed {dup} duplicates", dup))
    for col in out.select_dtypes("number").columns:
        n = int(out[col].isna().sum())
        if n:
            out[col] = out[col].fillna(out[col].median())
            actions.append(_Action(col, "NULL", f"Imputed {n} nulls", n))
    return out, _RepairReport(actions, 54.2, 96.8)


class DataContract:
    def __init__(self, null_threshold=0.05):
        self.null_threshold, self.columns = null_threshold, []

    def fit(self, df):
        self.columns = list(df.columns)
        return self

    def to_json(self):
        return json.dumps({"null_threshold": self.null_threshold, "columns": self.columns})

    def save(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_json())

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        c = cls(d["null_threshold"])
        c.columns = d["columns"]
        return c


class _V:
    def __init__(self, severity, column, message, expected, observed):
        self.severity, self.column, self.message = severity, column, message
        self.expected, self.observed = expected, observed


class _ContractReport:
    def __init__(self, violations):
        self.violations, self.passed = violations, not violations


def validate(df, contract, raise_on_failure=False):
    v = [_V("CRITICAL", c, f"Missing column {c}", "present", "absent") for c in contract.columns if c not in df.columns]
    return _ContractReport(v)


class _Col:
    def __init__(self, drifted):
        self.drifted, self.psi, self.ks_pvalue, self.jsd = drifted, 0.38 if drifted else 0.02, 0.001, float("nan")
        self.severity = "high" if drifted else "none"


class _DriftReport:
    def __init__(self, results):
        self.column_results = results


def drift(train, prod, columns=None, **kw):
    cols = columns or [c for c in train.columns if c in prod.columns]
    res = {}
    for c in cols:
        if np.issubdtype(train[c].dtype, np.number):
            res[c] = _Col(abs(prod[c].mean() - train[c].mean()) > train[c].std())
        else:
            res[c] = _Col(False)
    return _DriftReport(res)


def build_module():
    m = types.ModuleType("datamend")
    m.repair, m.validate, m.drift, m.DataContract = repair, validate, drift, DataContract
    return m
