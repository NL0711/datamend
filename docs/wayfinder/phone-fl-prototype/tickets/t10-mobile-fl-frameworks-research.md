---
title: Which mobile federated-learning frameworks exist, and which fits an Android prototype on free tiers?
labels: [wayfinder:research]
status: closed
assignee: research agent (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

The owner asked (2026-11-19) to use any app framework that helps with federated learning, relaxing "it will be a Flutter app". From primary sources, survey frameworks that give a phone client, a server side, or both: Flower (including any new Android or Kotlin SDK), FedML mobile, NVIDIA FLARE mobile, FedKit, TensorFlow Federated, PySyft/OpenMined mobile clients, Google's federated compute stack, and any others found. For each: whether a real Android client exists and trains on-device (not only simulation), last release and maintenance status, licence, how it integrates with Flutter (or whether a native Android app is required), what the server needs (language, memory, free-tier fit), how small models and a few clients are handled, and whether it costs money. Re-verify the two earlier findings that Flower's Android SDK lagged current Flower and that no Flutter binding trains on-device. Output: `docs/research/mobile-federated-learning-frameworks.md`. Feeds the model, update/aggregation and app-shape tickets.

## Resolution (2026-11-19)

Findings are in `docs/research/mobile-federated-learning-frameworks.md` (GitHub and pub.dev facts from their APIs, web pages through a summarising fetch tool; nothing installed or run, so "works" means "documented"; unverified items are marked there). A fact-finding result, not a decision; the choice is made in the update, aggregation and storage ticket and the app-shape ticket.

- Correction to the earlier on-device note: `flutter_litert` 4.2.0 (2026-11-17, Apache-2.0, publisher `hugo.ml`; "official Google plugin" UNVERIFIED) documents on-device training through `SignatureRunner` (`train`, `infer`, `get_weights`, `set_weights`), with weights as Dart lists. The earlier note looked only at `tflite_flutter`.
- Flower: framework maintained (1.44.0, 2026-11-18), but the Android SDK is declared incompatible and unreleased (confirmed); no Flutter client except the unmaintained community FedKit.
- NVFlare 2.9.1 has a real Android client (Kotlin plus ExecuTorch, source-only, API 29+), but it is heavy for 3 phones, native Android only, and sits on preview-level ExecuTorch training.
- FedKit (last commit 2024-02), FedML (2023, tied to a commercial platform), TensorFlow Federated (simulation only), Google federated compute (no usable server), PySyft (no mobile client found): not usable.
- Derived conclusion (not a decision): for 3 phones and 57 parameters, `flutter_litert` plus a plain HTTP upload plus a server-side weighted mean covers the need; leaving Flutter gains no usable ready-made federated client except NVFlare.
- Open: whether the 5 to 8 to 1 net's training graph converts with builtin LiteRT ops only (the README example is a linear model; needs a real build); whether the plugin works inside a `workmanager` isolate; the plugin's young age and single main contributor; free-tier server fit for Flower and NVFlare; React Native and Kotlin Multiplatform not searched.
