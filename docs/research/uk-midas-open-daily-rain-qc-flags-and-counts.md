# UK MIDAS Open daily rainfall: QC flag meanings and how many values QC changed

Date: 2026-11-17. Flag meanings were read by the agent from the primary document. Counts were computed by the agent from downloaded files for **one county (Devon) only**. Nothing here was checked by a second person.

## Sources

- Flag definitions: *MIDAS Data User Guide for UK Land Observations*, v20210705, Met Office (Zenodo record 7357335), sections 5.1-5.4.
- Data: CEDA archive, `badc/ukmo-midas-open/data/uk-daily-rain-obs/dataset-version-202607/devon/`. Open Government Licence. Listing is open; file download needs a free CEDA account and access token.
- Scope of the download: every `qc-version-0` file for Devon, the `qc-version-1` file for the same station-year, and capability files. 16,158 files, 311 MB, no errors. The 6,492 Devon station-years that have no `qc-version-0` file were **not** downloaded.

## What the files contain

- `qc-version-1`: the current best value for every record.
- `qc-version-0`: the original record, kept **only** when QC changed the record. A year with no `qc-version-0` file had no changed records.
- Changes made by a station's own correction message overwrite the original, so those originals are not kept (guide, section 5.1).
- Intermediate QC steps are not kept; only the first and the latest state.
- Columns used: `prcp_amt` (mm), `ob_day_cnt` (days the amount covers), `prcp_amt_q` (QC code), `rec_st_ind` (record state), `met_domain_name` (message type).

## The QC code (`prcp_amt_q`)

Five digits, read as marker, estimate, status, query, level. Leading zeros are dropped, so `9` means `00009`.

| digit | values |
|---|---|
| marker | 0 neither; 1 trace; 2 accumulated (multi-day) value; -2 trace and accumulation |
| estimate | 0 not an estimate/correction; 1 derived automatically; 2 set manually; 3 obtained later from the station; 4 snow-rain equivalence or trace consistency; 5 unit change; 6 systematic adjustment; 7 SREW snow or mechanical problem |
| status | 0 as observed, not suspect; 1 as observed, suspect; 2 estimate, expected observation not available; 3 estimate, original missing and irretrievable; 4 unreliable estimate (radiation only); 5 **correction, original considered in error**; 6 reverted to original; 7 original verified by observer |
| query | 0 no check failed; 1 failed MetDB check; 2 failed ingestion range check; 3 marine position check; 4 failed QC range check; 5 failed internal consistency check; 6 failed sequence check; 7 **failed areal (neighbour) check** |
| level | 0 no QC; 1-2 QCL checks; 4 range/consistency checks done; 6 areal checks done; 9 all QC complete |

Notes from the guide:
- A value can fail a check and not be suspect (unusual weather), and can pass every automatic check and still be corrected by staff.
- Rainfall is excluded from the automatic "QCL" checks; it gets ingestion range checks, areal checks against neighbours, and manual review.
- "With few exceptions" flagged messages are reviewed by trained staff, who supply corrections and estimates.
- Record state `1012` marks the original (version 0) record; `1013` means an original exists with no version 1.

## Counts for Devon (dataset version 202607)

| | count |
|---|---|
| stations | 675 |
| stations with at least one changed record | 531 |
| station-years, all | 14,241 |
| station-years with changed records | 7,749 |
| current-best records in those 7,749 station-years | 2,489,200 |
| original records kept (`qc-version-0` rows) | 226,421 |
| ... matched to a current-best record on date, station id and message type | 182,200 |
| ... not matched | 43,695 (29,385 have state `1013`, "original exists with no version 1") |

What happened to the 182,200 matched originals:

| category | count |
|---|---|
| amount changed, same period | 122,286 |
| multi-day total split into daily amounts | 54,590 |
| amount unchanged, only flags or other fields changed | 5,319 |
| missing to estimate, or value to missing | 5 |

Of the 122,286 changed amounts, by the flags on the current-best record:

| kind | count |
|---|---|
| manual correction, original in error, failed areal check (status 5, estimate 2, query 7) | 68,657 |
| automatic estimate replacing a placeholder (status 2, estimate 1) | 41,757 |
| no status or estimate flag set | 11,302 |
| other | 570 |

- **Human-corrected errors: about 68,700.** That is 2.8% of the 2,489,200 records in station-years that had any change. Across all 14,241 Devon station-years it is roughly 1.5%; this second figure is an **estimate**, because the row counts of the unchanged station-years were not downloaded (it assumes the same 321 records per station-year).
- The 41,757 automatic estimates are not corrections of gauge errors: the original was itself a placeholder (typically 0.0 with status 2).
- Direction: 69,521 increases, 52,765 decreases. Median absolute change 3.4 mm, 90th percentile 14.8 mm, largest 9,782.5 mm (a gross keying or unit error).
- 47,662 changed values had an original of exactly zero; 16,618 were changed to zero.
- Changed amounts by decade: 1970s 11,891; 1980s 21,375; 1990s 36,356; 2000s 20,452; 2010s 22,205; 2020s 9,910. Almost nothing before 1970.
- Message types in the current-best records: WADRAIN 2,305,218; DLY3208 152,102; NCM 21,664; SSER 5,294; WAMRAIN 4,922.

## What this means for the project

- Real "original versus human-corrected" labels exist for **daily** rainfall, in volume, and they cover the project's validation and test years (2013-2023).
- The dominant label is "failed the neighbour check and was corrected by hand". The labels are therefore tied to a spatial check; a spatial detector scored against them is partly being scored against the rule that produced them.
- Three other row types must be kept apart from errors: multi-day totals split into days, automatic estimates of placeholders, and flag-only changes.
- Originals overwritten by station correction messages are missing, so the labels undercount errors.
- These are station series, not a grid.
- Devon only. Other counties, and the UK total, are not counted.

Reproduction scripts (downloader and counter) are not in the repository; they were run from a session scratch directory.
