---
title: What model, features and labels does the phone train?
labels: [wayfinder:grilling]
status: open (reopened 2026-11-19, see the addendum)
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19, reopened 2026-11-19)
parent: MAP
blocked_by: [t01-barometer-rain-onset-research, t02-on-device-training-research]
---

## Question

Decide the rain-onset model (architecture sized for a phone), the feature window and sampling rate for pressure tendency, how tap labels are collected and kept honest (sparse, noisy), how sensor artefacts are handled, what the user-visible model name and status are, and confirm that this is a separate model and not the QC weights. Constraint from the owner and the research: no persistent notification, so barometer readings exist only while the app is open in the foreground (sparse, tied to alert-feature use); decide whether that is enough signal for this model or the signal must change. Open items while claimed: the owner chose a small neural net over logistic regression (5 to 8 to 1, seeded random shared start, not zeros), but how it is trained (hand-written code, or a federated-learning framework) waits on the framework research ticket; devices answered 2026-11-19: 4 to 5 real phones, all in Mumbai; still unknown which are within the label radius of a gauge.

## Resolution (2026-11-19, confirmed by the owner)

Settled with the owner (Q1 to Q6 as recommended; Q4 changed by the owner from logistic regression to a small neural net; Q7: 4 to 5 real phones, all in Mumbai). Vocabulary: Rain-soon model and Short pressure change in `CONTEXT.md`. Evidence base: `docs/research/phone-barometer-rain-onset.md` (no published skill figure for this target, so none is assumed).

1. **Target.** Will rain fall at the nearest gauge within the next 60 minutes. The label is derived: the nearest gauge's accumulation counter increases within 60 minutes. Because the counter's units and period are UNCONFIRMED, only an increase is used and no rainfall amount is claimed. The model is named the **rain-soon model (prototype)**, a new model separate from the QC weights, which are untouched and not claimed to improve.
2. **Labels.** Gauge-derived only; no user taps (taps need visible UI, are sparse and unresearched; they go to the map's Not yet specified). A sample is labelled only when the nearest live gauge is within 10 km (assumed, the alerts radius) and that gauge's verdict is OK. A SUSPECT or UNCERTAIN gauge never labels anything. Coverage is the 9 Mumbai gauges only.
3. **Features and windows.** The barometer is sampled once a minute while the app is open in the foreground (no persistent notification, so no background collection). A sample needs 30 contiguous minutes of readings or is not formed. Features: pressure change over the last 10, 20 and 30 minutes, the slope and the standard deviation, called **short pressure change** (never "tendency", which is WMO's 3-hour quantity). A step over about 0.3 hPa between consecutive samples rejects the window as a floor or elevator change (assumed, to be measured). Absolute pressure is never a feature (phone bias is about 1 to 2 hPa).
4. **Model.** A fully connected 5 to 8 to 1 network, tanh hidden layer, sigmoid output, 57 parameters, so an update is about 230 bytes. Training code is hand-written in plain Dart or Kotlin (about 40 lines, no ML runtime), checked in tests against a reference PyTorch implementation using generated data and a gradient check. This is a design choice with no research source. The owner chose a neural net over logistic regression. Whether training uses hand-written code or a federated-learning framework is decided in the update, aggregation and storage ticket after the framework research. The net can overfit tens of labelled windows, so the evaluation must compare it with a plain baseline (a fixed pressure-fall threshold) and the app claims nothing until it does.
5. **Shared start and rounds.** Version 0 is a fixed, seeded random initialisation committed to the repo (not zeros: a hidden layer started at zeros never learns). The server accepts an update only against the current version. A round closes when at least 2 updates against it have arrived (assumed; to be revisited at 3 with 4 to 5 phones), weighted by labelled-window count; each update's norm is clipped as a sanity check, not security.
6. **When a phone trains.** In the periodic background worker (charging, idle, unmetered), only with at least 50 labelled windows and both classes present (both assumed); otherwise it sends nothing.

**Not settled (facts, not decisions):** which of the 4 to 5 phones will be within 10 km of a gauge; if fewer than 2 are, labels are too sparse to evaluate and the evaluation ticket must say so.

## Addendum, ticket reopened (2026-11-19)

Owner answers: the net becomes a small temporal neural net (a 1D convolution or GRU over the raw window, replacing the 5 to 8 to 1 net, which also changes t06's update length); nearest-gauge context features are wanted (the gauge's own rain fields are never inputs); the owner asked to assume the other phones match the one checked.

**Blocking fact:** an adb sensor listing of the one connected phone (a Moto G67 Power 5G) shows no barometer, no ambient-temperature sensor and no humidity sensor. Items 1, 3 and 4 above (pressure features, 1-minute foreground samples, the 5 to 8 to 1 net) all assume a barometer, so they cannot run on this phone. Still true and unaffected: the gauge-derived label (item 2), the training gate, the update protocol, the evaluation rules and the simulated clients.

Open decision for the owner, to be settled in this ticket: (a) check the other phones for a barometer and use only phones that have one (a few phones may be too few to evaluate or federate); (b) borrow or buy barometer phones; (c) drop the phone barometer and make nearest-gauge context features (temperature, humidity, wind and their changes, plus time of day) the inputs. Under (c) every input and the label come from the same public gauge feed, so no private data stays on the phone and the federated setup is a demonstration of mechanics, not a privacy benefit; the app and docs must say so. The no-notification rule and the foreground-only collection constraint matter only for phone sensors.

Later the same day the owner chose (c), then asked to rework the federated task into data validation and anomaly detection. The rain-soon model, the barometer inputs and the 1-minute window design are therefore superseded pending the federated-validation design ticket; items 2 (gauge labels) and 6 (training gate) are to be re-examined there.

