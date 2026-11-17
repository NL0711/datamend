# Operational QC of daily rainfall: primary-source findings

> **STATUS: UNVERIFIED, SUBAGENT-EXTRACTED.** Written by a research subagent from web fetches; not reviewed line-by-line.
> Independently re-checked against the local copy of Pai et al. (2014) (`ref_paper_MAUSAM.pdf`): the 6995 (abstract/intro) vs 6955 (Fig. 1, Sect. 2) gauge-count inconsistency,
> 1450-3900 stations/day (about 3500 on average), Shepard IDW with 1-4 nearest stations within 1.5 degrees, and the one-sentence QC description (no thresholds, no per-value flags) are all confirmed.
> NOT re-checked: every GHCN-Daily (Durre et al. 2010) threshold, including the 1828.8 mm range limit, and the streak threshold of 20 (already flagged UNVERIFIED). Verify against the paper before relying on them.

Scope: daily precipitation QC rules, how IMD's 0.25-degree gridded rainfall was built, and how QC was evaluated. Primary documents only. Items not verified at the owning document are marked UNVERIFIED. Retrieved 2026-11-16. Text was extracted from the PDFs themselves, not from summaries.

Sources:
- [DURRE10] Durre, Menne, Gleason, Houston, Vose 2010, J. Appl. Meteor. Climatol. 49, 1615-1633: https://ncei.noaa.gov/pub/data/ghcn/daily/papers/durre-menne-etal2010.pdf (NOAA NCEI-hosted copy of the paper)
- [GHCND-README] GHCN-Daily readme: https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt
- [PAI14] Pai et al. 2014, MAUSAM 65(1), 1-18: https://imdpune.gov.in:443/cmpg/Griddata/ref_paper_MAUSAM.pdf (IMD-hosted)
- [WMO-AWS] WMO CIMO ET ST&MT-1 Doc.6.1(2), "Guidelines on Quality Control Procedures for Data from Automatic Weather Stations" (2004 draft proposal): https://old.wmo.int/extranet/pages/prog/www/IMOP/meetings/Surface/ET-STMT1_Geneva2004/Doc6.1(2).pdf
- [HADISD] Dunn et al., HadISD (author preprint, arXiv): https://arxiv.org/pdf/1210.7191

## 1. Rule-based checks for daily rainfall

The only primary source I could read in full that gives daily-precipitation thresholds is the GHCN-Daily system [DURRE10]. It has 19 tests in a fixed sequence. Each test ignores values already flagged by earlier tests (Sect. 2c). Tables 1-5 give the PRCP conditions below.

| Check | PRCP rule as written | Citation |
|---|---|---|
| Range / world record | Flag PRCP < 0 or > 1828.8 mm. Limits come from the WMO World Weather/Climate Extremes Archive. | [DURRE10] Sect. 3b, Table 1 (p. 1619) |
| Naught / trace | Flag PRCP > 0 if the measurement flag says trace ("T"). The temperature "naught" check targets zeros used as missing codes. | [DURRE10] Sect. 3a, Table 1 |
| Duplicate | Flag all PRCP values of two years that are identical (at least 3 nonzero values). The same applies to two months in one year, and to the same calendar month in different years (at least 3 nonzero values in the month). | [DURRE10] Sect. 3a, Table 1 |
| Streak (persistence) | Flag 20 or more consecutive identical nonzero PRCP values. Missing values and zeros are skipped. The PRCP row of the table was partly garbled in extraction, so the number 20 is UNVERIFIED; confirm it against PDF Table 1. (SNOW 10 and SNWD 90 were legible.) | [DURRE10] Sect. 3, Table 1 |
| Frequent value | Over 10 consecutive nonzero values, flag if at least 9 are identical and >= the 30th percentile, or at least 8 and >= the 50th, or at least 7 and >= the 70th, or at least 5 and >= the 90th. | [DURRE10] Table 1 |
| Gap | Flag nonzero PRCP values above a gap of >= 300 mm in the station/calendar-month distribution (one-tailed). | [DURRE10] Sect. 4a, Table 2 |
| Climatological outlier | Flag PRCP >= 9 times the 95th percentile of nonzero values for that calendar day (29-day window, at least 20 nonzero values required). A variant uses 5 times when the mean temperature is below 0 C. The z-score check (abs z >= 6) is used for temperature only. The paper says the z-score approach over-flags for the skewed PRCP distribution. | [DURRE10] Sect. 4, Table 2 |
| Internal/temporal | Only snow-related PRCP checks (SNOW with zero PRCP, SNOW/PRCP ratio) and a 3-day window to allow for observation-time shifts. There is no PRCP-only spike test. | [DURRE10] Sect. 5b, Table 3 |
| Spatial corroboration | Neighbours must be within 75 km, with at least 3 and at most 7 used, compared at lags -1, 0 and +1 day. Flag when the target falls outside the neighbour range by more than a threshold that falls as the percent-rank difference rises. Example: a threshold of 120.3 mm at a percent-rank difference of 26. | [DURRE10] Sect. 6b, Fig. 7, Appendix C |
| Zero vs missing | Streak and frequent-value checks skip zeros and missing values. The gap and outlier checks use nonzero values only. Missing is stored as -9999. | [DURRE10] Table 1; [GHCND-README] Sect. III |
| Flag codes | D duplicate, G gap, I internal consistency, K streak/frequent-value, L multiday length, M megaconsistency, N naught, O outlier, R lagged range, S spatial, T temporal, W too warm for snow, X bounds, Z Datzilla. Values are flagged, not deleted. | [GHCND-README] Sect. III (QFLAG) |

WMO material:
- [WMO-AWS] is a 2004 draft for sub-daily AWS data from a single station. It names a plausible-value (gross error) check, a rate-of-change (step) check, and a persistence check (one-minute values over 60/120/240 min). Failures are flagged "doubtful/suspect" or "erroneous". Its internal-consistency checks include precipitation against present weather and cloud. It excludes spatial QC (Chapter I, Chapter II).
- The step and persistence limit tables were not recoverable from the extracted text. All numeric limits for precipitation in this draft are UNVERIFIED. It proposes BUFR flag table 0 33 019 with Inconsistent, Doubtful, Erroneous, Not checked and Changed (Chapter I).
- WMO-No. 100 (Guide to Climatological Practices), WMO-No. 8, WMO-No. 488, WMO-No. 305 and WMO-No. 1269 could not be fetched (the WMO library returned an HTML shell). Everything those documents say about daily precipitation tolerance, consistency or spatial checks, and their thresholds, is UNVERIFIED.
- [WMO-AWS] itself says that basic steps for AWS QC are in WMO-No. 8 Part II Ch. 1, and details for data exchanged internationally are in WMO-No. 305 Ch. 6 (Introduction, Notes). Those are the owning documents to read next.

## 2. How RF25 (IMD "IMD4") was built [PAI14]

- Product: daily 0.25 x 0.25 degree grid over the Indian mainland, 1901-2010 (Abstract). IMD's data page now describes 1901-2024 (UNVERIFIED; I did not fetch that page).
- Stations: 6955 rain gauges in Sect. 2 and the Fig. 1 caption, but 6995 in the Conclusions. This is an internal inconsistency in the paper. Of the 6955, 547 are IMD observatories, 494 hydro-meteorological observatories and 74 agromet observatories. The rest are State Government rainfall stations (Sect. 2).
- Daily station counts: about 3500 per day on average, ranging between 1450 and 3900 (Conclusions). Sect. 2 and Fig. 2 describe about 1450 in 1901, about 3100 per day from 1951, and a later drop to about 1900 per day. I read this in a two-column layout and the exact wording is UNVERIFIED.
- QC (Sect. 3.1): the paper says station location was verified and typing/coding errors were checked. It then names "standard quality control tests such as tests for typing and coding errors, missing data, duplicate station check, extreme value check etc." The paper gives no thresholds, no test list beyond this one sentence, and no flag scheme. No per-value QC flags are described.
- Interpolation (Sect. 3.1): Shepard (1968) inverse distance weighting. For each grid point it uses a minimum of 1 and a maximum of 4 nearest stations within 1.5 degrees. Directional effects and barriers are included, as in Shepard (1968). Details are deferred to Rajeevan et al. 2006 (not read).
- Comparison: IMD4 was compared with IMD1, IMD2, IMD3, IMD_OP and APHRODITE. Examples: all-India annual means differed by roughly 1.5% from IMD3, the monsoon-season bias against APHRODITE was +0.84 mm/day, and the west-coast high-rainfall zone is narrowest in IMD4 (Sect. 4-5, Table 4).
- Limitations stated in the paper: the network is uneven in space and time, and station numbers vary from year to year (Sect. 1-2). The grid is a smoothed estimate, so grid values are not station values. I found no statement that quantifies interpolation error or flags interpolated values as low-confidence (UNVERIFIED as absent; this rests on my reading of the extracted text).
- Consequence for a QC project: RF25 contains no QC flags and no uncertainty field. Any anomaly flagging on RF25 must be done downstream, and station-level QC outcomes before gridding are not published.

## 3. How QC performance has been evaluated

- GHCN-Daily [DURRE10]. Evaluation uses real data, not injected errors.
  - Each test is run provisionally on the whole dataset. Random samples of flagged values are inspected manually for several candidate thresholds (Sect. 2b, p. 1628).
  - A value judged truly invalid counts as an error. A plausible one is a false positive. A questionable one counts as half a false positive.
  - The sample false-positive rate is false positives divided by values examined. The chosen threshold is the one with the highest detection that stays within a 20% per-check false-positive cap (Sect. 2b).
  - A typical sample is 10 values per threshold category, and 30-100 values are examined per check (Sect. 2b).
  - The final evaluation examined 50 randomly chosen values per element (half flagged, half unflagged). The paper says this sample is too small to be statistically representative (Sect. 8, p. 1626-1627).
  - Headline result: 0.24% of more than 1.5 billion values flagged, with an estimated false-positive rate of 1-2% (Abstract).
  - Methodology reference: Durre, Menne, Vose 2008, J. Appl. Meteor. Climatol. 47, 1785-1791 ("DMV08"). I did not read it.
- HadISD [HADISD]. It covers temperature, dewpoint, sea-level pressure, wind and cloud, not precipitation (Abstract). It follows a GHCN-Daily-like approach (Sect. 3). Validation is by case studies of known extreme events, such as Hurricane Katrina, to check that extremes are retained while bad data are removed (Sect. 5). Per-test removal rates by station are tabulated (Table 6). Injected errors were not found in the passages I checked (UNVERIFIED as absent).
- CHIRPS (Funk et al. 2015, Sci. Data): the Nature and PMC pages could not be fetched (login redirect and CAPTCHA). Its QC of station inputs and its limitations are UNVERIFIED here.
- IMD station QC: no IMD document I could read reports a QC performance evaluation (injected or real errors, or metrics). That includes [PAI14] (UNVERIFIED as absent beyond the paper).

## 4. Gaps, to be fetched with a normal browser

1. WMO-No. 100 (2018/2023) QC section, plus WMO-No. 8 Vol. I and WMO-No. 305 Ch. 6 and WMO-No. 1269, for daily precipitation tolerance, consistency and spatial thresholds.
2. Rajeevan et al. 2006 (Current Science), for the IMD interpolation details and any QC described there.
3. The CHIRPS paper, for station-input QC.
4. The PRCP row of [DURRE10] Table 1 (streak), the neighbour thresholds in Appendix C, and the Table 6 per-check false-positive rates, directly from the PDF.
