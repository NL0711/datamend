# Precipitation QC: prior work and open angles (2026-11-17)

Method: web search plus page or PDF fetches. A source is marked **opened** only if I read its abstract page or full text in this session. Anything seen only in a search-result snippet is marked **snippet only** and is unverified. Nothing here is a novelty claim: where I found no prior work, the text says "not found in the sources I checked" and lists what I searched (section 5). Several search tool summaries contained errors (for example one said the CODiT paper evaluates on weather data; its abstract page does not mention weather), so only text I opened is relied on.

Note on location: the brief asked for `docs/qc-novelty-research.md`; the existing research notes live in `docs/research/`, so the file is `docs/research/qc-novelty-research.md`. Move it if you want the other path.

## 1. Summary

**Already done in the literature (so not ours to claim):**

- Rule-based QC for daily precipitation: world-record limits, duplicate, streak and frequent-value checks, gap checks, climatological percentile outliers, and neighbour spatial-corroboration checks, applied at scale (Durre et al. 2010, opened).
- Designing QC explicitly to keep true extremes: Durre et al. state the false-positive goal; HadISD (temperature, dewpoint, pressure, wind, cloud; not precipitation) validated against known extreme events; RainGaugeQC lowers a quality index instead of rejecting range exceedances (opened).
- Deep-learning QC of precipitation observations trained on human labels, using gridded fields around each station (Sha et al. 2021, opened); ML QC using neighbour relationships to "preserve true extremes" (Met Office EMS 2025 abstract, opened, no validation stated).
- Space-time statistical QC that separates local from regional extremes and checks flags against radar and discharge (El Hachem et al. 2022, opened).
- Masked-reconstruction pretraining for rainfall (SSIN, snippet only) and supervised training with injected synthetic anomalies for time series (NCAD, Outlier Exposure; snippet only).
- Conformal anomaly detection with controlled error rates, conformal methods under distribution shift, and federated conformal prediction under label or covariate shift (Bates et al. 2023; Gibbs and Candes 2021; Plassier et al. 2023 opened; a 2026 covariate-shift preprint snippet only).
- Personalized federated learning for anomaly detection in general and for weather forecasting or radar nowcasting (snippet only).

**What appears open (not found in the sources I checked):**

- Combining gridded-rainfall QC, a per-cell spatial-coherence test of the event, and a calibrated false-alarm budget with protected-extreme false removal as a headline metric.
- A conformal or calibrated false-alarm guarantee for rainfall QC evaluated on held-out regions of a federated split.
- Fault-supervised training with an explicit penalty on protected extremes for rainfall.
- Federated or personalized learning applied to rainfall or weather-station QC.

**Top 3 directions and the evidence each needs:**

1. **Event-coherence evidence for extreme vs fault (angle a).** Add neighbour-consensus features (size of the connected above-threshold group, rank agreement with neighbours, same-day footprint shape) to the fusion and show protected-extreme false removal drops at a fixed budget without recall loss. Needs: ablation with and without the features, a non-injected check (named real events, ideally MIDAS flags), and a faults-that-mimic-coherence stress set.
2. **Calibrated thresholds with measured shift behaviour (angle b).** Set the budget by a conformal or split-quantile rule on clean cell-days, per client and stratified by wetness or extremeness, and report realised false-alarm rate on held-out clients and test years against the nominal target. Needs: coverage-by-client and by-year tables, a block-aware calibration because cell-days are spatially and temporally dependent, and an honest statement that no formal guarantee holds under that dependence.
3. **Fault-supervised loss with a protected-extreme penalty (angle d), framed as a controlled ablation.** Compare unsupervised NLL, NLL plus fault-supervised term, and the same plus a protected-extreme penalty, at equal budgets. Needs: three seeds, held-out fault kinds and test-only recipes, and the real-fault check from the MIDAS study to bound circularity.

## 2. Established practice

| Method | Source (year) | What it does | Status |
|---|---|---|---|
| GHCN-Daily QA, 19 tests | Durre, Menne, Gleason, Houston, Vose, J. Appl. Meteor. Climatol. 49(8), 2010 | Duplicate, world-record, streak, frequent-value, gap, climatological outlier (precip flagged above 9x the local 95th percentile of wet days, 5x below freezing), spatial regression and spatial corroboration (neighbours within 75 km, lags -1/0/+1 day), megaconsistency. Thresholds set by manual review to minimise false positives; flags 0.24% of values, reported false-positive rate 1-22% | Opened (PDF) |
| HadISD QC | Dunn et al., Climate of the Past 8, 2012 (v2: Dunn et al. 2016, GI) | Intra- and inter-station QC of sub-daily temperature, dewpoint, pressure, wind, cloud (not precipitation); flags not deletes; tests tuned against known extreme events (Katrina, 1989 Alaska cold snap) | Abstract opened; v2 snippet only |
| IMD gridded rain (IMD4, the RF25 lineage) | Pai et al., MAUSAM 65(1), 2014 | Station QC before gridding (typing and coding errors, missing, duplicate station, extreme-value checks), then inverse-distance interpolation on 0.25 degree. Details of the extreme-value check are not given in the text I read | Opened (PDF text) |
| CHIRPS station screening | Funk et al., Scientific Data 2, 2015 | Excludes station values with very large standardised anomalies (about 4 sd) or ratio above 5 to the satellite estimate; screens GTS/GSOD zeros on days the satellite estimate is above normal; ranks sources by reliability | Opened (via fetch summary of PMC page, first 100k chars) |
| Gauge-rainfall QC, PWSQC | de Vos et al., Geophys. Res. Lett. 2019 | Real-time four-module QC of crowdsourced personal weather stations with inter-station checks (faulty zeros, high influx, outliers) | Snippet only |
| GSDR-QC | Lewis et al., Environ. Model. Softw. 144, 2021 | Open-source 25-check rule base for hourly rainfall; compared with manually QC'd GPCC data | Snippet only |
| RainGaugeQC | Osrodka, Otop, Szturc, Atmos. Meas. Tech. 15, 2022 | Gross, climate-range, radar-conformity, temporal and spatial checks giving a 0-1 quality index; only very likely errors become no-data; radar can confirm an outlier; validated by case studies and one synthetic value, not manual flags | Opened |
| Space-time statistical QC of extremes | El Hachem, Seidel, Imbery, Junghanel, Bardossy, Hydrol. Earth Syst. Sci. 26, 2022 | Box-Cox plus cross-validated kriging from 30 neighbours; criteria ratio over 3 flagged; local high-ratio vs regional low-ratio events separated; radar and discharge checks; synthetic scaling of 25-100% on 20 clean stations | Opened |
| Deep-learning precipitation QC | Sha, Gagne, West, Stull, J. Atmos. Oceanic Technol., 2021 | CNN ensemble over gridded precipitation and elevation around each station, trained on human QC labels 2016-17; AUC 0.927, error rates under 15% | Opened (abstract) |
| ML monthly rainfall QC (UK) | Packman and Carlisle (Met Office), EMS Annual Meeting abstract 2025 | ML using nearby stations, elevation, coast distance, past observations, trained on historical data with known anomalies; aims to preserve true extremes and remove "bullseyes"; no validation given in the abstract | Opened (abstract only) |
| Spatial QC pitfalls for extremes | Serrano-Notivoli et al., WIREs Water 2021 (review); Osrodka 2022; sparse-network caution in the RainGaugeQC adaptation, Atmos. Meas. Tech. 18, 2025 | Spatial agreement signals good data but can discard real extremes; worse in sparse, convective regimes | Snippets only except Osrodka 2022 |
| Masked reconstruction for rainfall | Li, Shen, Chen, Ng, SSIN, Proc. ACM Manag. Data (SIGMOD 2023), arXiv 2311.15530 | BERT-style masked recovery with a Transformer for gauge-to-location interpolation; interpolation, not QC | Snippet only |
| Injected-anomaly supervised training | Carmona et al., NCAD, arXiv 2107.07702 / IJCAI 2022; Hendrycks, Mazeika, Dietterich, Outlier Exposure, ICLR 2019 | Train detectors with synthetic or auxiliary outliers to generalise to unseen anomalies | Snippet only |
| Conformal outlier testing | Bates, Candes, Lei, Romano, Sesia, Ann. Statist. 51(1), 2023 | Conformal p-values for outliers with FDR control and a uniform bound on false-positive rate for any detector | Snippet only |
| Conformal under shift | Gibbs and Candes, NeurIPS 2021, arXiv 2106.00170 | Adaptive miscoverage level giving long-run coverage without exchangeability | Snippet only |
| Federated conformal | Plassier, Makni, Rubashevskii, Moulines, Panov, ICML 2023, arXiv 2306.05131 | Importance-weighted federated conformal prediction under label shift, with privacy guarantees | Opened (abstract) |
| Federated conformal, covariate shift | arXiv 2606.00717 (2026, personalized federated weighted conformal) | Claims asymptotic marginal and calibration-conditional validity per agent | Snippet only; preprint |
| Time-series conformal OOD | Kaur et al., CODiT, arXiv 2207.11769, 2022 | Conformal detectors on deviation from temporal equivariance, combined by Fisher's method; abstract mentions driving and gait data, not weather | Opened (abstract) |
| Personalized federated AD / weather | PFAE (Infocom 2026 preprint), FedPoD (IJCAI 2024, weather forecasting), personalized FL for radar nowcasting (Earth Sci. Inform. 2024) | Shared backbone with private head for anomaly detection; personalized FL for forecasting across regions | Snippets only |
| WMO guidance | WMO-No. 8 (Vol. V, quality management); WMO-No. 485 Vol. I Part II, WMO-No. 305 | General QC responsibilities and standards for observational data | Exact precipitation QC clauses **not confirmed** |
| Benchmark critique | Wu and Keogh, "Current Time Series Anomaly Detection Benchmarks are Flawed", arXiv 2009.13807 (2020; ICDE 2022) | Argues common benchmark datasets are defective and progress may be illusory; introduces the UCR archive | Opened (abstract) |

ERA5-Land and ERA5 QC: not found in the sources I checked for precipitation fault detection; ERA5 precipitation is a model product, not QC'd station data (not researched further here; see `docs/research/era5-methodology-verification-20261117.md`).

## 3. Open angles

### (a) Genuine extreme vs fault from neighbour consensus and event coherence

- **Idea:** feed the fusion the coherence of the event (connected group size above the cell's own heavy-rain threshold, rank agreement of the target with its neighbours, same-day footprint compactness) so a coherent heavy-rain system is separated from a fault that shares the target's value but not its neighbourhood.
- **Why plausible:** the spec already defines protected extremes this way (at least 4 connected cells above the 99th percentile of wet days), and the spatial component sees a hidden disc. Durre et al. already use rank-based neighbour corroboration for precipitation, and El Hachem et al. separate local from regional extremes, so the signal is known to be useful. Known weakness: spatial checks mislabel isolated real convective extremes in sparse networks (RainGaugeQC adaptation, WIREs review; snippets).
- **Closest prior work:** Durre et al. 2010 spatial corroboration; El Hachem et al. 2022 local vs regional criteria ratio; Sha et al. 2021 (CNN on surrounding grid). Not found in the sources I checked: a trained gridded-rainfall fusion that scores protected-extreme false removal as a headline metric at a fixed false-alarm budget.
- **To show:** (1) ablation of the coherence features; (2) protected false removal at the same budget, by event size and client; (3) a hard stress set in which injected faults have large coherent footprints (radius 4 to 6) and genuine extremes are small (just above 4 cells), so the discrimination is not trivially solved by footprint size; (4) named real events (Kerala 2018, source-checked) as case studies; (5) a note that a protected group is defined by the same threshold the feature uses, which is circular (see section 4).

### (b) Conformal or calibrated thresholds with a controlled false-alarm rate, including regional shift

- **Idea:** replace "budget chosen from validation curves" with a calibrated rule: compute the fused score on clean calibration cell-days, set the threshold at the empirical quantile giving 1 per 1,000, optionally class-conditional (by wetness bin or heavy-rain flag) and per client; report realised rates on held-out years and held-out clients.
- **Why plausible:** conformal outlier testing gives a finite-sample bound on false positives for any detector under exchangeability (Bates et al., snippet only). Adaptive conformal inference handles temporal drift (Gibbs and Candes). Federated conformal methods address label and covariate shift between clients (Plassier et al., opened; 2026 preprint, snippet only).
- **Closest prior work:** the papers above; Durre et al. set thresholds by manual false-positive review rather than calibration. Not found in the sources I checked: any of these applied to rainfall QC, or tested on regionally held-out federated clients with real rainfall.
- **To show:** realised false-alarm rate against the nominal 1 per 1,000 per client, per season and per year, with intervals from resampled years; behaviour on held-out regions (client 3 northeast and client 6 west-central) before and after per-client or weighted calibration; and a statement of what is not guaranteed. Cell-days in one daily field are spatially correlated, and years drift, so the exchangeability assumption of split conformal fails; use days or blocks as the calibration unit and treat any guarantee as approximate. The headline claim should be "calibrated and measured", not "guaranteed".

### (c) Self-supervised masked-cell reconstruction for rainfall

- **Idea:** train the spatial model to reconstruct masked cells and discs from visible neighbours, then use residual under the zero-inflated Gamma NLL as the fault score.
- **Why plausible:** this is already the spatial component's design (hidden disc radius 2), so the work is mostly framing. SSIN shows masked recovery works for rainfall interpolation (snippet only). Measured recall is only 8% for the spatial component at the budget, so masking alone is weak evidence; the likely limitation is that faults with a footprint larger than the mask are partly reconstructible from the faulty neighbours.
- **Closest prior work:** SSIN (interpolation, not QC); partial-convolution U-Net gap filling of gauge fields (DKRZ report, snippet only). Not found in the sources I checked: masked reconstruction used as a rainfall QC score with a protected-extreme evaluation.
- **To show:** a mask-size sweep matched to fault footprint (radius 0, 1.5, 4, 6), a comparison with the leave-out-disc neighbour average baseline, and recall by footprint. Do not present as new; the realistic contribution is the evaluation, not the architecture.

### (d) Fault-supervised loss plus a penalty on protected extremes

- **Idea:** train the spatial and temporal models with the NLL plus a term that scores injected faults high and a penalty that keeps protected extremes' scores low, so the extreme-versus-fault boundary is learned in the component rather than only in the fusion.
- **Why plausible:** supervised injected-anomaly training is established (NCAD, Outlier Exposure, snippets). Temporal flagging of 22-34% of protected extremes shows the unsupervised temporal model confuses real extremes with faults, and boosted fusion already brings that to 2-3%, so the question is whether moving the penalty into the component helps or just duplicates the fusion.
- **Closest prior work:** NCAD (injected anomalies), Outlier Exposure (auxiliary outliers); GHCN-Daily and RainGaugeQC treat extremes by threshold design, not by a loss. Not found in the sources I checked: an explicit protected-extreme penalty in a learned precipitation QC model.
- **To show:** three-way ablation (NLL, NLL plus fault term, plus penalty), equal budgets, three seeds, and held-out fault kinds and test-only recipes so the gain is not the injection recipe. The penalty weight must be chosen on validation years only.

### (e) Federated heterogeneity handling (personalization) for QC

- **Idea:** shared body with local head and normalization (already the main variant), compared with FedAvg, FedAvg plus fine-tune, local-only.
- **Why plausible:** personalized federated anomaly detection with a shared backbone and private head exists in general (PFAE, snippet only); personalized FL has been applied to radar nowcasting across regions (snippet only).
- **Closest prior work:** those two. Not found in the sources I checked: federated or personalized learning for rain-gauge or gridded-rainfall QC.
- **To show:** per-client recall and false-alarm rate, performance on unseen clients, communication and compute costs, and that gains over local-only are real. The spec makes no privacy claim, so the case rests on accuracy and unseen-region transfer. Weakest of the angles for novelty since the techniques are standard; treat as an application result.

### (f) Other well-supported angles

- **Quality index instead of binary flag.** RainGaugeQC outputs a 0-1 index and only removes very likely errors (opened). The system's fused score plus review flag and final flag already resemble this. Showing that the review band catches ambiguous cases with a measured precision is a modest, defensible addition.
- **Independent corroboration for flagged extremes.** El Hachem et al. and RainGaugeQC use radar or discharge to confirm flags (opened). For RF25 an equivalent would be a second precipitation product (for example a satellite estimate) as a corroboration feature. Not tested here; it adds an external dependency and an independence question that must be argued.
- **Real-fault validation via MIDAS flags.** Already planned (spec section 12). This is the strongest answer to the circularity risk and I recommend treating it as required, not optional.

## 4. Risks and mitigations

| Risk | Why it matters | Accepted mitigations |
|---|---|---|
| Circularity: fusion learns the injection recipe | The fusion is fitted on synthetic faults from the same generator as the validation and test benchmarks, so measured recall partly measures recipe recognition | Hold out fault kinds, footprints above 4, weakest strengths and test seeds (the spec does this); report per-kind recall; fit on one recipe family and test on another; validate on real flagged faults (MIDAS). The injected-anomaly literature (NCAD, GenIAS snippet) acknowledges hand-crafted injection can be out of context; Wu and Keogh (opened) warn that benchmark flaws can mislead comparisons |
| Label leakage across time and space | Neighbour cells and adjacent days share information; temporal windows span splits | Year-based splits, buffer cells, leakage-audit tests (already in spec); calibrate on blocks, not independent cells |
| Protected extremes defined by the same threshold the model uses | A feature or loss built on the 99th-percentile group can look perfect on a set it defined | Evaluate on events chosen from an independent source (named real events, source-checked); report ambiguous extremes separately (spec does) |
| Synthetic labels presented as real | Violates the "no fabricated metrics" rule | Keep the "synthetic faults only" tier explicit; headline numbers labelled synthetic |
| How published work validates against real faults | Among the sources opened: Sha et al. use human labels from a sparse network; El Hachem et al. use synthetic scaling plus qualitative radar and discharge; RainGaugeQC uses case studies and one synthetic value; Durre et al. use manual review of flagged samples to estimate false-positive rates; HadISD uses known extreme events. No paper I opened reports a large expert-labelled rainfall fault set | Mirror these: small manual review of flagged protected-looking cells, case studies, real-flag benchmark where it exists |
| Conformal guarantee misread | Dependence across cells and years breaks exchangeability | Report realised rates, call guarantees approximate |
| Small base rates | 1 false alert per 1,000 clean cell-days on about 5,000 cells is several alerts per day | Report per-field alert counts too (spec does) |

## 5. Searched but not found

Queries run (web search): Durre GHCN-Daily QA; conformal anomaly detection weather sensors; rain gauge QC machine learning with extremes (IntenseQC, RainDT, PWSQC named; RainDT and IntenseQC not located); HadISD; IMD gridded rainfall QC; CHIRPS station data QC; PWSQC; masked autoencoder rainfall QC; GSDR-QC; WMO QC guidance; deep-learning precipitation QC; federated anomaly detection weather stations; federated conformal under shift; injected-anomaly circularity; SSIN; Outlier Exposure; NCAD; Bates conformal outliers; Gibbs and Candes; gridded rainfall QC with extremes (extended).

Not found in the sources I checked:

- Any federated or personalized learning paper on rain-gauge or gridded-rainfall QC.
- Conformal or calibrated false-alarm control applied to rainfall QC, or to weather-station QC with real data (search tool claimed a weather evaluation for CODiT; its abstract does not mention weather).
- Masked-reconstruction used as a rainfall QC score.
- A learned rainfall QC model with an explicit protected-extreme penalty.
- Published precipitation QC statistics from IMD for RF25 beyond the Pai et al. sentence (extreme-value check details not given).
- The precipitation-specific QC clauses of WMO-No. 8 or WMO-No. 305 (not opened).
- ERA5-Land or ERA5 precipitation QC against injected faults.

This is absence in a limited search, not proof of absence.

## 6. Sources

Opened (abstract page or full text read):

- Durre, I., Menne, M. J., Gleason, B. E., Houston, T. G., Vose, R. S. (2010). Comprehensive automated quality assurance of daily surface observations. J. Appl. Meteor. Climatol. 49(8), 1615-1633. https://ncei.noaa.gov/pub/data/ghcn/daily/papers/durre-menne-etal2010.pdf
- Dunn, R. J. H., et al. (2012). HadISD. Climate of the Past 8, 1649. https://cp.copernicus.org/articles/8/1649/2012/cp-8-1649-2012.html
- Pai, D. S., et al. (2014). MAUSAM 65(1). https://imdpune.gov.in/cmpg/Griddata/ref_paper_MAUSAM.pdf
- Funk, C., et al. (2015). CHIRPS. Scientific Data 2, 150066. https://pmc.ncbi.nlm.nih.gov/articles/PMC4672685
- El Hachem, A., Seidel, J., Imbery, F., Junghanel, T., Bardossy, A. (2022). Technical Note: space-time statistical quality control of extreme precipitation observations. HESS 26, 6137. https://hess.copernicus.org/articles/26/6137/2022/
- Osrodka, K., Otop, I., Szturc, J. (2022). Automatic quality control of telemetric rain gauge data (RainGaugeQC). AMT 15, 5581. https://amt.copernicus.org/articles/15/5581/2022/
- Sha, Y., Gagne, D. J., West, G., Stull, R. (2021). Deep-learning-based precipitation observation quality control. JTECH. https://www.cisl.ucar.edu/opensky-publications/articles:24497/deep-learning-based-precipitation-observation-quality-control
- Packman, S., Carlisle, E. (2025). Using machine learning based solution for quality control of UK monthly rainfall. EMS2025-637. https://meetingorganizer.copernicus.org/EMS2025/EMS2025-637.html
- Plassier, V., Makni, M., Rubashevskii, A., Moulines, E., Panov, M. (2023). Conformal prediction for federated uncertainty quantification under label shift. ICML. https://arxiv.org/abs/2306.05131
- Kaur, R., et al. (2022). CODiT. https://arxiv.org/abs/2207.11769
- Wu, R., Keogh, E. J. (2020/2022). Current time series anomaly detection benchmarks are flawed. https://arxiv.org/abs/2009.13807

Seen in search results only (unverified; read the paper before citing):

- Bates, S., Candes, E., Lei, L., Romano, Y., Sesia, M. (2023). Testing for outliers with conformal p-values. Ann. Statist. 51(1). https://arxiv.org/pdf/2104.08279
- Gibbs, I., Candes, E. (2021). Adaptive conformal inference under distribution shift. NeurIPS. https://arxiv.org/pdf/2106.00170v3
- Carmona, C. U., et al. (2021/2022). Neural contextual anomaly detection for time series. https://arxiv.org/abs/2107.07702
- Hendrycks, D., Mazeika, M., Dietterich, T. (2019). Deep anomaly detection with outlier exposure. ICLR. https://arxiv.org/pdf/1812.04606
- Li, J., Shen, Y., Chen, L., Ng, C. W. W. SSIN. https://arxiv.org/abs/2311.15530
- de Vos, L., Leijnse, H., Overeem, A., Uijlenhoet, R. (2019). Quality control for crowdsourced personal weather stations. GRL. https://doi.org/10.1029/2019GL083731
- Lewis, E., et al. (2021). GSDR-QC. Environ. Model. Softw. 144. https://doi.org/10.1016/j.envsoft.2021.105169
- Dunn, R. J. H., et al. (2016). HadISD version 2. GI. https://www.metoffice.gov.uk/hadobs/hadisd/HadISD_paper.pdf (URL is the 2012 paper copy; 2016 paper not opened)
- Serrano-Notivoli et al. (2021). From rain to data. WIREs Water. https://wires.onlinelibrary.wiley.com/doi/10.1002/wat2.1555
- AMT 18, 3229 (2025). Adaptation of RainGaugeQC. https://amt.copernicus.org/articles/18/3229/2025/
- arXiv 2606.00717 (2026), personalized federated weighted conformal prediction. https://arxiv.org/pdf/2606.00717
- FedPoD, IJCAI 2024. https://ijcai.org/proceedings/2024/638.md ; PFAE (Infocom 2026 preprint). https://wicon.arizona.edu/sites/default/files/2026-05/Phai_Infocom2026final.pdf ; personalized FL for radar nowcasting. https://aitopics.org/doc/arxivorg:B89327F1
- WMO-No. 8 landing page. https://community.wmo.int/node/36986 ; WMO-No. 485 Vol. I. https://old.wmo.int/extranet/pages/prog/www/DPFS/documents/485_Vol_I_en.pdf (clauses not read)
