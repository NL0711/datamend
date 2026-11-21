"""Scorer service: ONNX export of keras-io/timeseries-anomaly-detection, used as is (never retrained).

Imports onnxruntime, numpy, fastapi only; never tensorflow. Returns one number per window: the mean
absolute reconstruction error. It is a score only, never a verdict. Not validated (see AGENTS.md section 9).
Run: uvicorn app:create_app --factory --host 0.0.0.0 --port $PORT
"""
import hmac
import json
import os
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

WINDOW = 288
MAX_WINDOWS = 8
WEIGHTS = Path(os.environ.get("SCORER_WEIGHTS_DIR", Path(__file__).parent / "weights"))
MODEL_ID = "keras-io/timeseries-anomaly-detection"


class ScoreRequest(BaseModel):
    windows: list[list[float]]


def _model_info() -> dict:
    revision = "unknown"
    src = WEIGHTS / "SOURCE.json"
    if src.exists():
        revision = json.loads(src.read_text()).get("revision", "unknown")
    return {"id": MODEL_ID, "revision": revision, "format": "onnx"}


def create_app(session=None, secret: str | None = None) -> FastAPI:
    """`session` is anything with run(None, {name: array}) and get_inputs(); default loads weights/model.onnx."""
    if secret is None:
        secret = os.environ.get("SCORER_SECRET", "")
    if not secret and os.environ.get("SCORER_ALLOW_NO_SECRET") != "1":
        raise RuntimeError("SCORER_SECRET is not set (set SCORER_ALLOW_NO_SECRET=1 to run without auth, local only)")
    if session is None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        session = ort.InferenceSession(str(WEIGHTS / "model.onnx"), opts, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    info = _model_info()
    app = FastAPI(title="DataMend scorer")

    def auth(x_scorer_secret: str | None = Header(default=None)) -> None:
        if not secret:
            return
        if x_scorer_secret is None or not hmac.compare_digest(x_scorer_secret.encode(), secret.encode()):
            raise HTTPException(status_code=401, detail="bad or missing X-Scorer-Secret")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": info}

    @app.post("/score", dependencies=[Depends(auth)])
    def score(req: ScoreRequest) -> dict:
        if not 1 <= len(req.windows) <= MAX_WINDOWS:
            raise HTTPException(status_code=422, detail=f"need 1 to {MAX_WINDOWS} windows")
        for i, w in enumerate(req.windows):
            if len(w) != WINDOW:
                raise HTTPException(status_code=422, detail=f"window {i} has {len(w)} values, need {WINDOW}")
        x = np.asarray(req.windows, dtype=np.float32)
        if not np.isfinite(x).all():
            raise HTTPException(status_code=422, detail="non-finite values")
        x = x[:, :, None]
        y = session.run(None, {input_name: x})[0]
        errors = np.mean(np.abs(y - x), axis=(1, 2))
        return {"errors": [float(e) for e in errors], "model": info}

    return app
