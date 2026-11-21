"""Compare ONNX vs TensorFlow reconstructions on fixed seeded windows. Run in the TF venv. Tolerance 1e-4."""
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import tensorflow as tf

W = Path(__file__).parent / "weights"
TOL = 1e-4


def windows() -> np.ndarray:
    rng = np.random.default_rng(12345)
    t = np.linspace(0, 8 * np.pi, 288)
    out = [np.zeros(288), np.sin(t), rng.standard_normal(288), np.sin(t) + rng.normal(0, 0.1, 288)]
    spike = np.sin(t).copy()
    spike[140:150] += 6
    out.append(spike)
    out += [rng.uniform(-3, 3, 288) for _ in range(27)]
    return np.asarray(out, dtype=np.float32)[:, :, None]


def main() -> int:
    x = windows()
    tfm = tf.keras.models.load_model(str(W))
    y_tf = tfm.predict(x, verbose=0)
    sess = ort.InferenceSession(str(W / "model.onnx"), providers=["CPUExecutionProvider"])
    y_ox = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    d_out = float(np.max(np.abs(y_tf - y_ox)))
    mae_tf = np.mean(np.abs(y_tf - x), axis=(1, 2))
    mae_ox = np.mean(np.abs(y_ox - x), axis=(1, 2))
    d_mae = float(np.max(np.abs(mae_tf - mae_ox)))
    res = {"n_windows": int(len(x)), "max_abs_diff_output": d_out, "max_abs_diff_mae": d_mae, "tolerance": TOL, "pass": bool(d_out < TOL and d_mae < TOL)}
    (W / "parity.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
