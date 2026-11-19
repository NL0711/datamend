# IMERG Late Run V07 as a near-real-time daily rainfall source: facts from primary sources

> **NOT USED (2026-11-18): the owner dropped IMERG, so this note is kept only as a record of what was found. The code written from it was deleted.**

Compiled 2026-11-18 for DataMend (IMD RF25 daily rainfall QC, 03 UTC to 03 UTC rain day).

## BANNER: what was opened and what was not

OPENED (full text read, or structured metadata read):
- NASA CMR collection metadata for GPM_3IMERGHHL V07 and GPM_3IMERGDL V07 (JSON records on cmr.earthdata.nasa.gov, which is the metadata the GES DISC product pages are built from).
- NASA CMR granule metadata for the first and latest half-hourly Late granules and the latest daily Late granule (metadata only, no data file).
- IMERG Technical Documentation, dated 13 July 2023 (PDF at arthurhou.pps.eosdis.nasa.gov), text extracted locally with pdftotext. NOTE: this is the V07 document as it stood in July 2023; the CMR record says the current release is V07B/V07C, so details after July 2023 are not in it.
- IMERG V07 ATBD, dated 13 August 2026 (PDF at gpm.nasa.gov), text extracted locally.
- GPM IMERG page / FAQ https://gpm.nasa.gov/data/imerg (read through a summarising fetch tool, not verbatim).
- V07 release notes web page https://gpm.nasa.gov/resources/documents/imerg-v07-release-notes (read through a summarising fetch tool; the linked release-notes PDF was NOT opened).
- GPM data policy https://gpm.nasa.gov/data/policy and Earthdata data-use guidance https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance (summarising fetch tool).

COULD NOT OPEN (page rendered only the title "GES DISC", client-side rendered, retried via CMR as the other route):
- https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGHHL_07/summary
- https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDL_07/summary
- https://disc.gsfc.nasa.gov/information/documents?title=Data%20Access (same empty result)
So the GES DISC product-page text itself was never seen; the equivalent CMR records were used instead.

NOT OPENED, SNIPPET-LEVEL ONLY / NOT SEEN: the standalone IMERG file specification (ftp://gpmweb2.pps.eosdis.nasa.gov/pub/GPMfilespec/filespec.GPM.pdf, linked by CMR, ftp so not tried), the V07 release-notes PDF, the Data FAQ https://gpm.nasa.gov/data/faq, the GES DISC "How to" access pages, the quality index PDF.

NO IMERG DATA FILE WAS DOWNLOADED (no Earthdata Login is available). Sizes below are from CMR metadata, not from downloaded files. Consequently the HDF5 group/dimension layout of an actual V07C file is UNVERIFIED against a real file; it comes from documentation text.

A note on dates: the environment date is 2026-11-18. The latest granules seen in CMR are dated 2026-11-17 (half-hourly) and 2026-11-16 (daily).

---

## 1. Product names and short names

Source: CMR collection records, https://cmr.earthdata.nasa.gov/search/collections.json?short_name=GPM_3IMERGHHL&version=07 and ...short_name=GPM_3IMERGDL&version=07.

- Half-hourly Late: short name GPM_3IMERGHHL, version 07, title "GPM IMERG Late Precipitation L3 Half Hourly 0.1 degree x 0.1 degree V07", collection id C2723754845-GES_DISC, DOI 10.5067/GPM/IMERG/3B-HH-L/07 (DOI from https://cmr.earthdata.nasa.gov/search/collections.umm_json?concept_id=C2723754845-GES_DISC).
- Daily Late: short name GPM_3IMERGDL, version 07, title "GPM IMERG Late Precipitation L3 1 day 0.1 degree x 0.1 degree V07", collection id C2723754859-GES_DISC.
- The Technical Documentation calls the native half-hourly Late set "3IMERGHH_LATE" with the same DOI (https://arthurhou.pps.eosdis.nasa.gov/Documents/IMERG_TechnicalDocumentation_final.pdf, "short names and DOI list").
- Versions: the collection is "07"; the CMR abstract states Version 07B is the current release (same CMR record). Actual file names currently carry "V07C" (see section 2), so the file-level version letter is newer than what the collection summary says. UNVERIFIED which of B or C is the current official release; the release-notes PDF was not opened.
- Release notes page: reprocessing of V07 Final was redone as V07B; Early and Late initial processing effective from 1 June 2024, climatological calibrations for Early and Late recomputed relative to Final (https://gpm.nasa.gov/resources/documents/imerg-v07-release-notes).

## 2. File format and layout of the half-hourly Late file

- Format: HDF5 (Technical Documentation, "data set archive": "Version 5 Hierarchical Data Format (HDF5) files", one file per half hour). https://arthurhou.pps.eosdis.nasa.gov/Documents/IMERG_TechnicalDocumentation_final.pdf
- Daily Late files are NetCDF4 (.nc4), per the latest daily granule name (CMR granule record, below), not HDF5.
- File naming (CMR granule records, https://cmr.earthdata.nasa.gov/search/granules.json?collection_concept_id=C2723754845-GES_DISC&page_size=1&sort_key=-start_date):
  - latest seen: `3B-HHR-L.MS.MRG.3IMERG.20261117-S153000-E155959.0930.V07C.HDF5`
  - earliest seen: `3B-HHR-L.MS.MRG.3IMERG.19980101-S000000-E002959.0000.V07B.HDF5`
  - pattern: `3B-HHR-L.MS.MRG.3IMERG.<YYYYMMDD>-S<HHMMSS>-E<HHMMSS>.<minutes-of-day>.V07<letter>.HDF5`. The four-digit field equals the start minute of day in these two examples (0930 = 15:30 UTC); the Technical Documentation does not explain it, so treat that reading as inferred from the two examples.
  - Technical Documentation: "S" and "E" are start and end times, all UTC; Late prefix is "3B-HHR-L".
- Calibrated precipitation variable: `precipitation`, units mm/hr, described as the recommended complete estimate for Early and Late. The V07 name/location is `Grid/precipitation` (Technical Documentation, "changes from V06 to V07" list, lines naming `Grid/precipitation`, `Grid/Intermediate/precipitationUncal`, etc.). Other variables: precipitationUncal (mm/hr), randomError (mm/hr), MWprecipitation, IRprecipitation, probabilityLiquidPrecipitation (percent), and `precipitationQualityIndex` (unit given as "index"). Table 1 of the same document. Whether precipitationQualityIndex sits directly in `Grid/` is not stated in the text I extracted; UNVERIFIED against a real file.
- Quality index document linked by CMR: https://docserver.gesdisc.eosdis.nasa.gov/public/project/GPM/IMERGV06_QI.pdf (not opened). The Technical Documentation says the half-hourly QI is based on correlation to the reference PMW estimate.
- Dimension order: the native HDF5 fields are (time, lon, lat) with lengths (1, 3600, 1800); this changed from (lon, lat) in V05 (Technical Documentation, "Known data set access issues" item 5 and "changes from V06 to V07"). So longitude is the second axis and latitude the third (fastest-varying), i.e. a transposed layout relative to the usual (lat, lon).
- Grid: 0.1 x 0.1 degree global, 3600 x 1800. Latitude increases south to north from the southern edge, longitude west to east from the dateline. First point centre is (89.95 S, 179.95 W), second point centre (89.85 S, 179.95 W), last point centre (89.95 N, 179.95 E). Cell centres are therefore at x.x5 degrees. Datum WGS84. (Technical Documentation, "grid".) V07 fields are globally complete to the extent inputs cover (IR only 60 N-S).
- Fill (missing) value: -9999.9 for 4-byte floats, -9999 for 2-byte integers; carried in the metadata (Technical Documentation, "standard missing value", section 8). Whether the V07C file also stores it as `_FillValue` is UNVERIFIED without a file.
- Rounding and limits: V07 half-hourly rates rounded to 0.01 mm/hr; maximum permitted rate 200 mm/hr (Technical Documentation, "changes from V06 to V07").
- Time convention: each half-hourly file is a nominal 30-minute span starting on the hour or half hour, UTC; the first image of a day covers 00:00:00 to 00:29:59 UTC; start and end times are in the file name and metadata (Technical Documentation, "file date/time" and the sentence "each 3IMERGHH data set represents a nominal 30-minute span").

## 3. Building a day from half-hourly rates

- Rate to accumulation: half-hourly values are rates in mm/hr that should generally be treated as applying across the full half hour (IMERG FAQ summary, https://gpm.nasa.gov/data/imerg). That gives accumulation = rate x 0.5 h. The page itself gave no method for building daily totals (same source), so the multiplication by 0.5 is the documented reading of "rate over the half hour", not an owner-supplied recipe.
- How the owner's daily Late product is built (CMR record for GPM_3IMERGDL, https://cmr.earthdata.nasa.gov/search/collections.json?short_name=GPM_3IMERGDL&version=07): daily mean precipitation rate in mm/day, computed by averaging the valid half-hourly rates and multiplying by 24; V07 uses this to reduce dry bias from incomplete daily sampling. The day is a UTC calendar day (granule S000000-E235959, https://cmr.earthdata.nasa.gov/search/granules.json?collection_concept_id=C2723754859-GES_DISC&page_size=1&sort_key=-start_date). Consequence: the owner's daily product is a mean over VALID slices, so missing slices are not counted as zero. A hand-built sum should decide explicitly how to treat missing slices (the owner's approach is mean-of-valid x 24).
- 03 UTC to 03 UTC day (derived by me from the file naming above, not stated by the owner): for the IMD rain day ending 03 UTC on date D+1 (08:30 IST on D+1), the 48 slices run from the file starting S030000 (E032959) on day D to the file starting S023000 (E025959) on day D+1. First time stamp 03:00:00 UTC on D, last 02:30:00 UTC on D+1 (ending 02:59:59). This depends on the IMD convention that the rainfall is recorded at 03 UTC for the previous 24 h; that is a DataMend question, not an IMERG one.
- The FAQ states the GeoTIFF Early/Late downloads at PPS include 30-minute, 3-hour and 1-day files (scaled x10) (https://gpm.nasa.gov/data/imerg). Their day boundaries were not checked.

## 4. Regridding from 0.1 to 0.25 degree

- The owner gives NO conservative-remapping recipe in what I read. The only guidance found: many interpolation schemes suppress maxima in precipitation and can spread rain into neighbouring zero-rain areas; users should check this and document the interpolation scheme (https://gpm.nasa.gov/data/imerg, FAQ summary).
- 0.25 is not a multiple of 0.1 and IMERG cell edges sit at multiples of 0.1 (centres at x.x5); the choice of area-weighted (conservative) remapping is therefore DataMend's own, not an owner recommendation. Not found: any statement in the Technical Documentation text I extracted on regridding to 0.25. The ATBD text was searched for regrid terms only through a general keyword scan; a full read was not done, so "not found" means not found in those scans.

## 5. Access

- Earthdata Login: required. Technical Documentation: users must complete a free, automatic online registration at PPS and GES DISC to access the data (https://arthurhou.pps.eosdis.nasa.gov/Documents/IMERG_TechnicalDocumentation_final.pdf, "data user registration"). The CMR granule records list the s3 credentials endpoint https://data.gesdisc.earthdata.nasa.gov/s3credentials (an authenticated service). The GPM data policy page itself does not mention registration (https://gpm.nasa.gov/data/policy). The Earthdata guidance page does not state an EDL requirement either (https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance).
- HTTPS URL pattern (from CMR granule links):
  - half-hourly: `https://data.gesdisc.earthdata.nasa.gov/data/GPM_L3/GPM_3IMERGHHL.07/<YYYY>/<DOY, 3 digits>/<file name>` (example year 2026 day 321 for 17 Nov 2026).
  - daily: `https://data.gesdisc.earthdata.nasa.gov/data/GPM_L3/GPM_3IMERGDL.07/<YYYY>/<MM>/<file name>`.
  - s3 (in-region AWS, needs credentials): `s3://gesdisc-cumulus-prod-protected/GPM_L3/GPM_3IMERGHHL.07/...`.
- OPeNDAP: CMR lists a service link of the form `https://opendap.earthdata.nasa.gov/collections/C2723754845-GES_DISC/granules/<URL-encoded GPM_3IMERGHHL.07:file name>` (granule record above). Whether subsetting through it works for a given file and what auth it needs was not tested.
- earthaccess library: NOT VERIFIED from a primary source in this session; not mentioned in any page opened. Do not assume.
- Other routes named by the owner: PPS archive https://storm.pps.eosdis.nasa.gov/storm/ and https (not ftp) pages https://jsimpsonhttps.pps.eosdis.nasa.gov/ (near-real-time) and https://arthurhouhttps.pps.eosdis.nasa.gov/ (post-real-time) (Technical Documentation, "Known data set access issues" item 2 and "data set archive").
- Size: Technical Documentation (2023) says about 10 MB per half-hourly file with internal compression. CMR granule metadata now gives 7.33 MB (earliest, 1998-01-01) and 6.68 MB (2026-11-17 15:30 UTC) for half-hourly, with no unit stated in the feed (assumed MB), and 25.81 MB for the daily file of 2026-11-16 (same assumption). A day of 48 files is therefore roughly 320 to 480 MB; this is my arithmetic from those figures, not an owner number. Files NOT downloaded, so sizes are unverified against real files.
- Rate limits: NOT FOUND in any opened page. UNVERIFIED.
- Licence: NASA-led mission data are CC0 unless the content states its own restriction (https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance). CMR for the collection says access constraints "None", data "freely available" and points to that guidance (https://cmr.earthdata.nasa.gov/search/collections.umm_json?concept_id=C2723754845-GES_DISC).
- Citation: requested, not mandated ("very strongly urged"), same guidance page. GPM policy: acknowledge the dataset source; datasets with DOIs are cited by DOI (https://gpm.nasa.gov/data/policy). Citation from CMR: Huffman, G.J., Stocker, E.F., Bolvin, D.T., Nelkin, E.J., Tan, J., "GPM IMERG Late Precipitation L3 Half Hourly 0.1 degree x 0.1 degree V07", GES DISC, release date 2024-06-07, DOI 10.5067/GPM/IMERG/3B-HH-L/07 (collections.umm_json record above).
- Redistribution: reproduction and distribution generally permitted, no implied NASA endorsement (Earthdata guidance page). The GPM policy page sets no explicit redistribution terms and encourages primary NASA archives; if a secondary archive is used, verify the data are current and correct (https://gpm.nasa.gov/data/policy). If DataMend republishes derived grids, cite and avoid implying endorsement.

## 6. Latency, coverage, known issues

- Latency: nominal 14 hours after observation time, "in recent data it's more like 12" (Technical Documentation, "latency", https://arthurhou.pps.eosdis.nasa.gov/Documents/IMERG_TechnicalDocumentation_final.pdf). The FAQ repeats 14 hours nominal and about 12 recently (https://gpm.nasa.gov/data/imerg). The ATBD table lists Late at 12 hours (https://gpm.nasa.gov/sites/default/files/2026-08/IMERG_V07_ATBD_final_260813.pdf, run/latency table). The daily Late record says the daily file appears about 14 hours after the UTC day closes (CMR record for GPM_3IMERGDL). Mechanism: PPS waits about 11 hours for the following microwave overpass because Late uses forward and backward morphing.
  - Consequence for a 03 UTC day: the last slice (S023000 on D+1) would be expected roughly 12 to 14 hours after 03 UTC, about 15:00 to 17:00 UTC on D+1. This is my arithmetic from the owner's figure, not an owner statement.
- Coverage start: 1998-01-01T00:00:00Z for both Late collections (CMR records). The Technical Documentation says the TRMM-era period of record starts June 2000 in the text, with January 1998 noted in brackets in the same sentence; the CMR granule for 1998-01-01 00:00 UTC exists (S000000, V07B). Also, the Technical Documentation says no geo-IR data in the Indian Ocean sector for 1 Jan 1998 to 03 UTC 16 June 1998 (text-search result, line about "Indian" geo-IR). Reprocessing of Early/Late: retrospective processing began June 2024 with initial processing effective 1 June 2024 (release notes page). Whether the whole 1998 to 2026 Late record is currently populated in the archive was not checked beyond the first granule.
- Coverage end: no end date in CMR (EndsAtPresentFlag false); latest granules seen: half-hourly 2026-11-17 15:30 UTC (V07C), daily 2026-11-16 (V07C). This shows the live archive was about 8 hours behind the environment date at the time of the check, which is consistent with, but does not prove, the 12 to 14 hour latency.
- Calibration: Early and Late are NOT gauge-calibrated in the real sense. The V07 Late half-hourly estimates use a climatological (per calendar month) calibration to the Final satellite-gauge product, i.e. a fixed monthly adjustment from the long Final record; CORRA (the combined radar-radiometer calibrator) itself carries a climatological correction to GPCP (Technical Documentation, section on calibration, "climatological" explanation; CMR UMM record says Late values may differ from Final). V06 did not apply this final adjustment, V07 does.
- Known problem over India or the monsoon region stated by the owner: NOT FOUND. Searches of the Technical Documentation and ATBD text for monsoon, India and Himalaya returned no statement about the Late run's calibration there. The only related items seen: (a) no geo-IR over the Indian Ocean sector in early 1998; (b) V07 GPROF has an orographic adjustment (Technical Documentation); (c) reduced skill over frozen surfaces and high latitudes. Whether the release-notes PDF or the Data FAQ mention the region was not checked.
- Quality caveat from the release notes page: V07 Final reprocessing was redone as V07B after about 162 orbits of defective GPROF estimates were found; the second reprocessing finished 8 January 2024 (https://gpm.nasa.gov/resources/documents/imerg-v07-release-notes). This concerns the Final; its effect on Late is not stated on that page.

## Open items for DataMend

1. Confirm the real HDF5 layout (group path, dimension order, fill attribute, QI variable location) on one downloaded V07C file once an Earthdata Login exists; the text above is documentation only.
2. Decide the treatment of missing half-hourly slices (owner's daily product averages valid slices and multiplies by 24).
3. Choose and document the 0.1 to 0.25 degree remap yourself; the owner gives no recipe, only a warning about maxima suppression.
4. Verify rate limits and whether earthaccess is the sanctioned route; neither was established here.
5. Check the V07 release-notes PDF and the Data FAQ for any India-specific Late statement before concluding there is none.
