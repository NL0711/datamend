# Federated learning for weather-station QC: prior work, data custodians, and operational consistency checks (primary sources)

Compiled 2026-11-19 for the phone-fl-prototype map (ticket t13). Feeds the federated-validation design ticket. This note makes no novelty claim (`AGENTS.md` section 5): where prior work exists it is cited.

Existing notes were re-checked, not repeated: `qc-novelty-research.md`, `prior-work-precipitation-qc-positioning.md`, `rainfall-qc-without-labels.md`, `operational-rainfall-qc-primary-sources.md`, `federated-update-protocol.md`. The existing federated simulation (`ml-service/qc/federated.py`, `docs/qc-system-spec.md`) uses gauge-grid clients (six of eight training clients, two held out; other clients' cells masked as missing; variants fedpers, fedavg, fedft, local; "no privacy claim"). It was only skimmed.

## BANNER: what was opened and what was not

Read dates are all 2026-11-19. Pages read through the WebFetch tool are summaries by a small model, not verbatim, unless marked "text extracted" (PDF downloaded and run through `pdftotext`, then grepped; sections read, not every page).

OPENED:
- Chen and Long 2026, arXiv:2605.00322 (arXiv abstract page and ar5iv-style HTML page, summarising fetch).
- FedLGAN, PeerJ Computer Science 2023 (PMC10703019), PMC full text, summarising fetch.
- WMO Resolution 40 (Cg-XII, 1995): community.wmo.int/resolution-40 and its Annex 1 page (summarising fetch), plus the NOAA/NWS-hosted PDF of the WMO-No. 827 text (text extracted; quotes below are from it).
- WMO Unified Data Policy page (wmo.int/wmo-unified-data-policy-resolution-res1), summarising fetch.
- NOAA NCEI ISD `readme.txt` (summarising fetch).
- Down To Earth article on IMD locking the AWS/ARG portal (summarising fetch); IMD Patna data-supply procedure PDF (text extracted).
- Weather Union home page and its terms page shell (summarising fetch).
- Durre et al. 2010 PDF (text extracted, grep only); HadISD paper arXiv:1210.7191 / Dunn et al. 2012 (text extracted, tests 5, 11, 12 and 14 sections read); WMO CIMO ET-ST&MT-1 Doc 6.1(2) 2004 draft (text extracted, internal-consistency section read); Estevez et al. 2011 Adv. Sci. Res. 6, 141 (text extracted, grep and results/conclusion read).
- MADIS surface QC page (madis.ncep.noaa.gov/madis_sfc_qc.shtml) and Synoptic Data QC flag list (docs.synopticdata.com/services/qc-flag-types), summarising fetch.

NOT OPENED / SNIPPET-ONLY / FAILED:
- Radar-nowcasting personalized federated learning (ResearchGate 403): SNIPPET-ONLY.
- "Federated Learning for Environmental Monitoring: A Review", Applied Sciences 15(23), 12685 (MDPI 403): title and URL from search results only; contents UNVERIFIED.
- FedSW-TSAD (PMC12251651), industrial CPS reliability-weighted aggregation paper, Springer water-contamination federated chapter: SNIPPET-ONLY.
- Weather Union Terms and Conditions PDF: the terms page only links to a PDF, which was not opened. Its redistribution, caching and commercial clauses are UNVERIFIED.
- IMD data-supply tariff or the Data Supply Portal (dsp.imdpune.gov.in) page: 404 on the URL tried; fee schedule UNVERIFIED.
- WMO-No. 305, WMO-No. 8 and WMO-No. 100 (the owning documents for consistency checks): not opened. The 2004 CIMO draft is a secondary pointer to them.
- Durre PRCP streak threshold row: still not independently confirmed here (see the existing note).
- The text of WMO Resolution 1 (Cg-Ext 2021) itself: only the WMO summary page was read.
- State rain-gauge networks in India, universities, other commercial networks: not researched (UNVERIFIED, see Part 2).

## Part 1. Prior work on federated learning for weather/hydrometeorological QC and for sensor or time-series anomaly detection

Summary (DERIVED): prior work exists for each ingredient but I found no primary source that federates rain-gauge or weather-station QC on real labelled faults with custodians as clients. The negative is limited to the searches run (four web searches and the sources above), so it is "not found", not "does not exist".

1.1 FedLGAN, anomaly detection and repair of hydrological telemetry (PeerJ Computer Science, 2023; https://peerj.com/articles/cs-1664, read at https://pmc.ncbi.nlm.nih.gov/articles/PMC10703019/).
- Data: real telemetry from four devices in Hangzhou, Jinhua, Shaoxing and Lishui (Zhejiang, China); water level, rainfall and voltage at 5-minute intervals, using attributes common to all four. The dates in the paper are inconsistent (September to December 2022 in one place, January 1 to March 31, 2022 in another); I did not resolve this.
- Labels: real anomalies were rare, so synthetic noise was injected into normal data to make abnormal test samples; implausible readings were put in a separate test set. Last 15 days are the test set.
- Clients: FedAvg across "k edge devices"; the four stations appear to be the clients but the paper does not map them explicitly.
- Model: GAN with LSTM generator and attention bidirectional-LSTM discriminator; discriminator detects, generator repairs. Baselines LSTM, GRU (detection), VAE, GAN (repair).
- Results: detection precision 0.765, recall 0.812, F1 0.788; LSTM F1 0.739, GRU 0.717. LSTM had far lower MAPE (13.5% vs 74.1%). Training 5,334.7 s vs 3,868.1 s for the GAN-only variant.
- Stated limits: non-IID across clients not tested; no check on other provinces; federated training less efficient than centralized and needs heavy communication. The privacy benefit is argued, not measured. The search snippet's "first use of federated learning" claim for this setting is the authors' own claim, not verified by me.
- Relevance: closest found match (federated, hydrometeorological telemetry, rainfall among the variables). It is a small injected-noise study, not a rain-gauge QC benchmark.

1.2 FedLSTM, sensor fault detection in wireless sensor networks (Khan, Saeed, Koo, Electronics 13(24), 4907, 2024). Already in `prior-work-precipitation-qc-positioning.md` section 3: temperature data with six injected synthetic faults (bias, drift, spike, erratic, stuck, data-loss); federated LSTM; no numbers retrieved there; not reopened here (MDPI 403).

1.3 Federated data-quality profiling and FedDQ: in the same existing note, section 4 (clinical data with injected errors; FedDQ only a blog, UNVERIFIED). Not repeated.

1.4 "Federated Weather Modeling on Sensor Data" (Chen and Long, submitted 2026-05-01, arXiv:2605.00322; accepted for the Encyclopedia of GIS, Springer 2026). It is an encyclopedia-style overview with no experiments. It treats each weather station as a client (satellites and IoT devices also as sources), lists forecasting and anomaly detection as target tasks, and cites a prior work by Chen et al. (adapting pretrained LLMs to federated weather sequences) as reporting good results on "long-term forecasting, data imputation, and detecting anomalies", with no dataset, setup or metrics in the entry. It does not discuss data custodians or sharing agreements; its privacy argument is that sensitive-area stations make central transmission hard. Source: arXiv abs and HTML pages. Usable only as evidence that the framing "station as federated client" exists in the literature; no results can be taken from it.

1.5 Personalized federated learning for radar precipitation nowcasting on heterogeneous areas (adapFL; Earth Science Informatics 2024 per the existing note). SNIPPET-ONLY: the search snippet says the motivation is that radar information "is not open, or belongs to different institutions". That is a custodian-style motivation, for forecasting, not QC. Primary page not opened.

1.6 Other items that appeared in searches and were not opened: FedSW-TSAD (federated time-series anomaly detection with reconstruction plus prediction scoring, heterogeneous clients), an industrial cyber-physical-systems paper weighting client updates by sensor reliability, a 2025 Applied Sciences review of federated learning for environmental monitoring. SNIPPET-ONLY or title-only; cite only after opening them. `qc-novelty-research.md` row "Personalized federated AD / weather" (PFAE, FedPoD) is also snippet-only.

1.7 Centralized prior work that already does multi-source rain-gauge QC (SNIPPET-ONLY for the two search hits: Remote Sensing 17(24), 3976; Journal of Hydroinformatics 26(5), 1042). The existing positioning note has the confirmed Osrodka et al. 2025 (Atmos. Meas. Tech. 18, 3229). These show what a pooled model does; a federated version would have to be compared with it.

1.8 Generic federated-learning background (aggregation, poisoning, single-client case) is in `federated-update-protocol.md`; not repeated.

What is NOT found in the sources opened: federated QC of rain-gauge data with real (non-injected) fault labels; a federated study whose clients are real data custodians holding real gauge networks; a federated study that reports a clean-period false-alarm rate per 1,000 items. (UNVERIFIED as absent beyond the searches run.)

## Part 2. Custodians that hold gauge or weather data they cannot or will not share raw, and what the restrictions say

Caveat (DERIVED): a restriction on redistribution is a reason to move computation to the data only if the custodian also allows the model or its updates to leave. None of the texts below says anything about model weights trained on the data; that is UNVERIFIED for every custodian and would need to be asked.

2.1 WMO Resolution 40 (Cg-XII, 1995), text from the WMO-No. 827 PDF (text extracted).
- "Members shall provide on a free and unrestricted basis essential data and products" (ADOPTS (1)); footnote: "Free and unrestricted" means non-discriminatory and without charge; "without charge" means at no more than the cost of reproduction and delivery.
- "Members should also provide the additional data and products ... it is understood that WMO Members may be justified in placing conditions on their re-export for commercial purposes outside of the receiving country or group of countries forming a single economic group, for reasons such as national laws or costs of production" (ADOPTS (2)).
- Members "should provide to the research and education communities, for their non-commercial activities, free and unrestricted access to all data and products exchanged under the auspices of WMO", with their commercial activities subject to the same conditions (ADOPTS (3)).
- Members are urged to make known, through the WMO Secretariat, the additional data and products on which they have placed re-export conditions.
- Annex 1 (essential data, exchanged "without charge and with no conditions on use") covers, in general, "the data from the RBSNs and as many data as possible", for example six-hourly surface synoptic data from RBSNs (community.wmo.int Annex 1 page).
- Reading (DERIVED): Resolution 40 itself restricts only re-export for commercial purposes for the "additional" tier; it does not say "do not share raw data". The "cannot be redistributed" wording in practice comes from custodians applying it (2.2).

2.2 NOAA NCEI Integrated Surface Database. The ISD readme says: "The non-U.S. data in ISD are subject to WMO Resolution 40 restrictions, and cannot be redistributed to other users or customers." (readme, "IMPORTANT NOTE"; summarising fetch of https://www.ncei.noaa.gov/pub/data/noaa/readme.txt). The NCEI ISD product page itself said nothing about access conditions. This is the repo's own rule (`AGENTS.md` section 6).

2.3 WMO Unified Data Policy (Resolution 1, Cg-Ext 2021). The WMO page says Core data (standard practice, "shall be exchanged") and Recommended data (best practice, "should be exchanged") replace the Essential and Additional terms of Resolution 40, and that the policy "builds on existing WMO data policies", including Resolution 40; it does not say Resolution 40 is formally withdrawn. The page gives no conditions for Recommended data; details are in WMO Technical Regulations (UNVERIFIED, not opened). Search snippets say Resolution 1 covers all Earth-system data, not only weather, and that conditions may be placed on Recommended data (SNIPPET-ONLY). Consequence: which of a country's stations are Core is set by the Technical Regulations, so whether a given gauge can be restricted is UNVERIFIED here.

2.4 India Meteorological Department (IMD).
- Rain-gauge and AWS data are supplied through a paid Data Supply Portal. The Patna data-supply procedure document (PDF, text extracted) lists, among its terms: "Data is provided strictly for the declared purpose and must not be shared with third parties", requests on official letterhead, "IMD reserves the right to accept or reject any request in public interest", payment after a charge intimation letter (with GST). This is one regional centre's document; other centres' procedure PDFs exist and were not compared.
- Down To Earth reports that IMD restricted its AWS/ARG web portal to designated users around the second week of May 2025. Quotes attributed there to IMD's RTI replies: access "has been restricted to designated users" citing "the policy of India Meteorological Department and policy guidelines issued by the competent authority"; a later reply (early October 2025) cited "Data Sensitivity" with "Unrestricted access could lead to misuse or misinterpretation, especially in commercial contexts"; and "IMD does not permit the use of AWS data for any commercial purposes." These are a newspaper's quotations of RTI replies; I did not see the replies. Source: https://www.downtoearth.org.in/climate-change/imd-locking-up-its-awsarg-data-portal-hampers-public-weather-alerts-experts (read 2026-11-19).
- Search-snippet only: a Central Information Commission direction for IMD to review its paid-data policy; outcome not found.
- Fee schedule: not found (UNVERIFIED).
- Relevance: IMD's RF25 gridded product used by `ml-service/qc` is a different, published product; the station-level AWS and ARG data are the restricted ones. The existing note `operational-rainfall-qc-primary-sources.md` says RF25 carries no QC flags.

2.5 Weather Union (Zomato). The home page calls it "India's first crowd-supported weather infrastructure", "A Zomato Giveback", 750+ automated stations in 60 cities (the site's own figures, not verified), "Get free API access", opened "to everyone for public good", and says an enterprise customer with high server costs may be contacted to pay. Redistribution, storage and rate-limit clauses are in a Terms and Conditions PDF not opened: UNVERIFIED. Weather Union is a company that hosts its own feed; it has no stated reason to resist sharing in the sense of Resolution 40, so it is not an example of a custodian who "cannot share" (DERIVED).

2.6 Not researched, UNVERIFIED: Indian state rain-gauge networks, university networks, CWC/India-WRIS, and non-US national services other than as covered by ISD's note. I make no claim about their terms. Estevez et al. 2011 shows that a regional agrometeorological network (Andalusia, 85 stations tested) is a plausible custodian type, but it says nothing about its sharing terms.

2.7 Reading for the design (DERIVED): the sharing restriction text found is about redistribution of raw data (ISD, IMD Patna terms) and commercial use (IMD per Down To Earth). That supports "raw station data cannot be pooled", the premise of simulating custodians as clients. It does not show that any custodian would accept model updates leaving their premises.

## Part 3. Rain, humidity, temperature and wind consistency checks in operational QC

All thresholds below are quoted from the document named; none is validated by this project. Operational QC is rule-based; these rules are the inputs a gauge-context validator would learn from or be compared with.

3.1 WMO CIMO draft guidelines for AWS QC (2004, ET-ST&MT-1 Doc 6.1(2); text extracted). Draft proposal, so not a binding standard. Internal-consistency conditions that "shall be true" (for periods of at most 10 minutes where marked):
- dew point temperature <= air temperature; wind speed = 0 together with wind direction = 0, and wind speed not 0 with direction 0 (the symbols were garbled in extraction; read as "calm implies direction 0 and the reverse", UNVERIFIED wording); wind gust >= wind speed.
- both elements suspect if total cloud cover = 0 and precipitation amount > 0 (footnote: "or greater than the minimum resolution of the rain gauge, to take into account the deposition of water by dew"); same for precipitation duration > 0 (snow pellets can occur with cloud 0); precipitation amount > 0 with duration = 0.
- Section on BUFR reports: air temperature > +5 C with certain precipitation types (codes 6 to 12), air temperature < -2 C with precipitation type 2, > +3 C with type 3 and < -10 C with type 3; dew point depression > 5 C with some obscuration codes; present weather versus precipitation duration; visibility versus present weather thresholds (1 000 m, 10 000 m).
- Failures are flagged "inconsistent" (and doubtful or erroneous per check). The same document says WMO-No. 305 (Guide on GDPS) carries limits and further consistency checks for SYNOP; not opened.
- Previously noted in the existing note: the draft excludes spatial QC; its step and persistence limits could not be recovered.

3.2 HadISD (Dunn et al. 2012, Climate of the Past 8, 1649; arXiv:1210.7191; text extracted). Covers temperature, dewpoint, sea-level pressure, wind and cloud; not precipitation.
- Test 11, temperature and dewpoint cross-check (following Willett et al. 2008): supersaturation (dewpoint > temperature; only the dewpoint is flagged), wet-bulb reservoir drying (dewpoint depression 0 for a streak over 24 h with at least four observations; not flagged "unless there are simultaneous precipitation or fog observations for more than one-third of the continuous streak", with cloud base < 1000 ft or present weather used for fog), and cutoffs of dewpoint at temperature extremes (10 C bins; flagged when at least 50 per cent of values in a bin lack a simultaneous dewpoint).
- Wind used as context: sea-level-pressure outliers are kept when simultaneous wind speed exceeds the monthly median by 4.5 MADs ("storminess"), and storm detection also needs a coincident SLP minimum, to avoid removing true extremes. Calm wind (below 0.5 m/s, or 1 m/s for coarse resolution) is excluded from the streak test.
- Test 12, cloud logical checks, test 14 neighbour checks (including mention of precipitation or storms as a reason for neighbour disagreement in the text; wording not fully read).
- DERIVED: this is a published example of a QC check that uses other variables as context to avoid flagging a genuine extreme, which is the same design intent as `AGENTS.md` section 5, for non-rain variables.

3.3 MADIS surface QC (NOAA, madis.ncep.noaa.gov; summarising fetch). The MADIS page lists internal consistency checks of sea level pressure vs station pressure, 3 h pressure change vs station pressure, air temperature vs dewpoint temperature (and sea surface temperature vs air temperature). It states that a dewpoint observation must not exceed the temperature at the same station (via search result text; the fetched page gave only the check names). Precipitation has Level 1 validity marks only on that page. A spatial ("buddy") check by optimal interpolation exists at Level 3 (search snippet text); how precipitation enters it was not found.

3.4 Synoptic Data QC flag list (docs.synopticdata.com/services/qc-flag-types; summarising fetch; names only, no thresholds). It carries MADIS-derived checks relating rain to other variables: "MADIS Present Weather vs. Accumulated Precipitation", "Past Weather vs. Accumulated Precipitation", "Accumulated Precip (during period) vs. Accumulated Precip (24h)", versus snow depth and snowfall, "Present Weather vs. Air temperature", "Present Weather vs. Air temperature; Wind Speed; and Dewpoint", "Wind Speed vs. Present Weather", "Total Cloud Cover vs. Present Weather", visibility vs present weather, wind direction vs speed, speed vs gust, air temperature vs max/min and vs dewpoint. The page is a commercial aggregator's list of MADIS checks, so it is a secondary description of the MADIS system; thresholds are UNVERIFIED.

3.5 GHCN-Daily (Durre et al. 2010; text extracted, grep only). Daily precipitation cross-variable rules: a "too warm for snow" internal check for snow, a lower multiple of the 95th percentile for the climatological outlier when mean temperature is below freezing (reported in the existing note as 5 times instead of 9 times; the passage on precipitation outliers under cooler conditions was seen), and megaconsistency checks for TMAX, TMIN, TOBS. These use temperature as context for precipitation and snow, not humidity or wind. Spatial corroboration within 75 km with 3 to 7 neighbours is in the existing note. The paper does not use humidity or wind for precipitation checks (not found in the passages searched; UNVERIFIED as absent).

3.6 Estevez, Gavilan, Giraldez 2011 (Adv. Sci. Res. 6, 141; text extracted) validate daily temperature, relative humidity and precipitation with three statistical tests (threshold, step change, persistence) per variable, with a dynamic factor f to fix a Type I error rate across the region. The abstract of the related J. Hydrol. 402, 144 paper (snippet-only) lists record structure, range, time and internal consistency, persistence and spatial consistency. In the ASR paper I found no cross-variable consistency rule between rain, humidity, temperature and wind. The authors state automated tests should be accompanied by field visits, sensor calibration and manual inspection.

3.7 Summary of what exists operationally (DERIVED from 3.1 to 3.6, thresholds as quoted above):
- Rain vs cloud or present weather: precipitation with zero cloud cover is suspect; precipitation with no present-weather precipitation, or the reverse, is suspect (WMO draft, Synoptic/MADIS names).
- Rain vs temperature: precipitation type against temperature bands (WMO draft); snow with warm temperatures (GHCN-Daily W flag; WMO draft); lower outlier multiplier when freezing (GHCN-Daily).
- Humidity: dewpoint above temperature is an error (WMO draft, HadISD, MADIS); saturated humidity streaks are not flagged when rain or fog is reported (HadISD); no source opened gives a rule such as "rain with low relative humidity".
- Wind: direction vs speed, gust vs mean (WMO draft, MADIS); wind used to protect storm extremes from pressure flags (HadISD). No opened source cross-checks rain against wind.
- No source opened specifies a learned (trained) cross-variable consistency model for gauge QC; all opened operational rules are fixed logic.

3.8 Use of the gauge's own rain history: the temporal checks in the sources opened (persistence, step change, streaks, frequent values, spike) use the series' own history as input; this supports the map's point that the rain history is legitimate for validation. Source examples: Estevez et al. 2011 persistence and step tests; Durre et al. 2010 streak and frequent-value tests; HadISD tests 8 and 10. (Whether it is legitimate as an input to rain prediction is the map's own argument, not tested here.)

## Open uncertainties

- Whether any custodian would allow trained weights or updates to leave (Part 2 caveat).
- Weather Union terms, IMD tariff and other IMD centres' procedures, state and university networks (Part 2).
- Whether Resolution 40 is formally withdrawn after the 2021 policy, and which Indian stations are Core data (Part 2.3).
- WMO-No. 305, 8 and 100, the owning documents of the consistency checks, not opened; the 2004 draft is secondary and symbols were garbled in extraction (Part 3.1).
- FedLGAN date inconsistency; FedLSTM numbers unread; Chen et al. LLM federated-weather paper not opened; radar nowcasting and the 2025 review snippet-only (Part 1).
- The "no prior work" statements are limited to the searches run.

## Source list

- Chen, S., Long, G. Federated Weather Modeling on Sensor Data. arXiv:2605.00322 (2026). https://arxiv.org/abs/2605.00322
- FedLGAN: anomaly detection and repair of hydrological telemetry data based on federated learning. PeerJ Comput. Sci. 2023. https://peerj.com/articles/cs-1664 ; https://pmc.ncbi.nlm.nih.gov/articles/PMC10703019/
- Khan, Saeed, Koo. FedLSTM. Electronics 13(24), 4907 (2024). See existing positioning note for the record URL.
- WMO Resolution 40 (Cg-XII), WMO-No. 827. https://community.wmo.int/resolution-40 ; Annex 1 https://community.wmo.int/node/36328 ; PDF https://weather.gov/media/im/wmo_827_enCG-XII-Res40.pdf
- WMO Unified Data Policy Resolution (Res. 1). https://wmo.int/wmo-unified-data-policy-resolution-res1
- NOAA NCEI ISD readme. https://www.ncei.noaa.gov/pub/data/noaa/readme.txt
- Down To Earth, IMD locking up its AWS/ARG data portal. https://www.downtoearth.org.in/climate-change/imd-locking-up-its-awsarg-data-portal-hampers-public-weather-alerts-experts
- IMD Patna, Data Supply Procedure. https://mausam.imd.gov.in/patna/mcdata/Data_Supply_Procedure(ENGLISH).pdf
- Weather Union. https://www.weatherunion.com/ ; terms page https://www.weatherunion.com/tnc/
- Durre et al. 2010, J. Appl. Meteor. Climatol. 49, 1615. https://ncei.noaa.gov/pub/data/ghcn/daily/papers/durre-menne-etal2010.pdf
- Dunn et al. 2012, HadISD, Clim. Past 8, 1649. https://arxiv.org/pdf/1210.7191
- WMO CIMO ET-ST&MT-1 Doc 6.1(2), 2004. https://old.wmo.int/extranet/pages/prog/www/IMOP/meetings/Surface/ET-STMT1_Geneva2004/Doc6.1(2).pdf
- Estevez, Gavilan, Giraldez 2011 (J. Hydrol. 402, 144; abstract only) and Estevez et al. 2011, Adv. Sci. Res. 6, 141. https://asr.copernicus.org/articles/6/141/2011/asr-6-141-2011.pdf
- NOAA MADIS surface QC. https://madis.ncep.noaa.gov/madis_sfc_qc.shtml ; Synoptic Data QC flags https://docs.synopticdata.com/services/qc-flag-types
