---
title: How does a training snapshot leave the platform and a model come back?
labels: [wayfinder:grilling]
status: open
assignee:
parent: MAP
blocked_by: [t06-reviewer-workflow-and-proposals]
---

## Question

Decide the hand-off: the dataset snapshot format and its time cut (training earlier, validation later, never the future, never test years), the leakage rules for station-derived cells, how the offline run is triggered and logs its metrics (MLflow or a table in the platform), the artifact import and registry (champion and challenger), the promotion gate and shadow rule on this data, and how a rejected candidate or a rollback is recorded.

## Resolution (2026-11-20, decided by building on `feature/ingest-pipeline`; status stays open, see "Needs the owner")

**Decided and built** (`backend/app/pipeline/snapshot.py`, `fusion.py`, `training.py`, `kaggle_trigger.py`, `registry.py`, `lineage.py`, `backend/app/api/pipeline.py`, `frontend/src/validation/PipelineView.tsx` and `LineageGraph.tsx`; tests in `tests/test_pipeline.py` and `tests/test_pipeline_train.py`):

- **Snapshot:** `snapshot.build` writes one JSON line per labelled station-day (run, row, station, day, coordinates, original and effective value, whether a correction excluded it, verdict, rule score, the checks that fired, label, weight, label source, random-sample flag, tier). It is stored whole in `pipeline_snapshots.content` with its SHA-256 and a manifest (cut day, row and label counts, runs used, excluded years, skipped counts, notes). Download: `GET /snapshots/{id}/data.jsonl` with the hash in a header.
- **Time cut and locked years:** nothing after the cut day is included, and the locked test years 2018 to 2025 (`LOCKED_TEST_YEARS`) are left out by default; including them needs `allow_test_years` and is recorded in the manifest. Only reviewer decisions are labels; proposals never are.
- **What is retrained:** not the RF25 STNet. `fusion.py` fits a non-negative, weighted logistic regression over which of six checks fired (`impossible_value`, `repeated_value`, `climatology_upper_tail`, `neighbour_isolated_wet`, `neighbour_isolated_dry`, `duplicate_row`), so it learns how much to trust each check. It splits by time (earlier days train, later days validate, boundary day kept together), picks the flag threshold so the weighted false-alarm rate on the training clean days stays within 5 per 1,000 (`BUDGET_PER_1000`), and scores the platform's fixed rule weights on the same later days as the baseline. It refuses to train below 20 faults and 100 clean labels in the training part and at least 1 of each in validation (`MIN_FAULT`, `MIN_CLEAN`).
- **Where it runs:** `training.start` with target `local` runs it in a thread on the server's CPU; target `kaggle` pushes a private, internet-off CPU script notebook (`kaggle_trigger.build_bundle`: `fusion.py` plus the gzip and base64 snapshot embedded, so no dataset upload) with the `kaggle` command line and `KAGGLE_USERNAME` and `KAGGLE_KEY` from the server environment. `training.refresh` polls the notebook, fetches `result.json` and registers the model. The key is stripped from any error text. The training job table (`pipeline_training_jobs`) records target, notebook slug, status and error.
- **Registry and gate:** `registry.register` always creates a `challenger`; `registry.promote` runs the gate and either makes it `champion` (the old champion becomes `archived`) or marks it `rejected` with the gate result stored on the model (`pipeline_models.gate`). `rollback` puts the newest archived model back and appends " | rolled back" to the replaced model's notes. Two gate profiles: the generic one (declared metrics, frozen-protocol and test-years declarations, comparison with the champion) and `label_fusion` (`_evaluate_label_model`): temporal split, enough labels, false alarms within budget, recall not below the fixed rules on the same days, protected extremes not higher than the rules. A label-fusion champion trained on a different snapshot is not compared (reported as "not comparable").
- **Metrics are declared, not verified:** the platform cannot check a model trained elsewhere, so every model view says "declared by the training job, not verified by the platform", and the lineage graph (`lineage.build`, drawn by `LineageGraph.tsx`) shows metrics as "declared, not verified".
- **MLflow not used;** metrics live in the registry table.

**Rejected or not taken:** MLflow; retraining the RF25 STNet from station labels (no server-side scoring or cell mapping, ticket t07); training a neural model on the Render server (out of scope in the MAP); a shadow run; judging a candidate on a champion from a different snapshot.

**Caveats (some differ from `docs/mlops-feedback-loop-spec.md`):**

- **Untested against live Kaggle.** The tests mock the command line and run the generated notebook script locally; Kaggle's weekly quota cannot be read or a run cancelled through its public API. The snapshot is embedded in a private notebook, so derived CWC station data goes to Kaggle's servers (see the licence question below).
- **The gate is not the spec's gate.** Spec section 6 judges a candidate on the frozen validation benchmark and then a shadow run. Here the label-fusion model is judged on the later part of its own snapshot against the fixed rules. The shadow run and the spec's golden set (reviewed items never trained on) are NOT IMPLEMENTED; the later days of the snapshot are not a held-out golden set.
- **The budget is fixed on training days.** `fusion._threshold_for_budget` uses the training clean days; the validation false-alarm rate is then only checked. `AGENTS.md` section 9 says budgets are fixed on validation data only. This should be reconciled or the difference accepted explicitly.
- **The thresholds are duplicated:** 20 faults and 100 clean are in both `fusion.py` and the gate in `registry.py` (hard-coded), so changing one without the other would make the gate and the trainer disagree.
- **A 5 per 1,000 budget needs many clean validation days to mean anything:** with fewer than 200 clean validation days it tolerates zero false alarms, so a gate pass or fail is not informative at small label counts. The result states that the labels are one reviewer's judgements and not ground truth.
- **`artifact_sha256` on a registered model is the snapshot's hash** (`training._register`), not the hash of a model file; the weights are inside the stored metrics (`artifact`). Do not read it as an artifact checksum.
- **The locked test years rule blocks the CWC data that exists.** The real file measured in ticket t04 covers 2021 to 2025, all inside 2018 to 2025, so by default a snapshot from it is empty and the tests use 2026 data. See the owner questions.
- **Scoring is not built:** a champion changes nothing about any verdict or flag; it is registered and shown only. Nothing in the platform yet applies learned weights (NOT IMPLEMENTED, see MAP Not yet specified).
- **Never run on a real reviewer's labels.** All results so far come from generated files; the label-fusion test shows the trainer beats the fixed weights on generated labels, which is a test of the code, not evidence of improvement.

## Needs the owner

1. The minimum label counts, 20 faults and 100 clean (chosen by the build, not by evidence).
2. The false-alarm budget of 5 per 1,000 (a constant in `fusion.py`, not fitted to this data).
3. Whether the locked test years 2018 to 2025 should block CWC data entirely, or whether CWC (a different source from the RF25 test data) may be used for training and validation of this label-fusion model, with the test years kept for the RF25 protocol only.
4. Whether the threshold may be fixed on training days or must be fixed on a separate validation set as `AGENTS.md` section 9 says.
5. Whether sending a snapshot of derived CWC station data to Kaggle is allowed, which depends on the CWC licence answer (ticket t03: derived flags unconfirmed) and on whose Kaggle account is used.
6. Whether a gate on the model's own later days is enough, or a held-out golden set and a shadow run are required before a champion has any effect.

This ticket closes when items 1 to 4 are decided and one training run has been done on real reviewed labels (and Kaggle once, live, if Kaggle is to stay).
