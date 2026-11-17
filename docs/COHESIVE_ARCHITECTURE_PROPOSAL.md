# Cohesive architecture proposal

Status: PROPOSAL, 2026-11-17. Nothing here is built. It reconciles `GOAL.md` / `ARCHITECTURE.md` (AWS T/P/RH), `backend/app/ml` (two implemented pipelines), `ml-service/qc` (rainfall QC, locked spec) and the ERA5 temperature/humidity/pressure extension (`docs/qc-system-spec.md` section 16).

## 1. What exists today (verified in the repo)

| Piece | Data | Model | State |
| --- | --- | --- | --- |
| `backend/app/ml/legacy_tiers` (live ingestion path) | station T/P/RH, simulated + NOAA ISD | rules, point Isolation Forest, 30-step GRU autoencoder, Mahalanobis, hand-weighted fusion | runs; trained on 5,760 simulated rows; labels are injected |
| `backend/app/ml/stages` (phase2/3 services, `/api` routes) | station T/P/RH | STL residuals, residual IF, GRU/Conv sequence scorer, physics, classifier, explain, imputer | runs; same synthetic basis; overlaps the legacy path |
| `ml-service/training` (older) | RF25 rainfall | ScaleNet / RainNet BiLSTM + attention + zero-inflated Gamma | trained only on smoke/CPU runs; superseded by `qc/` for the paper |
| `ml-service/qc` (locked spec) | RF25 rainfall grid | spatial + temporal (GRU) + slow + rules, fusion, federated variants | built on synthetic worlds; **no real run yet** |
| ERA5 extension (`qc/era5.py`, `multivar.py`, `multivar_nn.py`) | ERA5 daily T/RH/P on the RF25 grid | rule experts, Mahalanobis, gradient-boosted neighbour regressors, masked-target CNN, `fusion_max` | built; **models not persisted**; run only through `era5-validate` on the CLI; **no notebook section** (`datamend_qc_kaggle.ipynb` covers rainfall only) |
| Locations feature + plan | Open-Meteo, grid cells | rule QC today; trained-model panel is an empty slot | v1 built; model scores planned (`LOCATIONS_MODEL_SCORES_PLAN.md`) |
| Dashboard tabs | station telemetry | read the legacy pipeline | work, but nothing trained on real data feeds them |

## 2. The conflicts

1. Two product definitions: AWS single-station QC (GOAL.md) vs gridded rainfall QC (qc spec). Different inputs, different splits, different claims.
2. Two backend pipelines (legacy tiers and stages) that do the same job.
3. The qc spec forbids repair and cause prediction; GOAL.md requires classification, explanation, health and optional imputation.
4. The ERA5 detector is trained on reanalysis grids; the dashboard consumes station and Open-Meteo values. Without a bridge, the trained model never touches the app. The risks are documented: pressure height offset, a cell/site gap, and ERA5 faults being easier to detect than real faults.
5. The time-series requirement (LSTM/GRU/Mamba) lives in three unrelated places.

## 3. Proposed shape: one QC engine, two lanes, one score contract

```
DATA PRODUCTS            DETECTORS (one fusion contract)                SERVING
RF25 rain grid     ->  GRID LANE / rainfall  (qc/)                 \
ERA5 daily T/RH/P  ->  GRID LANE / tphp      (qc/multivar*)         >-> score files (schema 1, with provenance)
Station streams    ->  STATION LANE (backend, time-series)         /     -> backend reads files / later online
(NOAA ISD, ESP32,                                                          -> dashboard tabs + Locations
 Open-Meteo)                  ^ ERA5 cell as reference "buddy"
```

**Grid lane (the research product).** Keep `ml-service/qc` as the source of truth: spatial, temporal, slow and rule components, fused with budgets fixed before test scoring. Two domains share the contract: `rainfall` and `tphp`. Test discipline, frozen benchmark and synthetic-label honesty stay as written.

**Station lane (what the legacy tabs show).** One pipeline, not two: pick the `stages` path (STL residuals, no hand-tuned weights) and retire `legacy_tiers` after the tabs are moved. Its temporal component is the sequence-model slot (GRU baseline, LSTM, Mamba-style SSM) behind one interface. It is trained and compared with the qc discipline: time splits, fixed seeds, leakage checks, per-fault-kind metrics. Real NOAA ISD series with their quality flags are the evaluation data where possible, not only injected faults.

**ERA5 as the bridge, in the station lane.** For a station with known coordinates, take the ERA5 cell value as a reference "buddy" and add one component: height-corrected anomaly of the station against its ERA5 cell. This reuses the ERA5-trained statistics and gives the station lane a component grounded in the ERA5 work. Prerequisites from the verification doc: reduce pressure to a common height, correct temperature for height, and validate on real AWS data before quoting any number.

**One output contract.** Every detector returns `components`, `fused score`, `flag` (none / review / final), `thresholds`, and `provenance`. This is already the score-file schema 1 in `LOCATIONS_MODEL_SCORES_PLAN.md`. Classification becomes driver attribution (which component drove the flag, and whether a spatially coherent extreme is protected), which is compatible with the qc spec. Sensor health is computed from the flag history. Imputation stays out of scope, and raw and corrected values are never merged.

**Serving.** Offline export first (ml-service writes per-cell score files, the backend only reads them, torch stays out of the web server). Online inference is a later phase.

## 4. Gaps this exposes (must be tracked, not hidden)

- ERA5 models are not persisted, so nothing can be loaded or exported yet.
- No notebook runs the ERA5 pipeline; it exists only as CLI commands.
- Nothing in rainfall or ERA5 has run on real data.
- Pre-1979 ERA5 is excluded from training; the 1979 break check is still open.
- Station lane models were trained on 5,760 simulated rows only.
- `GOAL.md`, `ARCHITECTURE.md`, `AGENTS.md` and `TODO.md` describe the AWS-only product and mark phases complete on synthetic evidence; they need rewriting to match whichever direction is chosen.

## 5. Suggested order

1. **Decide and document** (this file, then rewrite GOAL/ARCHITECTURE/TODO to the chosen shape).
2. **ERA5 persistence and notebook section**: `save`/`load` in `qc.multivar`, `era5-validate --save-models`, and an ERA5 block in `datamend_qc_kaggle.ipynb`.
3. **Score-file export** (`qc export-scores`) for rainfall, then tphp, matching schema 1.
4. **Station lane consolidation**: move the tabs to the `stages` path behind a sequence-model interface (GRU, LSTM, Mamba), compare on time-split NOAA series, retire `legacy_tiers`.
5. **ERA5 reference component** for stations (height correction first).
6. **Locations "Trained model" panel** reading the exported files.
