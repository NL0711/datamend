# Multi-resolution models, per-scale evaluation, and a live daily rainfall source for India

> **STATUS: RESEARCH NOTE WRITTEN BY A SUBAGENT, 2026-11-18. Not reviewed line by line.** New facts only; it does not repeat `docs/research/rainfall-qc-without-labels.md`, `operational-rainfall-qc-primary-sources.md` or `prior-work-precipitation-qc-positioning.md`. Where those files already hold a claim, this note says "repo note".
>
> **Source counts (approximate, I did not keep a formal log).**
> - **Read as text (about 42 pages or documents):** 14 papers or PDF reports (Mitra et al. 2025; IMD Hydromet SOP; IMERG V07 ATBD; WMO-No. 1245; WMO-No. 1090; El Hachem et al. 2022 and 2024; Lussana et al. 2019; Wadoux et al. 2021; Funk et al. 2026 (CHIRPS3); a Karnataka arXiv preprint; Pai et al. 2014 re-opened; the CRAN `SCI` manual; an IMD press-release PDF) plus about 28 provider or agency pages and READMEs (IMD, CHC/UCSB, NASA GES DISC and GPM, JAXA, MOSDAC, CRAN `climatol`, RHtests, Met Office, NCEI). Evidence grade A below.
> - **Abstract or landing page only (8):** Hiebl and Frei 2018; Wu and Keogh 2021; Kim et al. 2022; Tatbul et al. 2018; Lavin and Ahmad 2015; Hundman et al. 2018; Patna 23-product study 2024; Reddy et al. 2019 (library catalogue record). Grade B.
> - **Search snippet only, so UNVERIFIED (about 11):** Stagge et al. 2015; Wilks 2016; Roberts et al. 2017; the Environment Canada monthly QC system (Atmosphere-Ocean 2024); Thakur et al. 2020; Kumar et al. 2022; Lewis et al. 2021 (GSDR-QC; only as described in El Hachem 2024); several CHIRPS-versus-IMD regional papers; Hubbard spatial regression test; the 4-hour GSMaP_NRT latency; a North-West Himalaya IMERG V07 paper. Grade C.
> - **Could not open:** `hydro.imd.gov.in` (DNS failed twice, so "Rainfall Statistics of India 2024" was not read); Wiley, AMS, Taylor and Francis and ScienceDirect (HTTP 403, retried once) which blocked Reddy 2019, Kumar 2022, Thakur 2020, Stagge 2015, Roberts 2017 and the Canadian QC paper; Springer full text of Hiebl and Frei; Bureau of Meteorology (403); JAXA FAQ items 1 to 9 (404, so GSMaP_Gauge definitions and latency are unconfirmed); NCMRWF NRT report (connection reset twice); WMO-No. 100.
> - I did **not** download any rainfall data grid. Only small text pages and papers were read.

---

## 1. Models per scale (monthly or seasonal, yearly, decadal; few samples, no labels)

### 1.1 Neighbour prediction with the target hidden (leave-one-out interpolation)

- **El Hachem, Seidel, Imbery, Junghaenel, Bardossy 2022 (HESS 26, 6137).** Each value is removed, then re-estimated by ordinary kriging from the 30 nearest valid stations, in Box-Cox transformed space with a rank-space variogram. A value is suspicious when |estimate - observed| divided by the kriging standard deviation exceeds 3. "Space-time" means the same spatial test is repeated over several aggregation levels (hourly up to daily); time is not a kriging dimension. Data are DWD stations. The authors list their own limits: advective or frontal events with dry neighbours give false flags, simultaneous errors in neighbours give false flags, and only the four largest annual values per station were tested. https://hess.copernicus.org/articles/26/6137/2022/ (grade A)
- **Status:** one technical note on one national network. I would call it a proposal with a clear recipe, not an agency standard. It uses gauges, not an interpolated grid.
- **El Hachem et al. 2024 (HESS 28, 4715)** describes three open-source QC tools for personal-weather-station rain data. All use neighbours: faulty-zero filters compare a 0 against the neighbour median; GSDR-QC (as described there) runs its neighbour checks on daily totals to reduce hourly intermittency; one tool needs a trusted reference network. The note says it does not quantify false-alarm or false-rejection rates, uses one dataset and four events, and calls for open benchmarks. https://hess.copernicus.org/articles/28/4715/2024/hess-28-4715-2024.pdf (grade A for the quoted limits)
- **Lussana et al. 2019 (seNorge_2018, ESSD 11, 1531)** uses leave-one-out cross-validation (LOOCV) to evaluate an interpolation of daily precipitation and shows analysis quality depends on station density. Its QC is a separate spatial consistency test from a 2010 paper I did not open. https://essd.copernicus.org/articles/11/1531/2019/ (grade A for LOOCV; QC test itself not read)
- **Hiebl and Frei 2018 (SPARTACUS, Theor Appl Climatol)** build a daily precipitation grid in two tiers: monthly means by kriging with external drift, then daily relative anomalies, and keep the input network largely stationary over time for long-term consistency. Abstract only. https://link.springer.com/article/10.1007/s00704-017-2093-x (grade B)
- **Pooled machine-learning regression with the target hidden at monthly or yearly scale (gradient boosting, quantile regression):** I found no rainfall QC paper that does this. A search for quantile-regression QC returned only neighbour-range and interpolation checks (e.g. the IRI CDT user guide flags values far outside neighbour range or median scaled by interquartile range: https://iri.columbia.edu/~rijaf/CDTUserGuide/html/qc_outliers_precip.html, snippet only, grade C). So the spec's pooled regressors at monthly or yearly scale are **not established practice**; they are a reasonable generalisation of the leave-one-out idea above and must earn their place on the validation benchmark.

### 1.2 Climatological scores and gamma or zero-inflated models for totals

- The CRAN `SCI` package documents the standard mixed model for totals that can be zero: D(x) = p0 + (1 - p0) G(x) for x > 0, with G a fitted distribution (gamma and others) and p0 the probability of a zero month, with an optional plotting-position estimate of p0 for many zeros. https://cran.r-project.org/web/packages/SCI/SCI.pdf (grade A). That is established tooling for SPI-type indices.
- **WMO Standardized Precipitation Index User Guide (WMO-No. 1090, 2012):** at least 30 years of monthly values are needed; 20 to 30 is the ideal minimum quoted, 50 to 60 optimal; practical range is 1 to 24 months; beyond 24 months needs about 80 to 100 years or the tail probabilities are weak; missing months must be coded missing, and zero is a valid value. (Copy at https://www.droughtmanagement.info/literature/WMO_standardized_precipitation_index_user_guide_en_2012.pdf, grade A.) The mixed zero model itself is not described in the text I searched; I cite `SCI` for it.
- Consequence: about 62 training years is above WMO's minimum for monthly and seasonal and yearly standardisation, and below what WMO says is reliable for multi-year (decadal) tail probabilities. That is a documented limit, not just my view.
- Stagge et al. 2015 (candidate distributions for SPI) was **snippet only** (UNVERIFIED): reportedly gamma stays a reasonable default with alternatives better in some cases. https://zendy.io/title/10.1002/joc.4267
- **Quantile-regression z-scores for rainfall QC:** no primary source found. Treat as a proposal.
- Existing repo note covers the CHIRPS fixed 4-sigma screen; I did not re-open it.

### 1.3 Relative homogenisation and change-point tests (yearly and decadal)

- **WMO Guidelines on Homogenization, WMO-No. 1245 (2020)**, read in full text from a mirror (official record: https://library.wmo.int/?lvl=notice_display&id=21756, not opened): https://dgm-meteo.github.io/wmo-clino/Docs/WMO2020_1245_en_Guidelines%20on%20Homogenization.pdf
  - Tests compare a candidate with a reference (difference series for additive variables, ratio series for multiplicative ones such as monthly rainfall). Where monthly values can be zero, transform toward normal and use differences.
  - The significance level is usually 5%. Tests for unknown break dates must use the larger critical values of the "maximal" t or F tests; the regular t or F test used on unknown dates gives too many false alarms. Testing for unknown dates is equivalent to raising the significance level.
  - For precipitation, annual corrections were the most accurate in the HOME benchmark, and only the best methods improved precipitation data at all. HOME's break variance is stated as about two times too high and its station density unrepresentative of sparse networks.
  - Absolute (reference-free) homogenisation is called less reliable and not to be used automatically.
  - Reanalysis can serve as a reference only where no station neighbours exist, and reanalysis has its own breaks (for example when satellite inputs change).
  - It gives no ready threshold for a ratio test on interpolated gridded rainfall.
- **Climatol (R, `homogen`) reference manual:** the SNHT-type threshold `inht` defaults to 25, described as conservative for monthly temperature and less suitable for precipitation or daily data; daily series are to be tested on monthly aggregates; reanalysis grid-point series can be added as references (marked with an asterisk to skip their own break analysis); default 10 reference series in detection and 4 in the adjustment stage. https://search.r-project.org/CRAN/refmans/climatol/html/homogen.html (grade A)
- **RHtests (Environment and Climate Change Canada):** penalised maximal t and F tests, optional reference series, lag-1 autocorrelation handled; daily precipitation is a **separate** package (RHtests_dlyPrcp); critical-value tables are published with the code. https://github.com/ECCC-CDAS/RHtests (grade A for README claims; manuals not opened)
- **Interpolated or gridded inputs:** none of the three documents above says it is valid to test an interpolated grid against its own neighbour cells. WMO-1245 and Climatol only discuss reanalysis grid points as an extra reference. The ACMANT advice to prefer raw over interpolated inputs is in the repo note, not re-opened. For RF25 there is a further problem documented in the repo note: the contributing station count changes over time (about 1,450 to 3,900 per day), which itself creates breaks. So pairwise tests on RF25 cells are **unvalidated**; my opinion is that they measure network change as much as sensor change.
- **Thresholds:** a numeric SNHT or Pettitt critical value was not found in any text I opened. Setting thresholds by simulation on RF25-like series (the spec's plan) is consistent with how Menne and Williams did it per the repo note, but I found no document that endorses doing it for rain on a gridded product.
- Pettitt test documentation: not sourced.

### 1.4 Aggregated finer-scale scores as features

- Not found as a published design. The nearest practice is repeating the same spatial test on several aggregation levels (El Hachem 2022) and running neighbour checks on daily totals (GSDR-QC as described in El Hachem 2024). Feeding daily anomaly scores into a monthly or yearly model is **a proposal of this project**, untested elsewhere. Risk to state in the spec: the daily score already uses the same neighbours, so the monthly model would not be independent of it.

---

## 2. Per-scale evaluation and regional output

### 2.1 What comparable work reports

- **Synthetic faults with detection rates by aggregation.** El Hachem 2022 modified values at 20 stations by 25% to 100% (including drops to false zero) and report detection by aggregation: false zeros detected in about 60% of hourly and 94% of daily cases; inflations detected almost always. No false-alarm rate is given in the text; flagged events were checked only qualitatively against radar and river discharge. https://hess.copernicus.org/articles/26/6137/2022/ (grade A)
- **Real data, expert review (GHCN-Daily):** repo note (Durre et al. 2010): sample-based false-positive estimate with a 20% cap per check and 1 to 2% overall estimate. Not re-opened.
- **Blind benchmark limits.** WMO-1245 (section on numerical studies) says traditional validation focused on break-detection scores, that results depend on the metric, that detection scores do not say the best trade-off between hits and false alarms for users, and that newer work uses error against truth (RMSE, residual trend error). HOME limits: break variance about 2x too high, high density unrepresentative. https://dgm-meteo.github.io/wmo-clino/Docs/WMO2020_1245_en_Guidelines%20on%20Homogenization.pdf (grade A). The HOME paper itself is in the repo note.
- **Comparisons without false-alarm rates.** El Hachem 2024 compares three QC tools against a gauge-adjusted radar product with correlation, relative bias and coefficient of variation, and states it did not quantify false alarms or false rejections. https://hess.copernicus.org/articles/28/4715/2024/hess-28-4715-2024.pdf (grade A)
- **Event-level and false-alarm metrics from time-series anomaly detection (abstract pages only, grade B):**
  - Tatbul et al. 2018: classical point precision and recall do not fit anomalies that last over a period; they propose range-based versions with adjustable weights. https://arxiv.org/abs/1803.03639
  - Lavin and Ahmad 2015 (Numenta Anomaly Benchmark): scoring rewards early detection and penalises false alarms in a streaming setting. The abstract does not describe the windowing. https://arxiv.org/abs/1510.03336
  - Hundman et al. 2018: unsupervised thresholding with strategies to reduce false positives, evaluated on expert-labelled spacecraft data. https://arxiv.org/abs/1802.04431
  - Kim et al. 2022: point-adjusted F1 can make even a random score look state of the art; they propose a stricter protocol. https://arxiv.org/abs/2109.05257
  - Wu and Keogh 2021: most popular benchmark series have at least one of four flaws, so many published comparisons are unreliable; they propose the UCR anomaly archive. The abstract does not name the four flaws. https://arxiv.org/abs/2009.13807
  - These are general time-series papers, not rainfall; use them for metric design only.
- **Multi-scale reporting for rainfall products (not QC).** A study of 23 products at Patna evaluates at daily, weekly, monthly and annual levels with 13 continuous and 10 categorical metrics; abstract only. https://link.springer.com/article/10.1007/s00704-024-05191-3 (grade B). Mitra et al. 2025 evaluate their merged daily product against RF25 with percentage RMSE, false alarm ratio, equitable threat score and Peirce skill score, using a 0.5 mm/day rain threshold, for all India and four boxes (west coast 8-20N 72-78E; south-east peninsula 8-15N 77-82E; monsoon trough 18-28N 65-88E; north-east 22-30N 87-98E), for one month (July 2014). https://link.springer.com/article/10.1007/s12040-025-02550-0 (grade A). That is a usable regional-reporting template, with the limit that it covers one month.

### 2.2 Intervals under spatial and temporal dependence

- Wadoux, Heuvelink, de Bruin, Brus 2021 (full text) argue that spatial autocorrelation does not by itself invalidate accuracy assessment, that valid confidence intervals come from probability sampling of the validation units with design-based inference, and that in their experiment standard cross-validation had smaller bias than spatial cross-validation. Their subject is map accuracy, not QC. https://alexandrewadoux.github.io/assets/pdf/Wadoux_et_al_2021.pdf (grade A)
- Wilks 2016 (BAMS) recommends controlling the false discovery rate when many correlated grid points are tested at once; snippet only. DOI 10.1175/BAMS-D-15-00267.1 (grade C).
- Roberts et al. 2017 (block cross-validation) was blocked (403); not used.
- **No QC evaluation paper I opened uses a block bootstrap.** The block bootstrap over years and regions in the spec is therefore this project's choice, defensible but not documented QC practice. I did not open a primary source for the block bootstrap method itself (Kuensch 1989 and similar were not fetched). Nuance from Wadoux: if the test set is a census (all cells in all test years), the interval describes variability over years, not over cells; say which in the protocol.

### 2.3 How operational services present regional rainfall

- **IMD Hydromet SOP** (read in full text): https://mausam.imd.gov.in/imd_latest/contents/pdf/hydrology_sop.pdf
  - District rainfall is the arithmetic mean of the stations in the district; sub-division, state and country values are area-weighted from districts; four homogeneous regions are compiled the same way. More than 4,783 stations under the District-wise Rainfall Monitoring Scheme (DRMS); products cover 685 districts, 37 states and union territories, 36 meteorological sub-divisions.
  - Departure (%) = (actual - normal) x 100 / normal, with normals for 1961-2010 (1951-2000 used up to 2018).
  - Categories: large excess at +60% or more; excess +20 to +59; normal -19 to +19; deficient -59 to -20; large deficient -99 to -60; no rain at -100; no data. The IMD monsoon FAQ lists the same five bands: https://www.imdpune.gov.in/faq_monsoon.php
  - Daily products are the 24-hour rainfall "observed till 03 UTC"; weekly summaries are issued on Wednesdays; station data are quality checked at regional centres and reports are cross-checked, with discrepancies verified by phone (no automatic rule is described).
- **IMD mausam rainfall page** lists All-India districts, state-wise districts, meteorological sub-divisions, states, station rainfall, daily, weekly and cumulative maps by region, and weekly district, sub-division and state statistics. The daily label reads "recorded from 0830 hrs" of one date to 0830 of the next. https://mausam.imd.gov.in/responsive/rainfallinformation.php (grade A). The statistics page names categories large excess to no rainfall. https://mausam.imd.gov.in/responsive/rainfall_statistics.php?PAGE=1
- IMD's district rainfall map is stated to be interpolated from DRMS stations. https://webgis.imd.gov.in/webgis_DRMS/DRMS.html (grade A; categories and update frequency not stated there)
- **Met Office:** district, regional and UK values come from the HadUK-Grid dataset, with 30-year averages (1961-1990 and 1991-2020). https://www.metoffice.gov.uk/research/climate/maps-and-data/uk-climate-averages/regional-averages (grade A; how grid cells become areal means is not stated on that page)
- **NOAA NCEI Climate at a Glance:** selectable cities, states, regions, nation; says recent values are preliminary and may change after quality control. https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/ (grade A; percentile and base-period details not on that page)
- Bureau of Meteorology deciles page: could not open (403).
- What this shows: services summarise rainfall as areal means against a normal, with named bands. They summarise weather, not data quality. DataMend's regional output (share of suspect cells, count of review items by sub-division or the four homogeneous regions) is a different quantity and should not reuse the IMD category names.

---

## 3. Live or near-real-time daily rainfall for India

Common facts. IMD station rain is recorded at 0830 IST (0300 UTC), covering the previous 24 hours (IMD press release, SOP and mausam page above; press release: https://internal.imd.gov.in/press_release/20251125_pr_4498.pdf). The RF25 page does not state a rain-day definition and Pai et al. 2014 (re-opened) has no 0830 or UTC statement, so **which calendar date RF25 assigns to a 0830-IST reading is not documented** (UNVERIFIED; my assumption would be the date of the reading). https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html

### 3.1 IMD's own products

- **RF25 gridded rainfall (the training data).** Yearly NetCDF files, 365 or 366 daily records, 135 x 129 grid from 6.5N, 66.5E to 38.5N, 100.0E, mm. The page lists 1901-2024 in its description and offers 2025 in the year selector. No provisional or current-year grid is documented. No licence; asks for citation of Pai et al. 2014; accuracy disclaimed. https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html (grade A)
- **IMD / NCMRWF daily merged satellite-gauge rainfall (GPM), "Real-time".** This **exists and was not in the spec.**
  - Page: https://imdpune.gov.in/cmpg/Realtimedata/gpm/Rain_Download.html (grade A). Daily binary file chosen by date; the page's own script limits the date picker to yesterday or earlier. No licence text; asks users to acknowledge GPM data from NASA/GSFC and JAXA. No API, rate limit or automation terms are documented; the download is a web form.
  - The page's control file declares 241 x 281 points at 0.25 degree starting at 50E and 30S (so roughly 50-110E, 30S-40N). The RF25 window (6.5N, 66.5E start) falls on the same lattice if both use the same node convention (not verified).
  - Method and status (Mitra, Prakash, Pai et al. 2025, J Earth Syst Sci, open access, read in full): "Operational 24-hour accumulated rainfall dataset over Indian region by merging rain gauge and multi-satellite estimate from GPM". IMERG Late run is the first guess; about 2,600 real-time quality-controlled IMD gauges correct its bias by successive correction; daily totals are built from half-hourly IMERG ending at 0300 UTC to match gauge time; operational at IMD Pune and NCMRWF since 1 October 2015; latency about one day; newer IMERG versions are adopted when released; grid kept at 0.25 degree because of gauge density. https://link.springer.com/article/10.1007/s12040-025-02550-0
  - Validation in the paper: July 2014 only, against RF25, with RMSE falling after merging except in the north-east where gauges are sparse, and better false-alarm, ETS and Peirce scores than IMERG Late alone; numbers are in figures. It notes satellite-only products underestimate rain on the west-coast maxima. No multi-year or all-season bias table is in the paper.
  - Gauge-calibrated: yes, to IMD real-time gauges (a subset of the kind of gauges behind RF25), so agreement with RF25 is **not independent evidence**.
  - Unknown: how far back the archive on that page goes (the paper says operational since October 2015); whether scripted download is allowed; how the product changes when IMERG versions change.
- IMD RCC page lists this same merged product as "Real-time" and IMDAA reanalysis (1979-2018) and says model and hindcast data need an e-mail request. https://rcc.imdpune.gov.in/download.php (grade A)
- Other IMD real-time rain pages (district and station rainfall, DRMS map) are HTML maps and tables; I found **no documented API or machine-readable current-year grid.**
- IMD merged-product bias in a peer-reviewed multi-product comparison: Reddy, Mitra, Momin, Pai 2019 (Int J Remote Sens) compare IMERG (near-real-time and final), GSMaP (NRT and gauge-adjusted-Kalman type) and INSAT-3D with IMD gridded gauge rainfall at daily to seasonal scale; the abstract record says all are biased over mountains and north-east India, IMD-NCMRWF merged and IMERG-Final agree best, and the GPM products beat INSAT-3D. Percent underestimates quoted in a search snippet could not be tied to products. https://eld.bl.uk/catalog/100080306024_0x000001 (grade B; full text blocked)

### 3.2 NASA IMERG (GES DISC), version 07

| Run | Day definition | Latency (owner) | Gauge use | Source |
|---|---|---|---|---|
| Early, daily `GPM_3IMERGDE` | UTC day, mean of 48 half-hourly rates x 24 | about 4 h after the UTC day closes (target) | none directly; climatological calibration to Final | https://www.earthdata.nasa.gov/data/catalog/ges-disc-gpm-3imergde-07 |
| Late, daily `GPM_3IMERGDL` | UTC day | half-hourly target 14 h (about 12 h in recent data) | same as Early | https://www.earthdata.nasa.gov/data/catalog/ges-disc-gpm-3imergdl-07 ; https://gpm.nasa.gov/resources/faq/what-determines-latency-imerg |
| Final, daily `GPM_3IMERGDF` | boundaries not stated on the page | about 3.5 months (monthly batches) | GPCC monthly gauge analysis | https://www.earthdata.nasa.gov/data/catalog/ges-disc-gpm-3imergdf-07 |

- Resolution 0.1 degree, global; IR-based estimates 60N-60S, microwave-only estimates reach 90N/S in V07. https://gpm.nasa.gov/data/imerg
- V07 ATBD (read as text, table 3): Early and Late list a "climatological" gauge adjustment toward Final; Final uses the GPCC analysis; Early uses about 95% of the microwave sensors and trailing 45-day calibration. Retrospective Early and Late runs in V07 are produced from a superset of input data, so **historical "Early" is not identical to what was available live.** https://gpm.nasa.gov/sites/default/files/2023-07/IMERG_V07_ATBD_final_230712.pdf (grade A). The GPM page adds that extremes are more sensitive to these differences and that precipitation is less certain in mountains. https://gpm.nasa.gov/data/imerg
- Access and terms: product page says "openly shared, without restriction" under EOSDIS use and citation guidance (Early page). The pages I opened say Giovanni needs a free Earthdata account and PPS FTP needs PPS registration; the GES DISC download login requirement and any rate limits were **not confirmed** from an owner page I could open.
- Bias against IMD gauge grids: Mitra et al. 2025 (July 2014 versus RF25, text above) and Reddy et al. 2019 (abstract only) describe underestimation over India as a whole and large errors over mountains. A Karnataka monsoon preprint (arXiv 2509.20778, not peer reviewed as far as I know; reference is a state gauge network, not the IMD grid) found most products overestimating by up to about 20 mm/day on the Western Ghats and 5-10 mm/day in the north, and aligned products to the UTC day, not the IST day. https://arxiv.org/pdf/2509.20778 (grade A for what it says). So the sign of bias depends on region, reference and version; I found **no peer-reviewed multi-year IMERG V07 versus RF25 bias table I could open.**

### 3.3 JAXA GSMaP

- Hourly, 0.1 degree, 60N-60S, binary and CSV on a password-protected FTP site; **registration required**; terms: acknowledge JAXA, cite Kubota et al. 2020, **contact JAXA before distributing images or data widely, for example on the internet**. https://sharaku.eorc.jaxa.jp/GSMaP/guide.html (grade A)
- Products named by the owner: GSMaP_NRT, GSMaP_Gauge_NRT, GSMaP_MVK, GSMaP_Gauge and others; their definitions are in FAQ 6, which I could not open (404). Gauge adjustment uses NOAA CPC gauge daily totals according to the Google Earth Engine catalogue page, which is a host, not the owner. https://developers.google.com/earth-engine/datasets/catalog/JAXA_GPM_L3_GSMaP_v8_operational
- Version churn: per JAXA, algorithm version 9 products were released on 19 October 2026, and updates of the v7 near-real-time products ended on 29 June 2026. https://www.eorc.jaxa.jp/GPM/en/index_e.html (grade A)
- **NRT latency:** the owner pages I opened do not state it. About 4 hours appears in search snippets (UNVERIFIED).
- Day: hourly files in UTC; JAXA's own example accumulates hourly slices (for example a 24-hour sum ending at 09:59 UTC), so a 24-hour sum ending 03 UTC can be built.
- **GSMaP_ISRO (MOSDAC):** hourly, 0.1 degree, GSMaP_MVK adjusted with IMD 0.25-degree gridded rain and NOAA CPC gauges; version 1.0 beta; from March 2000; Single Sign-On download; latency and day boundary not stated. https://mosdac.gov.in/node/2024 (grade A). It is tuned to the IMD grid, so comparing it with RF25 is circular.

### 3.4 CHIRPS (UCSB Climate Hazards Center)

- **The actual preliminary daily path (found):** `https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/prelim/sat/2026/chirps-v3.0.prelim.YYYY.MM.DD.tif` (one GeoTIFF per day; 319 files, 1 January to 15 November 2026 at the time of reading; the last files were posted on 17 November). The older v2 folder `https://data.chc.ucsb.edu/products/CHIRPS/v2.0/prelim/global_daily/` has stale subfolders and CHC says v2 production ends after December 2026. https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/prelim/sat/ ; https://data.chc.ucsb.edu/products/CHIRPS/v2.0/README-CHIRPS.txt (grade A)
- Latency: preliminary is released two days after the end of a pentad (2nd, 7th, 12th, 17th, 22nd, 27th of the month); final in the third week of the next month. https://www.chc.ucsb.edu/data/chirps3 and the CHIRPS3 paper. My inference from this: a given day waits for its pentad, so the delay is about 2 to 6 days.
- Resolution 0.05 degree over land, 60S-60N, CC BY 4.0, no registration for the file directory. https://www.chc.ucsb.edu/data/chirps3
- **Daily definition and a key limit.** Daily values are not independent daily gauge products: the pentad total is blended with stations, and the within-pentad shape comes from IMERG Late V07 (`sat`) or ERA5 (`rnl`), with an even split when the shape source is zero, which can create artificial wet runs. The daily label is a UTC calendar-day tag; station reports follow other windows (some GTS reports about 06 to 06 UTC) and are not shifted to local time. CHC advises pentad or monthly totals where possible and warns that daily extremes, dry spells and wet-day counts are shaped by the disaggregation. https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/readme.txt (grade A)
- Preliminary uses rapidly available stations with less QC than final; preliminary v2 used only GTS and Conagua stations (v2 README); v3 preliminary documents "readily available" stations. https://data.chc.ucsb.edu/products/CHIRPS/v3.0/README-CHIRPSv3.0.txt (grade A)
- Bias against IMD: the CHIRPS3 paper (Funk et al. 2026, Sci Data 13, 718) validates against interpolated gauge data in twelve dense regions; **India is not mentioned in the text I read**. https://www.nature.com/articles/s41597-026-07096-4 (grade A). Regional CHIRPS-versus-IMD papers surfaced only as snippets (UNVERIFIED), generally suggesting overestimated light rain and weaker agreement in the Himalaya.

### 3.5 Others

- NOAA CPC global daily gauge analysis: the PSL page I opened was empty of specifications; not assessed.
- The user excluded MSWEP, PERSIANN-CCS and ERA5-Land. Not assessed.
- I found no other documented open daily rainfall product for India with an RF25-compatible day.

### 3.6 Ranked recommendation (opinion, based on the facts above)

1. **IMD/NCMRWF GPM-merged daily grid (IMD Pune real-time page).** Same owner, same 0.25-degree lattice (to be checked), 0300 UTC day, gauge-merged, about one-day latency, free. Conditions before use: confirm the archive start, confirm scripted download is allowed (ask IMD, address on the RF25 page), and accept that its IMERG-version changes make it non-stationary. Its paper validates only July 2014.
2. **IMERG Late V07, rebuilt from half-hourly files to a day ending 03 UTC** (daily product as a second choice with a one-day shift, see 3.7). Use Early only if a result is needed within hours. Use Final after about 3.5 months as an audit series. Fully documented, no gauge use at product time, but climatologically adjusted; mountains and extremes are weaker.
3. **GSMaP NRT or Gauge_NRT.** Hourly lets you build the 03 UTC day. Registration, version churn and the redistribution clause make it a secondary choice.
4. **CHIRPS3 prelim.** Poor fit for a daily QC model: the daily texture is borrowed from IMERG Late, delay is 2 to 6 days, and the owner discourages daily extremes and dry-spell use. Useful only if a pentad-scale scorer is added.
5. **GSMaP_ISRO.** Archive or cross-check only; it is tuned to the IMD grid.

Opinion beyond the documents: any satellite-based or merged field is smoother or differently textured than RF25 (which is inverse-distance interpolation of one to four gauges per cell), so the daily models trained on RF25 face a distribution shift even when the bridge check passes on means.

### 3.7 Day-boundary alignment

- IMD day D (0830 IST to 0830 IST) equals 03:00 UTC of D-1 to 03:00 UTC of D. A UTC calendar day D (IMERG, CHIRPS label) covers 00:00 to 24:00 UTC of D, offset by 3 hours.
- Using the **daily** IMERG file with the same label D therefore overlaps IMD day D by only 3 hours; the file labelled D-1 overlaps by 21 hours. (My arithmetic, assuming RF25 labels a day by the date of the 0830 reading, which is undocumented.)
- Best practice, as the IMD paper itself does: sum half-hourly IMERG (or hourly GSMaP) slices that end at 03:00 UTC.
- CHIRPS cannot be re-aligned at daily scale (pentad-based, windows of the stations unknown). Compare it only at pentad or longer.
- Determine the RF25 label convention empirically before anything else (bridge step 1).

### 3.8 Bridge check protocol (validation years 2013-2017 only; never 2018-2025)

0. Limits that change what can be tested: the IMD merged product is documented from 1 October 2015, so only about 2016-2017 (plus late 2015) overlap the validation years; **CHIRPS preliminary cannot be replayed historically** (history holds the final product, which uses more stations and QC); retrospective IMERG Early and Late are not identical to live data. The check therefore validates a product family, not the live stream. RF25 for the current year does not exist, so the live stream can only be checked against RF25 after the next release.
1. **Alignment.** For each product, build a daily field ending 03 UTC, test lags -1, 0, +1 day by correlating all-India and sub-division daily means with RF25; pick the lag per product on 2013-2015 (or 2015-2016 for the IMD merged product) and freeze it.
2. **Regrid** to the RF25 lattice (area-weighted for 0.1-degree products; direct subset for the IMD merged grid) and mask to the RF25 land cells.
3. **Agreement metrics** (borrowing Mitra et al.): rain/no-rain at 0.5 mm/day with false alarm ratio, equitable threat score and Peirce skill score; percentage RMSE; mean bias; by the four boxes and by season. Use block bootstrap by year and sub-division, stating whether cells or years are the resampling unit.
4. **Quantile check.** Compare daily intensity quantiles (50, 90, 99, 99.9) with RF25 per region, to see whether the heavy tail is shifted.
5. **Model shift check (the point of the exercise).** Feed the frozen daily scorers the product instead of RF25 and compare score quantiles and false alarms per 1,000 clean cell-days against RF25 at the frozen budgets (1.0 and 5.0). Pre-write an acceptance rule before running. No published acceptance rule exists; any threshold is the project's choice.
6. **Report** as "product bridge, validation years only", with the product name, run, lag and version; no live score is shown as RF25-validated until this passes. Re-run when the provider changes version (IMERG, GSMaP v9, IMD merged).

---

## Summary table

| item | recommendation for DataMend | evidence quality |
|---|---|---|
| Monthly or seasonal baseline | Standardise totals with a gamma-or-other fitted distribution plus a zero-probability term, per calendar month, instead of a plain z-score | A for the formula and the 30-year WMO guidance; B as a fit to RF25 (untested) |
| Leave-one-out neighbour residual (monthly and yearly candidate) | Add as a candidate and as a baseline; flag when residual over kriging spread exceeds 3, on Box-Cox values | A for one paper (El Hachem 2022), single network |
| Pooled gradient-boosted or quantile regression, target hidden | Keep as an experiment; do not call it established | C (no rainfall QC paper found) |
| Aggregated daily scores as yearly features | Keep only if it beats the climatological baseline; document non-independence | C (no precedent found) |
| Decadal ratio change-point tests | Keep as tests, not models; set thresholds by simulation; expect network-density breaks in RF25 | A for method and caution (WMO-1245, Climatol); C for use on interpolated grids |
| Event-level metrics | Report range-based event recall and false alarms per 1,000 clean periods; do not use point-adjusted F1 | B (abstracts only) |
| Intervals | Block bootstrap by year and region, stated as own choice | A (Wadoux caveats); no QC precedent |
| Regional output | Aggregate flagged-cell share by the 36 sub-divisions and 4 homogeneous regions; keep IMD departure bands for weather context only | A (IMD SOP) |
| Live source 1 | IMD/NCMRWF GPM-merged daily grid | A for documentation; C for archive depth and automation terms |
| Live source 2 | IMERG Late V07 rebuilt to a 03 UTC day; Early as a faster fallback | A |
| Live source 3 | GSMaP NRT or Gauge_NRT | A for registration and terms; latency C |
| CHIRPS3 prelim for daily QC | Do not use at daily scale | A |
| GSMaP_ISRO | Reference only, circular with RF25 | A |
| Bridge check | Run as in 3.8; note the IMD merged product allows only about 2016-2017 | A for constraints; protocol itself is opinion |

---

## What this means for the spec

Established practice (documented):
- Rain totals that can be zero are standardised with a mixed zero-plus-fitted-distribution model, with at least 30 years recommended by WMO (WMO-No. 1090, `SCI` manual).
- Break tests for unknown dates need the larger "maximal" critical values; precipitation corrections work best at annual scale; reference-free tests are risky; no document I opened gives a ready threshold for gridded rain (WMO-1245, Climatol, RHtests).
- Regional rain summaries are areal means against a normal with named bands (IMD SOP); IMD's daily day runs 0830 IST to 0830 IST.
- IMERG daily is a UTC day; CHIRPS daily is a disaggregated pentad; both mismatch the IMD day.

My opinion (not established practice):
- Leave-one-out neighbour residuals are the most defensible non-deep monthly and yearly candidate (one paper); pooled gradient-boosted regressors and aggregated-score features are untested ideas; keep them behind the validation gate.
- Yearly and decadal change-point tests on RF25 mainly detect station-network changes; label results "network or sensor change, not distinguishable".
- Rank the live sources as in 3.6; the IMD merged product first, subject to access confirmation.

Changes suggested to `docs/qc-multires-pipeline-spec.md` (not edited):
1. Section 7: add the IMD/NCMRWF GPM-merged real-time grid (`https://imdpune.gov.in/cmpg/Realtimedata/gpm/Rain_Download.html`; paper https://link.springer.com/article/10.1007/s12040-025-02550-0) and replace the line "no provisional current-year download was confirmed" with: no provisional RF25 exists; this separate merged product does.
2. Section 7: demote CHIRPS from primary to pentad-only and give the real path (`v3.0/daily/prelim/sat/YYYY/`); note daily values are IMERG-shaped, delay 2 to 6 days, and v2 production ends after December 2026.
3. Section 7: change IMERG wording to "UTC day; rebuild from half-hourly to end at 03 UTC"; add the day-alignment paragraph (3.7) and say RF25's date convention must be measured.
4. Section 7 and 8 step 6: bridge check covers about 2016-2017 for the IMD merged product, cannot replay CHIRPS prelim, and needs a pre-written acceptance rule and a model-shift step (3.8); add the circularity warning for IMD-tuned products.
5. Section 4 table: add the gamma-with-zero baseline and the leave-one-out residual candidate for monthly and yearly; restate decadal as "tests; thresholds by simulation; confounded by network change".
6. Section 5 metrics: add range-based event metrics, forbid point-adjusted F1, state the resampling unit for the block bootstrap.
7. Section 2 or 8 step 5: regional export by 36 sub-divisions and 4 homogeneous regions using area-weighted shares of suspect cells; keep IMD departure bands separate.
