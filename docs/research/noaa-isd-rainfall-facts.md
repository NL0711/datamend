# NOAA ISD liquid-precipitation facts for the DataMend rainfall QC demo

Compiled 2026-11-18 from owner documentation only. No observation data files were downloaded.

## Banner: what was opened versus only seen as snippets

Opened in full (downloaded as documentation, text extracted with pdftotext, read directly):
- ISD format document, "Federal Climate Complex Data Documentation for Integrated Surface Data (ISD)", dated January 12, 2018 (cited below as FORMAT-DOC). Fetched from https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf (the same file is in the bucket https://noaa-isd-pds.s3.amazonaws.com/isd-format-document.pdf).
- ISD-Lite format documentation, dated June 20, 2006 (LITE-FORMAT): https://noaa-isd-pds.s3.amazonaws.com/isd-lite/isd-lite-format.txt
- ISD-Lite technical document, dated June 20, 2006 (LITE-TECH): https://noaa-isd-pds.s3.amazonaws.com/isd-lite/isd-lite-technical-document.txt
- Lott, "The Quality Control of the Integrated Surface Hourly Database" (ISH-QC), https://www.ncei.noaa.gov/pub/data/noaa/ish-qc.pdf (also reachable via https://noaa-isd-pds.s3.amazonaws.com/ish-qc.pdf)
- ISD FTP access point readme (FTP-README): https://www.ncei.noaa.gov/pub/data/noaa/readme.txt
- ISD list of known systematic problems (ISD-PROBLEMS): https://noaa-isd-pds.s3.amazonaws.com/isd-problems.pdf
- NCEI ISD product page (NCEI-PAGE): https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database (HTML read directly with curl, text stripped of tags; a WebFetch summary was also used only as a cross-check).

Only seen as snippets or not opened: nothing in this file rests on a search-engine snippet. These pointers were seen but not opened and nothing here relies on them: the AMS conference page for Lott (2004), the NCEI "Access Data Service API" documentation, and the ISD-Lite directory page (its listing is JavaScript-driven; the directory contents were read from the S3 bucket listing instead).

Notes on source quirks that affect trust:
- FORMAT-DOC is dated 2018. Its page numbers and wording are as extracted; some characters (dashes) came through as replacement characters in the text extraction, which does not affect any code or number quoted here.
- The old URL https://www.ncei.noaa.gov/pub/data/noaa/isd-lite/isd-lite-format.pdf now answers with a 301 redirect to the S3 bucket index https://noaa-isd-pds.s3.amazonaws.com/index.html#isd-lite/ . The guessed URL https://www.ncei.noaa.gov/pub/data/inventories/ish-qc.pdf (given on the NCEI page) returned HTTP 404 for me; the QC paper is at /pub/data/noaa/ish-qc.pdf instead.

---

## 1. LIQUID-PRECIPITATION group AA1 to AA4

Source: FORMAT-DOC, section "Precipitation Data" (Additional Data Section), document page 13 (extracted text lines 618 to 687).

The group identifier is 3 characters, "AA1" to "AA4". The document says "An indicator of up to 4 repeating fields of the following items: period quantity, depth dimension, condition code, quality code". Each repeat is therefore identifier(3) + period(2) + depth(4) + condition(1) + quality(1) = 11 characters (arithmetic from the field lengths below, not stated as a total in the document).

| Field | Width | Content | Range / units / scaling | Missing |
|---|---|---|---|---|
| Identifier | 3 | AA1, AA2, AA3 or AA4 | - | - |
| Period quantity | 2 | Time over which the precipitation was measured | MIN 00, MAX 98, UNITS hours, SCALING FACTOR 1 | 99 = Missing |
| Depth dimension | 4 | Depth of liquid precipitation "measured at the time of an observation" | MIN 0000, MAX 9998, UNITS millimeters, SCALING FACTOR 10 (so the stored integer divided by 10 gives mm) | 9999 = Missing |
| Condition code | 1 | Whether the depth was a trace value, plus accumulation markers | see below | 9 = Missing |
| Quality code | 1 | Quality status | see below | (no missing code in this list; 9 means "Passed gross limits check if element is present") |

Depth is unsigned (domain is digits 0-9 only), so negative values cannot appear in this group. A depth of 9999 means missing.

Period 99: the document says only "99 = Missing." It says nothing else about 99. The valid maximum is 98 hours. The document does not say what 98 means (for example "98 or more").

Condition code values (every value in the document, FORMAT-DOC page 13 to 14):
- 1 = Measurement impossible or inaccurate
- 2 = Trace
- 3 = Begin accumulated period (precipitation amount missing until end of accumulated period)
- 4 = End accumulated period
- 5 = Begin deleted period (precipitation amount missing due to data problem)
- 6 = End deleted period
- 7 = Begin missing period
- 8 = End missing period
- E = Estimated data value (eg, from nearby station)
- I = Incomplete precipitation amount, excludes one or more missing reports, such as one or more 15-minute reports not included in the 1-hour precipitation total
- J = Incomplete precipitation amount, excludes one or more erroneous reports, such as one or more 1-hour precipitation amounts excluded from the 24-hour total
- 9 = Missing

Quality code values (every value in the document, FORMAT-DOC page 14):
- 0 = Passed gross limits check
- 1 = Passed all quality control checks
- 2 = Suspect
- 3 = Erroneous
- 4 = Passed gross limits check, data originate from an NCEI data source
- 5 = Passed all quality control checks, data originate from an NCEI data source
- 6 = Suspect, data originate from an NCEI data source
- 7 = Erroneous, data originate from an NCEI data source
- 9 = Passed gross limits check if element is present
- A = Data value flagged as suspect, but accepted as good value
- I = Data value not originally in data, but inserted by validator
- M = Manual change made to value based on information provided by NWS or FAA
- P = Data value not originally flagged as suspect, but replaced by validator
- R = Data value replaced with value computed by NCEI software
- U = Data value replaced with edited value

Known caveats from the owner's problem list (ISD-PROBLEMS, items 1, 2 and 17):
- Item 1: before 2006, global surface hourly data have a sporadic problem where 6-hour precipitation amounts are sometimes 0 when the 6-hourly amount was not reported but precipitation did occur.
- Item 2: for 1996 to present, some 3-hourly and 6-hourly fields carry condition code 2 (trace) when the amount is greater than 0; the document says to ignore the condition code in that case and treat the amount as correct. It says this is mainly in the U.S. and that "hourly and 24-hourly amounts, are not affected".
- Item 17: Katmandu, Nepal (USAF 444540) has precipitation invalid by a factor of 10 (whole millimeters versus tenths in the synoptic code). Not an Indian station, but shows the same synoptic-reporting risk.

Related but different groups in the same document (not AA, do not mix up): AB1 monthly total, AC/AD/AE day-count and 24-hour-maximum summaries, AH1-AH6 and AI1-AI6 maximum short duration (5 to 60 minute), AJ/AK/AL snow, and AA in the "Hourly/15-minute precipitation" sections near FORMAT-DOC lines 1497 to 1572, where the period is in minutes. Only the first AA group (period in hours, lines 621 to 687) is the one that applies to ordinary synoptic records.

## 2. Several AA groups in one record, and end-of-period stamping

Source: FORMAT-DOC, searched in full for "accumulat", "24-hour", "repeating", "end of the period".

NOT STATED. The document does not say how to combine or interpret several AA groups in one record. It says only that up to four repeating groups may appear. The only related statements are:
- The condition codes 3/4, "Begin accumulated period" and "End accumulated period", imply that a long accumulated amount is reported on an "End accumulated period" record, with the amount missing at the "Begin" record. This is an implication of the code definitions, not an explicit rule about stamping.
- The depth is described as "measured at the time of an observation" (FORMAT-DOC page 13). That wording is the closest the document comes to saying the period ends at the observation time. It does not say "the period ends at the observation time stamp" and does not say anything specific about 24-hour reports.

So: whether a 24-hour report is stamped at the END of its period is not stated by the owner's documentation. Treat "period ends at the record timestamp" as a working assumption to be checked against real records for a few Indian stations, and mark it as such in any code. Likewise the document does not say whether the four AA groups in one record are alternative periods (for example 3 h and 6 h) that overlap, or sequential non-overlapping segments; do not add the groups together on the strength of this document. ISD-Lite's technical note (section 4 below) treats 1-hour and 6-hour amounts as separate accumulations, which supports not summing them, but ISD-Lite is a derived product and that is not a statement about full ISD.

## 3. Fixed-width positions needed to read a line

Source: FORMAT-DOC, "Control Data Section" and "Mandatory Data Section", document pages 5 to 12 (extracted text lines 127 to 616). Positions are 1-based, "POS: a-b" as printed in the document.

| Item | POS (1-based) | Width | Format, scaling, missing |
|---|---|---|---|
| TOTAL-VARIABLE-CHARACTERS | 1-4 | 4 | Number of variable characters; "The total record length = 105 + the value stored in this field" |
| USAF station identifier | 5-10 | 6 | ASCII |
| WBAN identifier | 11-15 | 5 | 00000 to 99999; 99999 is the usual "none" value (the document gives the range only; the "99999 means no WBAN" convention is not spelled out in this field) |
| Observation date | 16-23 | 8 | YYYYMMDD |
| Observation time | 24-27 | 4 | HHMM, "based on Coordinated Universal Time Code (UTC)", range 0000 to 2359 |
| Data source flag | 28 | 1 | codes 1-9, A-O, see document (9 = Missing) |
| Latitude | 29-34 | 6 | Signed, MIN -90000 MAX +90000, SCALING FACTOR 1000 (divide by 1000 for degrees), +99999 = Missing |
| Longitude | 35-41 | 7 | Signed, MIN -179999 MAX +180000, SCALING FACTOR 1000, +999999 = Missing |
| Report type code | 42-46 | 5 | e.g. FM-12 (SYNOP), FM-15 (METAR), FM-16 (SPECI), SY-MT (synoptic and METAR merged), SY-SA, S-S-A, AUTO, SAO, 99999 = Missing; full list in the document |
| Elevation | 47-51 | 5 | Signed, MIN -0400 MAX +8850, UNITS meters, SCALING FACTOR 1 (no division), +9999 = Missing |
| Call letter identifier | 52-56 | 5 | 99999 = Missing |
| QC process name | 57-60 | 4 | V01 = No A or M Quality Control applied; V02 = Automated Quality Control; V03 = subjected to Quality Control |
| (mandatory data section starts at 61 and ends with sea-level-pressure quality code at 105) | 61-105 | 45 | Section lengths stated: control 60 characters, mandatory 45 characters |

Start of the additional section: the document defines the identifier as 3 characters, "ADD", "The identifier that denotes the beginning of the additional data section" (FORMAT-DOC page 13, FLD LEN: 3), but it prints no POS for it because the field is variable-position in the sense that it follows the fixed sections. Derived from the stated section lengths (control 60 + mandatory 45 = 105; sea level pressure quality code is POS 105-105): "ADD" occupies columns 106-108 when present, and AA groups follow it. This 106-108 range is my arithmetic from the document, not a printed range. Records with no additional data omit the section (FORMAT-DOC page 2: "If no groups are reported the section will be omitted").

Also relevant to reading the line: the additional data section is variable in length, up to 637 characters including the section identifier; the remarks section starts with "REM" and the element quality section with "EQD" (FORMAT-DOC page 3, pages 128 to 130). Search for "AA1".."AA4" only inside the ADD part of the line (between "ADD" and a following "REM" or "EQD") to avoid matching text inside remarks.

Station identifier note: the document's 2018 notice says station identifiers in positions 5-15 may in future include a letter in the leading digit; the first two digits of the 11-digit id represent the WMO block "if applicable" (FORMAT-DOC page 5, NOTE 2). Use the file name usaf-wban-year for station keying.

Redistribution restriction (FTP-README, last paragraph before contact details): "The non-U.S. data in ISD are subject to WMO Resolution 40 restrictions, and cannot be redistributed to other users or customers." This applies to Indian station data and matters for a public demo. Not further interpreted here.

## 4. Update behaviour and ISD-Lite

Update frequency
- NCEI-PAGE: "There are currently more than 14,000 active ISD stations that are updated daily in the database." That is the only update-frequency statement on the page. It does not say the yearly .gz file for the current year is rewritten daily; it says the stations are updated daily in the database.
- FTP-README: "for the current year, updates will be more frequent and will not be indicated in the updates.txt file." The word "more frequent" is not quantified. The readme also says updated older-year files are listed in updates.txt, whose first lines show whole-year replacements dated 2018-08-26.
- ISH-QC (2004 paper, section 5 Future plans, item b): plans to "perform a near real-time (daily) ingest and QC of all surface data into ISH format" for U.S. surface data. This is a stated plan for U.S. data in an old paper, not a current guarantee, and not about Indian data.
- Latency (expected delay between an observation and its appearance): NOT STATED in any owner document I opened. The NCEI page does carry a banner: "Please Note: NCEI is currently moving its data and applications to the cloud. This upgrade may result in temporary data access delays." and "Current Impact: Expect delayed data archival and slower update cycles for many products." No number of hours or days is given. The words "real-time" appear only in the future-plan sentence above. Latency for Indian synoptic reports must be measured empirically (for example compare a file's last timestamp with the clock over several days).
- The https://noaa-isd-pds.s3.amazonaws.com/ bucket also holds the same documentation files and the isd-lite data directory; the ISD-Lite format docs now redirect there (see banner). I did not verify whether the full-format yearly files are also in that bucket or whether the www.ncei.noaa.gov/pub/data/noaa/<year>/ path is kept equally current; this is NOT VERIFIED.

ISD-Lite and liquid precipitation
Source: LITE-TECH and LITE-FORMAT (both dated June 20, 2006).
- ISD-Lite carries liquid precipitation. Of its eight variables, two are precipitation: "One-hour accumulated liquid precipitation (millimeters)" and "Six-hour accumulated liquid precipitation (millimeters)" (LITE-TECH, Introduction, items 7 and 8).
- LITE-FORMAT: Field 11, positions 50-55, length 6, "Liquid Precipitation Depth Dimension - One Hour Duration", UNITS millimeters, SCALING FACTOR 10, MISSING VALUE -9999, "Trace precipitation is coded as -1". Field 12, positions 56-61, length 6, "Liquid Precipitation Depth Dimension - Six Hour Duration", same units, scaling, missing value, trace code -1.
- Those are the only two precipitation fields. There is no 3-hour, 12-hour, or 24-hour precipitation field, and no flag fields. A 24-hour rain total therefore cannot be taken from ISD-Lite except by summing hourly or six-hourly values, and the documents give no 24-hour value. For Indian synoptic stations (many report 24-hour or 3-hourly/6-hourly rainfall), ISD-Lite would likely miss the reports that matter; that is an inference, not a documented statement.
- Other ISD-Lite facts: time stamp is rounded to the nearest hour with a capture window "greater than or equal to ten minutes before the top of the hour up to and including the top of the hour"; "Sub-hourly observations were removed"; duplicates resolved by a ranking scheme; "No additional quality control was performed on the ISD-Lite product and the absence of flag data may make it difficult to determine good data from suspicious data."
- LITE-TECH adds that precipitation observation times can differ from mandatory-element times by up to ten minutes.
- Documentation quirk: LITE-FORMAT prints some column ranges inconsistently (for example Field 3 is given as "Pos 9-11, Length 2" and Field 4 as "Pos 12-13"). Do not copy ISD-Lite column ranges from it without testing against a real file; not tested here because no data was downloaded.

## 5. Quality-control process described by the owner

Sources: ISH-QC (Lott paper), NCEI-PAGE "Quality Control" section, FORMAT-DOC.

- Versions: NCEI-PAGE: "ISD Version 1 was released in 2001, and Version 2 (additional quality control applied) in 2003. Automated quality control software has improved incrementally since 2003."
- Tests (NCEI-PAGE): "algorithms checking for proper data format for each field, extreme values and limits, consistency between parameters, and continuity between observations (e.g., for temperature)."
- ISH-QC section 4: Phase 2 applied 57 QC algorithms to each observation: validity checks, extreme value checks, internal (within observation) consistency checks, and temporal continuity checks against another observation for the same station. It "is entirely automated during the processing stage" and "does not include any spatial QC ('buddy' checks with nearby stations), which is planned for later development."
- Which elements get the most checking (ISH-QC section 4): "wind data, temperature and dew point data, pressure data, cloud data, visibility and present weather data, precipitation amounts, snowfall and snow depth." Similar consistency checks are said to be performed for "precipitation amount, snow depth, etc." The paper does not list the precipitation tests, rain-gauge limits, or thresholds; it refers to separate documentation (Lott, 2003, "Quality Control Documentation for Federal Climate Complex Integrated Surface Hourly Data"), which I did not open.
- Worked example given in the paper is a temperature spike test; a temperature spike value is set to missing and "the original value is saved in a separate section of the data record" (the EQD section).
- Flags applied automatically and suspect values kept: FORMAT-DOC describes quality codes in each group (0 through 7, 9, plus A, I, M, P, R, U) and an Element Quality Data section: "The element quality data section contains information on data that have been determined erroneous or suspect during quality control procedures. Also, some of the original data source codes and flags are stored here." Each erroneous or suspect parameter takes 16 characters (FORMAT-DOC page 3). For liquid precipitation the EQD parameter code is "PRCP = LIQUID PRECIPITATION DEPTH DIMENSION" (FORMAT-DOC page 130, line 8231), with a 6-character original value text and a reason code 0 to 7 (0 original missing or corrupted; 1 gross error; 2 geophysical; 3 consistency; 4 to 7 combinations).
- Therefore: flags are set by software, values flagged as suspect or erroneous are kept in the record (the data value remains in the group with quality code 2/3/6/7, or is replaced with missing and the original saved in EQD), so a reader can choose. This reading combines FORMAT-DOC and ISH-QC; neither says in a single sentence "suspect values are never removed from the files". The paper's spike example shows a case where the main-field value is changed to missing and only the original is kept in EQD.
- Quality-code semantics worth noting: codes 0 and 4 mean only "passed gross limits check", not that all tests ran; 1 and 5 mean "passed all quality control checks"; 9 means "passed gross limits check if element is present". Many non-U.S. synoptic reports are expected to carry 1 or 5 only if the full check ran; this is not stated by the documents, so the real distribution of codes in Indian files is NOT VERIFIED.
- The QC process name field (control section POS 57-60) records V01 no A or M QC applied, V02 automated QC, V03 subjected to QC (FORMAT-DOC page 7).
- No spatial or buddy check is applied (ISH-QC section 4), so a DataMend cross-station check does not duplicate NCEI's.

---

## Unresolved items and what to verify empirically

1. How multiple AA groups in one record relate (alternative overlapping periods versus sequential): NOT STATED. Inspect real records.
2. Whether a 24-hour report is stamped at the end of its period: NOT STATED (only the phrase "measured at the time of an observation"). Check a few Indian stations against known rain-day reports.
3. Latency between observation and appearance in the current-year yearly file: NOT STATED. NCEI-PAGE gives only "updated daily" for stations, "more frequent" for the current year's files, and a cloud-migration delay banner without numbers.
4. Whether period 98 means "98 or more hours": NOT STATED.
5. Exact precipitation QC thresholds: not in the documents opened; they are in Lott 2003, not opened.
6. WMO Resolution 40: the FTP readme says non-U.S. data in ISD cannot be redistributed. Consider this before publishing any derived Indian-station data from the demo.
