# Systematic Literature Review: Architectures for Temperature, Humidity and Pressure Quality Control, Compared with the DataMend Rainfall Architecture

**Date**: 2026-11-17
**Papers included**: 16 (of 150 unique arXiv records retrieved across 12 queries)
**Scope**: arXiv only; relevance-sorted; submissions from 2019-01-01. Question: which model architecture is best suited to detecting erroneous temperature, relative humidity and pressure values (station or gridded), and how does it differ from the rainfall architecture in `ml-service/qc/`?
**Citation format**: APA 7th edition (arXiv preprints; publication status not verified)
**Evidence level**: titles and abstracts only. Abstracts were read to about 1,100 characters, and the endings of five of the most relevant ones were read in full. No full texts. Nothing below has been checked against a paper's body.

Companion notes: `slr-weather-anomaly-detection-models.md` (a broader earlier review of weather and rainfall anomaly detection; not repeated here) and `prior-work-precipitation-qc-positioning.md` (UNVERIFIED subagent notes).

## Executive Summary

**No retrieved paper compares architectures for detecting erroneous temperature, humidity or pressure values, so no architecture can be called "better" on evidence from this review.** What the literature does supply is a set of design principles that bear on the choice, and they are consistent enough to justify one recommended candidate and a test plan.

The supported points are these. First, weather-data QC is built as a staged pipeline: plausibility limits, then temporal and cross-variable consistency checks, flagged rather than overwritten (Castro et al., 2026; Jin et al., 2024). Second, a model that predicts a hidden or masked value from the others can serve detection, isolation and correction in one design (Fu & Yan, 2024), and multivariate residual models suffer "smearing", where one faulty sensor corrupts the residuals of healthy ones (Haldimann et al., 2019). Third, the temperature-humidity pair is strongly coupled (r = -0.66 in one long deployment), and a model predicting humidity from temperature and time was usable as a drift detector on its own (Sow, 2026). Fourth, station networks are irregular and sparse, and the forecasting literature handles that with graph convolutions rather than image-style patches (Lin et al., 2021; Zhu et al., 2023; Xiong et al., 2024; Zambon et al., 2025). Fifth, ERA5-style reanalysis differs from in-situ observation, so a detector validated on reanalysis may not transfer (Jin et al., 2024; Ramavajjala & Mitra, 2023).

**The candidate recommended for temperature, humidity and pressure** (a hypothesis, not a finding): keep the rainfall design's *masked-target* idea (hide the target cell, predict it from its neighbours and its own past, score the surprise), but replace the zero-inflated Gamma head with a heteroscedastic continuous head, feed all three variables jointly so cross-variable consistency is learned instead of fitted afterwards, and use a graph attention variant instead of the square patch when the data are irregular stations. It should be tested against the current rule-and-statistics baseline in `qc/multivar.py` on the same synthetic benchmark, and then on real station data, because ERA5 will flatter every detector.

## Methodology

- **Database**: arXiv via `arxiv_search.py`. No other database.
- **Queries** (all relevance-sorted, from 2019-01-01, 25 results requested; category in brackets): "weather station", "weather station" [cs.LG], "observation quality control", "quality control" [physics.ao-ph], "sensor anomaly detection", "anomaly detection" [physics.ao-ph], "spatiotemporal anomaly detection", "temperature anomaly" [physics.ao-ph], "meteorological" [cs.LG], "sensor fault", "anomaly detection graph neural network", "precipitation quality control". Returned: 25, 25, 0, 21, 6, 6, 4, 25, 25, 25, 1 and 0 records.
- **Search problems, stated honestly.** A first set of longer phrases (for example "automatic weather station quality control") returned 0 records for every query because the script quotes multi-word queries as exact phrases; they were replaced with short concept phrases. The first run of the short phrases failed to parse for 6 of 12 queries because of a Windows console encoding error, and was re-run with UTF-8 forced. Two queries still returned 0 records.
- **Screening**: 150 unique records by arXiv id; screened by title and abstract by one reviewer (the assistant), not double-coded. Included: weather or meteorological QC and anomaly detection; sensor-fault architectures that transfer to meteorological variables; station-network spatiotemporal models; and federated or personalised weather models. Excluded as off-topic or not about measured meteorological variables: for example video anomaly detection, industrial vision, spacecraft and robot control, climate-dynamics papers, and forecasting papers with no bearing on error detection. A few marginal items (for example satellite-precipitation artifact detection and surface-field QC, which the earlier review already covers) were left out to keep the set focused.
- **Extraction**: directly from abstracts; no delegation.
- **Limitations**: arXiv-only, so journal QC literature (for example WMO guidance, GHCN, HadISD and operational QC papers) is not covered here. A recall of 16 relevant papers from 150 retrieved suggests the arXiv coverage of this exact topic is thin, not that the topic is unstudied. Because the search used exact phrases, relevant papers using different wording may be missing.

## Themes

### Theme 1: QC is staged, and the cross-variable stage is the last line of defence

The METBRA25Y archive applies a two-stage protocol: implausible values are turned to missing and flagged, then temporal and cross-variable consistency checks produce diagnostic flags without necessarily overwriting measurements; it covers air temperature, dew point, relative humidity and pressure among other variables (Castro et al., 2026). WeatherReal also ships a public quality-control framework as part of its in-situ benchmark (Jin et al., 2024). Both support DataMend's layered design (rules, statistics, learned scores, fusion) for these variables. The abstracts do not say how much the cross-variable stage catches that single-variable checks miss.

### Theme 2: Predicting a masked value unifies detection, isolation and correction

Fu and Yan (2024) train a sequence model with random masks that act like faults on one or more sensors, so that training and inference are the same task: find the faulty sensors and correct them. They report that it outperforms existing approaches on a public and a wind-turbine dataset. This is the same principle as DataMend's hidden-disc spatial component, extended to several sensors and to correction. It also bears directly on the optional corrected-value requirement in the project's agent instructions.

### Theme 3: Multivariate residuals smear faults across variables

When a model predicts each sensor from the others, a fault in one propagates into misleading residuals for the healthy ones (the "smearing-out" effect); Haldimann et al. (2019) address this with a disentangled recurrent network and a probabilistic residual model that identifies the faulty sensors, with cost linear in the number of sensors rather than combinatorial. This matters for a joint temperature, humidity and pressure model: a spike in temperature will make a humidity predictor that uses temperature as input look wrong too. Hiding the target variable's own value, or designing the predictor so it does not read the variable it scores, are the available defences; the abstract describes only the authors' own disentangled network, tested on a petrochemical plant; the other defence is a suggestion of this review.

### Theme 4: Temperature and humidity are coupled strongly enough to predict each other, and a simple model already works as a detector

On a two-year LoRaWAN deployment, temperature and humidity had a correlation of -0.66; Isolation Forest found 2.12% multivariate anomalies where a univariate z-score found none; and a multilayer perceptron predicting humidity from temperature and time (R² = 0.67 in cross-validation) provided residuals used as a slow-drift detector (Sow, 2026). The same paper found that pressure was available for only 4.24% of the data, which is a reminder that variable coverage must be audited before any joint model is trusted. A greenhouse sensor-stream study makes the same point about correlated streams and concept drift, and uses a hashing-based isolation forest rather than a neural model (Yang et al., 2021).

### Theme 5: Irregular station networks favour graph models; gridded fields favour convolutions

For forecasting on ground stations, the literature uses graph convolutions with learned or geographic adjacency, local-coordinate convolutions on a station graph, and multi-graph convolutions over meteorological factors (Lin et al., 2021; Zhu et al., 2023; Xiong et al., 2024). PeakWeather provides 302 Swiss stations with topographic indices and an NWP baseline for such work (Zambon et al., 2025). One paper applies a graph attention autoencoder with a spatial regularisation term to anomaly detection in rainfall over India, with graphs built from rainfall, pressure and temperature attributes from IMD and ERA5 (Agarwal et al., 2024). That paper's anomalies are rainfall extremes, not data errors, so it supports the graph architecture for this region and these variables but not as evidence of error detection. DataMend's rainfall model uses a square patch on the RF25 grid, which is natural for gridded data; real AWS networks are not gridded.

### Theme 6: Reanalysis is not observation

WeatherReal reports that reanalysis products diverge substantially from observations for near-surface temperature and other variables, and builds a benchmark from in-situ data for that reason (Jin et al., 2024). A second study asks how well reanalysis simulates the real world and whether it does so equally well in every region (Ramavajjala & Mitra, 2023). For this project it means that a detector trained and validated on ERA5, as in the current ERA5 notebook, learns the statistics of a model, and its recall on injected faults will overstate performance on real sensors.

### Theme 7: Federated and personalised training exists for meteorological models, but for forecasting

A federated spatio-temporal Transformer with prompt learning handles heterogeneous multivariate meteorological sensors across regions (Chen et al., 2023). A personalised low-rank adapter keeps a client-specific component while fusing global knowledge, and reports forecasting and imputation results (Chen et al., 2024). Both support the shape of DataMend's `fedpers` variant (shared body, personalised parts) in meteorology generally, but neither addresses error detection and neither reports unseen-region evaluation in the abstract.

### Theme 8: Edge constraints and injected faults

An attention-based one-class autoencoder reached a usable state after thirty minutes of normal data and ran in about 31 kB on an edge device, tested on synthetic micro-anomalies (Choi, 2025). A few-shot fault classifier evaluates on bias, drift, spike and noise faults injected into real industrial measurements (Belay et al., 2026). Together they support the project's use of injected faults and its edge-friendly goal, with the caveat that both are non-meteorological sensors.

## Convergences and Disagreements

**Convergences**: (a) QC should be staged and should flag rather than overwrite (Castro et al., 2026; Jin et al., 2024); (b) cross-variable relationships carry information that single-variable tests miss (Sow, 2026; Castro et al., 2026); (c) station networks need graph or local-coordinate spatial models (Lin et al., 2021; Zhu et al., 2023; Xiong et al., 2024); (d) reanalysis is a proxy whose statistics differ from observation (Jin et al., 2024; Ramavajjala & Mitra, 2023).

**Disagreements and tensions**: the retrieved papers do not contradict one another empirically; they answer different questions. One real tension is between joint multivariate models (Fu & Yan, 2024) and the smearing problem that joint residuals create (Haldimann et al., 2019): joint models capture consistency but can blame the wrong sensor. Another is between simple and deep detectors: a small MLP and an Isolation Forest were enough for temperature and humidity in a small deployment (Sow, 2026; Yang et al., 2021), while the larger architectures are evaluated for forecasting. No paper tests whether the deeper model is needed for error detection.

## Gaps and Open Questions

1. No retrieved work compares architectures for detecting **erroneous** temperature, humidity or pressure values; the graph, convolutional and recurrent models in the set are evaluated for forecasting or for genuine anomalies.
2. No retrieved work shows how to protect **genuine** heat waves and cold spells from being flagged, which is the temperature counterpart of the rainfall "protected extreme" problem.
3. Real labelled error sets for these variables are not present in the retrieved abstracts; injected faults are the common substitute (Belay et al., 2026; Choi, 2025).
4. Pressure needs elevation handling (surface pressure on a plateau is far below sea level); none of the retrieved abstracts discusses it.
5. Evidence on whether federated or personalised training helps error detection (rather than forecasting) is absent.

## Comparison with the DataMend rainfall architecture

The left column is what the repository does for rainfall today. The middle column is a recommendation, derived from the themes above and from the properties of the variables; it is analysis, not a finding from any one paper.

| Element | Rainfall (current, `qc/`) | Temperature, humidity, pressure (recommended candidate) | Support |
|---|---|---|---|
| Target distribution | Zero-inflated Gamma: many exact zeros, heavy right tail | Heteroscedastic continuous head (Gaussian or heavier-tailed), no zero inflation; humidity bounded to 0-100 %, handled by a logit scale or clipping | Property of the variables; not tested in the set |
| Spatial component | 13 x 13 patch around a hidden disc, on the RF25 grid | Same masked idea. On a grid keep the patch; on irregular stations use a graph attention model with distance and elevation features | Lin et al., 2021; Zhu et al., 2023; Xiong et al., 2024; Agarwal et al., 2024 |
| Variables per model | One (rain) | All three jointly as input channels, so temperature and humidity inform each other's prediction | Sow, 2026; Fu & Yan, 2024 |
| Cross-variable consistency | None needed | Learned inside the joint model; the current Mahalanobis expert stays as a baseline | Castro et al., 2026 |
| Fault attribution | One variable | The target variable's own value is hidden from its own prediction, and residuals are attributed per variable to limit smearing | Haldimann et al., 2019 |
| Temporal component | GRU over the cell's own previous 30 days | GRU or similar over the cell's own history of all three variables; add a diurnal phase if hourly data are used | Not specific to any retrieved paper |
| Genuine extremes | Protected extreme: a spatially coherent group of heavy-rain cells | Needs a counterpart (a coherent regional heat or cold event) that does not exist yet | Gap 2 |
| Elevation | Static features | Required for pressure and strongly relevant to temperature | Gap 4 |
| Fault library | Point and footprint faults on rainfall | Spike, stuck, drift, amplitude error exist; add footprint faults and cross-variable (swapped or inconsistent) faults | Belay et al., 2026 for injected faults |
| Fusion | Logistic, mean, OR, boosted, per client | Same; add the consistency score as an input | Same design as rainfall |
| Federated | `fedpers`, `fedavg`, `fedft`, `local` | Same variants; personalised parts help most where regions differ in climate | Chen et al., 2023, 2024 (forecasting only) |
| Data caveat | RF25 is a gauge-derived product with no labels | ERA5 is modelled, so faults are easier to detect; real station data are needed | Jin et al., 2024; Ramavajjala & Mitra, 2023 |

## Implications for DataMend (analysis, not a finding)

1. **Reuse the masked-target design.** The rainfall hidden-disc model is already the architecture the literature favours for sensor fault work; extending it to three variables is a smaller step than adopting an unrelated model family.
2. **Test, do not assume.** Build the candidate as one more expert and compare it with the existing rule-and-statistics baseline on the same synthetic benchmark, at the same false-alarm budgets, with per-variable and per-fault-kind recall. The comparison to run: (a) current baseline, (b) single-variable masked model with a Gaussian head, (c) joint three-variable masked model, (d) the same with a graph attention spatial component on a station subset.
3. **Validate on real stations before believing any number.** ERA5 results show the code works, not that faults in real AWS data are caught.
4. **Add genuine-extreme protection first.** It is the gap most likely to change false-alarm results, and no retrieved paper provides a method for it.
5. **Audit variable coverage** before training, as in the LoRaWAN study (Sow, 2026), and handle elevation for pressure.

## Per-Paper Annotations

Abstract-level only. "Not stated" means the abstract does not say.

### Agarwal et al. (2024)
- **Question**: scalable anomaly detection in spatiotemporal rainfall over India, 1990-2015.
- **Method**: graph attention autoencoder with a spatial regularisation term; graphs built from rainfall, pressure and temperature attributes (IMD and ERA5), edges from event synchronisation.
- **Findings**: reports that it identifies anomalous rainfall patterns across India; no figures in the abstract.
- **Limitations**: anomalies are climatological extremes, not data errors; no injected-fault evaluation stated.

### Belay et al. (2026)
- **Question**: few-shot sensor fault diagnosis.
- **Method**: multi-episode prototypical networks aggregating prototypes from several support episodes; evaluated on bias, drift, spike and noise faults injected into industrial measurements.
- **Findings**: improvement over single-episode baselines in the one-shot setting; statistically indistinguishable from ProtoNet at equal support budget in another setting.
- **Limitations**: industrial data, not meteorological.

### Castro et al. (2026)
- **Question**: a harmonised, quality-controlled archive of hourly Brazilian surface observations.
- **Method**: two-stage QC: physically implausible values to missing and flagged, then temporal and cross-variable consistency checks producing flags without overwriting.
- **Findings**: 616 station codes, 2000-2025, with precipitation, air and dew point temperature, relative humidity and pressure; per-station flags and audits.
- **Limitations**: a data paper; no detection-performance numbers in the abstract.

### Chen et al. (2023)
- **Question**: a cross-region weather foundation model without sharing raw data.
- **Method**: federated spatio-temporal Transformer with a prompt-learning mechanism for low-resource sensors.
- **Findings**: effective on classical forecasting tasks across three multivariate datasets.
- **Limitations**: forecasting, not error detection.

### Chen et al. (2024)
- **Question**: on-device modelling of meteorological variables.
- **Method**: a pre-trained language model with a lightweight personalised adapter and low-rank communication.
- **Findings**: outperforms state of the art on forecasting and imputation on a real dataset.
- **Limitations**: forecasting and imputation; no error detection.

### Choi (2025)
- **Question**: edge-deployable sensor anomaly detection.
- **Method**: attention-based one-class autoencoder, seven sensor channels, trained on thirty minutes of normal data.
- **Findings**: F1 0.72, precision 0.89, recall 0.61 on synthetic micro-anomalies; about 31 kB; inference under two seconds.
- **Limitations**: laboratory liquid sensors; synthetic anomalies.

### Fu and Yan (2024)
- **Question**: sensor fault detection, isolation and accommodation.
- **Method**: masked self-supervised modelling; random masks act as faults.
- **Findings**: outperforms existing approaches on a public and a wind-turbine dataset.
- **Limitations**: not meteorological variables as such; abstract gives no numbers.

### Haldimann et al. (2019)
- **Question**: identifying multiple sensor faults with analytical redundancy.
- **Method**: disentangled RNN to limit smearing, with a probabilistic residual model for isolation; linear in the number of sensors.
- **Findings**: verified on a real petrochemical plant dataset.
- **Limitations**: industrial data; abstract gives no figures.

### Jin et al. (2024)
- **Question**: evaluating weather models against observations rather than reanalysis.
- **Method**: WeatherReal, a benchmark from global near-surface in-situ observations with a public QC and evaluation framework.
- **Findings**: reanalysis diverges substantially from observation for near-surface temperature, wind, precipitation and clouds.
- **Limitations**: a forecasting benchmark; its QC method is not described in the abstract.

### Lin et al. (2021)
- **Question**: spatial modelling for irregularly placed sensors in weather forecasting.
- **Method**: conditional local convolution on a graph with local coordinate systems and distance and orientation terms, inside a recurrent network.
- **Findings**: improved forecasting (details cut off in the abstract excerpt read).
- **Limitations**: forecasting.

### Ramavajjala and Mitra (2023)
- **Question**: verification of data-driven weather prediction against in-situ observations.
- **Method**: comparison with station observations, including regional differences.
- **Findings**: raises how well reanalysis simulates the real world and whether biases differ by region.
- **Limitations**: forecasting verification; abstract excerpt only.

### Sow (2026)
- **Question**: data quality audit and temperature-humidity analysis of a two-year LoRaWAN network.
- **Method**: coverage audit, modified z-score, Isolation Forest, PCA, clustering, and an MLP predicting humidity from temperature and time.
- **Findings**: correlation -0.662; Isolation Forest flags 2.12% multivariate anomalies where a univariate z-score flags none; MLP R² 0.672; pressure present in only 4.24% of frames.
- **Limitations**: one deployment of five devices; no labelled faults stated.

### Xiong et al. (2024)
- **Question**: sparse spatio-temporal meteorological forecasting.
- **Method**: graph convolution on station data fused with satellite images through a vision LSTM.
- **Findings**: first use of this fusion, per the authors.
- **Limitations**: forecasting.

### Yang et al. (2021)
- **Question**: anomaly detection on wireless sensor data streams in a smart greenhouse.
- **Method**: DLSHiForest, an isolation forest with locality-sensitive hashing and time windows; handles correlated streams and concept drift.
- **Findings**: reported practicable and accurate on a greenhouse dataset; no figures in the abstract.
- **Limitations**: single application domain.

### Zambon et al. (2025)
- **Question**: a dataset for spatiotemporal deep learning on station data.
- **Method**: PeakWeather, 10-minute observations from 302 MeteoSwiss stations over 8 years with topographic indices and an operational NWP baseline.
- **Findings**: a resource; supports spatiotemporal tasks.
- **Limitations**: forecasting benchmark, not QC.

### Zhu et al. (2023)
- **Question**: a multivariate benchmark for ground-station weather forecasting.
- **Method**: Weather2K, 2,130 stations, 20 meteorological factors; baselines and a multi-graph convolutional model.
- **Findings**: a resource with reported baselines.
- **Limitations**: forecasting; the abstract excerpt read does not give results.

## References

Agarwal, M., Das, P., & Bhatia, U. (2024). Spatially regularized graph attention autoencoder framework for detecting rainfall extremes. arXiv. https://arxiv.org/abs/2411.07753

Belay, M. A., Haghipour, A., & Salvo Rossi, P. (2026). Robust prototypical networks for few-shot sensor fault diagnosis. arXiv. https://arxiv.org/abs/2609.12287

Castro, M. L., Vichete, W. D., & Filho, L. L. (2026). METBRA25Y: Brazil surface meteorology archive with harmonized variables and quality control. arXiv. https://arxiv.org/abs/2605.08701

Chen, S., Long, G., Shen, T., & Jiang, J. (2023). Prompt federated learning for weather forecasting: Toward foundation models on meteorological data. arXiv. https://arxiv.org/abs/2301.09152

Chen, S., Long, G., Jiang, J., & Zhang, C. (2024). Personalized adapter for large meteorology model on devices: Towards weather foundation models. arXiv. https://arxiv.org/abs/2405.20348

Choi, S. (2025). Fast re-trainable attention autoencoder for liquid sensor anomaly detection at the edge. arXiv. https://arxiv.org/abs/2507.03995

Fu, Y., & Yan, W. (2024). One masked model is all you need for sensor fault detection, isolation and accommodation. arXiv. https://arxiv.org/abs/2403.16153

Haldimann, D., Guerriero, M., Maret, Y., Bonavita, N., Ciarlo, G., & Sabbadin, M. (2019). A scalable algorithm for identifying multiple sensor faults using disentangled RNNs. arXiv. https://arxiv.org/abs/1909.02449

Jin, W., Weyn, J., Zhao, P., Xiang, S., Bian, J., Fang, Z., Dong, H., Sun, H., Thambiratnam, K., & Zhang, Q. (2024). WeatherReal: A benchmark based on in-situ observations for evaluating weather models. arXiv. https://arxiv.org/abs/2409.09371

Lin, H., Gao, Z., Xu, Y., Wu, L., Li, L., & Li, S. Z. (2021). Conditional local convolution for spatio-temporal meteorological forecasting. arXiv. https://arxiv.org/abs/2101.01000

Ramavajjala, V., & Mitra, P. P. (2023). Verification against in-situ observations for data-driven weather prediction. arXiv. https://arxiv.org/abs/2305.00048

Sow, M. (2026). Data quality audit and bivariate temperature-humidity analysis of a long-term LoRaWAN network: Anomaly detection, PCA, clustering and machine learning. arXiv. https://arxiv.org/abs/2610.32438

Xiong, Y., Zhu, X., Wu, M., Li, W., Mo, F., Zhang, C., & Zhang, B. (2024). VN-Net: Vision-numerical fusion graph convolutional network for sparse spatio-temporal meteorological forecasting. arXiv. https://arxiv.org/abs/2404.16037

Yang, Y., Ding, S., Liu, Y., Meng, S., Chi, X., Ma, R., & Yan, C. (2021). Fast wireless sensor anomaly detection based on data stream in edge computing enabled smart greenhouse. arXiv. https://arxiv.org/abs/2107.13353

Zambon, D., Cattaneo, M., Marisca, I., Bhend, J., Nerini, D., & Alippi, C. (2025). PeakWeather: MeteoSwiss weather station measurements for spatiotemporal deep learning. arXiv. https://arxiv.org/abs/2506.13652

Zhu, X., Xiong, Y., Wu, M., Nie, G., Zhang, B., & Yang, Z. (2023). Weather2K: A multivariate spatio-temporal benchmark dataset for meteorological forecasting based on real-time observation data from ground weather stations. arXiv. https://arxiv.org/abs/2302.10493
