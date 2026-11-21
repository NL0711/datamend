# Mobile federated-learning frameworks: what exists for a real Android client, and what fits 3 phones on free tiers (primary sources)

Compiled 2026-11-19 for the DataMend phone prototype (wayfinder `phone-fl-prototype`, ticket t10). Question: which frameworks give a phone client, a server side, or both, and which fits a 5-8-1 network (57 parameters) on 3 real Android phones with a free-tier server. Flutter is the default UI; the owner is open to other app frameworks. Nothing here was built or run; this is reading of documentation, source trees and registries only. Today's date for all "read" stamps is 2026-11-19.

This note makes no novelty claim (`AGENTS.md` section 5). Every framework below is existing work.

## BANNER: what was opened and what was not

Method note: GitHub facts (licence, last commit, release dates, file trees, file contents) were read through the GitHub REST API with the `gh` CLI, which returns the repository's own data. pub.dev facts come from the pub.dev JSON API and package pages. Web pages were read through a summarising fetch tool, not verbatim, and quotes are as returned. Nothing was installed, built or run.

OPENED (read 2026-11-19):
- Flower: GitHub repo `adap/flower` metadata, latest release, file tree, commit history of `framework/kotlin`, `framework/swift`, `examples/android`, `examples/android-kotlin`, `framework/kotlin/flwr/.../Grpc.kt`, `framework/docs/source/tutorial-quickstart-android.rst`; the live pages https://flower.ai/docs/ and https://flower.ai/docs/framework/tutorial-quickstart-android.html.
- NVIDIA FLARE: `NVIDIA/NVFlare` metadata, release, file tree, `docs/user_guide/edge_development/flare_mobile.rst`, `mobile_android.rst`, `mobile_training.rst`, `examples/advanced/edge/mobile/android/README.md`.
- FedKit: `FedCampus/FedKit` metadata, README, `flutter/pubspec.yaml`.
- FedML: `FedML-AI/FedML` metadata, README, `android/README.md`, commit dates.
- TensorFlow Federated: `tensorflow/federated` README, release, recent commits.
- Google federated compute: `google-parfait/federated-compute` README and file tree.
- PySyft and `OpenMined/syft-flwr`: metadata, releases, README keyword grep.
- `flutter_litert`: pub.dev JSON API (versions and dates), pub.dev changelog page, GitHub repo `google-ai-edge/flutter_litert` metadata and README (on-device training section).

NOT OPENED or not resolved:
- The live NVFlare rendered documentation sites (two URLs returned 404 through the fetch tool; the `.rst` sources on GitHub were read instead).
- Flower's Kotlin SDK has no README in the tree; its API docs were not found. The search result summary said the docs home links an Android SDK page; the docs home itself says "Coming Soon" (section 1).
- FedML's TensorOpera pages; PySyft's docs site; the FedKit Flutter client's source code.
- No framework was installed or run, so every "works" below is "documented", not "tested".
- Search-engine summaries were used only to find leads and are marked snippet-only where they appear.

## 0. Summary table

Dates are from the GitHub or pub.dev APIs, read 2026-11-19. "Real Android on-device client" means the repository contains an Android client that trains on the phone (not simulation). It does not mean it was run.

| Project | Latest release (date) | Last commit on default branch or notable activity | Licence | Real Android on-device client | Maintained for mobile | Flutter fit | Server |
|---|---|---|---|---|---|---|---|
| Flower | framework-1.44.0 (2026-11-18) | repo active; mobile paths untouched since 2025-04 (SDK) and 2025-02 (examples), apart from CI/rename commits (2026-03-11) | Apache-2.0 | Old TFLite example only; docs say SDK incompatible with current Flower | No | No Flutter client in Flower repo; community FedKit has one | Python (SuperLink and ServerApp) |
| NVIDIA FLARE | 2.9.1 (2026-11-12) | Android example last changed 2026-06-24 | Apache-2.0 | Yes, Kotlin SDK plus ExecuTorch, source-only | Yes (active repo; mobile path touched in 2026) | None; native Android app required | Python, "hierarchical edge" configuration |
| FedKit (community, FedCampus) | `action0` tag (2023-07-30), no GitHub releases | 2024-02-03 | MIT | Android client yes; Flutter client UNVERIFIED for on-device training | No (about 2 years 9 months idle) | A Flutter package exists in the repo, not on pub.dev | Django plus on-demand Flower gRPC servers |
| FedML / TensorOpera | v0.8.9 (2023-10-28) | default branch last commit 2024-05-13; `android/` last 2023-11-07 | Apache-2.0 | Android SDK in repo; not assessed further | No | None found | Python, tied to TensorOpera platform (UNVERIFIED how tightly) |
| TensorFlow Federated | v0.88.0 (2024-09-26) | commits through 2026-11-18 | Apache-2.0 | No: README describes a single-machine simulation runtime | n/a for phones | None | Simulation only |
| Google federated compute (FCP) | none | commits through 2026-11-18 | Apache-2.0 | Client library parts used at Google; production server not open-sourced | Not usable as a stack | None | Not provided |
| PySyft | v0.9.5 (2025-02-13) | commits through 2026-11-18 | Apache-2.0 | No phone client found | n/a | None | n/a |
| `flutter_litert` (not an FL framework) | 4.2.0 (2026-11-17) | repo pushed 2026-11-16 | Apache-2.0 | Flutter plugin with on-device training on Android, documented | Yes (7 releases visible within 2026-11) | Native Flutter plugin | None (training only, no aggregation) |

## 1. Flower

Sources: GitHub `adap/flower` (redirects to `flwrlabs/flower`, per the 2026-03-11 commit message "Migrate GitHub org references from adap to flwrlabs"); https://flower.ai/docs/; https://flower.ai/docs/framework/tutorial-quickstart-android.html; the Kotlin and example paths in the repo tree.

1.1 Current state of the main project. Latest release `framework-1.44.0`, published 2026-11-18T17:03:30Z; repository licence Apache-2.0; repo pushed 2026-11-19. The 1.44.0 release notes read through the fetch tool concern agent runtime work, not mobile. Source: GitHub API, release page.

1.2 Android status on the docs, re-verified. The Android quickstart page still carries: "The experimental Flower Android SDK is not compatible with the latest version of Flower. Android support is currently being reworked and will be released in 2025. This quickstart tutorial is kept for historical purposes and will be updated once the new Android SDK is released." The same text is in the source file `framework/docs/source/tutorial-quickstart-android.rst` in the repo. The docs home https://flower.ai/docs/ lists "iOS SDK" and "Android SDK" under "Coming Soon" and a C++ SDK as "Coming Soon" with "Code example available, full docs coming soon". Flutter is not mentioned. So the earlier finding (Android SDK lagged) is confirmed, and the stated 2025 release did not appear by 2026-11-19: no new SDK is announced as released on the pages read.

1.3 What is in the repository. `framework/kotlin/flwr` is an Android library (`dev.flower.android`: `Client.kt`, `Grpc.kt`, `MessageHandler.kt`, `Serde.kt`, `TaskHandler.kt`, `Typing.kt`). `Grpc.kt` imports the older `FleetGrpc` pull messages (`PullTaskInsRequest`, `PushTaskResRequest`, `TaskIns`, `TaskRes`) and the bidirectional `FlowerServiceGrpc.join` stream. `framework/py/flwr/compat/server/grpc_bidi` exists on the server side under a `compat` package. DERIVED, not verified by running: the Kotlin SDK targets the older Flower protocol that the current server keeps only under a compatibility layer, which is consistent with the docs warning. Commit history for `framework/kotlin/flwr/src`: the only commit found touching `framework/kotlin/flwr/src` is 2025-04-03 (move of `src/*` to `framework/*`); the `framework/kotlin` folder as a whole also shows the 2026-03-11 org rename. `framework/swift` shows a 2025-08-13 formatter bump and the 2026-03-11 rename, no feature work. Source: GitHub API commit history.

1.4 Examples. `examples/android` (Java) and `examples/android-kotlin` (Kotlin, TFLite) both exist. Their last content commits are 2025-02-20 (dependency and minimum Python bump) and, apart from the 2026-03-11 rename, nothing later. The docs example page for Kotlin is titled "2022" (search result title, snippet-level). The example trains on the phone with TensorFlow Lite per its description (snippet-level; code not read). Flower also ships `fedavg_android.py`, a strategy "with custom serialization for Android devices" (header read), which handles raw-byte weights.

1.5 Flutter. No Flutter or Dart client in the Flower repo tree (a grep of the tree for `flutter|dart` outside the community FedKit returned nothing). Flower talks gRPC; a Dart client would need generated protobuf code. Community project FedKit does this (section 3).

1.6 Server. Python process(es) (SuperLink plus a ServerApp), gRPC-based. Whether it fits a free tier is covered by `docs/research/free-tier-aggregation-hosting.md`; for this note: a long-running gRPC server is a poorer match than a stateless HTTP function, DERIVED, not measured. Not verified: the memory the SuperLink needs idle.

1.7 Cost. Apache-2.0 library; no fee for the framework on the pages read. Hosted Flower services were not assessed.

Verdict: real Android client yes only in an old, unmaintained path that the project itself calls incompatible; maintained as a framework yes, for mobile no; Flutter no; free-tier server unproven.

## 2. NVIDIA FLARE (NVFlare)

Sources: GitHub `NVIDIA/NVFlare`; `docs/user_guide/edge_development/flare_mobile.rst`, `mobile_training.rst`, `mobile_android.rst`; `examples/advanced/edge/mobile/android/README.md`.

2.1 State. Latest release 2.9.1, published 2026-11-12T20:54:57Z; Apache-2.0; repo pushed 2026-11-19. The Android example directory's last commit is 2026-06-24. Source: GitHub API.

2.2 What it offers. "FLARE 2.7 introduces comprehensive mobile development support for both Android and iOS". The Mobile SDK is "native libraries for Android (Kotlin/Java) and iOS (Swift/Objective-C)" with on-device training "Using ExecuTorch", communication "with FLARE servers via HTTP/HTTPS". Android: minimum SDK API 29 (Android 10), Kotlin/Java, Gradle, dependencies ExecuTorch, OkHttp, Gson, Coroutines. The main class is `AndroidFlareRunner`; training is `ETTrainer`. Source: `flare_mobile.rst`.

2.3 Source-only. The Android README says the directory "intentionally does not include Gradle build files or a Gradle wrapper"; you add the SDK sources to your own Android Studio project and add ExecuTorch libraries to `app/libs/`. Prerequisites listed: JDK 17, Android SDK API 29 or later, NDK 29.0.13599879 "or compatible", Python 3.10 or later for ExecuTorch build scripts, CMake. The example trains CIFAR-10. Source: example README, `flare_mobile.rst`.

2.4 Model workflow. "No device-side programming is needed": the model is written in PyTorch, wrapped in a `DeviceModel` that returns loss and predictions, exported to ExecuTorch format. Source: `mobile_training.rst`. This matches the repo's PyTorch stack in `ml-service/qc` (see `docs/research/on-device-training-flutter-android.md` section 0). Caution from the earlier note: the ExecuTorch training extension README calls itself "experimental and under heavy active development" and "a technical preview"; NVFlare's docs do not change that statement, and whether a 5-8-1 net exports and trains is UNVERIFIED (not tried).

2.5 Server. A FLARE server with "hierarchical edge configuration" is a prerequisite (`flare_mobile.rst`). The server is Python; its memory and dependency size, and whether it runs on a free tier, were not documented in the pages read and are UNVERIFIED. Mobile devices connect over HTTP/HTTPS, which is friendlier to free-tier hosting than gRPC (DERIVED, not tested).

2.6 Flutter. No `flutter` or `dart` path in the repo tree (grep of the tree returned none) and no mention in the mobile docs read. A native Android app is required, or a Flutter app with a `MethodChannel` to Kotlin code that embeds the SDK (design inference).

2.7 Cost. Open source Apache-2.0; no fee on the pages read.

Verdict: real Android on-device client yes (documented, source-only, ExecuTorch-based, preview-level training under it); maintained yes; Flutter no (native Android only, or channel bridge); free-tier server UNVERIFIED and the framework is heavy for 3 phones.

## 3. FedKit (community, FedCampus)

Source: GitHub `FedCampus/FedKit`, README and `flutter/pubspec.yaml`.

- Description: "Mobile Federated Learning development kit for FedCampus". Parts: a Django REST Framework backend that spawns Flower gRPC servers on demand, an Android client, a Flutter client for Android and iOS (`flutter/`, example app `fed_kit_client/`), TensorFlow/Keras to `.tflite` model generation for Android. Licence MIT; 20 stars; no GitHub releases (a tag `action0` dated 2023-07-30); last commit 2024-02-03. Source: README, GitHub API.
- The Flutter package `fed_kit` is described in its pubspec as "Backend communication and Flower gRPC handling for FedKit", version 0.0.1, depends on `grpc`, `dio`, `protobuf`. It is not on pub.dev (the pub.dev API returned "NoSuchKey" for `fed_kit` and `fed_kit_client`). Whether the Flutter client trains on the device itself or only talks to a backend and relies on the native Android library is UNVERIFIED (source not read; the pubspec shows no TFLite dependency).
- The README says `gen_mlmodel` (iOS) is "still a work in progress". It states no maintenance policy.
- Verdict: a real Android client exists (README); not maintained (idle since 2024-02, built against the older Flower of that time); Flutter partially; depends on the Flower server stack. The earlier note's "snippet-only" status is now first-hand.

## 4. FedML / TensorOpera

Source: GitHub `FedML-AI/FedML`.

- Latest release v0.8.9 (2023-10-28). The default branch's most recent commit read is 2024-05-13 (a README fix). The repository's `pushed_at` field shows 2026-11-12, which is other-branch activity; what it contains was not inspected. Apache-2.0.
- The repo has `android/` with an Android app and SDK (`app`, `fedmlsdk`, `fedmlsdk_demo`) with Java API, JNI and a native library; `android/` last commit 2023-11-07. The README is branded around TensorOpera AI, a commercial platform ("cloud service for LLMs & Generative AI"). Which parts need the commercial platform, and pricing, are UNVERIFIED.
- Flutter binding: none found.
- Verdict: Android client exists in the repo; not maintained for mobile (no change since 2023-11); Flutter no; platform dependence UNVERIFIED. Not a candidate.

## 5. TensorFlow Federated and Google's federated compute

5.1 TFF. README: TFF "is an open-source framework for machine learning and other computations on decentralized data" and includes "a single-machine simulation runtime for experiments". Latest release v0.88.0 (2024-09-26), commits through 2026-11-18 (the recent commits read concern DP aggregation core code). Apache-2.0. No phone client. Source: README, GitHub API. Verdict: simulation only; real Android client no.

5.2 `google-parfait/federated-compute` (Federated Compute Platform). README states that parts of the repo, "in particular, code in the `client/` directory, and the service & data format definitions in `proto/`", are used in production in Google's federated learning infrastructure as of 12/7/2022, while "production server side infrastructure" has "not yet been open sourced due to its dependencies on proprietary infrastructure", and the reference demo server was "removed to reduce maintenance costs". No releases. The file tree has client C++ and Java sources (`fcp/client/...`, `fcp/java_src/...`); no standalone Android app or Flutter binding was seen. Verdict: not an end-to-end option; you would have to write the server. Source: README, file tree.

## 6. PySyft and OpenMined

`OpenMined/PySyft` v0.9.5 (2025-02-13), described as "Perform data science on data that remains in someone else's server"; `OpenMined/syft-flwr` v0.5.3 (2026-07-17), "Easy Setup, File-based, Offline Capable Federated Learning". A keyword grep of the `syft-flwr` README for `android|mobile|flutter|ios` returned nothing. No phone client found in either. Source: GitHub API and README. Verdict: no real Android client found. Not exhaustive: PySyft's docs site was not read.

## 7. Flutter route that did turn up: `flutter_litert`

This changes the earlier finding that no Flutter binding trains on-device. That earlier note read `tflite_flutter` (0.12.1) and the `tensorflow/flutter-tflite` README, neither of which mentions training. A separate plugin does.

7.1 Identity. pub.dev package `flutter_litert`, latest 4.2.0 published 2026-11-17T00:46:13Z; publisher `hugo.ml` (verified publisher on the pub.dev changelog page); the repo is `google-ai-edge/flutter_litert` (created 2026-02-11, 20 stars, Apache-2.0, last push 2026-11-16). Contributors list is led by `hugocornellier`. The pub.dev page and README do not call it an official Google package; since 4.1.2 the repo lives in the `google-ai-edge` GitHub organisation. Treat "official Google" as UNVERIFIED; "hosted under a Google organisation" is verified. It "started as a fork of `tflite_flutter`" (README). pub.dev: 160 of 160 points, about 19,500 downloads in 30 days. Source: pub.dev API, changelog page, GitHub API, README.

7.2 Training support (documented, not run). README "On-device training": training is supported "on native platforms via `SignatureRunner`", with `train`, `infer`, `get_weights`, `set_weights` signatures. Weights are read through `get_weights` and serialised in Dart (JSON in the README example), restored through `set_weights`. This path uses `TFLITE_BUILTINS` only, so "no Flex delegate or `SELECT_TF_OPS` needed", and it is the recommended approach. The checkpoint-based `save`/`restore` path is deprecated, needs the Flex delegate, and "is not available on Android since 4.0.0". The Dart training loop in the README calls `getSignatureRunner('train')` and `run`. Source: README lines for sections "On-device training" through "Choosing a persistence approach".

7.3 Version history (pub.dev changelog): 1.0.3 adds `SignatureRunner` for on-device training (package published 2026-03-03); 3.0.0 (2026-06-14) lowers `SignatureRunner.run()` overhead; 4.0.0 (2026-11-09) removes the Android Flex delegate and moves Android to LiteRT 2.x; 4.1.2 (2026-11-16) deprecates `FlexDelegate`; 4.2.0 (2026-11-17) renames the Android package. Most of these releases are days old; the plugin is young and moving fast, so APIs may still change (DERIVED from the dates).

7.4 What it answers from the earlier note's open list:
- Open item 1 (can a Flutter plugin call signatures?): yes, `SignatureRunner`, per the README.
- Open item 3 (extracting raw tensors): with `get_weights` the weights come back as Dart lists, so no TF checkpoint parsing is needed. This also removes the TF1-checkpoint problem noted in the earlier section 6.
- Open item 6 (builtins versus Flex ops): the documented path needs builtins only. Whether the gradient graph of a 5-8-1 net (matmul, bias add, activation, loss, gradients, SGD update) converts to builtins only, and what the activation choice does, is UNVERIFIED: the README's example is a 1-weight linear model and the repo has `example/assets/training_model.tflite` and `scripts/generate_training_model.py` which were not read or run.

7.5 Fit. A 57-parameter model is far below any size concern (DERIVED). The plugin provides training only: no client-server protocol, no aggregation, no scheduling. Upload would be plain HTTP from Dart, so the server can be a stateless HTTP function (matches `docs/research/federated-update-protocol.md`). Background execution still follows the earlier note's section 7 (WorkManager limits); whether this plugin loads inside a `workmanager` background isolate is UNVERIFIED (native FFI plugin; not tested).

## 8. Other app frameworks, briefly

The owner is open to non-Flutter apps. From sources read:
- Native Android (Kotlin) is the only platform for which any surveyed project ships a documented, source-level on-device FL client: NVFlare (ExecuTorch), Flower's old Kotlin SDK and example (TFLite), FedKit's Android client, FedML's Android SDK. Training libraries (LiteRT Java API, ONNX Runtime `onnxruntime-training-android`) are documented for Kotlin and Java too (`docs/research/on-device-training-flutter-android.md`, sections 1 and 2).
- No React Native, Kotlin Multiplatform or other cross-platform framework was found with FL support in the sources read; these were not specifically searched in package registries beyond the pub.dev and GitHub searches above (a GitHub repository search for "flutter federated learning" returned only unrelated personal repos with 0 to 1 stars). UNVERIFIED for npm and Maven registries.
- Consequence, DERIVED: a switch away from Flutter buys a ready FL client only through NVFlare (heavy, preview-level ExecuTorch training) or the stale Flower and FedKit paths. It buys nothing the 57-parameter prototype needs that `flutter_litert` plus a plain HTTP upload does not.

## 9. Small models and few clients

No surveyed project documents behaviour for fewer than a handful of clients as a target.
- Flower: the `FedAvg` default minimums are 2 nodes (`docs/research/federated-update-protocol.md` section 1.7); with 3 phones and one dropping out a round could stall unless set lower. DERIVED, not run.
- NVFlare, FedKit, FedML: no statements on minimum client counts were read.
- In all cases the aggregation is a weighted mean of at most 3 vectors of 57 floats (DERIVED), which a framework does not need to do.

## 10. Re-verification of the two earlier findings

1. "Flower's Android SDK lagged current Flower": CONFIRMED on 2026-11-19. The docs warning and the "Coming Soon" listing are unchanged and the "2025" release date has passed without an announced release on those pages. The Kotlin SDK in the repo was last substantively changed 2025-04-03 and uses an older protocol (section 1.3).
2. "No Flutter binding trains on-device": NOT CONFIRMED. `flutter_litert` (section 7) documents it. The earlier note examined only `tflite_flutter` and the `flutter-tflite` README; both indeed do not mention training. Update that note's summary table row for LiteRT.

## 11. Verdict per framework

| Framework | Real Android on-device client | Maintained | Flutter fit | Free-tier server fit |
|---|---|---|---|---|
| Flower | Old TFLite example only; SDK declared incompatible and unreleased | Framework yes, mobile no | None official; community FedKit | Python gRPC server, UNVERIFIED |
| NVFlare | Yes (Kotlin plus ExecuTorch, source-only) | Yes | None (native or channel bridge) | Python, hierarchical config, UNVERIFIED; HTTP transport |
| FedKit | Yes (Android); Flutter UNVERIFIED | No (2024-02) | Partial, not on pub.dev | Django plus Flower, heavy |
| FedML | In repo, not assessed | No (2023 to 2024) | None | Platform-tied, UNVERIFIED |
| TFF | No (simulation) | n/a | None | n/a |
| Google FCP | Client parts; no server | Not a usable stack | None | No server provided |
| PySyft | None found | n/a | None | n/a |
| `flutter_litert` | Yes, training via `SignatureRunner`, documented, not run | Yes, but young | Native plugin | Stateless HTTP upload suffices |

## 12. Open uncertainties

1. Whether the 5-8-1 net's training graph converts with builtin ops only and trains correctly in `flutter_litert` on a real phone (the README example is a linear model). Needs a build and run.
2. Whether `flutter_litert` works inside a `workmanager` background isolate on Android.
3. Whether `flutter_litert`'s maintainer posture will hold (very recent releases, one primary contributor, GitHub organisation affiliation with Google not otherwise documented on the pages read).
4. Whether a new Flower Android SDK shipped somewhere other than the pages read (no evidence found).
5. NVFlare and Flower server idle memory and free-tier fit; Flower minimum-client settings for 2 to 3 clients.
6. Whether FedKit's Flutter client trains on-device.
7. FedML's dependence on the TensorOpera platform and pricing.
8. Cross-platform frameworks other than Flutter (React Native, Kotlin Multiplatform) were not surveyed in npm or Maven registries.
9. Owner's "official Google plugin" status for `flutter_litert`: not stated by the package or README.
