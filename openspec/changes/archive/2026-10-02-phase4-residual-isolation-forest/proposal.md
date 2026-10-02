## Why

Phase 4 (Isolation Forest) is marked complete in TODO.md but has no OpenSpec and two competing implementations: the legacy 9D `IsolationForestPointDetector` (`legacy_tiers/tier2_point_ml.py`, logistic-sigmoid calibration) and the production `ResidualIsolationForest` (`stages/stage2_ensemble.py`). The declared truth is that legacies are not to be used — `stage2_ensemble.py::ResidualIsolationForest` is canonical. Without a spec, training, inference, and evaluation can silently drift back to the legacy path.

## What Changes

- Declare `ResidualIsolationForest` in `backend/app/ml/stages/stage2_ensemble.py` as the sole canonical Phase 4 detector.
- Define its input contract as 3-channel de-trended STL residuals `[T_resid, P_resid, RH_resid]` from Stage 1, not the legacy 9D scaled feature vector.
- Define the PyOD-preferred / sklearn-fallback engine, `contamination=0.02`, `random_state=42`, and piecewise-linear normalization mapping the decision threshold to exactly `0.50`.
- Mark the legacy path as **BREAKING** removal from the supported path: `legacy_tiers/tier2_point_ml.py::IsolationForestPointDetector`, its `kappa/tau` sigmoid calibration, `models/isolation_forest.joblib` 9D artifact, and the `backend.app.ml.tier2_point_ml` alias must no longer be used for training, inference, or evaluation.
- Scope ensemble fusion weights (`if_weight=0.55`), `SequenceAutoencoderScorer`, and `MultivariateEnsembleDetector` as consumers of this score, not part of this change's contract (documented as boundary only).

## Capabilities

### New Capabilities

- `residual-isolation-forest`: canonical Phase 4 residual Isolation Forest — input residuals contract, fit/score behavior, threshold-at-0.50 normalization, unfitted fallback, persistence, and legacy exclusion.

### Modified Capabilities

- None (no existing specs in `openspec/specs/` to modify).

## Impact

- Affected code: `backend/app/ml/stages/stage2_ensemble.py` (`ResidualIsolationForest`, `MultivariateEnsembleDetector`), Stage 1 STL residual producer contract, training entry points (`scripts/train_models.py` isolation-forest section), inference/consumers reading the IF score, tests referencing `tier2_point_ml` / `isolation_forest.joblib`.
- Dependencies: PyOD `IForest` preferred with scikit-learn `IsolationForest` fallback; NumPy; Stage 1 residuals.
- Systems: anomaly scoring pipeline, future evaluation/comparison against Phase 3 QC baseline, model artifact versioning (legacy `isolation_forest.joblib` superseded).
