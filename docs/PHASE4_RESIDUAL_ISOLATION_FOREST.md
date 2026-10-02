# Phase 4 — Residual Isolation Forest (Canonical)

**OpenSpec:** `phase4-residual-isolation-forest`
**Canonical class:** `backend/app/ml/stages/stage2_ensemble.py::ResidualIsolationForest`
**Contract:** `(m, 3)` Stage-1 STL residuals `[T_resid, P_resid, RH_resid]`, version `1.0.0`
**Engine:** PyOD `IForest` preferred, scikit-learn fallback; `contamination=0.02`, `random_state=42`
**Calibration:** piecewise-linear, fitted threshold → exactly `0.50` (`[0.0, 0.50)` normal, `[0.50, 1.0]` anomaly)
**Artifact:** `models/residual_iforest.joblib` (versioned, engine + contract metadata)

## Legacy supersession (UNSUPPORTED)

The following remain in-tree for backward compatibility only and MUST NOT be used
for Phase 4 training, inference, or evaluation:

- `backend/app/ml/legacy_tiers/tier2_point_ml.py::IsolationForestPointDetector`
- 9D scaled feature vector + logistic-sigmoid calibration (`kappa=15.0`, `tau=-0.05`)
- `models/isolation_forest.joblib` (9D payload + SHAP background sample)
- `backend.app.ml.tier2_point_ml` / `backend.app.ml.preprocessor` import aliases
  (emit `DeprecationWarning` on access)

No 9D → 3D weight conversion exists. Adopt the canonical detector by retraining
on STL residuals; do not load the legacy artifact in supported flows.

## Verification

See `tests/test_phase4_canonical_if.py` (guard + contract + both engines +
persistence + degraded-mode + latency) and the Phase 4 vs Phase 3 comparison
recorded in `docs/evaluation_report.md`.
