# STNet experiments: in-depth analysis (for explaining and defending them)

Written 2026-11-21 from the owner's results in `C:\Users\V\Downloads\results` (zips extracted to scratch, read with `python -I`; nothing executed; no checkpoint opened for this note; credentials file untouched). Companion to `stnet-results-review.md` (it holds the headline table; this note does not repeat it). STNet is the Part B research model; it is NOT on the live platform path.

Labels: **D** = derived here from stored numbers, **A** = analysis aid, not an evaluation, **ASSUMED** = my reading, not tested. Every fault in every number below is SYNTHETIC (injected by this repo's generator into IMD RF25; benchmark hash `c37de7e3cf2be90e`). Every number is a validation number (2013-2017); no test year was scored. One seed per configuration.

Source key: MAIN, HOLD, LMLC, DRIFT = the four result zips (`stnet_results_main/hold/lmb_lmc/drift.zip`, under `artifacts/qc/base/`); LOCAL = the earlier run still in the repo (`ml-service/artifacts/qc/base/stnet_s42`); `download.txt` is the MAIN Kaggle notebook log and `bbbbbbbbbbbbbbbbbbbb.log` is the HOLD notebook log (the file names are misleading); `job_lmb.log`, `job_lmc.log` are in LMLC.

## 0. Corrections to the earlier review (found while reading the code that wrote these files)

| # | Earlier statement | What the files and code show | Evidence |
|---|---|---|---|
| 1 | "800 optimiser steps in stage 1" | **47,200 steps** (D): `steps` is gradient steps PER YEAR VISIT (200), 59 training years x 4 epochs = 236 visits | `ml-service/qc/stnet.py` line 77 ("gradient steps per year visit") and the call `train_windows(..., cfg.steps)`; telemetry `stnet.train.stage1_year_visit` n=236, 6,400 frames per visit (200 x batch 2 x window 16) at 173 frames/s = 37 s per visit, matching the 37.0 s p50; the log has 239 rows (236 + 3 stage-2) |
| 2 | "long-memory stage 17 s" suggests a tiny stage | True for MAIN (3 visits x 30 steps = 90 steps, 17.2 s). LMB trained 24 visits x 300 = 7,200 steps; LMC 90 visits x 600 = **54,000 steps** (D) | telemetry `stnet.train.stage2_year_visit` n=3, 24, 90; `meta.json` long_steps 30, 300, 600 |
| 3 | lmb/lmc "best" checkpoint uses validation-year loss | The scored model is the final weights; `*_best.pt` is saved but not scored | `stnet.py` after training: `score_functions(p, model, long, ...)` uses the in-memory final model |
| 4 | Ceiling subset "UNEXPLAINED" (n=29,098) | It is the held-out threshold years **2016-2017** (`ceiling.py` uses `holdout_years` = `years.threshold`), not 2013-2017. The fusion ablation rows are also scored on 2016-2017 only. So ceiling recall 0.619 and the ablation PR-AUCs are not the same sample as 0.637 / 0.686 | `qc/ceiling.py` docstring and `qc/fusion_eval.py:34`; `qc/ablate.py` docstring |
| 5 | "100 of 132 drift events never detected", "101 never detected" | `never_detected` is counted only for the delay kinds (stuck, repeat, drift): 1 stuck + 100 drift = 101 of 240 events, not of 935 | `qc/metrics.py` lines 204-206 |
| 6 | "Event recall 0.659" read as events found | Event recall = share of events with AT LEAST ONE flagged cell-day (`f_arr > 0`). Very lenient for long footprints, which is why scale/zeroed show 0.28-0.31 event recall against 0.02-0.05 cell-day recall | `qc/metrics.py:186` |
| 7 | Recall is a 8-client result | **All validation recall numbers cover only the six training clients** (cells of training clients incl. buffer). The two held-out clients (3 = Assam & Meghalaya, 6 = Konkan & Goa) are scored for false alarms only; no file has fault recall for them. 935 events / 65,810 cell-days scored of 1,202 events / 90,764 cell-days in the validation benchmark (so 267 events, 24,954 cell-days, D, are unscored) | `qc/evaluate.py:33-39` (`group_cells`), `evaluate_component(... groups=("seen",))` for val; benchmark log line "val 2013-2017: 1202 faults, 90764 fault cell-days" in `download.txt` |
| 8 | Which run produced `stnet_s42_final.pt` is unknown | Very probably the Kaggle MAIN run: the LMLC (2026-11-20 05:23, commit `d3d1c62`) and DRIFT (09:45, `f202a79`) sessions re-scored `stnet_s42` from the uploaded checkpoint and wrote metric files **byte-identical** to MAIN (md5 `104a6872` for the fault file), while LOCAL's files differ (md5 `ee284642`). Still inferred, not logged | md5 of `stnet_fault_s42_val.json` in the four places |

## 1. What each experiment was and what it asked

| Experiment (files) | Question | Design | Answer in one line |
|---|---|---|---|
| **main** (MAIN `stnet_s42`, `download.txt`) | Can a small spatio-temporal CNN-GRU (1.76 M parameters, 11 input channels, 16-day window) flag synthetic faults at 1 false alert per 1,000 clean cell-days? | 4 epochs x 59 years (1951-2009) x 200 steps, batch 2, 48-cell crops (+16 margin), lr 0.001 AdamW; stage 2 = LSTM long memory on 2010-2012 (90 steps); Kaggle T4, 9,172 s | Recall 0.637, PR-AUC 0.686, 1.60 false/1,000 (target 1.0 missed). Strong on 4 kinds, near zero on 3 |
| **hold** (HOLD, `bbbb....log`) | Does exposure to a kind matter? (zeroed, scale, drift never in training) | Same config, `holdout_kinds` = zeroed, scale, drift; own Kaggle session, 8,959 s | The three kinds are no worse without training on them; the other four kinds are BETTER (PR-AUC 0.731). Says nothing about unseen real faults |
| **lmb / lmc** (LMLC `job_*.log`, `paired_*`) | Does a longer long-memory (LSTM) stage help drift/scale/zeroed? | `--init-from stnet_s42`: stage 1 encoder reused, only stage 2 retrained: 8 x 300 and 30 x 600 steps; pre-set decision rule (gain 0.05) | Rule not met either time: lmb PR-AUC +0.021, lmc +0.006 (interval includes 0); false alerts rise (2.09, 1.90) |
| **ablation / fusion** (`ablation_custom_*`) | Does fusing rules with STNet heads help? | Logistic/boosted fusion fitted on 2013-2015, scored on 2016-2017 only | Little: 0.682-0.707 PR-AUC vs fault head alone (different years, not strictly comparable); keeps protected extremes at 0.6-3% flagged |
| **calibration / budget check** (`budget_check_*`) | Does the 1.0 budget hold per client, including the unseen ones? | Threshold fitted on one clean year (2016 or 2017), false alerts counted on the other CLEAN year, per client; "global" and "per-client" rules | Pooled over training clients exactly 1.00 (D); unseen client 3 reaches 1.80 (main), 4.94 (lmb), 3.76 (lmc) |
| **ceiling** (`ceiling_*`) | Is the weak recall because faults are too small to see? | Recall at the budget threshold split by size of change, footprint weight, kind, radius, season proxy; 2016-2017 | 56% of fault cell-days change rain by under 1 mm and recall rises with size, BUT the weak kinds fail even on strong cell-days (section 3) |
| **probes** (`probe_*`) | Do the frozen features contain information about each kind? | Linear probe fit on 2013, scored on 2014; AUC | AUC 0.89-0.999; the same file for MAIN, LMB, LMC (shared encoder). HOLD (untrained on 3 kinds): zeroed 0.859, scale 0.931, drift 0.955 |
| **drift check** (DRIFT, notebook `stnet_F_drift`) | Does a plain untrained CUSUM beat STNet on drift? | Re-scores the MAIN checkpoint and compares a neighbour-residual CUSUM, fixed parameters, rule written first | CUSUM drift event recall 0.000 vs 0.242; 2.48 false/1,000; rule not met |
| **untrained baselines** (`untrained/`) | What do simple rules do? | rules, slow (30/90-day totals vs own and neighbours), neighbour-average residual | rules recall 0.452 at 2.39 false; slow and neighbour weak (PR-AUC 0.04, 0.10) |
| **telemetry** (`telemetry/*.md`) | Cost | Wall, GPU energy, spans | See section 4 |

Reading the logs:

- `download.txt` (MAIN notebook, 9,904 s): RF25 found (125 files, 2 T4 visible, single-gpu profile uses `cuda:0`); `prepare` 28-272 s (225 s of it the data-contract check over 125 yearly files); benchmark 275-297 s (log gives per-year fault counts: val 189-320 events and about 18,100 fault cell-days per year); untrained baselines 298-494 s; STNet training 496-9,736 s (a progress line every 60 s: 239 visits); ablation 150 s; ceiling 7 s; calibrate 5 s; zip written. Errors: none. Warnings: only the one-line "statics made finite: 10 cells without a heavy-rain threshold" (also in the HOLD and LMLC logs) and the harmless `No GITHUB_TOKEN`, Debugger/NbConvert notices. `PUSH_RESULTS skipped` (no token), so results were downloaded by hand.
- `bbbb...log` (HOLD notebook, 9,451 s): same start (14:15), same year order and the same code commit `70fe332`; finished rc=0; no errors.
- The two notebooks ran at the same time on separate Kaggle sessions (both started 14:15 on 2026-11-19).
- `job_lmb.log` / `job_lmc.log`: stage-1 encoder "taken from stnet_s42", stage 2 only; each epoch logs train loss vs one validation-year loss (2013). lmb 731 s, lmc 4,040 s on two GPUs in parallel (04:12-05:20), then a 157 s re-score of `stnet_s42` (05:23), then the paired tests.
- Total GPU time is about 6.5 T4 hours and about 380 Wh of GPU energy (D, sum of the stnet telemetry files: 165.7 + 163.4 + 12.9 + 38.2 + small re-scores).

## 2. Where STNet works and where it fails

### 2.1 By fault kind (MAIN, budget 1.0; cell-day recall / event recall; interval = whole-year bootstrap over 5 years)

| Kind | Events | Cell-days | Recall | Interval | Event recall | HOLD | LMB | LMC | LOCAL run |
|---|---|---|---|---|---|---|---|---|---|
| spike | 149 | 2,829 | 0.858 | 0.731-0.921 | 0.993 | 0.947 | 0.866 | 0.844 | 0.896 |
| phantom rain | 139 | 14,486 | 0.873 | 0.849-0.896 | 0.957 | 0.907 | 0.887 | 0.872 | 0.873 |
| combination | 138 | 25,075 | 0.823 | 0.748-0.883 | 0.841 | 0.901 | 0.868 | 0.841 | 0.873 |
| stuck | 108 | 7,425 | 0.770 | 0.685-0.840 | 0.991 | 0.897 | 0.860 | 0.840 | 0.834 |
| scale | 138 | 3,799 | 0.047 | 0.028-0.063 | 0.312 | 0.071 | 0.052 | 0.054 | 0.053 |
| drift | 132 | 9,026 | 0.027 | 0.011-0.062 | 0.242 | 0.044 | 0.040 | 0.026 | 0.025 |
| zeroed | 131 | 3,170 | 0.018 | 0.010-0.024 | 0.282 | 0.002 | 0.030 | 0.026 | 0.016 |
| all | 935 | 65,810 | 0.637 | 0.609-0.680 | 0.659 | 0.695 | 0.670 | 0.651 | 0.665 |

(Sources: `stnet_*fault*_val.json` in MAIN, HOLD, LMLC; LOCAL = repo file. Rules for comparison: spike 0.221, phantom 0.814, stuck 0.723, combination 0.472, the three weak kinds 0.005-0.015; neighbour baseline: all under 0.25.)

Checks (D, section 7): the kind rows add up exactly to 935 events and 65,810 cell-days, and the weighted recall reproduces 0.6366. Recall on the four strong kinds is 0.831 (49,815 cell-days); on the three weak kinds 0.030 (15,995 cell-days). The weak kinds are 24% of fault cell-days but 43% of events (each kind has about 14-15% of events), so the headline recall depends on how many cell-days each fault covers. The same pattern (strong four, weak three) appears in the independent LOCAL run, which is the best evidence that it is a property of model plus generator, not a seed accident.

### 2.2 By fault size, footprint, season (ceiling, MAIN fault head, 2016-2017 subset, n = 29,098 cell-days, threshold 1.634)

| Change in rain value (mm) | Recall | n | | Footprint weight | Recall | n |
|---|---|---|---|---|---|---|
| under 0.1 | 0.427 | 6,038 | | 0-0.25 | 0.615 | 20,709 |
| 0.1-1 | 0.567 | 10,297 | | 0.25-0.5 | 0.632 | 4,501 |
| 1-5 | 0.687 | 6,980 | | 0.5-0.75 | 0.762 | 1,297 |
| 5-20 | 0.794 | 3,567 | | 0.75-1 | 0.560 | 2,591 |
| 20-100 | 0.885 | 2,004 | | | | |
| 100 and above | 0.896 | 212 | | | | |

Strong cell-days (change 5 mm or more and footprint weight 0.5 or more): 0.778 (n=1,888, 6.5% of the total). 86.6% of fault cell-days have footprint weight under 0.5 (the edge of a disc, where the injected change is scaled by (1 - d/r)^2).

By footprint radius (all 2013-2017, MAIN): single-cell events 0.567 (475 events, 3,697 cell-days), radius 1.5-4: 0.641 (460 events, 62,113 cell-days). The generator has no larger footprints in validation (radius 4-6 exists only in test).

By season (the ceiling bins are "memory = 90 + day of year"; D mapping: 90-179 = days 0-89, about Jan-Mar; 180-269 = Apr-Jun; 270-364 = about 29 Jun-1 Oct, the monsoon; 365+ = Oct-Dec): MAIN 0.821, 0.494, **0.385**, 0.803. LMB 0.876, 0.543, 0.394, 0.836. LMC 0.832, 0.509, 0.401, 0.798. So recall roughly halves in the monsoon in every model; this is the largest single pattern in the files besides kind, and it is not mentioned in the earlier review. Protected extremes flagged (MAIN): monsoon 0.05%, rest of year 0.43%.

### 2.3 By year (what exists)

No file stores recall or PR-AUC per year for one model; only differences and false-alert rates are per year (`diff_by_year`, `per_year_a`).

| Year | 2013 | 2014 | 2015 | 2016 | 2017 | Source |
|---|---|---|---|---|---|---|
| False/1,000, MAIN | 1.57 | 1.98 | 1.90 | 1.17 | 1.39 | `drift_check_s42.json` `per_year_a` (mean 1.601, D = pooled rate) |
| False/1,000, LMB | 2.37 | 2.45 | 2.28 | 1.43 | 1.91 | `paired_*lmb*.json` `per_year_b` |
| False/1,000, CUSUM | 2.02 | 2.00 | 1.82 | 2.70 | 3.84 | drift check |
| Recall LMB minus MAIN | +0.027 | +0.040 | +0.030 | +0.040 | +0.031 | `diff_by_year` (better in 5 of 5) |
| PR-AUC LMB minus MAIN | +0.007 | +0.026 | +0.021 | +0.028 | +0.020 | same |

The false-alert rate is lowest in 2016 and 2017, the two years the threshold was fitted on (mean 1.28 against 1.82 for 2013-2015, D). Even in those two years it is above 1.0.

### 2.4 By region (client)

| Client | Role | Cells (train / buffer / held-out) | Clean cell-days (2 yrs) | False/1,000 MAIN (global threshold) | LMB | LMC | LOCAL run | Protected flagged MAIN |
|---|---|---|---|---|---|---|---|---|
| 1 | train | 646 / 6 / 0 | 475,918 | 0.56 [0.39, 0.74] | 0.76 | 0.50 | 0.82 | 0.04% |
| 2 | train | 243 / 387 / 0 | 459,496 | 1.06 [0.66, 1.55] | 0.99 | 0.69 | 0.84 | 0.00% |
| 3 (Assam & Meghalaya) | **held-out** | 0 / 0 / 493 | 358,125 | **1.80** [1.44, 2.11] | **4.94** | **3.76** | **3.08** | not scored |
| 4 | train | 507 / 121 / 0 | 458,614 | 0.77 [0.37, 1.18] | 0.79 | 0.60 | 0.46 | 0.00% |
| 5 | train | 439 / 148 / 0 | 427,932 | 0.72 [0.48, 1.00] | 0.69 | 1.01 | 0.75 | 0.04% |
| 6 (Konkan & Goa) | **held-out** | 0 / 0 / 665 | 484,827 | 1.15 [0.73, 1.56] | 0.97 | 1.44 | 0.59 | not scored |
| 7 | train | 550 / 112 / 0 | 483,084 | 1.09 [0.69, 1.54] | 1.10 | 1.32 | 1.11 | 0.46% |
| 8 | train | 372 / 275 / 0 | 472,060 | **1.79** [1.31, 2.30] | 1.63 | 1.87 | 2.05 | 0.15% |

Sources: `budget_check_*.json` (MAIN, LMLC, LOCAL), cell counts from the prepare output in the logs. Pooled over the six training clients, weighted by clean cell-days (D): 1.001 (MAIN), 1.000, 1.002, 1.011 (LOCAL). Held-out pair pooled: 1.42 (MAIN), 2.66 (LMB), 2.42 (LMC), 1.65 (LOCAL). Per-client threshold ("per_client" rule) brings training clients back to about 1.0 but cannot be fitted for unseen clients (identical to global in the files).

What this supports: the false-alarm rate on unseen region 3 is unstable between models and runs (1.8 to 4.9), so "generalises to unseen regions" is NOT supported, only "the false-alarm rate can be 2-5 times the budget on an unseen region". Which client is worst changes between runs (client 3 in three of four rows, client 8 in MAIN), so single-client conclusions are weak (one seed, two threshold years, intervals 0.5-1.0 wide). No file has recall per client or for the unseen clients.

### 2.5 Interval size

Whole-year bootstrap with only 5 years: the authors' own simulation says it covers 84-90% for a nominal 95% (`bootstrap-unit-check.md`, cited in the files). Typical widths (MAIN, 95%): overall recall 0.609-0.680 (7 points); false alerts 1.34-1.85 per 1,000; kind recall 0.7-0.92 for spike (19 points), 0.011-0.062 for drift. Paired differences are tighter (lmb vs main recall +0.034, interval 0.029-0.038) because the same years and the same encoder are compared; they do not include training randomness (section 5).

## 3. Why drift, scale and zeroed fail, and why the budget is missed

### 3.1 What the evidence supports

1. **They are largely invisible in the data by construction.** The generator (`ml-service/qc/faults.py` `_faulty`): zeroed sets the value to 0 (no change on a dry day); scale multiplies the value (0 x factor = 0 on a dry day); drift multiplies or adds only on wet days (`orig > WET_MM`) along a ramp that starts at zero. A cell-day inside a fault event is labelled a fault even when the observed value equals the true value. Share of fault cell-days with change under 1 mm (ceiling): drift 77.4%, zeroed 67.1%, scale 53.1%, against spike 15.5%.
2. **But size alone is not the explanation.** Phantom rain has 77.9% of cell-days under 1 mm and still 0.857 recall, stuck 51.3% and 0.826. And on the strong cell-days (5 mm or more, weight 0.5 or more) the fault head still reaches only zeroed 0.250 (n=48), scale 0.215 (n=121), drift 0.039 (n=152), against spike 0.910, stuck 0.868, combination 0.922. So size dilutes the cell-day recall (it explains a large part of why the three are near 0.02-0.05), but even visible zeroed/scale/drift cell-days are mostly missed.
3. **A single value of these kinds looks plausible.** Zero, a scaled wet value and a drifted wet value are legal rain values; phantom rain (drizzle where neighbours are dry) and stuck (a constant over days) break spatial or temporal consistency. This is consistent with the per-kind result and with the CUSUM and the hold run, but it is an interpretation (ASSUMED).
4. **The features separate them, the head does not use that at this operating point; a toy calculation shows these are compatible.** Probe AUC (MAIN, fit 2013, test 2014): spike 0.999, phantom 0.987, stuck 0.975, scale 0.938, drift 0.895, zeroed 0.888. A: if scores were equal-variance Gaussians, AUC 0.888-0.938 corresponds to recall of only about 0.09-0.18 at a false-positive rate of 0.1% (0.27-0.44 at 1%); AUC 0.975 corresponds to 0.38, AUC 0.999 to 0.90 (the toy values are illustrative, real tails differ). So an AUC of 0.89-0.94 does not contradict a recall of 0.02-0.05 at 1 per 1,000; AUC is dominated by the bulk of the distribution, the budget by the extreme tail. The probe was also fitted on labelled validation faults of that kind, so it is an upper-bound style diagnostic, not a detector.
5. **Training exposure is not the cause.** HOLD never trained on the three kinds and recalls 0.002, 0.071 and 0.044 (zeroed, scale, drift), no lower than MAIN (0.018, 0.047, 0.027); its probe AUCs are 0.859, 0.931, 0.955 (drift higher than MAIN's 0.895). The encoder learns features that carry these kinds either way.
6. **The three kinds act like irreducible label noise during training.** Last-epoch stage-1 loss is 0.0206 for HOLD and 0.0411 for MAIN (`train_log_*.json`); D: about half of MAIN's training loss is attributable to the three kinds, assuming the rest of the optimisation is comparable (not a clean ablation). Removing them also improves the other kinds (stuck 0.770 to 0.897, spike 0.858 to 0.947, PR-AUC 0.686 to 0.731), though at 1.99 instead of 1.60 false alerts.
7. **More memory or more steps did not fix it.** LMC trained its LSTM for 54,000 steps (600 times MAIN's 90) and drift event recall moved +0.008 (interval -0.030 to +0.046, so includes 0; drift PR-AUC -0.003); LMB (+0.068 drift event recall) also moved the control kind zeroed by +0.084, which the protocol reads as "not memory alone". The ceiling by memory shows no drift recall gain at any memory length (MAIN 0.003-0.062; LMB peak 0.121 on only 585 cell-days). The stage-2 LSTM fits training years but not validation: LMC train loss about 0.013 against a one-year validation loss about 0.040 (noisy single-year value), no trend over 30 epochs.
8. **An untrained neighbour-residual CUSUM does worse on drift** (event recall 0.000, drift check). It does not prove drift is undetectable; it shows that this simple accumulator is not an answer.

### 3.2 What is speculation (do not state as fact)

- That the three kinds are "undetectable in principle". Dedicated heads get further: the zeroed head's centre-cell recall is 0.482 (strong 0.771) and the drift head's overall recall 0.023 versus 0.383 on all fault cell-days at its own thresholds, but those thresholds belong to separate budgets and the kinds are still mostly missed.
- That the training loss weights are the reason (`pos_weight` 10, footprint weight 0.2 + 0.8w, protected extremes weight 3, ambiguous 2, the loss is the average over 7 output channels, plus 0.5 x clean-value loss and 0.5 x hidden-disc loss; fault prevalence about 1% of cell-days). Event shares per kind are equal (about 14-15%), so kind imbalance by event is not the issue; by cell-days scale and zeroed are only 5.8% and 4.8% of positives. No run varies the weights, so the weights are untested as a cause.
- That a longer schedule would help: loss has plateaued (section 4), but only under the same constant learning rate, model size and loss. Untested.

### 3.3 The false-alarm budget miss (1.60 against 1.0)

Supported by the files:

- The threshold is the 0.999 quantile of scores on CLEAN (un-injected) training-client cells of 2016-2017 (`evaluate.py thresholds_for`). Applied to the other clean year it gives exactly the budget for the training clients pooled (1.001, D, section 2.4). So the budget is held on clean data and missed on the benchmark.
- On the benchmark, false alerts are counted on non-fault, non-protected, non-ambiguous cell-days of the fault-injected years. The rate there is 1.60 overall, 1.17 and 1.39 even in the two threshold years.
- It depends on the component: clean head 1.15, disc head 0.96, neighbour baseline 0.99 (near budget); fault head 1.60, hold 1.99, lmb 2.09, rules 2.39, slow 5.57, CUSUM 2.48. The fault heads, which are trained to respond to faults and to spread over a footprint (IoU 0.73), miss it most.
- Year effect on top: 2013-2015 at 1.57-1.98 against 1.17-1.39 in the threshold years.

ASSUMED mechanism: scores near injected faults (the footprint edge, neighbour contamination of features) raise the score of "clean" cells next to a fault; these are counted as false alerts but are arguably partly true. Not tested; testing needs the stored score files or the checkpoint (section 6).

Also: the protocol's per-client guard (every client at most 2.0 x budget) is passed by MAIN (max 1.80) and failed by LMB (4.94) and LMC (3.76) on the pooled global threshold.

## 4. Training behaviour

| Stage-1 epoch (59 year visits each) | Kaggle MAIN mean loss (sd of visits) | LOCAL run | HOLD |
|---|---|---|---|
| 0 | 0.0551 (0.0116) | 0.0542 | 0.0394 |
| 1 | 0.0435 (0.0064) | 0.0422 | 0.0253 |
| 2 | 0.0421 (0.0062) | 0.0400 | 0.0218 |
| 3 | 0.0411 (0.0066) | 0.0389 | 0.0206 |
| Stage 2 (3 visits) | 0.0244 | 0.0235 | 0.0107 |

(D from `train_log_*.json`; each visit's loss is the mean of its 200 steps; faults are redrawn at each visit.)

- **Converged or not:** most of the fall is in epoch 0 to 1 (-0.0115; lower in 50 of 59 years). Epoch 1 to 2 is -0.0014 (lower in 29 of 59 years) and 2 to 3 is -0.0010 (32 of 59), about one standard error (0.0008-0.0009): the loss has flattened at the constant learning rate (config lr 0.001, no schedule found in the config). It is not a proof of convergence of detection quality; no validation curve per epoch exists for stage 1 (validation loss exists only for stage 2, one year, 2013).
- **"800 steps at batch 2" is wrong** (section 0): 47,200 steps, 94,400 crops of 80 x 80 cells (48 + margin) x 16 days, about 0.18 s per step on a T4 (GPU utilisation 93%, so GPU bound). Each of the 59 training years was seen 4 times with different injected faults. It is still a short schedule for a 1.76 M-parameter model (about 2.5 hours on one T4) but not a few hundred steps. The LOCAL run took 4,674 s on an RTX A6000 (vGPU) for the same schedule.
- **Long-memory stage:** trained on only 3 years (2010-2012) with 1,024 cells per step. Train loss falls with more steps (0.0244 MAIN; LMB epochs 0.015-0.022; LMC 0.011-0.017) while the one-year validation loss does not (LMB 0.029-0.037, LMC 0.030-0.046, no trend; the "best" epoch is a noisy pick that was not used). That is the signature of limited generalisation of this stage, not of under-training (ASSUMED reading; the validation value is one random year with one fault draw).
- **What a longer schedule might change (UNTESTED):** a few more points of recall on the strong kinds (their loss is still falling slowly in some years), possibly a different false-alarm level. The weak kinds are not expected to move on loss grounds alone (HOLD and LMC evidence above), but that is a hypothesis; a learning-rate decay, a larger crop, or a different loss for those kinds is the real test.

## 5. Reproducibility: LOCAL run against the Kaggle MAIN run

| | LOCAL (repo) | Kaggle MAIN |
|---|---|---|
| PR-AUC / recall / event recall / false per 1,000 | 0.720 / 0.665 / 0.673 / 1.53 | 0.686 / 0.637 / 0.659 / 1.60 |
| Threshold at budget 1.0 | 1.114 | 1.634 |
| Clean head PR-AUC | 0.366 | 0.451 |
| Client 3 false/1,000 (global) | 3.08 | 1.80 |
| Client 6 false/1,000 | 0.59 | 1.15 |
| Drift event recall | 0.379 | 0.242 |

Identical: seed 42, `config_digest` `b5af58ff5130c309`, split hash `a079504cc9e89c1b`, benchmark hash `c37de7e3cf2be90e`, the whole `stnet` config block (width 32, crop 48, steps 200, epochs 4, batch 2, window 16, pos_weight 10, lr 0.001, long 1 x 30), the year-visit order (all 239 visits are the same years in the same order, D) and the benchmark (6,867,311 clean cell-days in both). Per-visit training loss correlates 0.99 between the two runs (D), but the LOCAL run is lower in every epoch and the gap grows (-0.0008, -0.0014, -0.0021, -0.0022).

Different:

| Item | LOCAL | Kaggle MAIN | Could it explain the gap? |
|---|---|---|---|
| Code commit | `287c519+dirty` (uncommitted changes, unknown) | `70fe332` | The tracked diff 287c519..70fe332 adds scoring, `--init-from` and STNet-candidate code and does not touch `faults.py`, `evaluate.py`, `metrics.py`, `benchmark.py`, `features` (D, `git diff --stat`); the "dirty" part cannot be checked. Unlikely but unprovable |
| GPU | NVIDIA RTXA6000-12Q (Ampere, vGPU) | Tesla T4 (Turing) | Yes: different kernels, TF32 default behaviour and reduction order give different floating-point results; the code sets only `torch.manual_seed(seed)` and no determinism flags |
| torch / CUDA / Python / OS | 2.5.1+cu121 / 12.1 / 3.10.11 / Windows 10 | 2.11.0+cu130 / 13.0 / 3.13.16 / Linux 6.18 | Yes: random-number and kernel differences; different numpy/scipy versions not recorded |
| Wall time | 4,674 s | 9,172 s | Consequence, not a cause |
| Session | one run 12:05-13:23, then a short 18.6 s continuation to evaluate (`resumed` 13:23) | one uninterrupted run | Probably not (the continuation was only scoring and probe) |

The most plausible explanation is ordinary run-to-run numerical divergence amplified by training on 47,200 steps (hardware plus library versions, ASSUMED); nothing in the files points to a configuration difference. The size of the gap matters for claims: 0.034 PR-AUC between two runs of one configuration, larger than the LMB-MAIN difference (+0.021) that the paired test calls "5 of 5 years better" and larger than client-level false-alarm gaps being explained (client 3 1.80 vs 3.08). The paired intervals condition on a fixed encoder and a fixed set of years and therefore cannot see this randomness. Seed variance is unmeasured; this one pair is the only information on it.

## 6. Critical read

### 6.1 Threats to validity

| Threat | Evidence in the files | Effect |
|---|---|---|
| In-distribution faults | Training and evaluation use the same `FaultGenerator` and the same "seen" settings; the benchmark faults are drawn with the same code (kinds, footprints, strength ranges) | Recall measures "finds what the generator makes". The built-in out-of-setting test (`edge`, `repeat` kinds, radius 4-6, weak strength under 0.25: 665 test events, 4,188 stress events) has not been scored |
| HOLD does not test generalisation | Held-out kinds are still generator kinds evaluated on the same generator | It says exposure does not change recall; not that real unseen faults would be found |
| Years shared | Thresholds from clean 2016-2017 sit inside the 2013-2017 evaluation window; the fusion is fitted on 2013-2015; the probe is fitted on 2013 and scored on 2014 (all validation labels); lmb/lmc "best" epoch picked on 2013 loss (not scored) | Not independent confirmation; permitted by the protocol (validation only) |
| Unseen regions not scored for recall | Section 0 item 7 | The "held-out clients" story rests on false alarms only |
| RF25 as truth | RF25 is an interpolated gridded product (per the earlier review; not re-verified here); "clean" = not injected, with no quality flags | Some "false alerts" may be real errors or real extremes; real gauge faults after interpolation may not look like disc-shaped injected footprints |
| Synthetic faults | `label_tier` is "synthetic faults" in every file | Real fault statistics, durations and sizes unknown |
| Extremes defined by the same rule that shaped training | `find_extremes` sets "protected" (loss weight 3) and "ambiguous" (weight 2) in training and is the evaluation's protected set; protected cells are also forbidden for injection | "Protected extremes flagged 0.15%" is partly built in; a fault on top of a real heavy-rain event (the hard case) is never tested |
| Recall rewards the footprint, not the faulty value | 20.7% of fault cell-days change under 0.1 mm and the fault head still flags 43% of them (ceiling); clean head flags 0.6% | The head partly detects "near a fault"; this inflates recall relative to flagging the changed cells (and links to false alerts at footprint edges) |
| Event recall lenient | Section 0 item 6 | Report cell-day recall and delay beside it |
| One seed, five years | Sections 2.5 and 5 | Intervals undercover; run-to-run gap exceeds several reported gains |
| Budget not held | Section 3.3 | Recall "at budget" is at 1.6 to 2.1 false/1,000 for the heads; rules at 2.4, slow at 5.6; compare PR-AUC |
| Precision depends on prevalence | D, section 7: the same alert rates give precision 0.29, 0.67, 0.80 at prevalence 0.1%, 0.5%, 1.0% | Quote precision only with the 1% benchmark mix stated |

### 6.2 What to do next (cheapest first; what each would show)

| # | Experiment | Cost | What it would show |
|---|---|---|---|
| 1 | Re-score `stnet_s42_final.pt` on the five validation years with groups "seen" AND "unseen", and write recall by client, by year, by season, and by distance to the nearest fault footprint (also false alerts by that distance) | Minutes on a GPU, perhaps a few minutes on CPU (about 63 ms per day-grid on CPU per the earlier review; needs RF25 files) | Whether the unseen clients are detected at all; whether the 1.60 miss is footprint-edge spill; yearly spread |
| 2 | Report recall conditional on observable change (cell-days with value change at least 1 mm or at least 5 mm) for every kind and head | Same re-score | A fairer recall for the weak kinds; separates "invisible by construction" from "visible but missed" |
| 3 | Seed repeats (seeds 43 and 44; the notebooks exist) for MAIN, then the paired tests on all three | About 2.5 T4 hours each | Real run-to-run spread; whether lmb's +0.021 or the HOLD +0.045 PR-AUC are outside it |
| 4 | Extend the threshold to the evaluation conditions: fit the threshold on a fault-injected clean-year pair (labels excluded) or per-component calibration on benchmark-like data; report both clean and benchmark false-alarm rates | Re-score plus quantiles | Whether the 1.0 target can be held in operation and which of the two rates matters |
| 5 | Train a variant that labels only cell-days whose value changed, with per-kind loss weights and kind-balanced sampling, then repeat 1-2 | One run, about 2.5 T4 hours | Whether the weak-kind failure is label design and weighting rather than model capacity; also tests the footprint-recall effect |
| 6 | Longer or scheduled training (learning-rate decay, 2x steps) with a stage-1 validation loss each epoch | One or two runs | Whether the flat loss is a real plateau; whether strong-kind recall still rises |
| 7 | Freeze budgets in the protocol table, run `choose-stnet`, then ONE test pass including the test-only generator settings | Protocol steps, one scoring pass | The only in-protocol out-of-sample number; first look at the out-of-setting faults |
| 8 | A second, independently written fault generator (or real flags from the UK MIDAS archive in `docs/research`) | Larger, days | In-distribution versus real-world gap; the only route to a claim beyond "on our generator" |
| 9 | Real-station sparse-grid check (`sparse-check`, `score-gauges`, built, not run) | Moderate | Whether STNet is usable on gauges at all |

## 7. Extra check (A, analysis, NOT an evaluation)

Script `scratchpad/an/check.py` recomputed from stored counts (MAIN `stnet_fault_s42_val.json`, `drift_check_s42.json`, ceiling tables):

| Check | Result |
|---|---|
| Kind events and cell-days sum to the aggregate | 935 / 935 and 65,810 / 65,810 |
| Cell-day-weighted kind recall reproduces the headline | 0.6366 (stored 0.6366); event-weighted event recall 0.6588 (stored 0.6588) |
| False alerts / clean cell-days | 10,997 / 6,867,311 = 1.6014 per 1,000 (stored 1.6014) |
| Mean of the five per-year false-alert rates | 1.6014 (equals the pooled rate) |
| Ceiling bins rebuild the stated overall | change bins N = 29,098, weighted recall 0.619, share under 1 mm 0.561 (all as stated); kind rows N = 29,098, 0.619 |
| Precision / F1 from counts | TP 41,897 (D = recall x 65,810), FP 10,997: precision 0.792, recall 0.637, F1 0.706 at prevalence 0.95% (matches the review's 0.79 / 0.71). At prevalence 0.5% precision 0.67, at 0.1% 0.29 |
| Interval consistency | A naive binomial 95% interval for the false-alert rate is 1.571-1.631; the stored whole-year bootstrap is 1.34-1.85, 9 times wider, i.e. alerts cluster by year, region and event, so the effective sample is far smaller than 6.9 million. For kind recall the naive Wilson intervals are 3-7 times narrower than the stored ones (for example spike 0.845-0.870 against 0.731-0.921). The stored (wider) intervals are the honest ones; the naive ones must not be quoted |
| Budget table | Targets 0.5, 1, 2, 5, 10 reach 0.85, 1.60, 2.90, 6.43, 12.11 (achieved is about 1.2-1.7 x target at every level) |
| Seed-gap context | LOCAL vs MAIN: PR-AUC 0.720 vs 0.686 (gap 0.034); LMB vs MAIN +0.021 |

Everything reproduces from the stored counts; no inconsistency was found inside the files. The unexplained pieces are the ones in sections 3 and 5, not arithmetic.

## 8. Defend it: ten hard questions

1. **"Is 0.69 PR-AUC good?"** It is the best of the scores tried (rules 0.34, neighbour 0.10, slow 0.04) on synthetic faults in the validation years with one seed. It is not a result on real faults and no test year was scored. One other run of the same configuration gave 0.72, so differences below about 0.03 are within what we have seen between two runs.
2. **"You aimed for 1 false alert per 1,000; you got 1.6. Why is it valid?"** The threshold does reach 1.00 on clean years for the training regions (1.001) and misses on the benchmark (1.60; 1.17 and 1.39 even in the threshold years). The likely reason is that the benchmark counts false alerts near injected faults, which I have not tested. So compare recall only at matched false-alarm rates or use PR-AUC, and I do not claim the budget was met.
3. **"Three of seven fault kinds are almost never detected. Is the model useful?"** Recall is 0.83 on four kinds and 0.03 on scale, drift and zeroed (cell-days). In the data, over half of their cell-days change the rain by under 1 mm and many are zero changes by construction on dry days, but even the strong cases (5 mm or more) are mostly missed (0.04 to 0.25). I report it as a limit; the model is not a drift or zeroed-value detector.
4. **"Your held-out test shows generalisation."** No. The hold-out run excludes three kinds from training but uses the same generator for testing; their recall is equally low (0.2-7%), and it says that exposure to those kinds did not matter. Held-out regions 3 and 6 were scored for false alarms only (1.80 and 1.15 for MAIN, up to 4.94 for LMB), never for recall.
5. **"Why trust one seed?"** I do not. Two runs of the same configuration differ by 0.034 PR-AUC and by client-level false alarms of 1.80 against 3.08 on client 3. Paired tests with the same encoder do not capture this. Seed repeats are the first thing I would add.
6. **"Did longer memory help drift?"** No on the pre-set rule: lmb gave +0.068 drift event recall but also +0.084 on the control kind zeroed and false alerts rose from 1.60 to 2.09; lmc gave +0.008 with 54,000 stage-2 steps. The stage-2 stage fits its three training years and not the validation year.
7. **"How many training steps?"** 47,200 stage-1 steps at batch 2 (200 steps for each of 236 year visits), about 2.5 hours on a T4; loss flattened after epoch 1 (differences of 0.001 per epoch, about one standard error). I cannot say whether a longer schedule would help; I did not test it. (The earlier "800 steps" figure was wrong.)
8. **"Does it separate real extremes from faults?"** On this benchmark 0.15% of protected extreme cell-days are flagged, against 19.6% for the rules. But the protected set is defined by the same rule that weights the training loss, and faults are never injected on top of heavy-rain events, so this shows no more than consistency with that definition.
9. **"Why do the probes show 0.89 to 0.94 and the head 0.02 to 0.05?"** AUC measures ranking over all cell-days; the budget looks at the top 0.1% of clean scores. With normal scores, an AUC of 0.89 to 0.94 only implies recall of roughly 9 to 18% at that rate (an illustration, not a measurement). The probe was also fitted on labelled validation faults.
10. **"Can it run in DataMend?"** Not live: it needs a gridded rainfall field, 16 days of history (90 for long memory), and a torch service; the platform has gauges. It can be an offline research score file, labelled synthetic and not validated, as the earlier review concluded.

### Claims the student must avoid

- "800 steps" or "a few hundred steps" (it is 47,200).
- "Meets the 1-per-1,000 false-alarm budget" (1.60 and above; unseen client up to 4.94).
- "Generalises to unseen regions" or "to unseen fault types" (recall was not scored on the unseen clients; the hold run uses the same generator).
- "Detects drift, scale or zeroed faults" or any recall quoted without the kind split; "event recall" as if it were the share of faulty values found.
- "Long memory improves drift" (pre-set rule not met in both runs).
- Any figure as real-data, test-year or operational performance; "state of the art" or novelty (AGENTS.md section 5; no citation).
- Precision or F1 without "1% benchmark prevalence, derived".
- "The best/final checkpoint was chosen on validation loss" (the scored model is the final one).
- Naive confidence intervals (binomial over millions of cell-days); use the whole-year bootstrap and say it covers 84-90% for 95% nominal.
- "Seed-independent" or "reproducible to the digit" across hardware (the two runs differ).
