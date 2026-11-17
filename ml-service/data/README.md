# ml-service/data

Data for the rainfall QC work. Only this file and the empty folder markers are in git; everything else here is ignored. Setup steps are in [`../SETUP.md`](../SETUP.md).

```
ml-service/data/
├── rf25/                        RF25 gridded daily rainfall for India (main study)
│   └── RF25_ind<year>_rfp25.nc    one file per year, 1901-2023 (123 files, about 5.9 GB)
├── midas-open/                  UK Met Office MIDAS Open (separate real-label study)
│   └── uk-daily-rain-obs/
│       └── dataset-version-202607/
│           ├── 00README_catalogue_and_licence.txt
│           ├── download_summary.json
│           └── <county>/<station>/
│               ├── ..._capability.csv
│               ├── qc-version-0/    original records that QC later changed
│               └── qc-version-1/    current best records
├── splits/                      client map and split manifest (written by the build; empty for now)
└── benchmarks/                  frozen validation and test fault benchmarks (written by the build; empty for now)
```

## Where each folder comes from

| folder | how it is filled | used by |
|---|---|---|
| `rf25/` | Copy the 123 `RF25_ind<year>_rfp25.nc` files in by hand. On Kaggle, attach them as a dataset instead; nothing is copied. | `python -m training ...` today; the QC build later |
| `era5/` | `python scripts/download_era5.py --years A B` (needs a CDS key, see `../.env.example`; about 78 MB a month) | ERA5 temperature, humidity, pressure extension (hourly GRIB; daily files go to `<work>/era5_daily`) |
| `midas-open/` | `python scripts/download_midas.py --county <names>` (needs a CEDA token, see `../.env.example`) | the UK real-label study |
| `splits/`, `benchmarks/` | Written by the QC build (spec gates 1 and 2). Not built yet. | the QC build |

## Using a different location

Set `DATAMEND_DATA_DIR` to a folder with this same layout (for example on a larger disk). The training code looks for RF25 in `$DATAMEND_DATA_DIR/rf25`, and the MIDAS download goes to `$DATAMEND_DATA_DIR/midas-open`. Pointing `DATAMEND_DATA_DIR` straight at a folder of RF25 files also still works for training.

Run outputs do not go here. They go to `ml-service/artifacts/`, or under `$DATAMEND_OUT_DIR` if it is set.

## Data facts to check after copying

- RF25: variable `RAINFALL`, dimensions `(TIME, LATITUDE, LONGITUDE)`, mm, fill value -999, grid 129 x 135 at 0.25 degree.
- RF25 has no quality flags. MIDAS files are BADC-CSV: a metadata header, a line `data`, the table, then `end data`.
