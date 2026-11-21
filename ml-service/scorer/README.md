# Scorer service

ONNX serving of the pretrained `keras-io/timeseries-anomaly-detection` (conv reconstruction autoencoder, input `(288, 1)`, 9,505 parameters), used as is, never retrained. It returns one number per window: the mean absolute reconstruction error. A score only, never a verdict; NOT validated on this platform's data. Scaling, thresholds and the 288-reading rule live in the backend, not here.

The service imports onnxruntime, numpy and fastapi only (no TensorFlow).

## Setup (once)

```
python fetch_weights.py        # model files only -> weights/ (gitignored), revision in weights/SOURCE.json
# in a Python 3.11 venv with requirements-build.txt (TF 2.15, keras 2.15, tf2onnx):
python convert.py              # weights/model.onnx + weights/model_info.json
python parity.py               # ONNX vs TensorFlow on seeded windows, tolerance 1e-4 -> weights/parity.json
```

## Run

```
pip install -r requirements.txt
SCORER_SECRET=change-me uvicorn app:create_app --factory --port 8000
```

`SCORER_SECRET` is required (clients send it as `X-Scorer-Secret`); `SCORER_ALLOW_NO_SECRET=1` runs without auth, local only.

- `GET /health` -> `{status, model:{id, revision, format}}`
- `POST /score` `{"windows": [[288 floats], ...]}` (1 to 8 windows; wrong length or non-finite values -> 422) -> `{"errors": [...], "model": {...}}`

Tests: `python -m pytest tests` (the real-model test is skipped when `weights/model.onnx` is absent).

## Docker

```
docker build -t datamend-scorer .      # needs weights/model.onnx and SOURCE.json in weights/ first
docker run -p 8000:8000 -e SCORER_SECRET=change-me datamend-scorer
```

Or mount a weights directory at `/app/weights` (set `SCORER_WEIGHTS_DIR` to change the path); `PORT` is read from the environment.

## Render free tier

Web service from this Dockerfile (root directory `ml-service/scorer`), env `SCORER_SECRET`. The weights are not in git, so build them first and either commit-free deploy via a prebuilt image, or run fetch and convert in a CI step before the build. Free services sleep when idle, so the first call after a pause pays a cold start; the backend must keep its timeout and the "scorer not available" fallback. Measured footprint is in the section below.

## Measured (this laptop, onnxruntime 1.32, 1 thread; `assumed` for any other hardware)

- Process memory after loading the model: about 90 MB RSS (about 100 MB after requests), including FastAPI and the test client; far under 512 MB.
- Cold start (imports and model load): about 1.7 s locally; Render's start and wake time were NOT measured.
- Latency in-process: about 8 ms for 1 window, about 12 ms for 8 windows (no network).
- ONNX vs TensorFlow parity: max abs difference 1.5e-6 on outputs and 2.4e-7 on the error (32 seeded windows).
