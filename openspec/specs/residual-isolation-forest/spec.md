# residual-isolation-forest — Canonical Phase 4 Detector

`ResidualIsolationForest` (`backend/app/ml/stages/stage2_ensemble.py`) on
3-channel Stage-1 STL residuals is the sole canonical Phase 4 detector; the
legacy 9D `IsolationForestPointDetector` path is unsupported. Source change:
phase4-residual-isolation-forest.

## ADDED Requirements

### Requirement: Residual input contract

The system SHALL feed `ResidualIsolationForest` only 3-channel de-trended STL residuals ordered `[T_resid, P_resid, RH_resid]` and SHALL NOT substitute the legacy 9D scaled feature vector.

#### Scenario: Correct residual shape accepted

- **WHEN** a caller passes an `(m, 3)` residual matrix in `[T_resid, P_resid, RH_resid]` order
- **THEN** the detector accepts it for `fit`/`score` without reshaping or channel reordering

#### Scenario: Legacy 9D vector rejected from supported path

- **WHEN** a caller attempts to score a 9-element legacy vector through the canonical Phase 4 path
- **THEN** the system rejects it as an unsupported input contract (error or documented guard, not a silent score)

### Requirement: Engine selection and fitting

The system SHALL prefer PyOD `IForest` when available with a scikit-learn `IsolationForest` fallback, fit with `contamination=0.02` and `random_state=42`, and record the fitted threshold and normalization bounds.

#### Scenario: Fit records threshold mapping inputs

- **WHEN** fitting completes on at least 10 residual rows
- **THEN** the model stores `thresh_`, `min_val_`, and `max_val_` derived from the active engine's training scores

#### Scenario: Insufficient history is a no-op fit

- **WHEN** fewer than 10 residual rows are provided
- **THEN** the detector remains unfitted and reports unfitted status instead of producing a fitted-model score

### Requirement: Threshold-at-0.50 score normalization

The system SHALL emit scores in `[0.0, 1.0]` with the fitted threshold mapped to exactly `0.50`, normal observations below `0.50`, and anomalies at or above `0.50`, on both engines.

#### Scenario: Normal residual scores below boundary

- **WHEN** a fitted model scores a residual below its fitted threshold
- **THEN** the normalized score is in `[0.0, 0.50)` via the below-threshold piecewise mapping

#### Scenario: Anomalous residual scores at or above boundary

- **WHEN** a fitted model scores a residual at or above its fitted threshold
- **THEN** the normalized score is in `[0.50, 1.0]` via the above-threshold piecewise mapping

### Requirement: Degraded-mode fallback observability

The system SHALL provide a deterministic degraded-mode score when unfitted AND surface that the score did not come from a fitted Isolation Forest.

#### Scenario: Unfitted batch scoring is flagged

- **WHEN** scoring with no fitted model
- **THEN** the system returns MAD/z-based fallback scores in `[0.0, 1.0]` together with an unfitted/degraded indicator (log, flag, or status — not a silent fitted score)

### Requirement: Persistence carries residual contract

The system SHALL persist the fitted residual detector with engine identity, hyperparameters, normalization bounds, and residual contract metadata sufficient to reload and reproduce threshold-at-`0.50` scoring.

#### Scenario: Reloaded model reproduces scores

- **WHEN** a persisted residual detector is reloaded
- **THEN** it scores identical residuals identically within floating-point tolerance and restores `contamination`, `thresh_`, `min_val_`, `max_val_`, and engine tag

### Requirement: Legacy path exclusion

The system SHALL NOT use `legacy_tiers/tier2_point_ml.py::IsolationForestPointDetector`, its `kappa/tau` sigmoid calibration, or the legacy 9D `isolation_forest.joblib` artifact in any supported training, inference, or evaluation flow.

#### Scenario: Legacy calibration absent from canonical path

- **WHEN** reviewing the canonical Phase 4 scoring code path
- **THEN** no logistic-sigmoid `kappa/tau` mapping influences the emitted score

#### Scenario: Legacy artifact not loaded by supported flows

- **WHEN** a supported training, inference, or evaluation flow needs a Phase 4 model
- **THEN** it resolves to the residual-detector artifact/contract, never to the legacy 9D `isolation_forest.joblib` payload
