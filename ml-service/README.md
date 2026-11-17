````markdown
# ml-service

FastAPI anomaly-detection service using TSDB datasets and trained rainfall anomaly detectors.

## Setup

```bash
uv sync
````

Start the API:

```bash
uv run uvicorn main:app --reload
```

API:

```text
http://localhost:8000
```

## Endpoints

* `POST /api/v1/analyze` — detect anomalies above a threshold.
* `POST /api/v1/scores` — return anomaly scores for every timestamp.
* `POST /api/v1/datasets/live` — fetch a fresh dataset from a live public API
  (`source: "weather"` via Open-Meteo, `source: "crypto"` via CoinGecko) and
  ingest it as a normal dataset, ready for profiling/validation/analysis.
* `POST /api/v1/validate/suggest` — auto-detect a dataset's columns and
  propose default rule-based validation rules (range/not-null/data-type).
* `POST /api/v1/validate` — run rule-based validation (Objective #2: range
  check, not-null, data type, uniqueness, cross-field) against a dataset and
  return a `ValidationReport` with a 0–100 quality score.

See `validation/rule_based.py` and `datasets/live_api_loader.py` for details.

## Detectors (trained models)

Detectors are **trained from scratch** on rainfall data (see `training/`); nothing is run
zero-shot or downloaded at inference time. The API resolves `detector` through
`detectors/registry.py`:

| Name | Needs | What it is |
| --- | --- | --- |
| `rainfall_ae` | `RAINFALL_AE_ARTIFACT=<artifact dir>` | one trained model (`rainnet`, multi-granularity `msnet`, or the `lstm_ae` baseline) |
| `rainfall_ensemble` | `RAINFALL_ENSEMBLE_ARTIFACTS=<dir>,<dir>,...` | late-fusion ensemble of several trained artifacts |

The API score is in `[0, 1]`, monotone in the model's calibrated score, with the model's own
threshold mapped to `0.8` (the default API threshold). Thresholding stays in the API layer:
`anomaly = score >= threshold`. A known detector with no artifact configured returns HTTP 503;
an unknown name returns 400. Detectors expect rainfall in mm.

```bash
uv run python -m training train --preset smoke --epochs 2 --max-train-years 3 --out artifacts/smoke
RAINFALL_AE_ARTIFACT=artifacts/smoke uv run uvicorn main:app
```

See `../docs/ARCHITECTURE.md` for the model, the multi-granularity design and the GPU runbook.

TSDB downloads and caches datasets automatically.

## Missing Value Handling

The detectors do not support NaN values, so missing values must be handled explicitly.

Supported strategies:

* `reject` — default; returns HTTP 400 if NaNs are present.
* `ffill` — forward-fill, then back-fill leading NaNs.
* `bfill` — backward-fill, then forward-fill trailing NaNs.
* `mean` — per-column mean.
* `interpolate` — linear interpolation with edge filling.

No missing-value handling is performed automatically.

Example:

```json
{
  "missingValueHandling": {
    "strategy": "ffill"
  }
}
```

## PyGrinder Corruption

[PyGrinder](https://github.com/WenjieDu/PyGrinder) can optionally introduce synthetic missing values.

Supported methods:

```text
mcar
mar_logistic
mnar_x
mnar_t
mnar_nonuniform
rdo
seq_missing
block_missing
```

Example:

```json
{
  "corruption": {
    "enabled": true,
    "method": "mcar",
    "params": {
      "p": 0.1
    }
  },
  "missingValueHandling": {
    "strategy": "ffill"
  }
}
```

The response reports the actual missing rate:

```json
{
  "missingRate": 0.1003,
  "missingValueHandling": "ffill"
}
```

Original TSDB data is never modified.

## Example Request

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "analysisId": "ett-001",
    "datasetName": "ETTh1",
    "columns": ["HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL", "OT"],
    "detector": "rainfall_ae",
    "threshold": 0.8,
    "corruption": {
      "enabled": true,
      "method": "mcar",
      "params": {"p": 0.1}
    },
    "missingValueHandling": {
      "strategy": "ffill"
    }
  }'
```

## Evaluation

A basic evaluation can be run with (`--detector` picks a registry detector; it needs a trained artifact):

```bash
uv run python -m evaluation.experiment_runner \
  --dataset ETTh1 \
  --anomaly-rate 0.01 \
  --seed 0
```

With 10% MCAR missingness:

```bash
uv run python -m evaluation.experiment_runner \
  --dataset ETTh1 \
  --anomaly-rate 0.01 \
  --seed 0 \
  --missingness mcar \
  --p 0.10 \
  --strategy ffill
```

The evaluation reports:

```text
Precision
Recall
F1
PR-AUC
ROC-AUC
```

## Testing

Run all tests:

```bash
uv run pytest -q
```

Run unit tests:

```bash
uv run pytest tests/unit/ -q
```

Run integration tests:

```bash
uv run pytest tests/integration/ -q
```

Run evaluation tests:

```bash
uv run pytest tests/unit/metrics/ -q
```

Run API and corruption tests:

```bash
uv run pytest tests/integration/api/ tests/unit/corruption/ -q
```

Run the training pipeline, detector and registry tests:

```bash
uv run pytest training detectors -q
```

## Synthetic Dataset Generation

The `datasets/synthetic` module provides synthetic and semi-synthetic dataset generation for controlled evaluation with ground-truth labels.

### Quick Start

```bash
# Generate univariate synthetic dataset
uv run python scripts/generate_synthetic.py generate \
  --num-samples 100 \
  --seq-len 1000 \
  --anomaly-ratio 1.0 \
  --output synthetic_univariate.pkl

# Generate multivariate synthetic dataset (5 features)
uv run python scripts/generate_synthetic.py generate \
  --num-samples 50 \
  --seq-len 1000 \
  --anomaly-ratio 1.0 \
  --multivariate \
  --num-features 5 \
  --output synthetic_multivariate.pkl

# Generate with specific anomaly types
uv run python scripts/generate_synthetic.py generate \
  --num-samples 100 \
  --metrics spike,drift,trend_break \
  --output synthetic_spike_drift.pkl
```

### Semi-Synthetic Evaluation (TSDB + Injected Anomalies)

```bash
# Inject anomalies into ETTh1 with clean window detection
uv run python scripts/generate_synthetic.py inject-tsdb ETTh1 \
  --intensity 3.0 \
  --count 5 \
  --placement random \
  --output semi_synthetic_etth1.pkl

# Target specific sensors
uv run python scripts/generate_synthetic.py inject-tsdb ETTh1 \
  --sensors HUFL,MUFL \
  --metrics spike,drift \
  --output semi_synthetic_targeted.pkl
```

### Benchmarking

```bash
# Run benchmark on synthetic data
uv run python scripts/generate_synthetic.py benchmark \
  --type synthetic \
  --multivariate \
  --num-features 5 \
  --strategy best_f1

# Run benchmark on semi-synthetic data
uv run python scripts/generate_synthetic.py benchmark \
  --type semi_synthetic \
  --tsdb-dataset ETTh1 \
  --strategy best_f1

# Run with fixed threshold
uv run python scripts/generate_synthetic.py benchmark \
  --type synthetic \
  --threshold 0.8

# Save baseline for regression testing
uv run python scripts/generate_synthetic.py benchmark \
  --type synthetic \
  --save-baseline rainfall_ae_synthetic_baseline
```

### CI/CD Regression Testing

```bash
# Run CI benchmarks (compares against baselines)
uv run python scripts/generate_synthetic.py ci-benchmark

# Update baselines after verified improvements
uv run python scripts/generate_synthetic.py ci-benchmark --update-baselines

# Generate markdown report
uv run python scripts/generate_synthetic.py ci-benchmark --output-report ci_report.md
```

### Evaluation with Synthetic Data

```bash
# Run evaluation on synthetic data
uv run python -m evaluation.experiment_runner \
  --dataset-type synthetic \
  --num-samples 100 \
  --seq-len 1000 \
  --anomaly-rate 1.0 \
  --seed 42

# Run evaluation on multivariate synthetic data
uv run python -m evaluation.experiment_runner \
  --dataset-type synthetic \
  --multivariate \
  --num-features 5 \
  --num-samples 50 \
  --seq-len 1000 \
  --anomaly-rate 1.0

# Run evaluation on semi-synthetic data
uv run python -m evaluation.experiment_runner \
  --dataset-type semi_synthetic \
  --dataset ETTh1 \
  --injection-intensity 3.0 \
  --injection-count 5
```

### Supported Anomaly Types

```bash
uv run python scripts/generate_synthetic.py list-anomalies
```

Output:
- `spike` - Point anomaly (instantaneous)
- `drop` - Point drop anomaly
- `drift` - Gradual drift
- `trend_break` - Trend slope change
- `seasonality_break` - Seasonality disruption
- `noise_increase` - Increased variance
- `level_shift` - Permanent step change
- `pattern_change` - Frequency/phase shift

### Supported Pattern Types

```bash
uv run python scripts/generate_synthetic.py list-patterns
```

Output:
- `stationary` - No trend, no seasonality
- `linear_trend` - Linear trend
- `quadratic_trend` - Quadratic trend
- `single_seasonal` - Single seasonality
- `multi_seasonal` - Multiple seasonalities
- `trend_and_seasonal` - Trend + seasonality
- `high_noise` - High noise AR process
- `low_noise` - Low noise AR process

## Multi-scale, label-free ensemble

Goal: catch anomalies that show up at different temporal and spatial scales, and combine detectors **without
a supervised meta-model trained on synthetic labels**. **Nothing in this section has been trained at full size
and no performance claim is made.** Only unit tests and CPU smoke runs have been executed (they prove the code
runs, shapes are right, losses are finite, and checkpoints save and reload).

### Architecture

```
daily window (log1p, NaN-masked, causal)
  |- scalenet (arch "scalenet", new) ------------------------------ training/multiscale.py
  |     branches at scales [1, 5, 30] days (causal trailing means + parallel 3/5/7 kernels)
  |     -> attention-weighted scale fusion (weights exposed; any scale can be masked for ablation)
  |     + neighbourhood (3x3/5x5 patch, centre cell excluded, + neighbour mean/max), static (lat, lon,
  |       day-of-year, elevation if available), optional station embedding  -> intermediate fusion (gated)
  |     + coarse stream: climatology + causal low-frequency component -> reconstructs the clean trend;
  |       the residual (daily - low-frequency) feeds the fine branches
  |     -> shared trunk: BiLSTM + attention + zero-inflated Gamma head + supervised anomaly head
  |- rainnet, lstm_baseline (existing)
branches -> per-branch normalization on CLEAN data -> label-free fusion -> threshold on clean validation years
  rule (daily rules)   stat (per-cell per-day climatological bound)   lstm_baseline   rainnet
  multiscale   supervised_head (one branch among the others)                   ensemble/
cross-scale rules (daily vs monthly/pentad totals, climatological range) live in validation/cross_scale.py
```

| Piece | File | Switch |
| --- | --- | --- |
| Multi-scale temporal model | `training/multiscale.py` | `--preset scalenet`, `--scales 1 5 30`, `--single-scale` |
| Neighbourhood patch | `training/sampler.py` | config `patch` (0, 3 or 5) |
| Elevation | `training/elevation.py` | `--elevation file.npy` (otherwise logged and marked unavailable) |
| Station branch (interface + stub) | `training/stations.py` | `--use-stations` (stub: logs a warning, stations unavailable) |
| Statistical baseline branch | `ensemble/statbaseline.py` | built from training years when `ensemble` runs |
| Fusion rules | `ensemble/fusion.py` | `--fusion mean_rank`, `max`, `prob_avg` or `owa`; `--owa-orness` |
| Normalization | `ensemble/fusion.py` | percentile rank; temperature-scaled likelihood for the Gamma head |
| Threshold calibration | `ensemble/fusion.py` | `--threshold-method fpr` or `events`; `--target-fpr` (clean validation years) |
| Cross-scale rules | `validation/cross_scale.py` | pass totals / ranges to `cross_scale_flags` |
| Metrics | `evaluation/rainfall_metrics.py` | point-wise PR-AUC, affiliation F1, event/range metrics, random baseline, FPR on clean |
| Runner | `training/ensemble_run.py` | `python -m training ensemble ...` |

Config entries (`TrainConfig`): `arch`, `scales`, `single_scale`, `patch`, `coarse_weight`, `use_elevation`,
`use_stations`. Presets: `scalenet`, `scalenet_single`, `scalenet_large`; ensemble presets `smoke`, `ensemble`,
`ensemble_large` (members are trained on the same prepared data; a common window and patch size are enforced).

### Leakage rules (enforced and tested)

- Climatology, the normalization scale, the statistical-baseline bound, station affine parameters and the
  rank-normalization reference are fit on **training years only**.
- The operating threshold is calibrated on **clean validation years**. Test years never fit anything.
- Every aggregate (pentad, monthly, low-frequency) is a causal trailing mean inside the window, so it never
  includes days after the position it describes. The neighbourhood patch excludes the centre cell.
- `training/leakage.py` records which years each statistic used; the tests fail if any statistic uses the wrong
  split (including by perturbing val/test data and checking that nothing fitted moves).

### Validated vs hypothesis

Validated by unit tests (these are properties of the code, not of model quality): causal aggregation, NaN-mask
handling, no centre leakage in the patch, leakage guards, normalizer/fusion/threshold behaviour on toy data,
cross-scale rules, metric functions on toy arrays, checkpoint save/reload, and that every component runs end to end.

**Hypotheses, not facts (to test on the training machine):**
- multi-scale beats single-scale on real anomalies (use `scale_ablation` and the `scalenet_single` member);
- label-free fusion beats the best single branch, and `owa`/`max`/`mean_rank` differ meaningfully (`fusion_variants`);
- the supervised head generalizes to held-out anomaly kinds (`--holdout`);
- rank is an acceptable stand-in for a probability in `prob_avg`;
- injected-anomaly performance transfers to real IMD errors (RF25 has no human QC labels);
- `affiliation` follows the published definition exactly: **cross-check it against the reference
  `affiliation-metrics` package before quoting numbers**;
- the "monsoon onset" breakdown is a calendar proxy (June), not a per-region onset date;
- multi-teacher rank distillation is **not implemented** (skipped on purpose).

### Assumptions made

No station data, no elevation file and no monthly/pentad totals ship with the repo, so: stations are an interface
plus a logging stub; elevation is optional and marked unavailable when absent; the cross-scale rules need totals
passed in and otherwise fire nothing. Pentad = `(day_of_year - 1) // 5`. The rule branch in the ensemble uses the daily
rules (negative, implausibly large, stuck runs) because windows carry no aggregate totals; the cross-scale rules
are meant for the API/real-data path. Normalizers are fit on clean training-year windows, but the models were
trained on those years, so their training-year scores are optimistic; the validation-year threshold absorbs that.
Region breakdown uses latitude bands (no shapefile). The ensemble is not yet exposed through the API registry.

### On the training machine

Setup (one time; adjust the CUDA index to the installed driver):

```bash
cd ml-service
uv sync
uv pip install torch --index-url https://download.pytorch.org/whl/cu124
uv run python -c "import torch; print(torch.cuda.is_available())"   # must print True
uv run pytest training ensemble validation detectors evaluation/tests/test_rainfall_metrics.py -q
```

Sanity run (CPU, about a minute; proves wiring only):

```bash
uv run python -m training ensemble --preset smoke --fusion owa --seeds 0 --epochs 1 --max-train-years 2 --out artifacts/smoke-ensemble
```

Full training, **fixed seed list, every seed reported (no best-of-N)**:

```bash
uv run python -m training ensemble --preset ensemble_large --fusion mean_rank --scales 1 5 30 \
    --seeds 0 1 2 3 4 --epochs 30 --out artifacts/ens-main
```

Each run writes `results.json` (all seeds, mean/std, per-seed details) and `seed_<k>/` (member models + fusion
pipeline). The details already contain the fusion ablations, so they need no retraining: every fusion rule, each
branch dropped, each branch alone, plus per-kind, per-season (monsoon onset separate) and per-region breakdowns and
the false-positive rate on clean data.

Ablations that need their own training run:

```bash
# held-out anomaly kinds (excluded from training; per-kind results flag them seen=false)
uv run python -m training ensemble --preset ensemble_large --seeds 0 1 2 3 4 --epochs 30 \
    --holdout zeroed,repeat --out artifacts/ens-holdout
# single-scale vs multi-scale: the preset already trains `scalenet_single` as a standalone ablation member;
# to make the *fused* multi-scale branch single-scale instead:
uv run python -m training ensemble --preset ensemble_large --seeds 0 1 2 3 4 --epochs 30 --single-scale \
    --out artifacts/ens-single-scale
# other fusion rules as the primary rule (all rules are also in fusion_variants of every run)
for r in max prob_avg owa; do
  uv run python -m training ensemble --preset ensemble_large --fusion $r --seeds 0 1 2 3 4 --epochs 30 --out artifacts/ens-$r
done
# event-budget threshold instead of a point FPR target
uv run python -m training ensemble --preset ensemble_large --threshold-method events --seeds 0 1 2 3 4 --epochs 30 \
    --out artifacts/ens-events
# optional covariate
uv run python -m training ensemble --preset ensemble_large --elevation path/to/elevation_129x135.npy \
    --seeds 0 1 2 3 4 --epochs 30 --out artifacts/ens-elev
```

Single models (no fusion):
`uv run python -m training train --preset scalenet_large --set device=cuda --epochs 30 --out artifacts/scalenet-large`
(add `--scales 1 5 30`, `--single-scale`, `--holdout ...`). Sweep:
`uv run python -m training sweep --preset scalenet --grid '{"hidden":[128,256],"lr":[1e-3,2e-3]}' --epochs 8 --out artifacts/sweep-scalenet`.
Artifacts are large (the stat baseline bound is about 25 MB per seed) and should not be committed.

## Training on Kaggle / any machine

The repo contains code only; the RF25 `.nc` files (~870 MB) and run outputs are git-ignored.

1. Upload the `RF25_ind<year>_rfp25.nc` files once as a Kaggle Dataset and attach it to the notebook
   (any machine: put them anywhere and set `DATAMEND_DATA_DIR`).
2. In the notebook (GPU on):
   ```bash
   !git clone https://github.com/NL0711/datamend.git && cd datamend && git checkout <branch>
   !bash datamend/ml-service/scripts/kaggle_train.sh train --preset base --epochs 10
   ```
   The script installs `requirements-train.txt`, runs the training unit tests, then trains.
   The data dir is auto-detected (`--data-dir`, `$DATAMEND_DATA_DIR`, `../data`, `/kaggle/input/**`);
   outputs land in `/kaggle/working/` (or `$DATAMEND_OUT_DIR`), so Kaggle's "Output" tab keeps the artifact.
3. Any `python -m training ...` command from the CLI docstring works unchanged from `ml-service/`.

## Downloading UK MIDAS Open daily rainfall

`scripts/download_midas.py` downloads the UK Met Office MIDAS Open daily rainfall files from the CEDA archive (used by the separate real-label study; see `docs/qc-system-spec.md`, section 12). It uses the standard library only.

1. Create a free CEDA account and generate an access token at <https://services.ceda.ac.uk/account/token/>.
2. Copy `.env.example` to `.env` in `ml-service/` and paste the token after `CEDA_TOKEN=`. `.env` is ignored by git. Setting `CEDA_TOKEN` in the shell works too.
3. From `ml-service/`:
   ```bash
   python scripts/download_midas.py --check                      # test the token
   python scripts/download_midas.py --county devon --dry-run     # count files
   python scripts/download_midas.py --county devon cornwall      # download
   ```

- `--mode pairs` (default) fetches the original records that QC changed and the QC'd file for the same station-year. `--mode full` fetches every file, which gridding needs.
- Files go to `$DATAMEND_DATA_DIR/midas-open/uk-daily-rain-obs/`, or `ml-service/data/midas-open/uk-daily-rain-obs/` by default; `--out` overrides it.
- Existing files are skipped, so an interrupted run can be restarted. Tokens expire after a few days; the script says so when CEDA rejects one.
