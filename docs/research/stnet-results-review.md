# STNet results review (owner's training runs, 2026-11-19 to 2026-11-20)

Reviewed 2026-11-21 from `C:\Users\V\Downloads\results` (result zips extracted into a scratch folder, read with `python -I`; checkpoints loaded with `torch.load(weights_only=True, map_location="cpu")`; no notebook or script was executed; credential files untouched). STNet is the Part B research model (gridded rainfall, `ml-service/qc/`), NOT on the live platform path.

## 1. What the numbers are

- Data: IMD RF25 daily 0.25-degree grid (125 yearly files), 8 regional clients, clients 3 and 6 never seen in training. Time split: train 1951-2012, **validation 2013-2017**, test 2018-2025 (spec section 3). Thresholds from clean 2016-2017 on training clients.
- Faults: **SYNTHETIC**, injected by this repo's generator into real RF25 (benchmark hash `c37de7e3cf2be90e`, about 1% of cell-days; 935 fault events, 65,810 fault cell-days, 6,867,311 clean cell-days). `label_tier` in every metrics file is "synthetic faults". No real labels exist.
- **Every number below is a validation number. No test year (2018 onward) was scored** (no `stnet-test` output, `choose-stnet` not run, the budgets table in `docs/qc-evaluation-protocol.md` is still empty).
- One seed (42). Same config digest `b5af58ff5130c309`, split hash `a079504cc9e89c1b`.
- Training (main run, `stnet_s42/meta.json`, train log): 4 epochs x 200 steps, batch 2, 48-cell crops, 16-day window; stage 1 loss per epoch 0.0551, 0.0435, 0.0421, 0.0411 (years 1951-2009, 59 year visits per epoch); stage 2 (long memory) 3 years x 1 epoch x 30 steps, 17 s, loss 0.0244 (years 2010-2012). Fixed schedule: no early stopping, no best epoch in the main run. Wall 9,172 s on one Tesla T4 (165.7 Wh GPU), 1,761,769 parameters (+24,263 in the LSTM).

## 2. Headline metrics (budget target 1.0 false alert per 1,000 clean cell-days, validation 2013-2017)

Source: `artifacts/qc/base/*/metrics/*_val.json` (main, lmb_lmc, hold zips). "False/1,000" is the ACHIEVED rate, not the target. Precision and F1 are DERIVED here from stored counts (recall x 65,810 fault cell-days; false alerts count), not stored in the files, and depend on the benchmark's 1% fault mix.

| Score | PR-AUC | Recall (cell-days) | Event recall | False/1,000 (CI) | Precision (derived) | F1 (derived) | Delay median / p90 (days) |
|---|---|---|---|---|---|---|---|
| STNet fault head (main) | 0.686 | 0.637 | 0.659 | 1.60 (1.34-1.85) | 0.79 | 0.71 | 0 / 24 |
| + long memory 8 x 300 (lmb) | 0.707 | 0.670 | 0.675 | 2.09 (1.71-2.38) | 0.76 | 0.71 | 0 / 30 |
| + long memory 30 x 600 (lmc) | 0.692 | 0.651 | 0.663 | 1.90 (1.70-2.12) | 0.77 | 0.70 | 0 / 24 |
| Hold run fault head (zeroed, scale, drift never trained) | 0.731 | 0.695 | 0.631 | 1.99 (1.80-2.14) | 0.77 | 0.73 | 0 / 31 |
| STNet clean head (main) | 0.451 | 0.369 | 0.587 | 1.15 | 0.75 | 0.50 | 0 / 31 |
| STNet disc head (main) | 0.066 | 0.040 | 0.311 | 0.96 | 0.28 | 0.07 | 0 / 30.5 |
| Rules (untrained) | 0.344 | 0.452 | 0.517 | 2.39 (1.40-3.45) | 0.64 | 0.53 | 0 / 11 |
| Neighbour baseline (untrained) | 0.096 | 0.066 | 0.432 | 0.99 | 0.39 | 0.11 | 0 / 22 |
| Slow (untrained) | 0.038 | 0.083 | 0.199 | 5.57 | 0.13 | 0.10 | 2 / 8 |

Main fault head at other targets (same file): target 0.5 gives achieved 0.85, recall 0.612; 2.0 gives 2.90, 0.655; 5.0 gives 6.43, 0.676; 10.0 gives 12.1, 0.694.

Fused with rules (`ablation_custom_stnet_s42.json`, budget 1.0): logistic rules + fault head PR-AUC 0.691, recall 0.635, event 0.619, false 1.27, protected flagged 0.6%; boosted 0.682, 0.629, 0.573, 0.73, 2.7%; boosted rules + four heads 0.707, 0.644, 0.637, 1.38, 2.3%. The earlier daily fusion (repo `ablation_s42.json`, rules+slow+spatial+temporal) reached PR-AUC 0.459 to 0.540, recall 0.436 to 0.470.

Fault head by kind (cell-day recall / event recall, main, budget 1.0): spike 0.858 / 0.993; stuck 0.770 / 0.991; phantom rain 0.873 / 0.957; combination 0.823 / 0.841; scale 0.047 / 0.312; drift 0.027 / 0.242 (median delay 19.5 d, 100 of 132 events never detected); zeroed 0.018 / 0.282. Protected extremes flagged: 0.15% of cell-days (rules 19.6%). Ceiling by fault size (`ceiling_stnet.md`): recall 0.427 under 0.1 mm, 0.567 for 0.1-1 mm, 0.885 for 20-100 mm; "strong" faults (5 mm or more, footprint weight 0.5 or more) 0.778; 56% of fault cell-days change the rain by under 1 mm.

Probes (`probe_stnet_s42.json`, linear probe on frozen features, fit 2013, test 2014; NOT a detector): AUC spike 0.999, stuck 0.975, phantom rain 0.987, scale 0.938, zeroed 0.888, drift 0.895.

Long memory (`paired_stnet_vs_stnet_lmb_s42.md`, `_lmc_`): lmb vs main recall +0.034 (5 of 5 years), PR-AUC +0.021 (5 of 5), drift event recall +0.068 but the control kind zeroed +0.084 and false alerts 1.60 to 2.09; the pre-set rule (protocol) is NOT met for either length: "no gain on this encoder". lmc: recall +0.015, PR-AUC +0.006 (interval includes 0), drift -0.003. Validation-year loss of lmc wandered 0.033 to 0.044 with no trend. Drift check (`drift_check_s42.md`): CUSUM drift event recall 0.000 vs fault head 0.242, rule NOT met.

Compute (`telemetry/*.md`, T4): inference about 20 ms per day-grid on the T4 (`stnet.infer.network` 49.8 days/s), 8.2 GFLOPs per day-grid (`model.stnet.flops_per_day_full_grid`), checkpoint 7.17 MB file.

## 3. Suspicious or limiting findings

1. **The false-alarm budget is not held.** Every STNet head exceeds its 1.0 target on validation (1.60, 1.90, 2.09, 1.99; the fused rows 0.73 to 1.38), the interval for the main head (1.34-1.85) excludes 1.0, and the held-out client 3 reaches 1.80 (main), 4.94 (lmb), 3.76 (lmc) with the global threshold (`budget_check_*.json`). Comparing recall "at the budget" across rows is therefore not like for like (rules 2.39, slow 5.57); PR-AUC is the fair column.
2. **Same seed, same config, different result.** The first (local) run still in the repo (`ml-service/artifacts/qc/base/stnet_s42`, commit `287c519+dirty`) gave PR-AUC 0.720, recall 0.665, false 1.53, threshold 1.11; the Kaggle run gave 0.686, 0.637, 1.60, 1.63. Seed variance is unmeasured; differences of 0.02 to 0.03 PR-AUC (lmb vs main) are within what two identical runs differ by. Which of the two produced `stnet_s42_final.pt` is not recorded in the files I read (the zip dates suggest Kaggle; UNVERIFIED).
3. **In-distribution test.** The generator that injects the evaluation faults is the one that trained the model (`seen` settings; hold-out kinds excluded from training only in the hold run). The hold run (zeroed, scale, drift never trained) recalls 0.2%, 7.1%, 4.4%: about as low as the main run (1.8%, 4.7%, 2.7%) that did train on them. So these three kinds are essentially undetected by cell-day recall either way, and the hold run says nothing about generalisation to unseen real faults.
4. **Thresholds and evaluation share years.** Thresholds come from clean 2016-2017, which lie inside the 2013-2017 validation window used for the recall figures; the lmb/lmc "best" checkpoint uses validation-year loss. Allowed by the protocol (validation only), but it means these are not independent confirmation, and the protocol's budgets table has no entry yet.
5. **Ceiling table subset differs.** `ceiling_stnet.md` reports fault-head overall recall 0.619 on n=29,098 cell-days while the metrics file reports 0.637 on 65,810. The files do not say how the ceiling subset is drawn (UNEXPLAINED); I used the metrics file for headline numbers and the ceiling only for the by-size and by-kind breakdowns.
6. **Very short training**, unrepeated: 800 optimiser steps in stage 1 at batch 2 on 48-cell crops; the long-memory stage 17 s. Authors' own note: "memory NOT MEASURED" for the base run.
7. **"Clean" is assumed.** False alerts are counted on RF25 days not touched by the injector; RF25 has no QC flags, so some "false alerts" may be real errors or real extremes, and RF25 is itself an interpolation of gauges (smoother than gauges).
8. **Precision and F1 do not exist in the files** and depend on the 1% prevalence of the benchmark; treat the derived columns as illustrative.
9. Protocol status: `choose-stnet`, budgets table and `stnet-test` are not done; the sparse-gauge rule (frozen 2026-11-21) is "not run". No result here may be quoted as test or real-data performance.

## 4. Can the checkpoint be used in DataMend?

What it needs (`qc/stnet.py`): a daily rainfall FIELD on a regular grid (RF25 is 129 x 135, 0.25 degree, 4,964 land cells) with NaN for missing; 11 channels per day (log1p(mm)/scale, valid, land, cell minus neighbourhood median at radius 2 and 4 and mean at 8 and 16, climatology, heavy-rain threshold, day-of-year sin and cos), per-client normalisation scale, a 16-day window with a ConvGRU state, and for the long-memory correction a per-cell history that starts 90 days before the scored year. Output: a (7, H, W) logit map per day (any fault plus spike, stuck, scale, phantom rain, zeroed, drift), plus clean-value and masked-disc heads; scores are softplus of the logit.

What the platform has: 580 Weather Union point gauges (rain accumulation, daily 03 UTC totals only just starting, units assumed mm), Open-Meteo model estimates, simulator, uploads of single-station series; T/P/RH streams. No gridded rainfall product is connected (IMERG dropped).

Measured here (SMOKE TEST on a generated random 129 x 135 field, NOT an evaluation; torch 2.10.0+cpu, Windows laptop, 16 logical cores): the final checkpoint loads with `weights_only=True` (keys model, long, sig, seed, config_digest; 64 + 6 tensors; 1,761,769 + 24,263 parameters, 7.05 MB fp32 weights, 7.17 MB file) and returns a finite (20, 7, 129, 135) fault map. Network 63 ms per day-grid on 4 threads (148 ms on 1 thread), features 67 ms per day-grid. Memory: `import torch` alone is 201 MB working set; 5 to 20 day passes peaked at 480 to 800 MB (570 MB single thread, 10 days). The lmb final checkpoint loads and behaves the same (82 ms per day-grid, 480 MB).

| Option | Verdict | Reasons |
|---|---|---|
| (a) Offline research score file in the evidence (`score-export-v1` via `ml-service/qc/score_export.py`, read by `ScoreProvider`) | **Feasible, as research only** | The file format and the provider seam fit (`fault_*` arrays, `label_tier: synthetic`, `calibrated` false without a budget). Work: score a real daily gridded rainfall product or the gauges-as-sparse-grid path (`qc/sparse.py`, `score-gauges`, built but NOT RUN), run `sparse-check` on RF25 and record the rule result, fix the station-to-cell mapping (open research ticket; the provider's nearest-centre-within-0.13-degree is a stand-in), standardise on clean validation years, log the budget in the protocol before any threshold is exported, and keep every place labelled "synthetic, not validated". Rainfall only. |
| (b) Serve live behind the web app | **Blocked** | (1) No live gridded rainfall; a sparse set of gauges is far from the trained full field and its cost is unmeasured. (2) Needs 16 days (90 days for the long memory) of daily history per cell; the gauge feed has no back-fill. (3) torch is 200 MB to import and a full-grid pass peaked at 570 to 800 MB on this laptop against 512 MB on Render free; it would need a separate service (the Keras scorer already is one), an ONNX conversion (not tried) and a smaller crop. (4) The false-alarm budget is not held, there is no real-fault or test-year evidence, and the unseen client reaches 1.8 to 4.9 per 1,000. |
| (c) Not usable for | **Not usable** | Any verdict (the platform's rule: scores are evidence only); temperature, pressure or humidity (rainfall-only model); a station check without a grid. |

Versus the Keras scorer: the Keras model is a generic 288-step one-variable reconstruction autoencoder per station stream, pretrained by others and NOT validated; STNet is a trained, partly measured (synthetic) model but for a different input (spatial fields). They are not interchangeable; the Keras scorer remains the only live score path, and STNet's possible entry is the offline file in (a). Missing for any live use: retraining or at least calibration on station data, the station-to-grid mapping, a measured sparse-input result, a held budget on held-out clients, and a test-year pass.

Verdict: use as the offline research score file (a) after the sparse check; do not serve live now; not usable as a verdict.

## 5. Not verified

- Which run produced `stnet_s42_final.pt` (the three files `.pt`, `.pth`, `.zip` are byte-identical, md5 `c70e3a9c...`).
- Anything on real faults, real gauges or test years; ONNX conversion and the real Render memory (laptop numbers only); seed variance; the unexplained ceiling subset; the notebook `stnet_F_drift.ipynb` was read only as JSON text, never run.
