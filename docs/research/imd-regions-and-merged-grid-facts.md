# IMD regions and merged GPM grid: fact-finding (2026-11-18)

## BANNER: what was opened versus only seen

OPENED (content actually read):
- https://imdpune.gov.in/cmpg/Realtimedata/gpm/Rain_Download.html (page text read via fetch tool)
- https://imdpune.gov.in/cmpg/Realtimedata/gpm/dataddmmyyyy.php (control file, 229 bytes, read in full)
- https://imdpune.gov.in/cmpg/Realtimedata/gpm/mapgrid.php (text grid, 264.8 KB, parsed locally)
- https://link.springer.com/article/10.1007/s12040-025-02550-0 (opened on the 3rd attempt, after two cookie redirects; the content returned was the abstract/landing page, not the full paper text)
- https://mausam.imd.gov.in/imd_latest/contents/district_shapefiles/sd_boundary_rainfall.json (downloaded in full, 900,948 bytes, parsed)
- https://mausam.imd.gov.in/imd_latest/contents/rainfall_over_homogeneous.php (HTML downloaded; no region text in it) and its image https://mausam.imd.gov.in/ClimateInformation/imdweb/DAY_WEEK/homo.gif (112,538 bytes, viewed)
- https://mausam.imd.gov.in/imd_latest/contents/statewisedistricts.php and .../index_rainfall_subdiv.php and .../subdivisionwise-warning.php (menu pages only; no boundary downloads or lists)
- https://mausamjournal.imd.gov.in/index.php/MAUSAM/article/view/38 and /41 (abstract pages)
- https://gist.github.com/planemad/d347ad7485344fb0ba4b470721825427 (gist page; the GeoJSON itself was not displayed)
- https://groups.google.com/g/datameet/c/KJzvdH1gG40 (community thread, 2020)

COULD NOT OPEN:
- https://www.tropmet.res.in/~lip/Publication/RR-pdf/RR-138.pdf (IITM RR-138): fetch tool "certificate rejected"; retry with curl: schannel SEC_E_UNTRUSTED_ROOT (0x80090325). I did not bypass certificate checking.
- https://iridl.ldeo.columbia.edu/... (IITM Subdivision dataset docs and Readme_v1871-2016.pdf): returned an IRI Data Library sign-in page only.
- Full text of Mitra et al. 2025: only the landing page content was obtained (see Q2). The "Rain_Download" binary data file itself was not downloaded (not requested; large).

ONLY SEEN AS SEARCH SNIPPETS (UNVERIFIED): the claim that IMD's "four regions for forecasting" are northwest, northeast, central and south peninsula (snippet attributing it to Zheng et al. 2016 MWR); the IITM "five homogeneous regions" (NW, West Central, Central North East, North East, Peninsular) and "30 subdivisions" in RR-138 (snippet of RR-138 / frontiersin.org feart.2022.794634 text); data.gov.in pages listed in search results (no subdivision-boundary dataset seen there).

Downloaded files, all in the scratchpad folder C:\Users\V\AppData\Local\Temp\claude\023585c3c16dcdd2\c7078bc1-4f2e-4110-ae92-70618e71e5e7\scratchpad\imdjson\ (not in the repo): sd.json, homo.html, homo.gif, h.txt (response headers). The fetch tool also cached the control file and map grid under the Claude project tool-results folder (outside the repo).

---

## QUESTION 1: boundaries of the 36 sub-divisions and the 4 homogeneous regions

### 1.1 Sources

| # | Source | Owner / own or third party | URL | Format | CRS | Names/codes | Licence | Date |
|---|---|---|---|---|---|---|---|---|
| A | IMD sub-division boundary used by IMD's rainfall sub-division map page | India Meteorological Department (IMD). Owner's own file, served from IMD's site | https://mausam.imd.gov.in/imd_latest/contents/district_shapefiles/sd_boundary_rainfall.json | GeoJSON FeatureCollection, 36 features (Polygon/MultiPolygon) | No `crs` member in the file. Coordinates are in degrees (lon range 68.17 to 97.42, lat range 5.76 to 37.08, computed from the file). Datum not stated (GeoJSON default is WGS84, but the file does not say so). | Yes, names and a numeric id, see 1.3. Properties: OBJECTID, object_id, name, state_code, region_cod, subdivisio, uorder | None found. No terms were seen on the JSON, the sub-division map page, or the warning page. Treat as unlicensed; ask IMD before redistributing. | HTTP Last-Modified: Wed, 28 Aug 2024 09:55:24 GMT (from the response header, same URL) |
| B | "Shapefiles of districts of India used by IMD" (district layer joined with sub-division properties) | planemad (GitHub user). THIRD-PARTY copy derived from IMD's district-wise warning page JSON files | https://gist.github.com/planemad/d347ad7485344fb0ba4b470721825427 | GeoJSON (`india-district-imd.geojson`), district polygons, not a pure sub-division layer | Gist says reprojected from UTM 44N (EPSG:32644) to WGS84 | Not verified (GeoJSON content was not shown); gist says sub-division properties were joined | Gist lists licence as "Unknown" | Gist author estimates 2015-2018 (675 districts); outdated vs. file A |
| C | Datameet community maps, Census 2011 districts (could be dissolved to sub-divisions by the user) | Datameet community. THIRD-PARTY, not IMD, not a sub-division layer | https://github.com/datameet/maps/tree/master/Districts/Census_2011 (link seen in thread https://groups.google.com/g/datameet/c/KJzvdH1gG40; the repo page itself was NOT opened) | Not verified | Not verified | Not verified | Not verified | Thread dated 18-20 May 2020 |

Notes:
- The datameet thread (https://groups.google.com/g/datameet/c/KJzvdH1gG40, May 2020) reports that file A is "not in the right projection" for one user; that is a user comment, and I found no `crs` member, consistent with geographic degrees. It also reports IMD staff said sub-divisions were being redone for new districts/UTs, not the shapefile. Treat as a 2020 comment.
- No IMD page opened offered a downloadable shapefile or KML. https://mausam.imd.gov.in/imd_latest/contents/statewisedistricts.php, .../index_rainfall_subdiv.php and .../subdivisionwise-warning.php showed menus and, on the warning page, a GIS warnings page (`subDivisionWiseWarningGIS.php`, not opened) only.
- No data.gov.in sub-division boundary dataset was found (search only; UNVERIFIED that none exists). The data.gov.in search results seen were unrelated shapefiles (one-degree rainfall grid points https://data.gov.in/resource/shapefile-one-degree-grid-rainfall-points, watershed boundaries); not opened.
- Vintage: IMD's own paper says there are 36 sub-divisions as of 2020 (https://mausamjournal.imd.gov.in/index.php/MAUSAM/article/view/38). File A has 36 features and matches that count.
- Coordinates and dissolved shapes are only as accurate as IMD's file; the gist states 1-5 km accuracy for its copy (https://gist.github.com/planemad/d347ad7485344fb0ba4b470721825427).

### 1.2 The 4 homogeneous regions: what IMD documents

IMD's own graphic (https://mausam.imd.gov.in/ClimateInformation/imdweb/DAY_WEEK/homo.gif, linked from https://mausam.imd.gov.in/imd_latest/contents/rainfall_over_homogeneous.php, titled "Daily mean rainfall over the four homogeneous regions (2026)") names the four regions as:

1. NORTH WEST INDIA
2. EAST & NORTH EAST INDIA
3. CENTRAL INDIA
4. SOUTH PENINSULAR INDIA

IMPORTANT DISCREPANCY with the task wording: the four-region scheme on IMD's site is NOT "north-west, central north-east, north-east, south peninsula". It has "East and North East India" as one region and "Central India" as a separate one. "Central North East" and "North East" belong to the five-region IITM scheme (Kothawale and Rajeevan, RR-138), which I could not open (see banner). That five-region scheme (UNVERIFIED, snippet only) has different names and a separate West Central region.

IMD's pages opened give NO prose list of which sub-divisions form each region. The only machine-readable composition I found is the `region_cod` attribute of file A (https://mausam.imd.gov.in/imd_latest/contents/district_shapefiles/sd_boundary_rainfall.json), which uses exactly four values: NORTH WEST INDIA, EAST AND NORTH EAST INDIA, CENTRAL INDIA, SOUTH PENINSULA. That is IMD's own data file, but whether it is identical to the regions behind the homo.gif statistics is not stated by IMD; it is an inference that they correspond (same four names).

### 1.3 Exact sub-division list (36), from the `name`/`subdivisio` fields of file A

Source for everything below: https://mausam.imd.gov.in/imd_latest/contents/district_shapefiles/sd_boundary_rainfall.json. Below, each entry gives the name as written, object_id (numeric id in the file, 1-36) and, for the first region, uorder (display order).

NORTH WEST INDIA (9):
- WEST UTTAR PRADESH (object_id 1, uorder 11)
- EAST RAJASTHAN (object_id 5, uorder 18)
- WEST RAJASTHAN (object_id 19, uorder 17)
- HAR. CHD & DELHI (object_id 23, uorder 13)
- HIMACHAL PRADESH (object_id 24, uorder 15)
- JAMMU & KASHMIR AND LADAKH (object_id 34, uorder 16)
- PUNJAB (object_id 11, uorder 14)
- EAST UTTAR PRADESH (object_id 9, uorder 10)
- UTTARAKHAND (object_id 10, uorder 12)

EAST AND NORTH EAST INDIA (7):
ARUNACHAL PRADESH (id 30), ASSAM & MEGHALAYA (id 20), BIHAR (id 15), GANGETIC WEST BENGAL (id 21), N M M T (Nagaland, Manipur, Mizoram, Tripura; id 4), SHWB & SIKKIM (Sub-Himalayan West Bengal and Sikkim; id 25), JHARKHAND (id 22).
(The expansions of N M M T and SHWB in parentheses are standard IMD usage not spelled out in the file; the file only has the abbreviations.)

CENTRAL INDIA (10):
GUJARAT REGION (id 2), SAURASHTRA & KUTCH (id 28), WEST MADHYA PRADESH (id 8), EAST MADHYA PRADESH (id 26), CHHATTISGARH (id 27), ORISSA / subdivisio "ODISHA" (id 13), MARATHWADA (id 16), MADHYA MAHARASHTRA (id 3), KONKAN & GOA (id 36), VIDARBHA (id 6).

SOUTH PENINSULA (10):
A & N ISLAND (id 35), LAKSHADWEEP (id 32), TELANGANA (id 31), COASTAL KARNATAKA (id 33), S. I. KARNATAKA (id 18), N. I. KARNATAKA (id 17), RAYALASEEMA (id 12), KERALA & MAHE (id 7), CO AP and YANAM (Coastal Andhra Pradesh and Yanam; id 29; the `subdivisio` string has a trailing CR/LF in the file), TN PUDU and KKL (Tamil Nadu, Puducherry and Karaikal; id 14).

Totals: 9 + 7 + 10 + 10 = 36, matching the 36-feature count in the file and the 36 stated by IMD (https://mausamjournal.imd.gov.in/index.php/MAUSAM/article/view/38).

Data caveats seen in the file: `name` and `subdivisio` differ for ORISSA/ODISHA and for CO AP and YANAM (trailing CR/LF); `state_code` is the state of the sub-division and is not unique per sub-division. Use `object_id` as the key and strip whitespace from names. A & N Islands and Lakshadweep are assigned to SOUTH PENINSULA in this file, which matters for any region-mean rainfall computed on the land/ocean grid.

Not verified against any IMD prose or table: that this region assignment is what IMD uses for the homo.gif statistics.

---

## QUESTION 2: IMD/NCMRWF merged GPM daily rainfall (Rain_Download.html)

### 2.1 What the page says (https://imdpune.gov.in/cmpg/Realtimedata/gpm/Rain_Download.html)

- Daily merged satellite-gauge rainfall from GPM at 0.25 x 0.25 degree, as a real-time binary file; joint product of IMD and NCMRWF; algorithm per Mitra et al. (2025); acknowledgement to NASA/GSFC and JAXA for GPM estimates.
- Links: a date selector for the binary file, a sample control file `dataddmmyyyy.php`, a map grid file `mapgrid.php` (241 x 281 grid), and the citation link https://link.springer.com/article/10.1007/s12040-025-02550-0.
- The page states no date range, archive start, terms of use or licence, and no contact. (Read via fetch tool, which summarises; verify on the live page before relying on absence of terms.)

### 2.2 Control file (https://imdpune.gov.in/cmpg/Realtimedata/gpm/dataddmmyyyy.php), verbatim

```
DSET p:\ddmmyyyy.grd
TITLE 0.25 degranalyzed normal grids
UNDEF -999.0
XDEF  241  LINEAR  50.0 0.25
YDEF  281  LINEAR  -30.0 0.25
ZDEF   1 linear 1 1 
TDEF 1 LINEAR 1jun2014 1DY
VARS  1
rf 0 99 GRIDDED RAINFALL
ENDVARS
```

Reading it:
- It IS a GrADS-style descriptor (DSET/XDEF/YDEF/TDEF/VARS keywords). The data file is named `ddmmyyyy.grd` (placeholder name; the DSET path `p:\` is a local drive of the publisher and is not a real path for users).
- Grid: 241 points in longitude from 50.0 E, step 0.25, so 50.0 to 110.0 E (computed). 281 points in latitude from -30.0, step 0.25, so -30.0 to 40.0 N (computed). One level, one time per file, one variable `rf` described as "GRIDDED RAINFALL". Points per field: 241 x 281 = 67,721.
- Missing value (UNDEF): -999.0.
- TDEF start `1jun2014` is the sample file's date label in the control file; it is a template value, not an archive start.
- NOT STATED in the control file: units of `rf`, data type, byte order, whether rows run south-to-north or north-to-south (no OPTIONS line such as yrev), the sequential/record layout, or the time of day. GrADS convention, if no OPTIONS line, is 32-bit float, native-order, south-to-north, x fastest; that is the GrADS manual's default and is NOT confirmed by IMD for these files. I did not download a .grd file, so no byte count was checked against 67,721 x 4 = 270,884 bytes. Verify with one real file before writing a reader.
- The line "TITLE 0.25 degranalyzed normal grids" is as published (appears copied from an older template).

### 2.3 Map grid file (https://imdpune.gov.in/cmpg/Realtimedata/gpm/mapgrid.php)

Parsed locally: a text file, 281 lines of 241 space-separated values each (so 281 rows x 241 columns, consistent with the control file). Values are only `0.0` (61,640 cells) and `1.0` (6,081 cells). It is a 0/1 mask; the page does not say what 1 means (inference: Indian land/domain cells, UNVERIFIED). The 1-cells span row indices 10-133 and column indices 69-191 (0-based, line order as in the file). If columns map from 50.0 E at 0.25, columns 69-191 are 67.25 E to 97.75 E. Row direction is not stated; if the first line is the northern edge (40 N), rows 10-133 are 37.5 N to 9.25 N, which looks like India; if the first line were the southern edge, the 1-cells would lie at -27.5 to 3.25 N, which is not India. So the mask file is probably north-first (inference, not a statement by IMD), and that says nothing about the binary file's row order.

### 2.4 Relation to the RF25 grid (129 x 135, 6.5-38.5 N, 66.5-100 E, 0.25 degree)

Arithmetic only (no IMD statement):
- RF25: longitudes 66.5 to 100.0 at 0.25 = 135 points; latitudes 6.5 to 38.5 at 0.25 = 129 points. This matches 129 x 135.
- Merged grid: same 0.25 spacing and same lattice (66.5 and 6.5 are multiples of 0.25 offset from 50.0 and -30.0). RF25 is a sub-window of the merged grid.
- In the merged grid's 0-based indices, RF25 would be longitude indices 66 to 200 (66.5 = 50 + 66 x 0.25; 100.0 = 50 + 200 x 0.25) and latitude indices 146 to 274 counted from -30 northward (6.5 = -30 + 146 x 0.25; 38.5 = -30 + 274 x 0.25). If the file stores rows north-first, flip the latitude index (row = 280 - j).
- Both ends fall on grid nodes exactly, so cropping needs no interpolation. Whether the two datasets use the same cell convention (node versus cell centre) is NOT stated by IMD; check against a real RF25 file.
- Merged domain is larger: 50-110 E, -30-40 N, i.e. it includes ocean and neighbouring land; the 1-mask above is a subset.

### 2.5 Time of day, archive start, licence, citation

From the Springer landing page for Mitra, Prakash and Pai (2025), J Earth Syst Sci 134, 89, https://doi.org/10.1007/s12040-025-02550-0 (https://link.springer.com/article/10.1007/s12040-025-02550-0; landing page text only, not the full paper; extracted via fetch tool):
- Time of day: daily totals end at 0300 UTC, i.e. 0830 IST, from half-hourly IMERG data ending at that time (the 24-hour accumulation ends at 0830 IST; the fetch output quoted "daily rain gauge data are available at 0300 UTC"). The start of the 24-hour window (previous day 0830 IST) is implied, not confirmed from the full text.
- Archive start: 1 October 2015, "when the product became available on a near real-time basis from the IMD Pune website" (landing page as returned). The Rain_Download page itself gives no start date.
- Data availability: no formal statement seen; text says the dataset is freely available from the IMD Pune website and that NCMRWF also lists it.
- Licence: none stated on the Rain_Download page or on the landing page (only Springer Nature's generic rights and permissions notice).
- Citation requested: the Rain_Download page links to the paper without a format. Reference: Mitra, A.K., Prakash, S. and Pai, D.S. (2025), J Earth Syst Sci 134, 89. Also acknowledges NASA/GSFC and JAXA for GPM estimates (Rain_Download page).
- Automated-download terms: none found on the page or landing page. Absence of terms is not permission; contact IMD Pune (CMPG) before bulk scraping.
- File format description in the paper: not stated in what I could read.
- I did not read the paper's full text, so the algorithm details (gauge density, IMERG version, product variable definition, units) are not covered here.

## Summary of status

- Q1: PARTLY FOUND. Found IMD's own 36-feature sub-division GeoJSON with names, ids and a four-way region attribute; no CRS stated; no licence found; no KML/shapefile from IMD; IITM RR-138 not openable. The task's "central north-east / north-east" four-region wording does not match IMD's published four regions.
- Q2: PARTLY FOUND. Control file and mask opened and fully reported; byte order, data type, units, row order and the real binary layout are not stated; start date and 0830 IST come from the paper's landing page only.
