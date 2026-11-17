#!/usr/bin/env bash
# One-shot training entrypoint for Kaggle / any machine.
#   Kaggle:  !git clone <repo> && bash datamend/ml-service/scripts/kaggle_train.sh train --preset base --epochs 10
# Data: attach the RF25 .nc files as a Kaggle dataset (auto-detected under /kaggle/input),
#       or set DATAMEND_DATA_DIR. Outputs go to /kaggle/working (or $DATAMEND_OUT_DIR).
set -euo pipefail
cd "$(dirname "$0")/.."
python -c "import torch" 2>/dev/null || pip install -q torch
pip install -q -r requirements-train.txt
python -m pytest training -q -x
python -c "import torch; print('cuda:', torch.cuda.is_available())"
python -m training "$@" --out "${OUT_NAME:-run}"
