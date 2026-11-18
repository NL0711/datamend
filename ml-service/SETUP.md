# Setting up the rainfall QC work on a new machine

This covers the rainfall anomaly-detection and QC work in `ml-service/` on branch `main`: Python environment, data, and a check that everything runs. It does not cover the DataMend web app (backend, frontend, hardware); for that see the repository's top-level `README.md`.

**What exists today:** the training package (`python -m training ...`), its tests, the Kaggle notebook and the MIDAS download script. **QC system:** built as `ml-service/qc/` (gates 0-9 of [`docs/qc-system-spec.md`](../docs/qc-system-spec.md)) and tested on small synthetic worlds only; it has not been run on real RF25 or MIDAS data. See [`qc/README.md`](qc/README.md). There is no single `python -m qc run`; each step is its own command.

## 1. Get the code

```bash
git clone https://github.com/NL0711/datamend.git
cd datamend
git checkout main
cd ml-service
```

All commands below are run from `ml-service/`.

## 2. Python environment

Python 3.10 or newer.

```bash
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# Linux / macOS:         source .venv/bin/activate
```

Install PyTorch first, choosing the build for your machine (CPU, or the CUDA version of your GPU) from <https://pytorch.org/get-started/locally/>. Then:

```bash
pip install -r requirements-train.txt
```

On Kaggle and Colab, PyTorch is already installed; skip that step.

## 3. Data

The folder layout is described in [`data/README.md`](data/README.md). The empty folders are already in the repository.

### RF25 (India, main study)

Copy the 125 files `RF25_ind<year>_rfp25.nc` (1901-2025, about 6.2 GB; the configured years need all of them) into `data/rf25/`.

The files are not downloaded by any script here. Copy them from a machine that has them, or attach them as a Kaggle dataset (see section 6).

### UK MIDAS Open (separate real-label study)

1. Create a free CEDA account and generate an access token at <https://services.ceda.ac.uk/account/token/>.
2. Copy `.env.example` to `.env` and paste the token after `CEDA_TOKEN=`. `.env` is ignored by git; never commit a token.
3. Download:
   ```bash
   python scripts/download_midas.py --check                    # is the token accepted?
   python scripts/download_midas.py --county devon --dry-run   # how many files?
   python scripts/download_midas.py --county devon             # about 16,000 files, about 310 MB
   ```

- The default mode (`pairs`) fetches only station-years in which QC changed something. Add `--mode full` to fetch every file, which the gridding step in the spec needs.
- Tokens expire after a few days. When the script reports that CEDA rejected the token, generate a new one.
- An interrupted download can simply be run again; existing files are skipped.

### Keeping data somewhere else

Set `DATAMEND_DATA_DIR` to a folder with the same layout as `data/` (in the shell, or in `.env` for the download script). Set `DATAMEND_OUT_DIR` to choose where run outputs go; the default is the current folder, so `--out artifacts/run1` lands in `ml-service/artifacts/run1`.

## 4. Check the setup

```bash
python -m pytest training -q
```

The training tests run in under a minute (`python -m pytest -q` runs everything, including the metric and rule tests). They use generated data, so they pass without RF25.

Then a short training run on the real data:

```bash
python -m training train --preset base --epochs 1 --max-train-years 1 --out artifacts/smoke
```

- It should print the years found (`years=1901-2023 missing=[]`), `land_cells=4964`, one epoch, then validation and test scores.
- On a laptop CPU this took about five minutes. With a GPU add `--set device=cuda`.
- The scores from this run mean nothing: one training year, one epoch, and the older training package's own year split, which is not the split fixed in the spec.

If it stops with "No RF25_ind*_rfp25.nc files found", the files are not in `data/rf25/`; pass `--data-dir <folder>` or set `DATAMEND_DATA_DIR`.

## 5. Running on one machine with a single GPU

```bash
python -m training train --preset base --epochs 10 --set device=cuda --out artifacts/run1
```

Other commands (`sweep`, `ensemble`, other presets) are listed at the top of `training/__main__.py` and in `README.md`.

## 6. Running on Kaggle

**The QC system:** use `notebooks/datamend_qc_kaggle.ipynb`. Paste the Kaggle link of the RF25 dataset into `DATASET_LINK`, attach the dataset (Add Input), turn on a GPU and Internet. It pulls the latest commit of the branch from git, runs the whole pipeline in two phases (the budgets are yours to choose between them), and can push the small results to the `kaggle-results` branch. Start with `SMOKE = True`. `datamend_qc_kaggle.ipynb` has not been run on Kaggle yet. The steps below are for the older `training` package.

1. Upload the RF25 files as a Kaggle dataset and attach it to the notebook. It is found automatically under `/kaggle/input`.
2. Either open `notebooks/datamend_training.ipynb`, or run in a cell:
   ```
   !git clone https://github.com/NL0711/datamend.git && cd datamend && git checkout main
   !bash datamend/ml-service/scripts/kaggle_train.sh train --preset base --epochs 10
   ```
3. Outputs go to `/kaggle/working`.

- For a private repository, supply a GitHub token through Kaggle Secrets; do not paste it into the notebook.
- The notebook was tested locally as a script. It has not been run on Kaggle.

## 7. Where things are

| what | where |
|---|---|
| Build spec for the QC system | `docs/qc-system-spec.md` |
| Standing evaluation rules | `docs/qc-evaluation-protocol.md` |
| Vocabulary | `CONTEXT.md` |
| Research notes (several marked unverified) | `docs/research/` |
| Data layout | `ml-service/data/README.md` |
| Training package | `ml-service/training/` |
| MIDAS download script | `ml-service/scripts/download_midas.py` |
| Environment template | `ml-service/.env.example` |
