# Plan: trained-model scores in the Locations feature

Status: plan, rewritten 2026-11-18 for a rainfall-only project (ERA5 temperature, humidity and pressure work was removed). Nothing here is built. It extends `docs/LOCATIONS_DESIGN.md` (v1 is built: place to cells, live values, weather anomaly, rule-based data-QC, and an empty "trained model" slot).

## 1. Goal

For the cells of a location (Mumbai first), show what the **trained** `ml-service/qc` rainfall models say about the data of a date: per-component scores, one fused score, whether it crosses the fixed final or review thresholds, and which component drove it. Every score is shown with where it comes from and what it has and has not been validated on.

## 2. Facts that shape the plan

**A. The models only know RF25.** They are trained on RF25 (IMD gauge-based grid, annual files). The v1 app shows Open-Meteo values, a different product. Feeding Open-Meteo rainfall to an RF25-trained model is a distribution shift, not a valid score.

**B. Rainfall score files exist only for some years and only on corrupted data.** The score store holds validation, test and stress years scored on the **benchmark** (injected faults), plus the clean threshold years 2016-2017. Real, uncorrupted scores for other years do not exist and must be produced by a separate scoring run.

**C. Mumbai is in held-out region 6.** The rainfall models never trained on it, so a score there is a genuine unseen-region result. (Pre-2013 years of other regions were trained on; Mumbai's cells never were.)

**D. Test-year discipline.** Scoring any 2018-or-later year on real data must wait until budgets are fixed and the single test pass is done, so the evaluation stays clean.

**E. Coverage is historical, not live.** RF25 comes in yearly files. Model scores will exist for dates the input data covers; "yesterday in Mumbai" will usually have no model score. The UI must say so.

## 3. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Score rainfall only on RF25 values. Never apply RF25-trained models to Open-Meteo values. | Fact A. |
| D2 | Offline export first. ml-service scripts write per-cell score files; the backend only reads them. Online inference in the backend is later. | Keeps torch out of the web backend; matches the existing `FileScoreProvider`. |
| D3 | Model scores get their own panel with a date or timeline control. They are not merged into the live verdict. | Different data, different dates. |
| D4 | Provenance is part of the file: run name, benchmark hash, budgets, split hash, label tier ("synthetic faults"), model version. The UI prints it. | No score without its origin. |

## 4. Score file format v1 (replaces the v0 sketch in `scores.py`)

`data/location_scores/<row>_<col>.json`, one per cell, small (a few hundred KB for years of daily values):

```json
{"schema": 1, "cell": {"row": 50, "col": 25, "lat": 19.0, "lon": 72.75, "client": 6, "held_out": true},
 "domain": "rainfall",
 "provenance": {"run": "base", "git_commit": "...", "split_hash": "...", "benchmark_hash": "...",
                "model": "fusion_logistic (qc)", "seeds": [0,1,2], "label_tier": "synthetic faults",
                "input": "RF25 clean (no injected faults)", "scored_on": "2026-..."},
 "thresholds": {"final": 7.1, "review": 5.4, "final_per_1000": 1.0, "review_per_1000": 5.0},
 "components": ["rules", "slow", "spatial", "temporal"],
 "scores": {"2018-07-01": {"fused": 2.3, "flag": "none", "by_component": {"spatial": 1.9, "temporal": 0.4}, "value": 12.4}}}
```
The backend rejects files with an unknown `schema`, a missing `provenance`, or a `held_out` that disagrees with its own client map.

## 5. Phases

**P0. Prerequisites (not code).** (a) Rainfall: budgets fixed and the single test pass done. (b) Decide the years to export (see section 7).

**P1. Rainfall export (ml-service).** New command `python -m qc export-scores --cells <rows/cols or place> --years ...`.
- Loads the saved checkpoints and fusion fit; scores **clean** real years for the full grid (the normal scoring path) and slices the requested cells.
- Writes the files of section 4 plus a `thresholds` block from the fixed budgets.
- Refuses test or stress years if the test lock is not `done`.
- Tests on the small generated world: cell slicing is correct, no injected fault leaks in, thresholds match `thresholds_for`, refusal before the lock, deterministic output.
- A notebook cell runs it on Kaggle and pushes the small JSON files through the existing `kaggle-results` branch.

**P2. Backend.**
- `FileScoreProvider` reads schema 1 and validates it.
- New `GET /api/locations/{id}/model-scores?from=&to=` returning per-cell series with thresholds and provenance; the status call embeds the latest available date with its age.
- Plain reasons for every "not available": date outside coverage, no file for this cell, sea cell, schema rejected.
- Tests with fixture files, including a corrupted file and a mismatched client.

**P3. Frontend.** A "Trained model" panel: a timeline of the fused score per cell with the final and review thresholds, a date click showing the component breakdown, a provenance box, and the labels "validated on synthetic faults only" and "model never trained on this region". No colour-only signalling.

**P4. Real-event check (the part that answers whether it is useful).** Run the Mumbai history through the exported scores and look at known events: the heavy-rain days of July 2005 and the monsoon peaks. Report how often a genuine, widespread event is flagged. All event dates stay "plausible, unverified" until checked against IMD records.

**P5. Later.** Online inference service, a live gridded rainfall source, alerts and websocket integration, a scheduled export.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Product mismatch (Open-Meteo vs RF25) makes everything look faulty | D1; only RF25 values are scored |
| Showing synthetic-fault performance as if it were real accuracy | Provenance and label tier on every score; wording reviewed in P3 |
| Test years scored too early | Export refuses before the lock is `done` |
| Score files drift from the models that made them | `git_commit`, `split_hash`, `benchmark_hash` in each file; backend shows them |

## 7. Decisions needed from you

1. Which years to export for Mumbai: the test years 2018-2025, plus chosen historic events (for example 2005)?
2. Where the score files live: committed to the repo (small, simple) or only on the `kaggle-results` branch and pulled?

## 8. Done when

- A score for a Mumbai cell and date opens with its components, thresholds and provenance, and a date without a score says why.
- The panel states plainly that validation so far is on synthetic faults.
- Tests cover export, schema validation, refusal rules and the API.
