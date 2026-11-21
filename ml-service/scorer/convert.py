"""Load the SavedModel (TensorFlow 2.15 + keras 2.15 + tf2onnx), record its structure, export weights/model.onnx.

Run in a build-time venv only; the service itself never imports tensorflow.
"""
import json
from pathlib import Path

import tensorflow as tf
import tf2onnx

W = Path(__file__).parent / "weights"


def main() -> None:
    model = tf.keras.models.load_model(str(W))
    model.summary()
    info = {
        "tensorflow": tf.__version__,
        "params": int(model.count_params()),
        "input_shape": [list(i.shape) for i in model.inputs] if hasattr(model, "inputs") else None,
        "output_shape": list(model.output_shape),
        "layers": [{"name": l.name, "type": type(l).__name__, "output_shape": str(l.output_shape)} for l in model.layers],
    }
    spec = (tf.TensorSpec((None, 288, 1), tf.float32, name="input"),)
    tf2onnx.convert.from_keras(model, input_signature=spec, opset=13, output_path=str(W / "model.onnx"))
    (W / "model_info.json").write_text(json.dumps(info, indent=2))
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
