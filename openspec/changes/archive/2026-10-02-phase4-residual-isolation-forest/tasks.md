## 1. Truth lock-in and legacy exclusion

- [x] 1.1 Add guard test failing when supported flows import `legacy_tiers/tier2_point_ml.py::IsolationForestPointDetector` for Phase 4 scoring
- [x] 1.2 Document legacy supersession (`kappa/tau` sigmoid, 9D `isolation_forest.joblib`) as unsupported in Phase 4 docs
- [x] 1.3 Confirm `backend/app/ml/__init__.py` alias no longer routes any supported Phase 4 flow to legacy

## 2. Residual contract wiring

- [x] 2.1 Pin Stage 1 → Stage 2 contract to ordered `[T_resid, P_resid, RH_resid]` `(m, 3)` input for `ResidualIsolationForest`
- [x] 2.2 Add input validation rejecting legacy 9D vectors on the canonical path with a clear error
- [x] 2.3 Verify `MultivariateEnsembleDetector` consumes the canonical IF score with `if_weight=0.55` and `anomaly_threshold=0.50` unchanged

## 3. Training and persistence

- [x] 3.1 Rewire training entry point to fit `ResidualIsolationForest(contamination=0.02, random_state=42)` on STL residuals
- [x] 3.2 Persist versioned residual-IF artifact with engine tag, `contamination`, `thresh_`, `min_val_`, `max_val_`, and residual contract version
- [x] 3.3 Verify reload reproduces identical scores within floating-point tolerance

## 4. Scoring behavior and degraded mode

- [x] 4.1 Verify threshold-at-0.50 piecewise mapping on PyOD engine (below → `[0.0, 0.50)`, at/above → `[0.50, 1.0]`)
- [x] 4.2 Verify identical threshold mapping on sklearn fallback engine
- [x] 4.3 Surface unfitted MAD/z fallback as degraded/unfitted (log/flag/status, never silent)
- [x] 4.4 Measure single-batch inference latency against the ≤15 ms budget

## 5. Evaluation and close-out

- [x] 5.1 Re-run standalone Phase 4 vs Phase 3 QC comparison (precision, recall, F1, false-positive rate) on canonical scores
- [x] 5.2 Update TODO.md Phase 4 exit evidence to cite canonical implementation and metrics
- [x] 5.3 Run affected test subset (`test_tier2_ml.py`, ensemble/stage tests) and record results
