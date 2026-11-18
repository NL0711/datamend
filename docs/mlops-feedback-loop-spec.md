# MLOps feedback loop: reviewer actions improve the model

Status: PROPOSED, 2026-11-19. NOT BUILT. This is the last phase, after the per-scale training and the architecture choice (`docs/qc-multires-pipeline-spec.md`).

## 0. Decisions made by the owner

1. **Reviewers:** only the owner. No real labels can be obtained for India, so the India loop uses a SIMULATED reviewer and every result there is labelled "simulated feedback". **Real labels can be obtained for the UK** (MIDAS Open, hand corrections), so the main demonstration is a replay of those real corrections (section 3b); the two are never pooled.
2. **What labels may change:** thresholds and model weights (not only thresholds).
3. **Shadow period:** dynamic, ended by evidence and not by a fixed number of days (rule in section 6).
4. **Tooling:** MLflow.
5. **Federated tie:** regional reviewers train a local head on their own labels while the shared body stays common (the `fedpers` idea). Still a one-machine simulation with no privacy claim.

## 1. What this can and cannot show

- It can show that the mechanism works end to end: flag, review, label, recalibrate or retrain, gate, promote, monitor, with every step logged and reproducible.
- It can show adaptation to things the original training did not contain, because the simulated reviewer is given fault kinds and regional fault mixes the model never trained on.
- It cannot show that real QC improves. A simulated reviewer is built from synthetic faults, so any gain is a gain at finding synthetic faults. The documents must say so wherever the results appear.

## 2. The loop

```
stream of days -> score (all scales) -> ranked review queue
       ^                                      |
  promote champion                   simulated reviewer: faulty / genuine / unsure
       ^                                      |
  promotion gate  <-  update candidate  <-  label store (append-only)
       ^                                      |
  dynamic shadow run                   monitoring: flag rate, drift, precision trend
```

## 3. The simulated reviewer (so the demonstration is not circular)

- It is a separate process from the model's training. It never sees scores except through the queue.
- Its ground truth comes from a fault generator whose settings the model did not train on: fault kinds held out, other strengths, and a different fault mix per region (client).
- It has a label error rate, a rate of "unsure", a daily review budget, and a tendency to confirm high-scoring items. All are configured and seeded.
- Sampling for review: the top of the ranking, a random audit of unflagged data (to measure what is missed), and items near the threshold. Audit items are weighted by how unlikely they were to be sampled.
- The stream uses validation-year data with fresh fault seeds. **No test year and no frozen benchmark fault is ever used.**

## 3b. Demo with real labels: replaying UK MIDAS corrections (proposed main demo)

What the labels are (`docs/research/uk-midas-open-daily-rain-qc-flags-and-counts.md`, Devon only, agent-computed, not checked by a second person): `qc-version-0` keeps the original value only where QC changed it, `qc-version-1` the corrected one. About 68,700 daily values in Devon were corrected by hand after a failed neighbour check, 1.5% to 2.8% of records, mostly 2010-2023 for the years this project uses. Their direction and size vary (median 3.4 mm, largest 9,782.5 mm).

**Replay design (time-forward, so improvement is measured on later real errors):**
1. Train on UK years up to 2012 (the UK study's training years). Set thresholds on clean 2013-2017 as in `qc/configs/uk.yaml`.
2. Stream the UK days in time order, year by year or month by month. Each flagged cell-day goes to the review queue.
3. The "reviewer" is the real correction record: a flagged cell-day that a hand correction fed is **faulty**. The reviewer's decisions arrive only after the period ends, as a real reviewer's would.
4. After each period the update ladder (section 5) runs on the labels received so far. A candidate must pass the gate before it replaces the champion.
5. Measure on the NEXT period's real corrections: recall at the fixed false-alarm budget, with and without the updates. The no-update champion is the control. Test years 2018-2023 stay locked for a final single pass.
6. Federated tie with real labels: the counties (Devon, Cornwall, Somerset, Dorset) are the clients, and each county's corrections are its own regional reviewer. A local head learns from its county's labels while the shared body stays fixed.

**Limits that must be stated with the result:**
- The labels come from a neighbour check, so the spatial component is partly scored against the rule that produced the labels. Report it beside the neighbour-average baseline.
- A flagged item with no correction record is not a confirmed genuine value; it may be a missed error. Report recall on corrected values and the flag rate, and treat precision as a lower bound, never as a measured number.
- Originals overwritten by station correction messages are missing, so errors are undercounted. Multi-day totals split into days, automatic estimates of placeholders, and flag-only changes are excluded and counted separately.
- These are station series; they are gridded with the same inverse-distance method as RF25 (`qc uk-grid`), so a bad station spreads over several cells.
- The UK is a different rain regime and network from India. This shows the mechanism and the real-label behaviour, not Indian QC performance. Never pooled with India.
- The UK reader is written from the documented layout and has not been tested on real files. Only a Devon subset has been downloaded (station-years where QC changed something), which inflates the error share; the full files for the chosen counties are needed.

## 4. Label store

Append-only table: cell, date, model version, scores of every scale at flag time, queue rank, reviewer id (`simulated:<seed>`), label (faulty, genuine, unsure), confidence, sampling stratum and weight, timestamp. SQLite first, written so it can move to PostgreSQL.

## 5. Update ladder, from safest to riskiest

| step | what changes | automatic? | gate |
|---|---|---|---|
| A | thresholds per region and season, from confirmed false alarms | yes, within a guard band | false alarms per 1,000 stay near the budget |
| B | confirmed genuine extremes added to the protected set | yes | protected extremes flagged not higher |
| C | fusion weights refit (non-negative logistic) on weighted labels mixed with synthetic ones | candidate only | full promotion gate |
| D | local head per region on that region's labels, shared body fixed | candidate only | full promotion gate, plus held-out region check |
| E | full retrain | manual trigger only | full promotion gate |

## 6. Promotion gate and the dynamic shadow run

- A candidate must pass the frozen architecture rule (`docs/qc-evaluation-protocol.md`) on the frozen validation benchmark: recall at the final budget not lower, false alarms within budget, protected extremes flagged not higher.
- Then it runs in shadow: it scores the stream silently next to the champion. It ends when the evidence is in, not on a date. Proposed rule, to be confirmed: at least 14 simulated days and 200 reviewed items where the two disagree; promote if the candidate's precision on those items has a 95% lower bound above the champion's and its flag rate stays inside the budget band; reject if its flag rate leaves the band or the evidence points the other way; stop at 60 days with no decision and keep the champion.

## 7. MLflow

- Local tracking store (SQLite backend plus a file artifact folder). One experiment per phase.
- Each run logs: parameters (config), metrics, and tags: git commit, config digest, split hash, benchmark hash, data hash, library versions, seed, and the label tier ("synthetic" or "simulated feedback").
- Artifacts: checkpoints, score summaries, the manifest, the decision file.
- Registry: one model per component with the aliases `champion` and `challenger`. Promotion moves the alias, and the gate result is stored as a tag.

## 8. Monitoring

Weekly (simulated) flag rate per region against the budget, score distribution against the clean training reference, share of reviewer-confirmed false alarms, and the gauge-network change signal from the decadal tests. An alarm opens a retraining candidate; it never changes the champion by itself.

## 9. Leakage rules

- Test years (2018-2025) and the stress years are never used.
- A golden set of reviewed items, split by date, is never trained on and is the only evidence for promotion besides the frozen benchmark.
- Unreviewed items are never treated as clean.

## 10. Build order

0. Get the full MIDAS files for the chosen counties, run `uk-grid`, `uk-labels`, `prepare` and the untrained scores with `qc/configs/uk.yaml`, and check the UK reader on real files.
1. Label store schema, the replay reviewer (real corrections), and the simulated reviewer (India).
2. Review queue (ranking plus audit sampling) on top of the stored scores.
3. Steps A and B (thresholds and protected set), with their guards.
4. MLflow logging and the registry aliases around `run_qc.py`.
5. Steps C and D, the promotion gate and the shadow rule.
6. Monitoring and a replay of a simulated multi-month stream.
7. The review screen in the web app, and the live federated view (`docs/PROJECT_OVERVIEW_WEBAPP.md`).

## 11. Open points

- Confirm the shadow rule in section 6 and the simulated reviewer settings in section 3 (error rate, unsure rate, review budget).
- Decide whether MLflow runs as a local file store only or also as a small tracking server.
- The live data source is still parked, so the stream is a replay.
