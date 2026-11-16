# Prior work on precipitation / meteorological QC: verification for positioning

> **STATUS: UNVERIFIED, SUBAGENT-EXTRACTED.** Written by a Haiku research subagent from web fetches; not reviewed line by line. Open and check every source before citing it.

"Confirmed" means the record and stated content were read at a primary or repository page. "UNVERIFIED" means only search snippets were available (source blocked, HTTP 403). Nothing is inferred beyond the cited page.

## 1. CNN ensembles using gridded precipitation context for gauge QC

**Found: Sha, Gagne, West, Stull (2021), "Deep-learning-based precipitation observation quality control," *J. Atmos. Oceanic Technol.* 38(5), 1075-1091. DOI 10.1175/JTECH-D-20-0081.1.**
- Confirmed: DOI redirect target (AMS page returned 403, so details come from the repository record). Abstract summary: https://impacts.ucar.edu/en/publications/deep-learning-based-precipitation-observation-quality-control-2/ ; PDF metadata at https://opensky.ucar.edu/system/files/2024-08/articles_24497.pdf (binary, unreadable here).
- Data: sparse station network in complex terrain, British Columbia.
- Labels: human QC labels (2016-2017). Not operational flags, not synthetic.
- Model: CNNs in a multiclassifier ensemble. Inputs: gridded precipitation and elevation analyses. Saliency maps.
- Metrics: AUC 0.927; type I and type II error "lower than 15%" across coastal and inland regions.
- Leaves open: the record does not state the temporal resolution of the gridded input, does not report interpolation-shaped error analysis, does not report extreme-value preservation beyond AUC, and has no federated component.

## 2. LSTM autoencoders for weather-station QC

**Found: Spohn et al. (2026), "A machine learning approach using autoencoders to perform quality control on meteorological data," *Environmental Data Science* 5, e1. DOI 10.1017/eds.2026.10030.** Confirmed at https://www.cambridge.org/core/product/4576781508080877E36C0CA6612E5590/core-reader.
- Data: Athenry (Met Eireann TUCSON network), 1-minute air temperature; training 2010-2022 excluding 2014; test 2014.
- Labels: expert-QC'd series treated as error-free for the QC test; manual QC flags for the raw-data test.
- Models: standard AE, VAE, LSTM-AE (sequence lengths 60 to 4320 min); 99th-percentile validation-MSE threshold.
- Metrics: 99.6% accuracy on valid observations (raw data); 79% of manual flags replicated (85 of 107); 5 false negatives; 6 false positives "over a full year" as stated in the abstract. The body suggests the false-positive count is understated (593 valid points flagged on the 3-day LSTM run). Verify against the full text before citing the 6.
- Leaves open: single station, single variable, temporal anomaly detection only; no gridded or spatial evidence; no federated training.

**Found: Supriyatna et al. (2026), "Flatline Anomaly Detection in Automatic Weather Station Air Temperature Sensor Data Using LSTM Autoencoder," *Jurnal Penelitian Pendidikan IPA* 12(4), 323-332. DOI 10.29303/jppipa.v12i4.14486.** Confirmed at https://jppipa.unram.ac.id/index.php/jppipa/article/view/14486.
- Data: AWS air temperature, 985,730 sliding windows (station, span and interval not stated).
- Labels: not described.
- Model: LSTM-AE plus Level-1 QC; normal-only training; MSE threshold 0.01177.
- Metrics: about 0.578% of windows flagged. No precision, recall or F1 reported.
- Leaves open: one fault type (flatline), no ground truth reported, no spatial or gridded context.

## 3. Federated LSTM for sensor fault detection

**Found: Khan, Saeed, Koo (2024), "FedLSTM: a federated learning framework for sensor fault detection in wireless sensor networks," *Electronics* 13(24), 4907. DOI 10.3390/electronics13244907.** Confirmed at https://researchportal.beds.ac.uk/en/publications/fedlstm-a-federated-learning-framework-for-sensor-fault-detection-5/ (MDPI page returned 403).
- Data: temperature data augmented with synthetic sensor data simulating six faults (bias, drift, spike, erratic, stuck, data-loss).
- Labels: synthetic (injected).
- Model: federated LSTM; baselines are centralized, federated 1D-CNN and MLP.
- Metrics: accuracy, precision, sensitivity, F1 are named. The repository record gives no numbers. Client count is not stated there. Do not cite numbers from secondary snippets.
- Leaves open: no gridded or spatial precipitation context; synthetic faults only; not rain-gauge data.
- Warning: arXiv 2303.13015 (https://arxiv.org/abs/2303.13015) is a different paper (Katzef et al., "Failure-tolerant Distributed Learning for Anomaly Detection in Wireless Networks," Tol-FL). It must not be cited as FedLSTM.

## 4. Federated data-quality assessment for sensors / IoT

**Found: Navaz, Serhani, El Kassabi, Taleb (2023), "Empowering Patient Similarity Networks through Innovative Data-Quality-Aware Federated Profiling," *Sensors* 23(14), 6443. DOI 10.3390/s23146443.** Confirmed at https://pmc.ncbi.nlm.nih.gov/articles/PMC10384464/.
- Data: fetal cardiotocography dataset (2,126 instances, 23 attributes), split across five edge nodes. The authors state the data had few quality issues, so errors and noise were synthesized.
- Labels: class labels from expert obstetricians; quality errors are injected (synthetic).
- Method: federated data-quality profiling (FDQP), with federated feature selection.
- Metrics: per-node accuracy gains (e.g. node 2: 70.71% to 91.92%). The text is internally inconsistent on the scenario-4 gain (about 10% vs 10% average / 15% max with LDQP), so do not cite a single headline figure.
- Leaves open: not sensor-fault or transmission-fault scenarios; clinical data; no precipitation.

**Also found, not confirmed at primary source:**
- FedDQ (Fadlallah blog, https://hadifadl.github.io/2025-02-22-feddq): federated context-aware data quality for IoT/WSN radiation data (LAEC). **UNVERIFIED**: no paper page or metrics found; blog is not a primary source.
- Valente Neto et al. (2025), "Adding data quality to federated learning performance improvement," *IEEE Access* 13, 126623-126648. DOI 10.1109/ACCESS.2025.3578301. Record at https://ciencia.iscte-iul.pt/publications/adding-data-quality-to-federated-learning-performance-improvement/111690. Datasets are MNIST, Fashion-MNIST, CIFAR-10/100 (image data). IoT is motivation only. Publisher page not fetched.

## 5. 2025 study on heavy-rainfall QC with minute-level and remote-sensing context

**Candidate, UNVERIFIED: Sun et al. (2025), *Remote Sensing* 17(24), 3976. DOI 10.3390/rs17243976.** The publisher returned 403 and the preprint (https://www.preprints.org/manuscript/202510.1276, DOI 10.20944/preprints202510.1276.v1) returned 403. Only search snippets were available:
- Snippet data: AWS, Doppler radar, satellite and minute-level precipitation, June 2022 to December 2024; focus on hourly precipitation above 40 mm.
- Snippet results: ML-based QC; remote-sensing and minute-level inputs are the dominant predictors. No metrics were retrieved.
- The snippet describing operational errors and transmission faults is attributed to an "earlier deep-learning QC study" and is not tied to a confirmed paper. Do not attribute it to this paper without the full text.

**Closest confirmed 2025 paper, which does NOT match the claim:** Osrodka et al. (2025), "Adaptation of RainGaugeQC algorithms for quality control of rain gauge data from professional and non-professional measurement networks," *Atmos. Meas. Tech.* 18, 3229-3245. DOI 10.5194/amt-18-3229-2025. Confirmed at https://amt.copernicus.org/articles/18/3229/2025/amt-18-3229-2025.pdf.
- Uses 10-minute gauges and 5-minute radar; daily verification against manual gauges.
- Minute-level data: not used. Satellite: not in the reported experiments.

## 6. Rain-gauge QC evaluations: synthetic/injected faults vs. operational or expert labels

**Expert labels, confirmed: Villalobos-Herrera et al. (2022), "Sub-hourly resolution quality control of rain-gauge data significantly improves regional sub-daily return level estimates," *QJRMS* 148(748), 3252-3271. DOI 10.1002/qj.4357.** Confirmed at https://pmc.ncbi.nlm.nih.gov/articles/PMC9826504/.
- Data: 1,301 Great Britain gauges (sub-hourly), no radar or satellite.
- Labels: expert manual inspection (68 training maxima; 30 flood events for validation). EA operational flags not used.
- Metrics: 19% false positives (14 of 74), 10% false negatives (7 of 72).
- Leaves open: no synthetic injection; no gridded or interpolation analysis; no federated training.

**Operational/expert labels, confirmed: Sha et al. (2021)** (see claim 1). Labels are human QC.

**Synthetic/injected faults, found but UNVERIFIED (403 at source; snippets only):**
- Bayesian streaming QC, *Environmental Modelling & Software* (https://www.sciencedirect.com/science/article/abs/pii/S1364815212002538): synthetic errors; reported false alarm 0.90% and false negative 1.5%. Snippet only.
- Co-kriging radar-gauge QC, *Hydrological Sciences Journal* (https://www.tandfonline.com/doi/full/10.1080/02626667.2013.839873, DOI 10.1080/02626667.2013.839873): controlled tests with injected clogging, large reports and transmission contamination; reported detection rate 55% for a false 10 mm observation. Snippet only.

**Not found:** a gauge QC evaluation combining synthetic fault injection with expert labels, reporting precision/recall. Two searches on injected/synthetic gauge faults returned no match.

## Summary for positioning

- Claims 1-3 have confirmed papers at abstract or record level. Claim 4 is confirmed only for clinical and image data. Claim 5 is UNVERIFIED. Claim 6 has confirmed expert-label evaluations; the synthetic-injection evaluations are UNVERIFIED snippets.

| claim | paper found? | confidence |
|---|---|---|
| 1. CNN ensembles with gridded precipitation context for gauge QC | Yes: Sha et al. 2021, JTECH, DOI 10.1175/JTECH-D-20-0081.1 | High for citation and abstract summary; medium for method details (AMS page 403) |
| 2. LSTM autoencoders for weather-station QC | Yes: Spohn et al. 2026, Env. Data Sci., DOI 10.1017/eds.2026.10030; also Supriyatna et al. 2026, JPPIPA (flatline) | High for citation; medium for headline metrics (false-positive count disputed in body) |
| 3. Federated LSTM for sensor fault detection | Yes: Khan, Saeed, Koo 2024, Electronics, DOI 10.3390/electronics13244907 (no metrics retrieved) | High for citation; low for numbers |
| 4. Federated data-quality assessment for sensors / IoT | Partly: Navaz et al. 2023 FDQP (clinical data, synthetic errors); Valente Neto et al. 2025 (image data); FedDQ IoT not confirmed | Medium (FDQP); low (FedDQ, IEEE Access sensor scope) |
| 5. 2025 heavy-rainfall QC with minute-level and remote-sensing context | Candidate only: Sun et al. 2025, Remote Sensing, DOI 10.3390/rs17243976 (publisher 403; snippets only). Confirmed 2025 paper does not match (Osrodka et al. 2025, AMT) | Low (candidate, UNVERIFIED) |
| 6. Gauge QC with synthetic/injected faults, and with operational or expert labels | Expert/human labels: Villalobos-Herrera et al. 2022 (QJRMS); Sha et al. 2021. Synthetic injection: Bayesian streaming QC and co-kriging papers (UNVERIFIED snippets) | High (expert labels); low (synthetic injection); no match for both combined |
