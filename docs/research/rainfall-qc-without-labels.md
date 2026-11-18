# Rainfall QC and anomaly detection without labels: what others do

> **STATUS: PARTIAL, WRITTEN BY A RESEARCH SUBAGENT, 2026-11-18. Not reviewed line by line.**
> Opened and read as full text (8): Venema et al. 2012; Becker et al. 2013 (GPCC); Funk et al. 2015 (CHIRPS); Menne and Williams 2009; Domonkos and Coll 2017 (ACMANT3); Alemohammad et al. 2015; Rajeevan, Bhate, Jaswal 2008; Deforce et al. 2023 (soil-moisture sensors, not rainfall).
> Seen only as search snippets or catalogue records, so UNVERIFIED (7): Kothawale and Rajeevan 2017 (IITM RR-138), Rajeevan et al. 2006, Khaliq and Ouarda 2007, Lewis et al. 2021 (GSDR-QC), Osrodka et al. 2022 (RainGaugeQC), Mestre et al. 2013 (HOMER), the Brazilian BRA-QCP paper.
> Could not open: Yatagai et al. 2012 (APHRODITE, AMS returned an HTML shell), Menne and Williams via AMS (403; the NCEI copy opened), Rajeevan et al. 2006 and RR-138 (no file returned), WMO-No. 100 (not retried; already a gap in `operational-rainfall-qc-primary-sources.md`).
> Not fetched at all, so no claim is made: Alexandersson 1986 (SNHT), Pettitt 1979, Wijngaard et al. 2003.
> Already in the repo and NOT re-researched: GHCN-Daily flags and Durre et al. 2010 thresholds, MIDAS, Sha et al. 2021, DWD/KNMI, Pai et al. 2014 QC sentence. Where this file leans on them it cites the repo note, not the paper.
> Text of the PDFs was extracted locally with pdftotext. Two-column layouts were messy, so exact page numbers are not given.

## 1. Operational QC with no labels

**GPCC (monthly station totals, global).** Becker et al. 2013 say the GPCC database merges up to eight sources, and that redundant records of the same station and month allow cross-comparison and quality control. A semi-automatic comparison against neighbouring stations flags suspect values. Suspect values are checked and then confirmed, corrected where possible, or flagged as erroneous and excluded. The authors state that this needs much human interaction because there are "no general valid screening criteria". The original data are kept next to corrected data so corrections can be traced. Thresholds are not given in this paper; it defers to Schneider et al. (2013), which I did not open. Source: https://essd.copernicus.org/articles/5/71/2013/essd-5-71-2013.pdf (Sect. 3).
Take-away: the global monthly archive relies on neighbour comparison plus human review, and says so.

**CHIRPS (daily station inputs).** Funk et al. 2015 describe automatic screening of station values that are extreme by standardised anomaly (more than 4 in absolute value), very large in absolute terms, or more than 5 times the satellite-based CHIRP estimate. Flagged values are excluded from the blending. A separate screen targets "false zeros": where a source codes missing data as zero, the daily value is dropped if it is zero while the CHIRP estimate for that day is above normal. The authors say this reduces but does not eliminate false zeros. They also rank sources and treat GSOD and GTS as lowest because of zeros standing in for missing data and repeated daily observations. Source: https://www.nature.com/articles/sdata201566.pdf (Methods, station data).
Take-away: the thresholds (4, 5x) are fixed numbers chosen by the authors, not derived from a label set. The z-score is not stated to be robust or rain-specific. Durre et al. (via the repo note) say a plain z-score over-flags skewed rain.

**GHCN-Daily.** Repo note `operational-rainfall-qc-primary-sources.md` records thresholds that come from the station's own data (95th percentile of nonzero values by calendar day, a gap test, a 75 km neighbour check) and a threshold-selection method that uses manual review of flagged samples with a 20% false-positive cap. Not re-opened here. That note itself flags the streak threshold as UNVERIFIED.

**IMD.** Rajeevan, Bhate and Jaswal 2008 (GRL) say "multi-stage quality control" was applied to station rainfall before interpolation for a 1901-2004 gridded product, with no tests or thresholds listed. They used 1384 stations with at least 70% data availability to limit inhomogeneity from changing station density. Source: https://imdpune.gov.in/cmpg/Griddata/Analysis%20of%20variability%20and%20trends%20of%20extreme%20rainfall%20events%20over%20India.pdf (Sect. 2). Pai et al. 2014 (RF25) is in the repo note: one sentence of QC, variable network of about 1450 to 3900 stations per day.

**Which of these need no labels?** All of the above are rule or neighbour based. None used labels to fit the test. Thresholds are either set by the authors (CHIRPS: 4 sigma, 5x) or from the data distribution (GHCN: percentiles, per the repo note). I found no operational archive where a trained model replaced the rule layer.

## 2. Evaluating QC without ground truth

**Synthetic benchmarks and their stated limits (homogenisation context).** Venema et al. 2012 (HOME) built a blind benchmark of real inhomogeneous data plus simulated networks with inserted breaks, outliers, missing periods and a network-wide trend. Participants did not know the truth until after submission. The authors list the limits themselves: results from 15 networks are few and errors are non-Gaussian; the benchmark has limited realism (break annual cycle exaggerated, break cross-correlation weaker than in real data, so network-mean errors are smaller and easier than reality); results depend on which metric is used; the benchmark does not allow tuning-free studies and could be tuned to; and break-detection scores correlate only modestly with error against truth, so detection scores should not be the sole criterion. They recommend also testing on real data with good metadata. For precipitation they say too little homogenised real data existed to validate the benchmark's precipitation break properties. They suggest a dedicated precipitation benchmark. Source: https://cp.copernicus.org/articles/8/89/2012/cp-8-89-2012.pdf (Sects. 7 and 8).
Relevance: this is the clearest primary statement that synthetic-injection results depend on how realistic the injected faults are, and that detection metrics alone mislead. It concerns break detection, not spike or stuck faults.

**Menne and Williams 2009.** Evaluated with simulated temperature series (hit rate about 67%, false-alarm rate 6.77% for steps only and 19.65% for steps plus trends). The authors explain the higher false alarms with trend inhomogeneities mistaken for steps. Temperature, not rainfall. Source: https://ncei.noaa.gov/pub/data/ushcn/papers/menne-williams2009.pdf

**Hold-out gauges.** Funk et al. 2015 withheld 10% (338 of 3,380) of Colombian stations, and 403 Peruvian stations, from CHIRPS, then compared product values against them. Reported seasonal-total R and MAE only. These are accuracy checks of a product, not QC-flag evaluations, and the gauges came from the same national agencies as the inputs. Source: https://www.nature.com/articles/sdata201566.pdf (Technical Validation).

**Independent products.** Funk et al. validate against GPCC and extra national gauge data screened to remove values in FAO or GHCN archives (same source). Pai et al. 2014 compare RF25 against other IMD and APHRODITE grids (repo note). Both share gauges with the products they are compared with, so agreement is not independent.

**Triple collocation (TC).** Alemohammad et al. 2015 apply multiplicative TC to rainfall products (NEXRAD-IV, TRMM 3B42RT, GPCP 1DD, GPI; 2 degree grid, biweekly totals, 2002-2014, central US). TC estimates each product's error variance without truth but needs at least three products and assumes errors are independent across products and independent of truth. The authors aggregated to biweekly totals because zero values make errors depend on the truth, and dropped zero samples. They checked TC against dense Oklahoma gauges and found TC underestimates true error where the independence assumption fails, for example when a product has been gauge-corrected. Source: https://hess.copernicus.org/articles/19/3489/2015/hess-19-3489-2015.pdf
Relevance: RF25 is built from the same gauges as any gauge-corrected product, so the independence assumption would fail for most India comparisons. TC is also an error-variance estimator, not a per-value flagger.

**Not found at a primary source I could open:** expert review of a sampled subset as an evaluation protocol is documented in the repo note for GHCN-Daily (Durre et al.), not re-opened here. GSDR-QC (Lewis et al. 2021) says it compares against manually QC'd gauge data; UNVERIFIED (catalogue record only).

## 3. Long-record inhomogeneity detection without truth

**Relative testing.** Venema et al. state that relative homogenisation, comparing a series with neighbours, is the most common approach, and that nearby stations are assumed to share the climate signal. Their top-performing methods (ACMANT, Craddock, MASH, PRODIGE, USHCN) all handle an inhomogeneous reference through pairs or multiple references. Methods that first detect the largest breaks, or use moving windows, were clearly less accurate. They also found automatic methods can match manual ones. Source: the Venema 2012 PDF above (Sect. 7, 8).

**Rainfall is harder.** Same paper: for precipitation, only the best algorithms improved the data; the problem likely lies in the noisy correction factors, since annual corrections (PRODIGE main) beat monthly ones; improvements were much larger at yearly and decadal scales than monthly, because the ratio series has low signal to noise due to high spatial variability. They recommend annual corrections for typical precipitation networks. Break detection scores were positive even where corrected precipitation got worse.

**Pairwise algorithm and how thresholds are set.** Menne and Williams (temperature) form target-minus-neighbour difference series, run SNHT on each, and combine evidence across pairs. Confidence limits for a changepoint date as a function of step size came from simulation of 10,000 series (n = 100). For adjustments, at least 3 pairwise estimates are required, and a step is called significant when the median plus 2.5 times the distance to the nearer quartile does not cross zero, an approximation to a one-sided 5% test. The simulations also show the pairwise approach cut false alarms compared with a composite reference, and that hit rate matched or exceeded it with at least seven usable neighbours. Source: https://ncei.noaa.gov/pub/data/ushcn/papers/menne-williams2009.pdf. SNHT is run with semi-hierarchical splitting at a 5% significance level. The paper says a search over unknown change dates needs more conservative critical values than a test of a known date, which makes undocumented-change tests less sensitive. It does not state a numeric critical value in the passages I read.

**ACMANT3 (Domonkos and Coll 2017, includes a precipitation programme).** Precipitation uses candidate/reference ratios. The method is fully automatic and joint (multiple breaks). The authors give explicit caveats that matter here: do general QC first, check zero-as-missing, expect synchronous breaks to reduce efficiency (even below 50% of series), prefer raw records over interpolated or previously adjusted products, and keep networks to about 20-30 series. Source: https://mural.maynoothuniversity.ie/8728/1/Domonkos_et_al-2016-International_Journal_of_Climatology.pdf (Sect. 5). I read the text of this PDF; the efficiency tests it reports are for temperature.

**SNHT critical values, HOMER.** Khaliq and Ouarda 2007 (critical values by Monte Carlo) and Mestre et al. 2013 (HOMER, in the Hungarian journal Idojaras) were seen only in snippets: UNVERIFIED. The Pettitt test was not sourced.

## 4. Learning-based approaches with few or no labels

- **Self-supervised sensor-level anomalies:** Deforce et al. 2023 (arXiv 2305.05495) train a triplet network with contrastive loss and cluster with DBSCAN to find rogue soil-moisture sensors without labels. Findings were checked by expert validation. It is not rainfall and the paper reports no numbers I used. Source: https://arxiv.org/pdf/2305.05495. Stated limits: prior methods assumed most sensors are good.
- **Neighbour-based QC without a reference set:** snippets only (BRA-QCP uses Local Moran's I against neighbours; RainGaugeQC uses a spatial check; GSDR-QC has 25 checks). All UNVERIFIED.
- **Reconstruction autoencoders, federated, CNN:** already in `prior-work-precipitation-qc-positioning.md`; not repeated.
- **Not found:** a rainfall paper I could open that trains a masked-neighbour or masked-value predictor and uses its residual as the QC score with no labels. I will not list one.

## 5. India and monsoon specifics

- IMD's 1901-2004 1-degree product (Rajeevan et al. 2008) chose a fixed network (1384 stations, at least 70% data) to avoid inhomogeneity from changing station density, and validated by comparison with the earlier 1951-2004 product. This is a design choice that RF25 did not make (Pai et al. 2014: variable network, per repo note).
- Rajeevan et al. 2008 define 150 mm/day or more as very heavy rain and analyse 1901-2004 trends of such events in central India; this is the source for the repo's heavy-rain threshold (opened). Same source, same page.
- IITM subdivision series (Kothawale and Rajeevan 2017, 306 fixed stations): UNVERIFIED snippet; the file did not open. It is the likely place for a fixed-network, homogeneity-aware all-India series, to be checked.
- No India-specific labelled QC evaluation was found in anything I opened.

## Technique table

| technique | needs labels? | evidence quality | daily | monthly | yearly | decadal |
|---|---|---|---|---|---|---|
| Range, duplicate, streak, zero-as-missing rules | no | high (GHCN, CHIRPS, ACMANT caveat) | yes | yes (via totals) | marginal | no |
| Robust percentile outlier per calendar day | no | high (GHCN per repo note) | yes | yes | too few samples | no |
| Fixed z-score cut (CHIRPS 4 sigma) | no | medium (fixed by authors, not tuned) | weak for skewed rain | ok on log or anomaly | weak | no |
| Neighbour comparison / spatial check | no | high (GPCC, GHCN) | yes if neighbours independent; interpolated grid neighbours are not | yes | yes | marginal |
| Pairwise change-point (SNHT-type) on difference or ratio series | no | high for temperature, lower for rain (Venema) | no | possible, noisy | best fit | few points |
| Joint multi-break (ACMANT, HOMER-type) | no | high (blind benchmark) | no | yes, rain corrections noisy | recommended for rain | limited by 125 years |
| Synthetic fault injection | no (builds its own labels) | medium, realism is the stated limit | yes | yes | yes | yes |
| Hold-out gauge / other product | no | medium, not independent for RF25 | n/a | n/a | n/a | n/a |
| Triple collocation | no | medium, fails when errors correlate | n/a | possible | no | no |
| Self-supervised sensor-level clustering | no | low for rain (soil sensors only) | maybe | maybe | no | no |

## What this means for DataMend

Established practice:
- Operational archives (GHCN, CHIRPS, GPCC, IMD) use rules and neighbour checks; none depends on labels, and GPCC says outright that human review is needed (Becker 2013).
- Rain needs special handling of zeros (zero-as-missing, nonzero-only statistics, CHIRPS false-zero screen).
- Relative (pairwise or reference) tests are the standard for long records, and for rain they work better on yearly corrections than monthly (Venema 2012).
- Benchmark authors say synthetic faults are only as informative as they are realistic, and that detection scores alone mislead (Venema 2012).

My opinion, not established practice:
- Keep synthetic injection as a unit test, and report it as such. Its realism is untested for India, so do not read its scores as real-world precision.
- Yearly and decadal models should be pairwise ratio change-point tests with simulation-set thresholds, not deep nets. 125 samples fits this; a neural net does not.
- RF25 neighbours come from shared gauges, so neighbour-independence assumptions in these tests (and in TC) are weaker than in raw gauge networks; ACMANT's advice to avoid interpolated inputs points the same way. This is untested.
- Fixing the network to one stable gauge set, as IMD did for 1901-2004, is a cleaner way to avoid inhomogeneity than detecting it afterwards.

## Remaining gaps

WMO-No. 100 QC section; Schneider et al. 2013 (GPCC QC detail); Yatagai et al. 2012; Rajeevan 2006 and RR-138 full text; Khaliq and Ouarda critical values; Mestre 2013; GSDR-QC and RainGaugeQC full text; the numeric SNHT critical values (Menne and Williams cite a more conservative set for unknown change dates but give no number in the text I read).
