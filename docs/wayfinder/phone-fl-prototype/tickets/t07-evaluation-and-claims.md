---
title: How is the phone model evaluated and what may we claim?
labels: [wayfinder:grilling]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: [t05-model-features-labels]
---

## Question

Decide the evaluation on one device (time-split holdout, baseline such as persistence or a fixed tendency threshold, precision, recall, false-alarm rate, latency), what is reported in the app, and a "Not claimed" list. Phone data is not part of the RF25 protocol, so it needs its own frozen rules, written before any run.

## Resolution (2026-11-19, confirmed by the owner)

Settled with the owner (Q1 to Q6, all as recommended). Precedent: `docs/qc-evaluation-protocol.md` (rules frozen and committed before any run; false alarms are the main operational cost). Evidence base: `docs/research/phone-barometer-rain-onset.md` (no published skill for this target).

1. **Where the rules live.** A new file, `docs/phone-model-evaluation-protocol.md`, committed before any evaluation run. After a run, a change means a new dated version, never an edit. Writing that file is a build-slice step, not a decision.
2. **Splits.** Leave-one-device-out: the held-out phone is the test set and none of its windows is used for training or tuning. On the other phones, train on earlier days and validate on later days; the future never enters training. Every threshold and setting is chosen on validation only. Each held-out phone is scored once per frozen configuration, with no re-run after seeing test results.
3. **Comparisons (all four mandatory).** (a) always predict no rain (the base rate); (b) a fixed pressure-fall threshold on the 30-minute short pressure change, its value `assumed` and fixed in the protocol, never tuned on test; (c) logistic regression on the same five features; (d) local-only training, each phone alone. Federated versus local-only is the federated-learning question.
4. **Metrics.** Precision, recall, F1, false alarms per 1,000 negative windows, and precision-recall area; also the positive rate, window counts per phone, on-device inference latency, training time and update size. If pooled test positives are under 30, or a held-out phone has under 5 (both `assumed`), the status is **NOT EVALUATED: too few positives** and no metrics are shown for it. It is November, after the monsoon, and the one real gauge poll was dry, so this outcome is likely.
5. **Claims.** "Better than the threshold baseline" only if, at a fixed false-alarm rate, the improvement's interval (bootstrapped by day, not by window, since windows are correlated in time) excludes zero; otherwise the text says "no demonstrated advantage". The app shows the prototype label, the device count and the result status. A "Not claimed" list: no generalisation beyond Mumbai or these phones, no privacy or security guarantee, no rainfall amount, no improvement to the QC models.
6. **Synthetic data.** Allowed only for tests and demonstrations of mechanics, labelled synthetic wherever shown, and never counted in any reported metric. If real data is insufficient, the status stays NOT EVALUATED.

## Addendum (2026-11-19, after the device count settled)

The resolution above assumed 4 to 5 phones. The device count then went 4 to 5, then 2, and the owner's final answer is **3 labelled phones** (Bhandup, Goregaon, Dadar) once the polled gauge set was decided (see the polled-gauge ticket). Consequences, to be written into the protocol file:

- Leave-one-device-out trains on 2 phones, so comparison (d) (federated versus local-only) is computable with 2 clients; every result states the device count (3) and that 3 phones are a handful, not a population.
- The phones are roughly 10 to 18 km apart (approximate), so no held-out phone is a near-duplicate of a training phone; report per-fold results anyway.
- Dadar West has no polled neighbour within 10 km, so the neighbour check is "not run" for it and its label guard rests on rule checks alone; the protocol states this and reports Dadar folds separately.
- Comparisons (a), (b) and (c) and the positive-count rule still apply; NOT EVALUATED remains the expected status in post-monsoon weather, and no federated advantage is claimed unless rule 5 is met.

