# India QC label and extreme-event sources for the RF25 anomaly detector

> **STATUS: UNVERIFIED, SUBAGENT-EXTRACTED.** Written by a Haiku research subagent from web fetches; not reviewed line by line. Open and check every source before citing it.

Checked 2026-11-16 with WebFetch/WebSearch. Items marked **UNVERIFIED** were not opened at the primary source (fetch failed, file too large, or only a search snippet was seen). No figures below are from memory.

## 1. NOAA GHCN-Daily (tier 2 candidate)

- **Access:** HTTPS at https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/ and metadata at https://www.ncei.noaa.gov/pub/data/ghcn/daily/ ([product page](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily)).
- **Scale:** "more than 100,000 stations in 180 countries and territories" (same product page).
- **India:** country code "IN India" is in [ghcnd-countries.txt](https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-countries.txt). **UNVERIFIED:** the India station count and year coverage. [ghcnd-stations.txt](https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt) exceeds the fetch size limit, so it must be counted locally with `grep "^IN"`.
- **QFLAG meanings (QFLAG1 etc.):** per the [readme](https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt), blank = passed all checks; D duplicate; G gap; I internal consistency; K streak/frequent value; L multiday length; M megaconsistency; N naught; O climatological outlier; R lagged range; S spatial consistency; T temporal consistency; W too warm for snow; X bounds; Z Datzilla investigation. The readme text says "fourteen possible values" but lists fifteen symbols including blank, so check the file itself.
- **Flag quality:** the product page says automated QA flags about 0.3% of nearly 2 billion values and estimates 98-99% of flagged values are true errors.
- **Terms:** the product page gives no licence or data-use terms. The readme asks for citation of Menne et al. (2012), DOI 10.1175/JTECH-D-11-00103.1, and the dataset DOI 10.7289/V5D21VHZ. Licence wording: UNVERIFIED.
- **Grid mapping:** assign each station to the RF25 cell containing its lat/lon, then take the flagged PRCP for that station-day. Coverage over India per cell may be sparse.

## 2. GSOD (Global Summary of the Day)

- **Readme:** [GSOD readme](https://www.ncei.noaa.gov/data/global-summary-of-the-day/doc/readme.txt). PRCP is in inches. The PRCP_ATTRIBUTES letters A-I describe how many sub-daily reports were summed. H and I mark incomplete data. They are **not** outlier QC flags.
- **Coverage:** "over 9000 stations" worldwide; data from 1929, most complete from 1973. India count: UNVERIFIED.
- **Terms:** "free and unrestricted use in research, education, and other non-commercial activities." Non-US data may not be re-exported for commercial services.
- **Mapping:** could mask station-days that are incomplete, not label anomalies.

## 3. IMD station data and gridded product

- **IMD Data Service Portal:** https://dsp.imdpune.gov.in/ ([portal](https://dsp.imdpune.gov.in/)). Open items include Climate Tables, Historical Extremes and Gridded Climatological Data. Observation data requires account enrolment, and fees are set through a cost-estimate page. Contact: data.service@imd.gov.in. Commercial reproduction is not permitted without permission.
- **Station daily rainfall with QC flags:** not stated on the portal. **UNVERIFIED** whether any flags exist. Requesting would be needed to confirm.
- **RF25 gridded product:** [IMD gridded page](https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html) gives 0.25 degree, 135 x 129 grid, 1901-2024, mm, and asks users to cite Pai et al. (2014). The page does not state station count, generation method or QC, and I found no per-value flags.
- **Station count in Pai et al. (2014):** the figure of 6995 gauges came from a search snippet. The local copy of [the MAUSAM paper](https://imdpune.gov.in:443/cmpg/Griddata/ref_paper_MAUSAM.pdf) could not be rendered here, so this is **UNVERIFIED**.

## 4. Other gauge datasets

- **APHRODITE:** [products page](https://www.chikyu.ac.jp/precip/english/products.html). Monsoon Asia daily at 0.5 and 0.25 degree, 1951-2007 (Yatagai et al. 2012). The domain covers India. No station-level data, QC flags, licence or station count is stated. Products are downloaded through DIAS with registration. Period ends in 2007, so it cannot label recent events.
- **GPCC:** [DWD download gate](https://opendata.dwd.de/climate_environment/GPCC/html/download_gate.html) and [Full Data Daily v2022](https://opendata.dwd.de/climate_environment/GPCC/html/fulldata-daily_v2022_doi_download.html). QC is described generically. No India-specific station flags confirmed. Terms of Use page: **UNVERIFIED**.

## 5. Extreme-rainfall events over India

No reviewed, ready-made event catalogue for India was found. The events below are candidates, with values **UNVERIFIED** at the primary source.

- **Mumbai, 26 July 2005:** search summary of Kumar et al. (2008): 944 mm at IMD Santacruz for the 24 h to 0300 UTC 27 July, and 73 mm at Colaba. Source: [Kumar et al. PDF](https://www2.mmm.ucar.edu/people/rotunno/files/kumar.pdf). The PDF returned a certificate error. **UNVERIFIED.**
- **Kedarnath / Uttarakhand, 16-17 June 2013:** reported totals conflict (about 325 mm at one station in 24 h, from a secondary citation of Dobhal et al. 2013; "more than 340 mm" on 17 June in an NCMRWF report). Sources: [NCMRWF report](https://websevak.ncmrwf.gov.in/KEDARNATH_REPORT_FINAL.pdf) and [Singh et al. 2015, NHESS](https://nhess.copernicus.org/articles/15/1597/2015/nhess-15-1597-2015.pdf). Neither was opened. **UNVERIFIED.** Use only the date window, not one total.
- **Chennai, Nov-Dec 2015:** van Oldenborgh et al. (2016, BAMS) is the cited analysis, and a "1049 mm" figure appeared in a search snippet with unclear scope. Station 24 h totals (Tambaram 49 cm, Chembarambakkam 47 cm, 2 Dec morning cutoff) come from a non-peer-reviewed [IIT rapid assessment](https://www.cag.org.in/sites/default/files/database/chennai-floods-rapid-assessment-report_1.pdf). **UNVERIFIED.**
- **Kerala, Aug 2018:** secondary press figures cite IMD totals of 2346.6 mm (1 June-19 Aug) against a normal of 1649.5 mm, and Idukki at 3555 mm against 1852 mm. The official Post-Disaster Needs Assessment was not located. **UNVERIFIED.** Check IMD press releases.
- **Peer-reviewed threshold reference:** Rajeevan, Bhate and Jaswal (2008), Geophysical Research Letters, DOI 10.1029/2008GL035143, which defines very heavy rain as 150 mm/day or more. Seen in a search snippet; not opened. **UNVERIFIED.** Lin et al. (2018, GRL) warns that changing station coverage biases IMD extreme-rainfall trends (snippet only).

## Summary

- GHCN-Daily PRCP QFLAGs are the only open, documented per-observation flag set found with India stations. India station count is still open.
- IMD station data may hold the best labels, but flag availability and cost are unconfirmed.
- For reviewed extremes, use the cited papers only as candidate lists and confirm every value at source.

| source | tier it could fill | obtainable now? | main caveat |
|---|---|---|---|
| GHCN-Daily PRCP QFLAG | tier 2 (historical/weak flags) | Yes, open HTTPS | Automated global checks, not expert labels; India station count and coverage UNVERIFIED |
| GSOD PRCP attribute flags | tier 2 at most (completeness only) | Yes, open | Not QC flags; non-commercial terms |
| IMD DSP station daily rainfall | tier 1 if expert or QC flags exist | Partly, registration and fees | Flags not confirmed on portal |
| IMD RF25 gridded | none (base grid, no flags) | Yes | No per-value flags; station count UNVERIFIED |
| APHRODITE Monsoon Asia | none | Yes, DIAS registration | Ends 2007; no flags stated |
| GPCC full data daily | tier 2 candidate only | Yes, DWD | India station flags and Terms of Use UNVERIFIED |
| Mumbai 2005, Kedarnath 2013, Chennai 2015, Kerala 2018 (event values) | reviewed extremes ("must not flag") | Partly; primaries not opened | All values UNVERIFIED; use dates and sources as leads |
| Rajeevan et al. 2008 GRL | threshold reference for extremes | Paper not opened | Snippet only; UNVERIFIED |
