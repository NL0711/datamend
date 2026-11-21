---
title: Can a Flutter Android app train a small model on the device, and with what framework?
labels: [wayfinder:research]
status: closed
assignee: research agent (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

Establish from official docs and source what is feasible for on-device training inside a Flutter app on Android: TensorFlow Lite on-device training, ONNX Runtime training, ExecuTorch or PyTorch Mobile, Flower (flwr) mobile support, or a plain Dart implementation of a tiny model. Cover Flutter plugin maturity, how weights are exported and imported, Android background execution limits (WorkManager periodic work, constraints for charging, idle and unmetered), and the barometer sensor API in Flutter. Which ML framework `ml-service/qc` uses is a repo fact to check. Output: `docs/research/on-device-training-flutter-android.md`.

## Resolution (2026-11-19)

Findings are in `docs/research/on-device-training-flutter-android.md` (summarising fetch tool, so not verbatim; unconfirmed items are marked UNVERIFIED there). This is a fact-finding result, not a decision; the model and framework choice is made in the model, features and labels ticket.

- `ml-service/qc` is PyTorch; its weights need an export step before any mobile runtime can load them.
- LiteRT has documented on-device training on Android (train, infer, save, restore signatures). CORRECTED by the framework research ticket: this note found no Flutter binding only because it looked at `tflite_flutter`; the `flutter_litert` plugin documents training through `SignatureRunner`, so a Kotlin `MethodChannel` bridge is a fallback, not the only route (UNVERIFIED until built and run). ONNX Runtime has Android training libraries and no Dart binding. ExecuTorch training is "experimental". Flower's Android SDK is behind current Flower. A plain-Dart tiny model is a design inference with no source, not a finding.
- WorkManager (Flutter `workmanager` plugin): minimum periodic interval 15 minutes; constraints include unmetered, charging and idle; Android may delay or skip runs.
- **Constraint on the owner's design:** from Android 9, apps in the background receive no sensor events. A periodic worker cannot read the barometer. Readings must be collected while the app is in the foreground or in a foreground service (which shows a persistent notification), and stored locally for the worker. "Background and unaware" therefore applies to training and upload, not to collection.
- `sensors_plus` exposes a barometer stream in hPa on Android.
- Open: whether `sensors_plus` or a `MethodChannel` works inside the `workmanager` isolate, how to extract raw tensors from a LiteRT checkpoint, OEM reliability of periodic work, whether the target phone has a barometer.
