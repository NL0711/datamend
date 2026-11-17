# qc: precipitation QC system

Design: [`docs/qc-system-spec.md`](../../docs/qc-system-spec.md). Standing rules and the budget log: [`docs/qc-evaluation-protocol.md`](../../docs/qc-evaluation-protocol.md). Paper outline: [`docs/qc-paper-methods-outline.md`](../../docs/qc-paper-methods-outline.md).

**Status:** gates 0-9 are built and tested on small generated worlds. Nothing has been run on real RF25 or MIDAS data, no budgets are chosen, and no result in this repo is a real result. Offline comparison and fusion on federated components are built (tiny-run tests only; the offline test uses random-weight artifacts). NOT AVAILABLE: local-only variant on unseen clients. UK reader: UNVERIFIED on real files.

## Setup

```bash
cd ml-service
uv venv --python 3.11 .venv
uv pip install -r requirements-train.txt pytest
python -m pytest qc -q     # about 10 minutes on CPU, no RF25 needed
```

## Run order (training machine, real RF25)

Each step is its own command; add `--config qc/configs/base.yaml` and optionally `--profile kaggle|single-gpu`, `--set key=value`.

| step | command | note |
|---|---|---|
| 1 | `python -m qc client-map` | once; fixes the client map (held-out clients 3 and 6) |
| 2 | `python -m qc prepare` | contract check, splits, training statistics, leakage audit |
| 3 | `python -m qc benchmark` | frozen, hashed validation, test and stress faults |
| 4 | `python -m qc untrained` | rules, slow component, neighbour baseline |
| 5 | `python -m qc train` | spatial, temporal, plain GRU; three seeds |
| 6 | `python -m qc federated --variants fedpers fedavg fedft local` | federated simulation |
| 7 | `python -m qc fusion` | fits fusion, validation curves; repeat with `--on fedpers` (or fedavg, fedft) for a fusion on federated components |
| 8 | `python -m qc set-budgets --final F --review R` | once, before any test scoring; logged in the protocol |
| 9 | `python -m qc test-score` | single use: test years are scored once. Offline comparison runs if `offline.artifacts.<arch>` is set (non-causal; leak-checked) |
| 10 | `python -m qc paper` | tables, figures, claim check under `<run>/paper/` |

Timing run and compute caps: spec section 14, gate 0. UK study: `qc/configs/uk.yaml` (run order in its header); `python -m qc paper --config qc/configs/uk.yaml` writes the UK table with its caveats.

## Running on Kaggle

`notebooks/datamend_qc_kaggle.ipynb` runs the pipeline above on Kaggle from a dataset link (`qc/kaggle_data.py` finds the mounted RF25 files; `qc/kaggle_sync.py` pushes the small results to the `kaggle-results` git branch when asked). Phase 1 runs through the fusion step; you choose the budgets, then phase 2 runs the single test pass and the paper outputs. Not yet run on Kaggle.

## Layout

`config`, `paths`, `grid`, `clients`, `splits`, `stats`, `prepare` (data and splits); `faults`, `extremes`, `benchmark` (benchmark); `baselines`, `untrained`, `neighbours`, `scoring`, `metrics`, `evaluate` (untrained scores, metrics); `models`, `batches`, `trained` (components); `fusion`, `fusion_eval` (fusion, budgets); `federated`; `testscore`; `uk/` (MIDAS study); `paper` (tables, figures, claims); `tests/` (one file per gate).

## ERA5 temperature, humidity, pressure (extension)

Spec section 16. Download by hand from the CDS web form (ERA5 hourly data on single levels; variables 2m temperature, 2m dewpoint temperature, surface pressure; all days and 24 hours; area N 38.5, W 66.5, S 6.5, E 100; GRIB or NetCDF, unarchived) into `era5.hourly_dir` (default `ml-service/data/era5`); file names and spans do not matter. `python -m qc era5-inventory` lists what the files cover; `python -m qc era5-daily --years 2016 2016` writes `ERA5D_<year>.nc`, then `python -m qc era5-validate` (synthetic-fault validation: rule and consistency experts plus the gradient-boosted neighbour regression experts, with `fusion_max`; optional GPU neural experts via `--set era5.nn.enabled=true --set era5.nn.trials=4`). Day alignment (`era5.label_offset_hours`) is UNVERIFIED against IMD; footprint faults, genuine-extreme protection and federated variants are NOT IMPLEMENTED; ERA5 is modelled, not measured, so faults are easier to detect than real ones.
