# Systematic Literature Review: Weather / Rainfall Anomaly Detection Models

**Date**: 2026-11-16
**Papers included**: 24 (of 91 unique arXiv records retrieved across 8 queries)
**Scope**: arXiv only; relevance-sorted; no date filter. Purpose: ground the DataMend rainfall-anomaly training pipeline (`ml-service/training`) in the literature.
**Citation format**: APA 7th edition (arXiv preprints; publication status not verified)
**Evidence level**: titles and abstracts only (no full-text reading; several abstracts were truncated by the retrieval script's field and are annotated as such)

## Executive Summary

> **Provisional.** The central negative claim below ("no retrieved paper ...") holds only for the arXiv queries listed in Methodology and abstract-level reading. Papers from other sources (e.g. Consensus) were not included in this version; add them and re-check before treating the gap as established.

The retrieved arXiv literature splits into two sets that barely overlap. One is weather and climate work that does quality control (QC) or anomaly detection: it is mostly rule-based or classical-statistical, concentrated on temperature, wind and ocean data, and rarely evaluated with labelled errors (Dunn et al., 2012; Castro et al., 2026; Bruns et al., 2018; Castelão, 2015; Bazlen et al., 2026). The other is a large general time-series anomaly detection (TSAD) literature dominated by reconstruction, prediction, contrastive and Transformer models, which is not evaluated on precipitation (Darban et al., 2022; Alves et al., 2026; Qiu et al., 2025).

**No retrieved paper addresses ML detection of erroneous daily gauge or gridded rainfall values with injected-error training.** The nearest items are satellite-precipitation artifact detection (Monsalve et al., 2026) and MRF detection of climatological rainfall anomalies over India (Mitra & Seshadri, 2017; Mitra, 2017), which concerns genuine extremes rather than data errors. The DataMend design (synthetic injected errors, zero-inflated Gamma likelihood, multi-scale inputs, label-free fusion) therefore cannot be called validated by this literature; the supporting evidence is indirect and general-purpose. This conclusion is limited to arXiv and to the queries used; it does not show the gap exists elsewhere (journals such as MAUSAM, JGR, J. Hydrometeorology were not searched).

## Methodology

- **Database**: arXiv via `arxiv_search.py` (Atom API). No other database.
- **Queries** (relevance-sorted; category in brackets): "anomaly detection" [physics.ao-ph, 25], "quality control" [physics.ao-ph, 20], "outlier detection" [physics.ao-ph, 15], "anomaly detection" [stat.AP, 20], "rainfall anomaly" [15], "precipitation quality control" [15 requested, 0 returned], "time series anomaly detection" [20], "weather station" [15]. An earlier set of longer phrase queries (e.g. "weather anomaly detection", "automatic weather station anomaly detection") returned 0-1 records because the script quotes multi-word queries as exact phrases; these were abandoned in favour of the shorter concept phrases above. Searches ran with UTF-8 forced after a Windows console encoding error truncated one result set; that query was re-run.
- **Screening**: records deduplicated by arXiv id (91 unique), then screened by title/abstract by one reviewer (the assistant) for: weather/climate QC or anomaly detection, or influential general TSAD surveys, benchmarks, metrics and methods bearing on the DataMend design. 24 included. Many retrieved records (e.g. wind-energy, forecasting, climate-dynamics papers) were excluded as off-topic. Screening was judgment-based, not double-coded.
- **Extraction**: performed directly from abstracts; no subagents were used for extraction.

**Limitations of this review**: arXiv-only; semantic search quirks mean relevant papers may be missed; selection of general TSAD papers is illustrative, not exhaustive; findings are abstract-level and should be verified against full texts before being quoted in the project's own papers.

## Themes

### Theme 1: Weather QC is dominated by rule tests with flags, increasingly combined

Operational-style archives apply physical-limit checks first, then temporal and cross-variable consistency, and keep flags rather than overwriting data (Castro et al., 2026; Dunn et al., 2012). HadISD explicitly designs tests to preserve true extremes (Dunn et al., 2012), and WIND-Bench separates sensor failure from real high wind by comparing against an independent model field (Bazlen et al., 2026). Castelao (2015) argues that combining many tests into one learned multidimensional criterion cut error by at least 50% relative to traditional tests, on ocean data (Castelão, 2015). This supports the DataMend choice to keep a rule branch and fuse it with learned detectors (the project's `ensemble` package), but the evidence is from non-rainfall variables.

### Theme 2: Distinguishing real extremes from errors is the central difficulty

Both the HadISD and WIND-Bench QC designs are built around not deleting genuine extremes (Dunn et al., 2012; Bazlen et al., 2026); the MRF papers treat extremes as the object of study rather than as errors (Mitra & Seshadri, 2017; Mitra, 2017). For zero-inflated, heavy-tailed rainfall this matters more than for temperature, and none of the retrieved papers evaluates it for rainfall. In DataMend the `spike` and `scale` injected anomalies are exactly the cases that mimic heavy rain.

### Theme 3: Reconstruction and prediction models dominate general TSAD; multi-scale and decomposition are common

The taxonomy survey reports convergence toward Transformer-based and reconstruction/prediction models (Alves et al., 2026); the DL survey provides a category taxonomy (Darban et al., 2022). Decomposition and multi-scale design recur: RobustTAD (seasonal-trend decomposition plus a multi-scale CNN) (Gao et al., 2020), TFAD (time-frequency plus decomposition) (Zhang et al., 2022), DCdetector (multi-scale dual attention) (Yang et al., 2023), and streaming multi-scale PCA (Kiran, 2017). This gives general-purpose precedent for the project's `scalenet` (daily/5-day/30-day branches plus a trend stream); whether it helps on rainfall is untested here and is marked as a hypothesis in the project's own code.

### Theme 4: Training on contaminated or unlabelled data

Reconstruction autoencoders are sensitive to anomalies in the training series (Zhang et al., 2025), and identity-mapping leakage is a known failure mode (Yang et al., 2023). A scarce-label strategy appears in satellite-precipitation artifact detection, which combines pre-trained vision models with limited human labels (Monsalve et al., 2026). DataMend instead injects labelled synthetic errors into presumed-clean RF25; that makes the contamination risk (real errors already in RF25) and the sim-to-real gap the key unknowns, and none of these papers tests the injection approach itself.

### Theme 5: Probabilistic, likelihood-based scoring

Hyndman and Frazier define anomalies as low probability under a possibly misspecified model, scoring by the tail probability of the surprisal and keeping effectiveness under misspecification (Hyndman & Frazier, 2026). This is conceptually close to the DataMend `nll` stream (negative log-likelihood under a zero-inflated Gamma) and to its calibration against clean validation scores, though the paper itself reports no weather application.

### Theme 6: Evaluation practice is a known weakness

Point-adjusted and event-based TSAD metrics can be gamed: an adversary can reach high precision and recall on almost any dataset (Huet et al., 2022), which motivates affiliation metrics. TAB argues current benchmarks have dataset and protocol deficiencies (Qiu et al., 2025). The project already reports point-wise PR, affiliation F1 and event metrics with fixed seeds and no point-adjusted F1, consistent with this critique.

## Convergences and Disagreements

**Convergences**: (a) QC should flag rather than silently remove data (Castro et al., 2026; Dunn et al., 2012); (b) learned or statistical detectors help most when combined with physical tests (Castelão, 2015; Sow, 2026); (c) reconstruction-based detectors are the default but have known failure modes (Alves et al., 2026; Yang et al., 2023; Zhang et al., 2025).

**Disagreements / tensions**: The retrieved papers do not directly contradict one another. A tension exists between threshold-based and threshold-free definitions of anomaly: Mitra (2017) explicitly aims to avoid fixed thresholds (Mitra, 2017), while the QC archives rely on fixed physical limits (Castro et al., 2026; Dunn et al., 2012). This is a difference in problem framing (climate extremes vs. data errors), not an empirical disagreement.

## Gaps and Open Questions

1. No retrieved work evaluates ML detection of erroneous **daily rainfall** values, gauge or gridded, with or without injected errors.
2. No work retrieved validates whether **injected synthetic anomalies transfer to real instrument and data errors**.
3. Real labelled error sets are essentially absent from the weather papers retrieved; most evaluations are on temperature, wind or ocean data (Bruns et al., 2018; Castelão, 2015; Bazlen et al., 2026).
4. The multi-scale and Transformer TSAD models are benchmarked on generic data, not zero-inflated heavy-tailed series.
5. Handling of the zero-versus-missing ambiguity in rainfall (the DataMend `zeroed` anomaly) is not addressed in any retrieved abstract.

Suggested follow-up: search journals and non-arXiv sources (the project's reference paper MAUSAM, WMO QC guidance, GHCN-Daily QC); see `docs/research/operational-rainfall-qc-primary-sources.md` if present, which a separate primary-source pass was asked to produce.

## Implications for DataMend (analysis, not a finding from any single paper)

| Design element | Closest literature support | Strength of support |
|---|---|---|
| Rule branch fused with learned branches | Combined tests beat single tests (ocean) (Castelão, 2015); flag-don't-delete QC (Castro et al., 2026) | Indirect (non-rainfall) |
| Zero-inflated Gamma NLL score + clean-val calibration | Surprisal tail-probability scoring (Hyndman & Frazier, 2026) | Conceptual |
| Multi-scale `scalenet` | RobustTAD, DCdetector, multi-scale PCA (Gao et al., 2020; Yang et al., 2023; Kiran, 2017) | General TSAD only |
| Injected-anomaly training | Contamination and scarce-label issues (Zhang et al., 2025; Monsalve et al., 2026) | Not tested anywhere retrieved |
| Affiliation/event metrics, fixed seeds | (Huet et al., 2022; Qiu et al., 2025) | Direct (metrics) |

## Per-Paper Annotations

### Dunn et al. (2012)

*HadISD: a quality-controlled global synoptic report database for selected variables at long-term stations from 1973--2011* - arXiv:1210.7191

**Research question**: Build an automatically quality-controlled global station database.

**Methodology**: Merges station records, converts to netCDF, applies automated objective QC tests tuned on UK data and known extreme events, then filters stations.

**Key findings** (abstract-based):
- Over 6000 stations, 3427 judged suitable for sub-daily climate use.
- QC was designed to keep true extremes; validated on Katrina, the 1989 Alaska cold snap and 2009 SE Australia heat waves.

**Limitations**: Covers temperature, dewpoint, pressure, wind and cloud - not precipitation; coverage skewed to Northern mid-latitudes.

### Castelão (2015)

*A Flexible System for Automatic Quality Control of Oceanographic Data* - arXiv:1503.02714

**Research question**: Replace many independent rule tests for ocean-profile QC with one learned criterion.

**Methodology**: Combines multiple QC tests into a multidimensional score and treats bad samples as outliers of the learned 'good' behaviour (anomaly detection).

**Key findings** (abstract-based):
- On 13 years of hydrographic profiles the anomaly-detection approach had the best classification performance, reducing error by at least 50% versus traditional methods (per abstract).

**Limitations**: Oceanographic profiles, not rainfall; abstract does not state the label source or metrics.

### Kiran (2017)

*Multi-scale streaming anomalies detection for time series* - arXiv:1706.06910

**Research question**: Handle varying pseudo-periodicity in streaming TSAD.

**Methodology**: Streaming PCA over a multi-scale lag matrix with three score-aggregation methods.

**Key findings** (abstract-based):
- First systematic study of multi-scale streaming anomaly scores (authors' claim), evaluated on Yahoo! and Numenta.

**Limitations**: Not weather; benchmarks are generic.

### Mitra & Seshadri (2017)

*Detection of Spatiotemporally Coherent Rainfall Anomalies Using Markov Random Fields* - arXiv:1703.09007

**Research question**: Detect spatio-temporally coherent rainfall anomalies in Indian gridded rainfall.

**Methodology**: Markov Random Fields with latent high/low/normal states per (location, year), estimated by Gibbs sampling; edge potentials enforce spatial and temporal coherence.

**Key findings** (abstract-based):
- Can be tuned to recover threshold-based anomalies; finds non-stationarity in anomaly occurrence between halves of 1901-2005.

**Limitations**: Annual climatological anomalies (extreme weather), not erroneous observations; annual resolution.

### Mitra (2017)

*Identifying Coherent Anomalies in Multi-Scale Spatio-Temporal Data using Markov Random Fields* - arXiv:1711.00395

**Research question**: Detect anomalies across spatial and temporal scales without fixed thresholds.

**Methodology**: Spatio-temporal MRF whose latent states denote anomaly type, applied to multi-scale data such as daily rain-gauge series viewed at daily to annual scales.

**Key findings** (abstract-based):
- Frames anomalies as extended regions whose values differ significantly from long-term means, avoiding subjective thresholds (per abstract).

**Limitations**: Targets coherent climate anomalies rather than instrument or data errors.

### Bruns et al. (2018)

*Automated Quality Assessment of (Citizen) Weather Stations* - arXiv:1802.06018

**Research question**: Learn the quality of individual (citizen) weather stations dynamically.

**Methodology**: Weighted Gaussian-process regression whose sensor weights are optimized by a genetic algorithm.

**Key findings** (abstract-based):
- Evaluated on 1561 stations (Wunderground vs DWD temperature, SW Germany, Aug 2016).

**Limitations**: Temperature only, one month; abstract truncated before reported accuracy figures.

### Gao et al. (2020)

*RobustTAD: Robust Time Series Anomaly Detection via Decomposition and Convolutional Neural Networks* - arXiv:2002.09545

**Research question**: Scalable, robust TSAD for large service fleets.

**Methodology**: RobustTAD: robust seasonal-trend decomposition plus a convolutional encoder-decoder with skip connections; systematic study of time- and frequency-domain augmentation.

**Key findings** (abstract-based):
- Decomposition simplifies the network; encoder-decoder captures multi-scale information.

**Limitations**: Industrial (Alibaba) monitoring series.

### Darban et al. (2022)

*Deep Learning for Time Series Anomaly Detection: A Survey* - arXiv:2211.05244

**Research question**: Survey deep-learning methods for time-series anomaly detection.

**Methodology**: Taxonomy by model category with advantages, limitations, datasets and applications.

**Key findings** (abstract-based):
- Provides the structured overview of DL TSAD families (reconstruction, prediction, etc.).

**Limitations**: Survey; general-purpose, not weather-specific.

### Huet et al. (2022)

*Local Evaluation of Time Series Anomaly Detection Algorithms* - arXiv:2206.13167

**Research question**: Fix limitations of precision/recall and event-based TSAD metrics.

**Methodology**: Parameter-free 'affiliation' metrics based on distances between ground-truth and predicted sets.

**Key findings** (abstract-based):
- Shows an adversary can reach high precision/recall on almost any dataset under weak assumptions with existing event-based metrics (per abstract).

**Limitations**: Metric paper; no weather evaluation.

### Kimpson et al. (2022)

*Deep learning for quality control of surface physiographic fields using satellite Earth observations* - arXiv:2210.16746

**Research question**: Use ML to assess the quality of surface physiographic fields.

**Methodology**: Neural network (VESPER) maps physiographic fields plus ERA5 meteorology to MODIS skin temperature; prediction error then indicates field quality.

**Key findings** (abstract-based):
- Lake-field updates improved land-surface-temperature accuracy by 0.37 K on average where updated.

**Limitations**: Quality control of model input fields, not of observed time series.

### Liu et al. (2022)

*FedTADBench: Federated Time-Series Anomaly Detection Benchmark* - arXiv:2212.09518

**Research question**: Benchmark TSAD under federated learning.

**Methodology**: FedTADBench evaluates five representative TSAD algorithms in federated settings.

**Key findings** (abstract-based):
- Provides the only federated reference point in this set.

**Limitations**: General; relevant only to the project's optional federated seam.

### Pacher et al. (2022)

*AWT -- Clustering Meteorological Time Series Using an Aggregated Wavelet Tree* - arXiv:2212.06642

**Research question**: Cluster meteorological time series with implicit outlier detection.

**Methodology**: AWT: aggregated wavelet tree clustering that auto-selects cluster count from a threshold parameter and handles larger-than-memory data.

**Key findings** (abstract-based):
- Detects outliers and recovers land-use-related structure in crowd-sourced hourly Vienna 2-m temperature.

**Limitations**: Temperature, crowd-sourced; no labelled-error evaluation in the abstract.

### Zhang et al. (2022)

*TFAD: A Decomposition Time Series Anomaly Detection Architecture with Time-Frequency Analysis* - arXiv:2210.09693

**Research question**: Exploit both time and frequency domains for TSAD.

**Methodology**: TFAD: time-frequency architecture with series decomposition and data augmentation.

**Key findings** (abstract-based):
- Reports state-of-the-art results on benchmark datasets and improved interpretability (per abstract).

**Limitations**: General benchmarks; not weather.

### Yang et al. (2023)

*DCdetector: Dual Attention Contrastive Representation Learning for Time Series Anomaly Detection* - arXiv:2306.10347

**Research question**: Detect time-series anomalies with contrastive learning instead of reconstruction.

**Methodology**: DCdetector: multi-scale dual-attention contrastive model with an asymmetric design and no negative samples.

**Key findings** (abstract-based):
- Positions contrastive representation learning against reconstruction-based methods.

**Limitations**: Abstract truncated before benchmark numbers; general-purpose.

### Yang et al. (2023)

*DDMT: Denoising Diffusion Mask Transformer Models for Multivariate Time Series Anomaly Detection* - arXiv:2310.08800

**Research question**: Reduce noise and weak identity mapping in reconstruction-based multivariate TSAD.

**Methodology**: DDMT: adaptive dynamic neighbour mask with a Transformer and denoising diffusion model.

**Key findings** (abstract-based):
- Identifies identity-mapping leakage as a failure mode of reconstruction detectors.

**Limitations**: General multivariate TSAD.

### Jin et al. (2024)

*WeatherReal: A Benchmark Based on In-Situ Observations for Evaluating Weather Models* - arXiv:2409.09371

**Research question**: Benchmark weather models against in-situ observations rather than reanalysis.

**Methodology**: Builds WeatherReal from global near-surface observations with a public QC and evaluation framework.

**Key findings** (abstract-based):
- Reanalyses diverge substantially from observations for precipitation, wind, temperature and clouds (per abstract).

**Limitations**: Primary aim is forecast evaluation; QC detail is outside the abstract.

### Qiu et al. (2025)

*TAB: Unified Benchmarking of Time Series Anomaly Detection Methods* - arXiv:2506.18046

**Research question**: Fair, unified evaluation of TSAD methods.

**Methodology**: TAB benchmark: 29 multivariate datasets, 1,635 univariate series, methods from non-learning to LLM-based, one automated pipeline.

**Key findings** (abstract-based):
- Aims to fix dataset, protocol and evaluation deficiencies in prior comparisons; code and data are public.

**Limitations**: Abstract contains no weather or precipitation dataset.

### Zhang et al. (2025)

*An Encode-then-Decompose Approach to Unsupervised Time Series Anomaly Detection on Contaminated Training Data--Extended Version* - arXiv:2510.18998

**Research question**: Train unsupervised autoencoder detectors on training data that contains anomalies.

**Methodology**: Encode-then-decompose: split representations into stable and auxiliary parts with a mutual-information objective.

**Key findings** (abstract-based):
- Targets the sensitivity of reconstruction autoencoders to contaminated training series.

**Limitations**: General TSAD; abstract truncated before results.

### Alves et al. (2026)

*Unified Taxonomy for Multivariate Time Series Anomaly Detection using Deep Learning* - arXiv:2603.18941

**Research question**: Systematize deep-learning multivariate TSAD methods.

**Methodology**: Eleven-dimension taxonomy over Input, Output and Model, validated on additional recent papers.

**Key findings** (abstract-based):
- Reports convergence toward Transformer-based and reconstruction/prediction models.

**Limitations**: General multivariate TSAD; no weather focus.

### Bazlen et al. (2026)

*WIND-Bench: A Benchmark Dataset for In-Situ Near-Surface Wind Speed Observations Across the Conterminous United States* - arXiv:2609.12228

**Research question**: Provide a quality-controlled wind benchmark.

**Methodology**: QC validates MADIS observations against HRRR forecasts to distinguish sensor failures from genuine high wind.

**Key findings** (abstract-based):
- Shows the pattern of checking observations against an independent model field to avoid discarding true extremes.

**Limitations**: Wind, not rain; abstract gives no QC performance figures.

### Castro et al. (2026)

*METBRA25Y: Brazil Surface Meteorology Archive with Harmonized Variables and Quality Control* - arXiv:2605.08701

**Research question**: Provide a harmonized Brazilian hourly surface archive with explicit QC metadata.

**Methodology**: Two-stage QC: physically implausible values become missing and flagged; temporal and cross-variable consistency checks produce diagnostic flags without overwriting data.

**Key findings** (abstract-based):
- Flags and missing-data audits are shipped with the data; includes daily precipitation aggregates for 2000-2025.

**Limitations**: Data paper; the rule thresholds and any error-detection accuracy are not in the abstract.

### Hyndman & Frazier (2026)

*Anomaly detection using surprisals* - arXiv:2603.09318

**Research question**: Define anomalies without ad hoc rules and including 'inlier' anomalies.

**Methodology**: Anomaly = low probability under a possibly misspecified model; score = tail probability of the surprisal (negative log density), estimated empirically or with a GPD fit.

**Key findings** (abstract-based):
- Gives finite-sample guarantees for the empirical estimator; effective under substantial misspecification (mortality and cricket data).

**Limitations**: No weather application.

### Monsalve et al. (2026)

*A Sensor-Adaptive Incremental Learning Framework for Artifact Detection in Satellite Precipitation Data* - arXiv:2609.01514

**Research question**: Detect artifacts in near-real-time satellite precipitation products before release.

**Methodology**: Pre-trained computer-vision models plus scarce human-labelled data, with incremental learning per sensor.

**Key findings** (abstract-based):
- On SSMI/SSMIS data it separates regular from artifact-containing orbits per satellite with performance comparable to existing in-place methods; offers explainability and iterative refinement.

**Limitations**: Image-level artifact detection on satellite orbits, not station or daily gauge series; needs human labels.

### Sow (2026)

*Data Quality Audit and Bivariate Temperature-Humidity Analysis of a Long-Term LoRaWAN Network: Anomaly Detection, PCA, Clustering and Machine Learning* - arXiv:2610.32438

**Research question**: Audit variable coverage before analysing a long-term LoRaWAN network.

**Methodology**: Pipeline of modified Z-score, Isolation Forest, PCA, clustering and an MLP-residual drift detector on temperature-humidity.

**Key findings** (abstract-based):
- Isolation Forest flagged 2.12% multivariate anomalies where the univariate Z-score flagged none; MLP humidity predictor R2 = 0.672.

**Limitations**: Single deployment, temperature and humidity only, no injected or labelled errors.

## References

Alves, B., Pinho, A. J., & Gouveia, S. (2026). Unified Taxonomy for Multivariate Time Series Anomaly Detection using Deep Learning. arXiv. https://arxiv.org/abs/2603.18941

Bazlen, K., Buster, G., Benton, B., North, L., Baring, A., Turner, D. D., Wells, E., & Vimmerstedt, L. (2026). WIND-Bench: A Benchmark Dataset for In-Situ Near-Surface Wind Speed Observations Across the Conterminous United States. arXiv. https://arxiv.org/abs/2609.12228

Bruns, J., Riesterer, J., Wang, B., Riedel, T., & Beigl, M. (2018). Automated Quality Assessment of (Citizen) Weather Stations. arXiv. https://arxiv.org/abs/1802.06018

Castelão, G. P. (2015). A Flexible System for Automatic Quality Control of Oceanographic Data. arXiv. https://arxiv.org/abs/1503.02714

Castro, M. L., Vichete, W. D., & Filho, L. L. (2026). METBRA25Y: Brazil Surface Meteorology Archive with Harmonized Variables and Quality Control. arXiv. https://arxiv.org/abs/2605.08701

Darban, Z. Z., Webb, G. I., Pan, S., Aggarwal, C. C., & Salehi, M. (2022). Deep Learning for Time Series Anomaly Detection: A Survey. arXiv. https://arxiv.org/abs/2211.05244

Dunn, R. J. H., Willett, K. M., Thorne, P. W., Woolley, E. V., Durre, I., Dai, A., Parker, D. E., & Vose, R. E. (2012). HadISD: a quality-controlled global synoptic report database for selected variables at long-term stations from 1973--2011. arXiv. https://arxiv.org/abs/1210.7191

Gao, J., Song, X., Wen, Q., Wang, P., Sun, L., & Xu, H. (2020). RobustTAD: Robust Time Series Anomaly Detection via Decomposition and Convolutional Neural Networks. arXiv. https://arxiv.org/abs/2002.09545

Huet, A., Navarro, J. M., & Rossi, D. (2022). Local Evaluation of Time Series Anomaly Detection Algorithms. arXiv. https://arxiv.org/abs/2206.13167

Hyndman, R. J., & Frazier, D. T. (2026). Anomaly detection using surprisals. arXiv. https://arxiv.org/abs/2603.09318

Jin, W., Weyn, J., Zhao, P., Xiang, S., Bian, J., Fang, Z., Dong, H., Sun, H., Thambiratnam, K., & Zhang, Q. (2024). WeatherReal: A Benchmark Based on In-Situ Observations for Evaluating Weather Models. arXiv. https://arxiv.org/abs/2409.09371

Kimpson, T., Choulga, M., Chantry, M., Balsamo, G., Boussetta, S., Dueben, P., & Palmer, T. (2022). Deep learning for quality control of surface physiographic fields using satellite Earth observations. arXiv. https://arxiv.org/abs/2210.16746

Kiran, B. R. (2017). Multi-scale streaming anomalies detection for time series. arXiv. https://arxiv.org/abs/1706.06910

Liu, F., Zeng, C., Zhang, L., Zhou, Y., Mu, Q., Zhang, Y., Zhang, L., & Zhu, C. (2022). FedTADBench: Federated Time-Series Anomaly Detection Benchmark. arXiv. https://arxiv.org/abs/2212.09518

Mitra, A., & Seshadri, A. K. (2017). Detection of Spatiotemporally Coherent Rainfall Anomalies Using Markov Random Fields. arXiv. https://arxiv.org/abs/1703.09007

Mitra, A. (2017). Identifying Coherent Anomalies in Multi-Scale Spatio-Temporal Data using Markov Random Fields. arXiv. https://arxiv.org/abs/1711.00395

Monsalve, A. F., Moreno, H. A., & Kummerow, C. D. (2026). A Sensor-Adaptive Incremental Learning Framework for Artifact Detection in Satellite Precipitation Data. arXiv. https://arxiv.org/abs/2609.01514

Pacher, C., Schicker, I., deWit, R., Schindler, K. H., & Plant, C. (2022). AWT -- Clustering Meteorological Time Series Using an Aggregated Wavelet Tree. arXiv. https://arxiv.org/abs/2212.06642

Qiu, X., Li, Z., Qiu, W., Hu, S., Zhou, L., Wu, X., Li, Z., Guo, C., Zhou, A., Sheng, Z., Hu, J., Jensen, C. S., & Yang, B. (2025). TAB: Unified Benchmarking of Time Series Anomaly Detection Methods. arXiv. https://arxiv.org/abs/2506.18046

Sow, M. (2026). Data Quality Audit and Bivariate Temperature-Humidity Analysis of a Long-Term LoRaWAN Network: Anomaly Detection, PCA, Clustering and Machine Learning. arXiv. https://arxiv.org/abs/2610.32438

Yang, C., Wang, T., & Yan, X. (2023). DDMT: Denoising Diffusion Mask Transformer Models for Multivariate Time Series Anomaly Detection. arXiv. https://arxiv.org/abs/2310.08800

Yang, Y., Zhang, C., Zhou, T., Wen, Q., & Sun, L. (2023). DCdetector: Dual Attention Contrastive Representation Learning for Time Series Anomaly Detection. arXiv. https://arxiv.org/abs/2306.10347

Zhang, B., Kieu, T., Qiu, X., Guo, C., Hu, J., Zhou, A., Jensen, C. S., & Yang, B. (2025). An Encode-then-Decompose Approach to Unsupervised Time Series Anomaly Detection on Contaminated Training Data--Extended Version. arXiv. https://arxiv.org/abs/2510.18998

Zhang, C., Zhou, T., Wen, Q., & Sun, L. (2022). TFAD: A Decomposition Time Series Anomaly Detection Architecture with Time-Frequency Analysis. arXiv. https://arxiv.org/abs/2210.09693
