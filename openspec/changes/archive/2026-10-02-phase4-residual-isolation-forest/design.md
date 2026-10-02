## Context

Phase 4 currently has two Isolation Forest implementations. The legacy `legacy_tiers/tier2_point_ml.py::IsolationForestPointDetector` fits sklearn `IsolationForest(n=100, contamination=0.01)` on a 9D scaled vector (T/P/RH + deltas + rolling std) and calibrates via logistic sigmoid (`kappa=15.0, tau=-0.05`). The production path `stages/stage2_ensemble.py::ResidualIsolationForest` fits on 3-channel Stage-1 STL residuals `[T_resid, P_resid, RH_resid]`, prefers PyOD `IForest` with a sklearn fallback, uses `contamination=0.02`, and normalizes piecewise so the fitted threshold maps to exactly `0.50`. A compat shim in `backend/app/ml/__init__.py` aliases `backend.app.ml.tier2_point_ml` to the legacy module, which lets `scripts/train_models.py` and `tests/test_tier2_ml.py` keep importing the legacy path silently. Stakeholder decision: legacies are not to be used.

## Goals / Non-Goals

**Goals:**

- Establish `ResidualIsolationForest` as the single canonical Phase 4 detector with a testable contract.
- Pin input (STL residuals), engine selection, normalization, threshold semantics, fallback, and persistence rules.
- Explicitly exclude the legacy 9D path, its calibration, and its artifact from all supported flows.

**Non-Goals:**

- Retuning `contamination`, `if_weight`, or threshold values (this change pins current truth; tuning is future work).
- Redesigning Stage 1 STL, `SequenceAutoencoderScorer`, `MultivariateEnsembleDetector` fusion, or Phase 3 QC comparison methodology.
- Migrating persisted legacy artifacts in place (handled as supersede-and-retrain, not in-place conversion).

## Decisions

- **Canonical class is `ResidualIsolationForest` (`stages/stage2_ensemble.py`).** Rationale: it operates on de-trended residuals, matching the Stage 1 → Stage 2 contract, whereas the legacy 9D vector mixes raw magnitudes with deltas and reintroduces diurnal/seasonal structure the STL stage is meant to remove. Alternative (keep both, route by flag) rejected: dual truth caused the current ambiguity.
- **Keep PyOD-preferred / sklearn-fallback engine.** Rationale: matches shipped code (`_HAS_PYOD` branch), preserves behavior on hosts without PyOD. Decision records the exact fallback threshold derivation (percentile of negated decision function) so both engines map threshold → `0.50` identically.
- **Keep piecewise-linear threshold-at-0.50 normalization, reject legacy sigmoid.** Rationale: downstream fusion and alerting treat `0.50` as the anomaly boundary; the legacy `kappa/tau` sigmoid centers elsewhere and is not comparable. All scores stay in `[0.0, 1.0]`, normal `< 0.50`, anomaly `>= 0.50`.
- **Keep residual MAD/z fallback for unfitted models, but classify it as degraded-mode.** Rationale: avoids crashes on cold start / warm paths, but it MUST be observable (logged / flagged) so it is never mistaken for a fitted IF score.
- **Supersede, don't convert, the legacy artifact.** `models/isolation_forest.joblib` (9D + background sample) is superseded by a residual-IF artifact with its own version and metadata (`model`, `contamination`, `thresh_`, `min_val_`, `max_val_`, engine tag, residual contract). Retraining from STL residuals is required; no 9D→3D weight mapping exists.

## Risks / Trade-offs

- [Risk] `scripts/train_models.py` and tests still import the legacy path via alias → Mitigation: tasks rewire training/tests to `stages/stage2_ensemble.py` and add a guard test failing on legacy import in supported flows.
- [Risk] PyOD vs sklearn score distributions differ despite shared `0.50` mapping → Mitigation: spec pins per-engine derivation and requires threshold-mapping tests on both engines.
- [Risk] Residual contract drift (Stage 1 changes units/scaling) silently invalidates the fitted IF → Mitigation: spec pins 3-channel order/units and artifact metadata records residual contract version.
- [Trade-off] Piecewise normalization clips extremes to `[0, 0.49]` / `[0.50, 1.0]` by construction — good for threshold stability, but compresses tail resolution vs raw scores. Accepted for operational consistency.

## Migration Plan

1. Land spec + design (this change), no runtime edits.
2. Follow-up implementation: rewire training to fit `ResidualIsolationForest` on STL residuals, persist new versioned artifact, update consumers to the 3-channel path, deprecate legacy module (import guard / docs), refresh Phase 3-vs-4 comparison on the canonical score.
3. Rollback: implementation change reverts to prior commit; this planning change needs no rollback (docs only).

## Open Questions

- New residual-IF artifact filename/version scheme (e.g. `residual_iforest.joblib` + `model_metadata.json` entry)?
- Minimum residual history (currently `len < 10` no-op fit) — is that threshold acceptable for production warm-up?
- Where should the unfitted-fallback observability surface (log only vs API flag)?
