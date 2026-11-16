> **STATUS: UNVERIFIED, SUBAGENT-EXTRACTED.** Check every source before relying on it.

# National rain-gauge archives with official QC flags: usable as real labels?

Scope: daily precipitation only. Each claim cites the URL that was opened. "UNVERIFIED" means the claim came from a search snippet, a catalogue listing, or nothing at all, not from the primary document. The DWD PDFs were not readable through the fetch tool (they returned compressed PDF streams), so DWD flag meanings are weaker than the other sections.

## 1. Germany, DWD Climate Data Center

- **Daily precipitation:** `more_precip` (historical/recent) and `kl` daily products. The English description PDF for `more_precip` was returned only as compressed stream data, so its text could not be read: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/more_precip/DESCRIPTION_obsgermany-climate-daily-more_precip_en.pdf (opened, unreadable).
- **Quality field:** The wetterdienst documentation says `more_precip` has `qn_6`, described as "Quality flag published by the source for the values in the same dataset." It gives no code list: https://wetterdienst.readthedocs.io/en/latest/_sources/data/provider/dwd/observation/daily.md (opened).
- **QN code meanings (1, 2, 3, 5, 9, 10):** Only seen in search-result summaries of the DWD `kl` and monthly descriptions, which were not opened. Those summaries say QN 1 is formal control only, QN 3 is automatic control and correction, QN 5 is historic subjective procedures, QN 10 is finished with all corrections, and data up to and including 1980 can reach QN 5 at best. Source: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/DESCRIPTION_obsgermany-climate-daily-kl_en.pdf (URL found in search, text not read). **UNVERIFIED.** Do not use these codes until the text is read.
- **Raw vs corrected:** Not confirmed. The wetterdienst page says `recent` data have not completed QC and `historical` data are quality-controlled (search summary only, **UNVERIFIED**).
- **Licence:** The copyright link (https://www.dwd.de/copyright) was linked but not opened. The DWD portal page had no licence text: https://cdc.dwd.de/portal/ (opened). **UNVERIFIED.**
- **Station count and years:** Not verified.
- **Gridded counterpart:** HYRAS-DE-PR (v6.0 description found in search, not opened: https://opendata.dwd.de/climate_environment/CDC/grids_germany/daily/hyras_de/precipitation/DESCRIPTION_HYRAS-DE-PR_V6_en.pdf). A search snippet says the v5 German description states CC BY 4.0, but it was not opened. REGNIE daily (1 km) is listed in a DWD catalogue record (https://gdk.gdi-de.org/gdi-de/srv/api/records/de.dwd.hydromet.regnie.daily, not opened). **UNVERIFIED.**

## 2. UK, Met Office MIDAS Open (CEDA)

- **Catalogue record opened:** "MIDAS Open: UK daily rainfall data, v202407" (marked superseded): https://catalogue.ceda.ac.uk/uuid/8606115371e44b079e25d479cfec465c. It states "Use of these data is covered by ... the UK Open Government Licence version 3" and "Access to these data is available to any registered CEDA user." Coverage 1853-01-02 to 2023-12-31. About 13% of daily rainfall observations are excluded from this open subset. Station count not stated.
- **Versions:** The User Guide describes qc-version directories. Per https://help.ceda.ac.uk/article/4982-midas-open-user-guide (opened): `qc-version-1` "denotes the latest state of the data lines," and `qc-version-0` holds the original values "If QC changes a data line." `_q` flag value 0 is "no QC has run on the data when the file was produced." Other `_q` values are deferred to section 5 of the MIDAS User Guide (https://zenodo.org/record/7357335), which was not opened. **UNVERIFIED for all other flag codes.**
- **Field name:** The catalogue calls the variable "midas qc version number" (`version_num`). The name `qc_version` was not found on the page. **UNVERIFIED.**
- **Newest release:** v202607 (data to 2025) was seen only in search results. **UNVERIFIED.**
- **Gridded counterpart:** None checked.

## 3. Netherlands, KNMI

- **Station data:** The daily station page lists 52 stations (IDs 209 to 392) and says "Het KNMI voert op werkdagen een controle uit op deze gegevens" and "De gegevens worden op kwaliteit gecontroleerd en eventueel aangepast." It warns that validated data can differ from unvalidated 10-minute data: https://www.knmi.nl/nederland-nu/klimatologie/daggegevens (opened). Precipitation is "neerslag" but the RH column was not confirmed. No per-value flag scheme was found on this page. Raw values are not confirmed as retained.
- **Licence:** KNMI fair-use page: "For most datasets this is CC BY 4.0," and "Not all datasets carry the same license." Attribution is "Source: KNMI": https://developer.dataplatform.knmi.nl/fair-use (opened). Per-dataset licence still needs checking in the Data Catalog.
- **Gridded counterpart:** A gridded daily precipitation sum (1965 to present) on the KNMI Data Platform appears in search results. Not opened. **UNVERIFIED.**

## 4. United States

- **GHCN-Daily:** The readme defines QFLAG values: blank "did not fail any quality assurance check," plus letters D, G, I, K, L, M, N, O, R, S, T, W, X and Z (for example, "G: failed gap check," "X: failed bounds check," "Z: flagged as a result of an official Datzilla investigation"). It says FIRSTYEAR is "the first year of unflagged data," which implies flagged values remain in the files. Raw retention is not stated. Station count, period, licence (only a citation request), and flagged share are not stated: https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt (opened). Gridded counterpart: not checked.
- **USCRN:** The daily readme says "There are no quality flags for these derived quantities." When raw data are flagged, "these derived values are not calculated, and are instead reported as missing." Raw values are not kept beside the daily values. The precipitation field has no flag codes. No licence: https://www.ncei.noaa.gov/pub/data/uscrn/products/daily01/readme.txt (opened). USCRN is not a per-value flag source for daily precipitation.
- **NOAA HPD (COOP Hourly Precipitation):** The readme URL returned 404. A search summary says legacy DSI-3240 flags were kept in the merged v2 dataset. Flag codes not verified. **UNVERIFIED.** It is hourly-based and would need aggregation to daily.

## 5. Sha, Gagne, West, Stull (2021), JTECH, DOI 10.1175/JTECH-D-20-0081.1

- **The China claim is wrong.** The paper is about **British Columbia, Canada**: "the complex terrain of British Columbia" per the OpenSky abstract: https://www.cisl.ucar.edu/opensky-publications/articles:24497/deep-learning-based-precipitation-observation-quality-control (opened). The search result that surfaced a China-related preprint (https://www.preprints.org/manuscript/202510.1276) is a different work by different authors.
- **Labels:** "We train CNNs using human QC'd labels from 2016 to 2017 with gridded precipitation and elevation analyses as inputs." The abstract says the human labels were QC'd but does not say who produced them, the network name or operator, station count, or observation count. Label availability was not confirmed. The UCAR data-page URL (https://data.ucar.edu/dataset/deep-learning-based-precipitation-observation-quality-control) returned 502. The journal page (DOI redirect) returned 403. **UNVERIFIED** for labels, data access, and licence.

## Summary table

| archive | real labels? | raw + corrected? | licence OK for research? | gridded counterpart | verdict |
|---|---|---|---|---|---|
| DWD (more_precip / kl) | Yes, per-record QN codes exist; meanings UNVERIFIED (text not read) | UNVERIFIED | UNVERIFIED (copyright page not opened) | HYRAS-DE-PR, REGNIE (UNVERIFIED) | Promising, needs PDF text before use |
| UK MIDAS Open | Yes, qc-version and _q flags; full code list UNVERIFIED | Yes: qc-version-0 keeps original when QC changes a line | Yes, OGL v3 (catalogue); registration required | None checked | Strong candidate; read MIDAS User Guide section 5 |
| KNMI daily | Partial: QC described, no per-value flags seen | Corrected, raw not confirmed | Likely CC BY 4.0 (fair-use page); per-dataset check needed | Gridded daily precip 1965+ (UNVERIFIED) | Possible, flags unclear |
| GHCN-Daily (US) | Yes, QFLAG letters defined | Raw not stated | Not stated (citation request only) | None checked | Real flags, but no raw-value evidence |
| USCRN (US) | No: no precip flags, flagged values set missing | No | Not stated | None | Reject |
| NOAA HPD | UNVERIFIED | UNVERIFIED | UNVERIFIED | None | Unverified, hourly |
| Sha et al. 2021 | Human labels, BC Canada, 2016–2017; producer unstated | UNVERIFIED | UNVERIFIED | Gridded precip inputs (not an archive) | Not China; labels availability unknown |
