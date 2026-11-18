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
| 7b | `python -m qc ablate` | optional, validation only: refits the fusion on component subsets (without rules, without temporal, with the neighbour average or plain GRU added) and compares them at budget 1; writes to `<run>/ablation/` and never touches the main fusion or the test years. Use it before the single test pass |
| 8 | `python -m qc set-budgets --final F --review R` | once, before any test scoring; logged in the protocol |
| 9 | `python -m qc test-score` | single use: test years are scored once. Offline comparison runs if `offline.artifacts.<arch>` is set (non-causal; leak-checked) |
| 10 | `python -m qc paper` | tables, figures, claim check under `<run>/paper/` |

Timing run and compute caps: spec section 14, gate 0. UK study: `qc/configs/uk.yaml` (run order in its header); `python -m qc paper --config qc/configs/uk.yaml` writes the UK table with its caveats.

## Running on Kaggle

`notebooks/datamend_qc_kaggle.ipynb` runs the pipeline above on Kaggle from a dataset link (`qc/kaggle_data.py` finds the mounted RF25 files; `qc/kaggle_sync.py` pushes the small results to the `kaggle-results` git branch when asked). Phase 1 runs through the fusion step; you choose the budgets, then phase 2 runs the single test pass and the paper outputs. Several accounts: run the same notebook on each with the same `RUN_NAME` and its own `SEEDS`, then merge the outputs on one account with `MERGE_LINKS` before phase 2 (see the notebook's introduction). `python -m qc test-score --splits test` scores only the test years (the 1901-1950 stress period is a robustness check and most of the scoring time).

## Layout

`config`, `paths`, `grid`, `clients`, `splits`, `stats`, `prepare` (data and splits); `faults`, `extremes`, `benchmark` (benchmark); `baselines`, `untrained`, `neighbours`, `scoring`, `metrics`, `evaluate` (untrained scores, metrics); `models`, `batches`, `trained` (components); `fusion`, `fusion_eval` (fusion, budgets); `federated`; `testscore`; `uk/` (MIDAS study); `paper` (tables, figures, claims); `tests/` (one file per gate).

## Time resolutions (`qc/resolution.py`)

STATUS: the data layer is built and unit-tested on generated arrays (`qc/tests/test_resolution.py`). No model uses it yet, and nothing has run on real RF25. The monthly, seasonal, yearly and decadal models are PROPOSED, NOT BUILT.

- `aggregate(block, year, scale)` turns one calendar year of daily mm into monthly (12), seasonal (June-September) or yearly periods: total, wet-day count and largest day. A period is never filled: too few finite days gives NaN. A block with the wrong number of days for its year is refused.
- `aggregate_labels(...)` turns daily fault labels into period labels: `present` (a faulty day is inside) and `visible` (the period total actually moved).
- `fit_scale_stats(...)` fits the climatological mean, a robust spread and a per-client normalisation on training years only, and refuses other years.
- `corrupt_periods(...)` makes synthetic faults that only exist at period level (a whole month or year scaled, or lost). Labelled only if the total changed.
- `yearly_to_decades(...)` gives decade means for the decadal change-point tests. Missing years are not interpolated.

