# On-device training in a Flutter Android app: frameworks, plugins, background limits, barometer (facts from primary sources)

> **Correction (2026-11-19, from `mobile-federated-learning-frameworks.md`):** the finding below that no Flutter binding exposes on-device training is NOT confirmed. This note looked only at `tflite_flutter`. The later note found `flutter_litert` 4.2.0 (published 2026-11-17, repo `google-ai-edge/flutter_litert`, Apache-2.0), whose docs describe training through `SignatureRunner` with `train`, `infer`, `get_weights` and `set_weights` signatures. "Official Google plugin" is UNVERIFIED and it has not been run. Read the rows and statements below that say "no Flutter binding" with this in mind.

Compiled 2026-11-19 for the DataMend phone prototype (wayfinder `phone-fl-prototype`, ticket t02). Question: what is feasible for training a small model on the phone inside a Flutter app, and with what framework. Nothing here was built or run; this is documentation reading only.

## BANNER: what was opened and what was not

OPENED (fetched through a summarising fetch tool, not verbatim page dumps; quotes below are as returned by that tool):
- LiteRT on-device training pages on developers.google.com (overview and conversion guide).
- ONNX Runtime pages: on-device training overview, install page (training section), API index.
- ExecuTorch `extension/training` README on GitHub.
- Flower Android quickstart on flower.ai.
- pub.dev pages: `workmanager`, `sensors_plus`, `tflite_flutter`; the `workmanager` docs on docs.page (quickstart, customization); the `tensorflow/flutter-tflite` GitHub README.
- Android developer docs: WorkManager "define work", Doze and App Standby, sensors overview, environment sensors.
- Flutter docs: background processes, platform channels.

NOT OPENED, snippet-level only (web search result summaries): PyTorch Mobile retirement notice, ExecuTorch GitHub issue 16123, the NVFlare mobile training page, the FedKit repository, a community forum thread on the LiteRT C API. These are marked below.

Pub.dev pages give only relative dates ("about 2 months ago", "12 months ago"), so exact release dates are UNVERIFIED. Sources for all claims are given inline.

## 0. Repo fact: ML framework of `ml-service/qc`

`ml-service/qc` is PyTorch. Evidence (grep of imports, this repo): `import torch`, `from torch import nn`, `torch.nn.functional` in `ml-service/qc/models.py`, `stnet.py`, `trained.py`, `federated.py`, `batches.py`; scikit-learn is used for fusion and scoring (`ml-service/qc/fusion.py`, `scale_scorers.py`, `metrics.py`). No `tensorflow` or `keras` import was found in the grep over `ml-service`. Consequence: weights from `ml-service/qc` are PyTorch state, so they cannot be loaded by TensorFlow Lite or ONNX Runtime without an export step. The MAP already says the phone model is a NEW small model and is not the RF25 QC weights.

## 1. TensorFlow Lite / LiteRT on-device training

Source: https://developers.google.com/edge/litert/examples/on_device_training/overview and https://developers.google.com/edge/litert/conversion/tensorflow/build/ondevice_training (the old tensorflow.org URL returns a 301 to ai.google.dev, then to developers.google.com).

- The model is extended with four functions exposed as signatures at conversion: `train` (one step on a batch), `infer`, `save` (trainable weights to a checkpoint file), `restore` (load weights from a checkpoint).
- "The On-Device Training APIs are available in TensorFlow version 2.7 and higher." Target devices must support local file storage.
- Android is the only mobile platform covered: "On Android, you can perform on-device training with LiteRT using either Java or C++ APIs." Java uses `Interpreter` and `runSignature`. The page does not mention Dart or Flutter.
- Weights: the checkpoint is a file in the app's internal storage; "Anytime you create an Interpreter for a model, if the checkpoint exists, load it", because a new interpreter starts from the original weights. Checkpoints use the TensorFlow 1 format (overview page). Loading can take time depending on variable count and checkpoint size.
- The page recommends running training in the background, for example with WorkManager, and not while the user is active.
- The conversion example sets both `TFLITE_BUILTINS` and `SELECT_TF_OPS`; the page does not state in prose whether Flex ops are required for training, so the op coverage for a tiny dense or GRU model is UNVERIFIED.
- Deprecation: neither LiteRT page mentions deprecation. A web search also found no source declaring it deprecated, but a search summary noted a January 2026 Google blog post on LiteRT that does not mention training (snippet-level, not opened). Treat the long-term maintenance of the training path as UNVERIFIED.
- Snippet-level only: a community forum thread reports the C API does not support the restore-weights operation (user report, undated, not opened).

Flutter plugin maturity (TFLite):
- `tflite_flutter` on pub.dev, version 0.12.1, publisher tensorflow.org, "12 months ago" (https://pub.dev/packages/tflite_flutter). The page does not mention on-device training or a signature runner. It states the "helper library has been deprecated" with a replacement in development at `google/flutter-mediapipe`, and calls itself a work-in-progress fork.
- GitHub README of `tensorflow/flutter-tflite` (https://github.com/tensorflow/flutter-tflite): marked work-in-progress, last dated update shown is 26 April 2023, no mention of training or signature runner.
- So no official Flutter plugin was found that exposes the train/save/restore signatures. Whether `tflite_flutter` 0.12.1 exposes `runSignature` at all is UNVERIFIED (not stated on the pages read; its source was not read).
- Practical route supported by official docs: write the training loop in Kotlin using the Android Java API and call it from Dart through a `MethodChannel` (see section 6).

## 2. ONNX Runtime on-device training

Sources: https://onnxruntime.ai/docs/get-started/training-on-device.html, https://onnxruntime.ai/docs/install/ (training section), https://onnxruntime.ai/docs/api/.

- Offline phase: training artifacts are prepared on a server or desktop "that does not have access to user data" using the ONNX Runtime Training Python artifact generation tools; the artifacts are then deployed to the device. After training, an inference-ready ONNX model can be generated on the device. Federated learning is listed as a use case; aggregation is not described.
- Android packaging: Java/Kotlin package `com.microsoft.onnxruntime:onnxruntime-training-android` on Maven; C and C++ on Android also listed (install page).
- No Dart or Flutter binding is listed on the install page or the API index. A third-party Flutter wrapper may exist; none was assessed. UNVERIFIED.
- The overview page read does not describe how a checkpoint is exported or what files make up the artifact set (it does not name training, eval, optimizer model or checkpoint files). Checkpoint export mechanics are UNVERIFIED from this fetch.

## 3. ExecuTorch and PyTorch Mobile

- ExecuTorch training README (https://github.com/pytorch/executorch/tree/main/extension/training): the on-device training feature is "experimental and under heavy active development", "all the APIs are subject to change", and the state is "a technical preview". The README walkthrough is an XOR network. It does not list supported platforms.
- Snippet-level only: GitHub issue 16123 asks whether backends support runtime weight updates for fine-tuning (status "To triage", no maintainer answer seen); a 2026 arXiv paper and NVIDIA NVFlare docs describe ExecuTorch-based Android training and federated training. These were not opened and are not relied on.
- PyTorch Mobile: search results state the legacy mobile runtime is no longer actively supported and points users to ExecuTorch (snippet-level, official page not opened). PyTorch Mobile is therefore not a candidate. UNVERIFIED at primary-page level.
- Positive for the repo: `ml-service/qc` is PyTorch, so ExecuTorch would be the closest fit for sharing model definitions, but it is the least mature path for training and has no Flutter binding that was found.

## 4. Flower (flwr) mobile support

Source: https://flower.ai/docs/framework/tutorial-quickstart-android.html. The page's only warning block says:
- "The experimental Flower Android SDK is not compatible with the latest version of Flower."
- "Android support is currently being reworked and will be released in 2025."
- "This quickstart tutorial is kept for historical purposes and will be updated once the new Android SDK is released."

That page still carries this text on 2026-11-19 as fetched, so no replacement Android SDK was confirmed. Whether a new SDK shipped elsewhere is UNVERIFIED. No Flutter or Dart client was found in the Flower docs read. The older Kotlin TensorFlow Lite example (https://flower.ai/docs/examples/android-kotlin.html, snippet-level) uses a custom `FedAvgAndroid` strategy that handles serialised byte buffers, which shows weights travel as raw bytes through a custom gRPC client. The community project FedKit (https://github.com/FedCampus/FedKit) was only seen in search results; UNVERIFIED.

Consequence for a degenerate single-client prototype: a Flower client is not required. The update can be sent as plain HTTP from the app to the small aggregation service; this is a design inference, not a source claim.

## 5. Plain Dart implementation of a tiny model

No primary source covers this; it is a design inference. A tiny model (for example logistic regression or a small dense net over a pressure-tendency window) can be trained in pure Dart with `Float32List`/`Float64List`, with no native dependency, and runs inside the same Dart isolate as WorkManager tasks (section 7). Trade-offs: no framework tooling, you own the optimizer and the serialisation, and the exported weights are a plain list of floats that any server can aggregate without a conversion step. Use of Dart's typed lists across `MethodChannel` is documented (section 6).

## 6. Getting weights in and out of the app

- LiteRT: the checkpoint is a file in app-internal storage written by the `save` signature (section 1). Reading it back to send to a server needs your own code (read file bytes on the Kotlin side or via Dart `dart:io`). Format is the TF1 checkpoint, which a server would need TensorFlow to parse; UNVERIFIED how to extract raw tensors without it.
- ONNX Runtime: checkpoint export UNVERIFIED (section 2).
- Flutter to Kotlin bridge: Flutter docs (https://docs.flutter.dev/platform-integration/platform-channels) document `MethodChannel` with the standard codec mapping `Uint8List` to `ByteArray`, `Float32List` to `FloatArray`, `Float64List` to `DoubleArray`, `List` and `Map` to their Kotlin counterparts. Channel methods run on the platform main thread by default; a background `TaskQueue` is documented for off-main-thread handlers. The docs say the channel is not type-safe and recommend Pigeon for new projects.
- Plain Dart: weights are already a `Float32List` or `Float64List`; send as bytes or JSON.

## 7. Android background execution limits

WorkManager (https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started/define-work):
- Minimum repeat interval for periodic work is 15 minutes; the interval is "the minimum time between repetitions" and the exact run time depends on constraints and system optimisation.
- Available constraints: `NetworkType` (for example Wi-Fi is `UNMETERED`), `BatteryNotLow`, `RequiresCharging`, `DeviceIdle`, `StorageNotLow`. With several constraints, work runs only when all are met. If a constraint becomes unmet while running, WorkManager stops the worker and retries later.
- Constraints on periodic work can delay a run or skip it: "even if the defined repeat interval passes, the `PeriodicWorkRequest` will not run until this condition is met... or even skipped if the conditions are not met within the run interval."
- Expedited work and quotas exist but are for short, user-important tasks, not for training (same page).

Doze and App Standby (https://developer.android.com/training/monitoring-device-state/doze-standby):
- In Doze the system "doesn't let JobScheduler run. WorkManager uses JobScheduler internally, so WorkManager tasks don't run" until a maintenance window; windows get less frequent over time while unplugged.
- Plugging in the charger exits Doze and releases apps from App Standby ("When the user plugs the device into a power supply, the system releases apps from the standby state"). This is why a charging constraint fits the plan, but the page does not guarantee a run time.
- Direct battery-optimisation exemption requests are restricted by Google Play policy unless the core function is affected (same page).

Flutter side:
- `workmanager` 0.10.10, publisher fluttercommunity.dev, "about 2 months ago" (https://pub.dev/packages/workmanager). Android and iOS via WorkManager and BGTaskScheduler.
- Docs (https://docs.page/fluttercommunity/flutter_workmanager/quickstart and .../customization): Android needs no extra setup; 15-minute minimum for periodic tasks; tasks run in a separate isolate through a top-level `callbackDispatcher` annotated `@pragma('vm:entry-point')`, so dependencies must be initialised inside the task; constraint fields are `networkType` (`connected`, `unmetered`, `not_required`), `requiresBatteryNotLow`, `requiresCharging`, `requiresDeviceIdle`, `requiresStorageNotLow`, `contentUriTriggers` (Android 7.0+). The docs state that if tasks stop after the app is closed the cause is usually the device battery optimiser, not the plugin.
- Flutter docs (https://docs.flutter.dev/packages-and-plugins/background-processes) confirm Dart can run in a background isolate and that the WorkManager plugin gives persistent processing that survives app restarts and reboots.
- Whether a native plugin (a `MethodChannel` or `sensors_plus`) works from inside the `workmanager` background isolate on Android is UNVERIFIED in the pages read. The quickstart only warns about plugin registration on iOS.
- The sample in the docs shows `requiresDeviceIdle` set to `false`; the combination of charging plus idle plus unmetered is supported by the field list, but its real-world run frequency on OEM devices is UNVERIFIED (OEM battery optimisers are named as the usual cause of missed runs).

## 8. Barometer sensor

- Android: `TYPE_PRESSURE` reports ambient air pressure in hPa or mbar, one value in `event.values[0]` (https://developer.android.com/develop/sensors-and-location/sensors/sensors_environment). It is hardware-based and present only if the manufacturer built it in; "verify at runtime whether an environment sensor exists" using `getDefaultSensor` (null means absent) (same page and sensors overview). The sensors overview says fewer devices have barometers than accelerometers.
- Sampling: the requested delay is only a suggestion; the system and other apps can change it (sensors overview).
- Key limit: "On devices running Android 9 (API level 28) or higher, apps running in the background" do not receive events from continuous-mode sensors, nor from on-change or one-shot sensors. The docs advise sampling in the foreground or in a foreground service (https://developer.android.com/develop/sensors-and-location/sensors/sensors_overview, "Only gather sensor data in the foreground"). Consequence: a periodic WorkManager task cannot read the barometer live on Android 9 and later. Readings must come from a window when the app is in the foreground, or from a foreground service (which shows a notification), then be stored locally for the worker to use. Which reporting mode the barometer uses on a given phone is device-specific and UNVERIFIED, but the page restricts all three modes, so it does not change the conclusion.
- Rate limiting (200 Hz cap, `HIGH_SAMPLING_RATE_SENSORS`) applies to motion and position sensors, not the pressure sensor (sensors overview).
- Flutter: `sensors_plus` 7.1.1, publisher fluttercommunity.dev, "48 days ago" (https://pub.dev/packages/sensors_plus). Exposes a barometer stream (`BarometerEvent`, pressure in hPa); Android supported; some low-end or older devices lack sensors, so add `onError`; Android rate is not guaranteed; the page lists no Android permission for these sensors; barometer not supported on web. The page names both `barometerEvents` and `barometerEventStream`, so the exact current stream name is UNVERIFIED.

## 9. Summary table (what the sources support)

| Option | Android training documented | Flutter binding found | Maturity signal |
|---|---|---|---|
| LiteRT on-device training | Yes (Java, C++; train/save/restore signatures) | No official one; `tflite_flutter` pages do not mention training and call the helper library deprecated | Docs current, training not mentioned in a Jan 2026 blog (snippet) |
| ONNX Runtime training | Yes (Java/Kotlin, C, C++ packages) | None listed | Docs current; export mechanics not seen |
| ExecuTorch training | Preview, platforms not listed | None found | README: experimental, APIs subject to change |
| PyTorch Mobile | n/a | n/a | Reported unmaintained (snippet-level) |
| Flower | Old TFLite example only | None found | Android SDK "being reworked", page unchanged |
| Plain Dart | Not applicable (design inference) | Native | No framework risk; you own the maths |

## 10. Open uncertainties for the next tickets

1. Whether `tflite_flutter` 0.12.1 can call `runSignature` (needed to avoid a Kotlin bridge). Not stated on the pages read.
2. Whether `sensors_plus` or any plugin can be called from the `workmanager` background isolate on Android.
3. Checkpoint extraction: how to get raw tensors out of a LiteRT checkpoint or an ONNX Runtime checkpoint for upload.
4. Whether a new Flower Android SDK was released after the 2025 notice.
5. How reliably periodic work with charging, idle and unmetered constraints runs on real OEM phones.
6. Op support for the chosen tiny architecture under LiteRT training (builtins versus Flex ops).
7. Which barometer reporting mode the target phone uses, and whether the phone has a barometer at all.
