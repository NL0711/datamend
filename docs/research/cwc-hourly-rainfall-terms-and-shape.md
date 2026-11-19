# CWC hourly telemetry rainfall (NWDP): terms and shape

Dataset: "Rainfall (Telemetry - Hourly), Central Water Commission", National Water Data Portal (NWDP), run by the National Water Informatics Centre (NWIC).
Read on 2026-11-19 by fetching web pages only. No data file was downloaded and no API was called.

Labels: **READ** = seen on the cited page. **NOT VERIFIED** = not found on any page read, or the source could not be read. Page text was read through a fetch tool that summarises pages, so quotes marked "as returned" are fragments of the page, not a full copy.

Note: the ticket `docs/wayfinder/ingest-and-feedback-loop/tickets/t03-cwc-terms-and-shape.md` does not exist in this worktree or the shared checkout (only `phone-fl-prototype` and `rainfall-validation-platform` exist under `docs/wayfinder`). The questions below follow the task brief instead.

## Sources

- S1: https://nwdp.nwic.gov.in/dataset/rainfall-cwc-telemetry-hourly (dataset page)
- S2: https://nwdp.nwic.gov.in/footer/copyrightPolicy (Copyright Policy)
- S3: https://nwdp.nwic.gov.in/footer/disclaimer (Disclaimer)
- S4: https://nwdp.nwic.gov.in/dataset_api/home_api_page (APIs landing page)
- S5: https://nwdp.nwic.gov.in/dataset/rainfall-cwc-telemetry-hourly/resource/fdabc65b-0018-4d4a-a6d0-7b5985873912 (resource page, Andhra Pradesh 2021-2025)
- S6: https://nwdp.nwic.gov.in/pdf/national-water-data-policy.pdf (National Water Data Policy PDF)

## Publisher

- READ (S1): Data producer is the Central Water Commission (CWC), an attached office of the Ministry of Jal Shakti. Portal operator is NWIC, Department of Water Resources, River Development and Ganga Rejuvenation. Contacts: helpdesk-nwic@gov.in, +91-011-20863687; producer email rdcdte-cwc@nic.in.
- READ (S1): Description: hourly rainfall from telemetry-based stations across India; each record has a timestamp, station ID, geographic hierarchy and rainfall value. Stated uses: real-time hydrology, flood forecasting, water management, climate studies.

## Licence, copyright, reuse and redistribution

- READ (S5): The resource page metadata gives "License: Other (Open)". No licence name, version or URL is attached to it.
- READ (S1): The dataset page itself states no licence.
- READ (S1, S2): Footer reads "© 2025 NWIC All Rights Reserved."
- READ (S2): The Copyright Policy says site material "may be reproduced free of charge in any format or media without requiring specific permission", subject to the material being "reproduced accurately and not being used in a derogatory manner or in a misleading context". Where material is "published or issued to others, the source must be prominently acknowledged". The permission does not extend to material explicitly identified as third-party copyright; that needs the holder's authorisation.
- NOT VERIFIED: whether the Copyright Policy's "material featured on this site" covers the dataset CSV files (the policy text read does not mention datasets).
- NOT VERIFIED: any term about storing, transforming or redistributing derived data (aggregates, flags, model outputs, scores). Neither S1, S2 nor S5 mentions derived data. The "accurately" and "misleading context" conditions in S2 are the only conditions read that could bear on modified material.
- NOT VERIFIED: any explicit statement that CWC data is third-party copyright on this portal. No such marking was seen.
- READ (S3, summarised by the fetch tool): NWIC publishes data sourced from producer agencies; users should contact those agencies for clarification; producers are responsible for validating their data and documenting metadata; NWIC gives no warranty and disclaims liability for accuracy or completeness; users should verify independently.
- NOT VERIFIED (S6): The National Water Data Policy PDF (1.8 MB) is linked from the portal. The fetch tool returned only raw PDF structure, so its text on data sharing, classification or licensing was not read. A local copy was cached by the fetch tool in the Claude tool-results folder; it was not opened.

## Documented columns

- READ (S1): Description names only timestamp, station ID, geographic hierarchy and rainfall value.
- READ (S5): Resource page shows no column names, no data dictionary, no preview rows (resource view "not available at the moment"), no file size, no row count.
- NOT VERIFIED: actual column names, units, accumulation interval, timestamp timezone, missing-value convention, quality flags. Seeing them would require opening a CSV, which was out of scope.

## Station coordinates

- NOT VERIFIED: S1 and S5 state nothing about latitude/longitude. The description mentions a "geographic hierarchy" only.

## Station counts

- NOT VERIFIED: no station count appears on S1 or S5.

## Resource layout and update frequency

- READ (S1): 83 CSV resources in three period groups: 1991-2020 (28 files, includes Daman and Diu and Punjab, no Dadra and Nagar Haveli), 2021-2025 (28 files, includes Dadra and Nagar Haveli), 2026-2030 (27 files). One file per state or union territory per period. Naming: `rainfall_tel_hr_cwc_<state code>_<period>.csv`, e.g. `rainfall_tel_hr_cwc_ap_2021_2025.csv`.
  - Group totals as read: 28 + 28 + 27 = 83.
- READ (S1): "Last Update Date" for the dataset is shown as November 19, 2026, 00:41 (UTC); the "Last updated on" field is blank.
- READ (S5): For the Andhra Pradesh 2021-2025 resource, data last updated January 24, 2026.
- NOT VERIFIED: any stated update frequency (S1 lists frequency as not stated). Latency between observation and publication is not stated.
- READ (S5): Download formats offered: CSV, TSV, JSON, XML. Direct CSV URL pattern: `https://nwdp.nwic.gov.in/dataset/792f0818-bedf-42ab-a119-dc7002ceb312/resource/<resource id>/download/<file>.csv` (not fetched).

## API and limits

- READ (S1): "Data Format: CSV, API". No dataset-specific endpoint is listed.
- READ (S4): The landing page says NWIC "has prepared 572 APIs for dissemination of water dataset". It lists no endpoints, authentication, parameters, formats or rate limits.
- NOT VERIFIED: the API's endpoint for this dataset, whether a key or registration is required, rate limits, and API-specific terms. The fetch of S4 returned only a landing page, so a separate API documentation page may exist that was not located.
- NOT VERIFIED: download limits or registration requirements for the CSV links.
