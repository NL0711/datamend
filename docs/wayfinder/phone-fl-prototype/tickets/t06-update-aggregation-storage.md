---
title: What is the update format, aggregation rule, validation and weights storage?
labels: [wayfinder:grilling]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: [t02-on-device-training-research, t03-free-tier-hosting-research, t04-federated-update-protocol-research, t10-mobile-fl-frameworks-research]
---

## Question

Decide the update payload and its versioned schema, the aggregation service (separate under `ml-service/`, per the owner), how updates are validated and rejected, where aggregated weights live on free tiers, how the phone fetches the current weights, and how the single-client degenerate case is labelled in the API and the UI.

## Resolution (2026-11-19, confirmed by the owner)

Settled with the owner (Q1 to Q5 as recommended; Q6 revised to option A). Evidence base: `docs/research/free-tier-aggregation-hosting.md`, `docs/research/federated-update-protocol.md`, `docs/research/mobile-federated-learning-frameworks.md`. There are 3 phones, so this is a real 3-client average, still a handful and never called private or secure.

1. **Hosting.** A Cloudflare Worker (TypeScript) with D1 holding pending updates, every weight version and the evaluation counts; no R2, so no payment method is expected (UNVERIFIED). The platform backend is untouched, keeping the isolation rule. The owner creates a free Cloudflare account (owner task). Cloudflare's terms for this use and the current D1 free limits are UNVERIFIED and are checked before the build.
2. **Update payload, `fedupdate-v1`.** JSON: `schema`, `update_id` (random UUID), `base_version`, `device_id` (random install ID, never a hardware ID), `n_windows`, `n_positive`, `delta` (57 floats, trained minus base weights, norm-clipped on the phone to a bound M, `assumed`, measured later), `app_version`, `trained_at`. Body capped at 64 KB. No raw readings, coordinates or gauge IDs. Marked `synthetic: false` unless it came from a test.
3. **Rounds.** One current version. One update per device per version, accepted only against the current version (stale `base_version` gets 409). The server re-clips as a sanity check and rejects non-finite values or a wrong length. When updates from at least 2 different devices have arrived (`assumed`), the next version is the current weights plus the mean of the deltas weighted by `n_windows`. All versions are kept.
4. **Who may upload.** An allowlist of 3 per-phone tokens stored as Worker secrets, never in the repo; no open registration. A token taken from a rooted phone allows impersonation, so this is a prototype defence, not a guarantee. Reading the current weights is public and read-only.
5. **Shared model spec.** A committed `model-spec-v1` fixes the architecture (5 to 8 to 1, tanh, sigmoid), the feature order, fixed scaling constants (`assumed`, never computed per phone) and the seeded initial weights, with a hash. `GET /weights/latest` returns the version, the 57 weights, the spec hash and the contributing-device count; a phone refuses weights with a different spec hash.
6. **Retries, evaluation reporting, labelling.** Uploads are idempotent by `update_id`, with backoff. The server holds no labelled data, so evaluation is done on the phone: a held-out phone scores its own windows with the fold model and each baseline and uploads an `eval-v1` payload of per-day outcome counts (true positives, false positives, false negatives, true negatives, window count) and never windows; the server stores and sums them and derives NOT EVALUATED from the t07 thresholds. This amends the earlier rule: only model updates **and aggregate result counts** leave the phone. Every weights response and result carries `n_devices`, `round`, `quorum_met` and `prototype: true`.

**Consequences for the build (not decisions):** each leave-one-out fold needs its own weights lineage trained from the other two phones, so a phone trains once per lineage it belongs to; the baselines (threshold, always no rain, logistic regression, local-only) also run on the phone. The protocol file must define how the local-only comparison is scored, since a held-out phone's windows cannot train its own model.
